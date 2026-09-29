"""Governed persistent terminal capability for Astron Single R1.

The model can propose a bounded terminal operation, but it cannot reach a
shell except through this module's schema validation, permission evaluation,
durable action runtime, and redacted journal.  This is a macOS/Unix backend;
the public service boundary intentionally leaves room for a future PowerShell
backend without pretending that one exists today.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePath
import re
import secrets
import signal
import subprocess
import termios
import threading
import time
from typing import Any, Mapping

from ..permissions import PermissionEngine, PrincipalContext, ScopeGuard
from ..protocols import ActionRequest, ActionResult, ActionStatus
from ..runtime import DurableActionRuntime
from ..state import SQLiteDurableStateStore
from .bounded import ToolExecution, ToolInputError


MAX_OUTPUT_CHARS = 4_096
MAX_READ_CHARS = 16_384
MAX_COMMAND_BYTES = 32_768
MAX_ENVIRONMENT_ITEMS = 64
MAX_ENVIRONMENT_VALUE_BYTES = 8_192
_SECRET_KEY_MARKERS = ("SECRET", "TOKEN", "PASSWORD", "API_KEY", "CREDENTIAL")
_TERMINAL_ID = re.compile(r"term_[a-z0-9]{20}")
_DANGEROUS_COMMAND = re.compile(
    r"(?:^|[;&|\s])(?:sudo|doas|launchctl|shutdown|reboot)(?:\s|$)|\brm\s+-[^\n;]*[rR][^\n;]*[fF]",
    re.IGNORECASE,
)
_NETWORK_COMMAND = re.compile(r"(?:^|[;&|\s])(?:curl|wget|nc|ncat|ssh|scp|ftp)(?:\s|$)", re.IGNORECASE)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def terminal_tool_schemas() -> list[dict[str, object]]:
    """Return the model-visible bounded terminal function schemas."""

    return [
        {"type": "function", "function": {"name": "terminal_open", "description": "Open a persistent terminal session rooted in the trusted workspace.", "parameters": {"type": "object", "properties": {"cwd": {"type": "string"}, "env": {"type": "object", "additionalProperties": {"type": "string"}}}}}},
        {"type": "function", "function": {"name": "terminal_send", "description": "Send one command to an owned persistent terminal. Output is bounded and secrets are redacted.", "parameters": {"type": "object", "required": ["terminal_id", "input"], "properties": {"terminal_id": {"type": "string"}, "input": {"type": "string"}, "run_in_background": {"type": "boolean"}, "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 60}}}}},
        {"type": "function", "function": {"name": "terminal_read", "description": "Read newly produced, bounded output from an owned terminal.", "parameters": {"type": "object", "required": ["terminal_id"], "properties": {"terminal_id": {"type": "string"}, "max_chars": {"type": "integer", "minimum": 1, "maximum": 16384}}}}},
        {"type": "function", "function": {"name": "terminal_signal", "description": "Safely interrupt an owned foreground terminal command with SIGINT.", "parameters": {"type": "object", "required": ["terminal_id", "signal"], "properties": {"terminal_id": {"type": "string"}, "signal": {"type": "string", "enum": ["SIGINT"]}}}}},
        {"type": "function", "function": {"name": "terminal_close", "description": "Close an owned terminal and terminate its process group.", "parameters": {"type": "object", "required": ["terminal_id"], "properties": {"terminal_id": {"type": "string"}}}}},
        {"type": "function", "function": {"name": "terminal_list", "description": "List only the caller's terminal sessions; environment values are never returned.", "parameters": {"type": "object", "properties": {}}}},
    ]


class TerminalPolicy:
    """Small explicit policy hook set for the R1 Unix terminal backend.

    It is intentionally not described as an OS sandbox.  It validates the
    workspace entrypoint, blocks a few unambiguously dangerous/admin commands,
    and denies direct network clients by default.  Container isolation remains
    the future SWE-bench boundary.
    """

    def __init__(self, workspace_root: Path, *, allow_network_commands: bool = False) -> None:
        self.workspace_root = workspace_root
        self.allow_network_commands = allow_network_commands

    def normalize_cwd(self, value: object | None) -> Path:
        if value is None:
            return self.workspace_root
        if not isinstance(value, str) or not value or "\x00" in value:
            raise ToolInputError("terminal cwd must be a non-empty path")
        raw = Path(value)
        candidate = raw if raw.is_absolute() else self.workspace_root / raw
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(self.workspace_root)
        except (OSError, ValueError) as exc:
            raise ToolInputError("terminal cwd escapes the trusted workspace") from exc
        if not resolved.is_dir() or resolved.is_symlink():
            raise ToolInputError("terminal cwd must be an existing non-symlink directory")
        return resolved

    def validate_command(self, value: object) -> str:
        if not isinstance(value, str) or not value or "\x00" in value:
            raise ToolInputError("terminal input must be non-empty text")
        if len(value.encode("utf-8")) > MAX_COMMAND_BYTES:
            raise ToolInputError("terminal input exceeds the deterministic byte bound")
        if _DANGEROUS_COMMAND.search(value):
            raise ToolInputError("terminal policy blocks administrator or destructive command syntax")
        if not self.allow_network_commands and _NETWORK_COMMAND.search(value):
            raise ToolInputError("terminal policy blocks network-capable command syntax")
        return value


class _SecretRedactor:
    def __init__(self, environment: Mapping[str, str]) -> None:
        self._values = sorted(
            {
                value for key, value in environment.items()
                if isinstance(value, str)
                and value
                and any(marker in key.upper() for marker in _SECRET_KEY_MARKERS)
            },
            key=len,
            reverse=True,
        )

    def redact(self, text: str) -> str:
        for value in self._values:
            text = text.replace(value, "***REDACTED***")
        return text


@dataclass
class _TerminalSession:
    terminal_id: str
    owner: str
    cwd: Path
    shell: str
    environment: dict[str, str]
    process: subprocess.Popen[bytes]
    master_fd: int
    log_path: Path
    redactor: _SecretRedactor
    created_at: str = field(default_factory=_utcnow)
    last_activity: str = field(default_factory=_utcnow)
    status: str = "running"
    raw_output: bytearray = field(default_factory=bytearray)
    lock: threading.RLock = field(default_factory=threading.RLock)
    output_ready: threading.Condition = field(init=False)

    def __post_init__(self) -> None:
        self.output_ready = threading.Condition(self.lock)


class TerminalService:
    """Owns live PTY sessions and enforces caller ownership at every access."""

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        shell: str | None = None,
        allow_network_commands: bool = False,
        log_root: str | Path | None = None,
    ) -> None:
        root = Path(workspace_root)
        if not root.exists() or not root.is_dir() or root.is_symlink():
            raise ToolInputError("terminal workspace root must be an existing non-symlink directory")
        self._root = root.resolve(strict=True)
        self.policy = TerminalPolicy(self._root, allow_network_commands=allow_network_commands)
        selected_shell = shell or ("/bin/zsh" if os.name == "posix" and Path("/bin/zsh").is_file() else "/bin/sh")
        if os.name != "posix" or not Path(selected_shell).is_file():
            raise ToolInputError("Terminal R1 has no backend for this platform")
        self._shell = selected_shell
        self._sessions: dict[str, _TerminalSession] = {}
        self._lock = threading.RLock()
        # Logs deliberately sit beside, not inside, the agent workspace.  A
        # terminal service must not perturb the repository tree merely by
        # becoming available (especially important to deterministic verifiers).
        # ``log_root`` may be pinned explicitly (the SWE-bench adapter pins it
        # outside the task repository so the prediction patch stays clean), but
        # it is always refused if it would land inside the workspace root.
        self._logs = Path(log_root) if log_root is not None else self._root.parent / ".astron-terminal-logs"
        if self._logs.is_symlink():
            raise ToolInputError("terminal log root must not be a symlink")
        # Resolve without creating anything: a rejected log root must leave no
        # trace at all, not even an empty directory inside the workspace.
        resolved_logs = Path(os.path.realpath(self._logs))
        if resolved_logs == self._root or self._root in resolved_logs.parents:
            raise ToolInputError("terminal log root must live outside the agent workspace")
        resolved_logs.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._logs = resolved_logs.resolve(strict=True)

    @property
    def workspace_root(self) -> Path:
        return self._root

    @property
    def log_root(self) -> Path:
        return self._logs

    @staticmethod
    def _normalize_env(value: object | None) -> dict[str, str]:
        if value is None:
            return {}
        if not isinstance(value, Mapping) or len(value) > MAX_ENVIRONMENT_ITEMS:
            raise ToolInputError("terminal environment is invalid or exceeds its item bound")
        normalized: dict[str, str] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", key):
                raise ToolInputError("terminal environment variable name is invalid")
            if not isinstance(item, str) or "\x00" in item or len(item.encode("utf-8")) > MAX_ENVIRONMENT_VALUE_BYTES:
                raise ToolInputError("terminal environment value is invalid")
            normalized[key] = item
        return normalized

    def open(self, owner: str, *, cwd: object | None = None, env: object | None = None, terminal_id: str | None = None) -> dict[str, object]:
        if not isinstance(owner, str) or not owner:
            raise ToolInputError("terminal owner is invalid")
        selected_cwd = self.policy.normalize_cwd(cwd)
        overrides = self._normalize_env(env)
        if terminal_id is None:
            terminal_id = "term_" + secrets.token_hex(10)
        if not isinstance(terminal_id, str) or not _TERMINAL_ID.fullmatch(terminal_id):
            raise ToolInputError("terminal id is invalid")
        with self._lock:
            if terminal_id in self._sessions:
                raise ToolInputError("terminal id already exists")
            environment = {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "HOME": str(self._root),
                "TERM": "dumb",
                "PS1": "",
                "PROMPT": "",
                "PYTHONUNBUFFERED": "1",
            }
            environment.update(overrides)
            master_fd, slave_fd = os.openpty()
            attributes = termios.tcgetattr(slave_fd)
            attributes[3] &= ~termios.ECHO
            termios.tcsetattr(slave_fd, termios.TCSANOW, attributes)
            try:
                # ``-c`` keeps zsh non-prompting even though it is attached to
                # a PTY.  The small trusted dispatcher evaluates one
                # delimiter-framed script at a time in this *same* shell, so
                # cwd, exports, aliases, and jobs remain persistent without
                # terminal echo reflecting model input (which could be secret).
                dispatcher = (
                    "while IFS= read -r __astron_line; do "
                    "__astron_script=''; "
                    "while [[ $__astron_line != __ASTRON_EOF_* ]]; do "
                    "__astron_script+=\"$__astron_line\"$'\\n'; "
                    "IFS= read -r __astron_line || exit; "
                    "done; eval \"$__astron_script\"; done"
                )
                process = subprocess.Popen(
                    [self._shell, "-dfc", dispatcher],
                    cwd=str(selected_cwd),
                    env=environment,
                    stdin=slave_fd,
                    stdout=slave_fd,
                    stderr=slave_fd,
                    start_new_session=True,
                    close_fds=True,
                )
            finally:
                os.close(slave_fd)
            session = _TerminalSession(
                terminal_id=terminal_id,
                owner=owner,
                cwd=selected_cwd,
                shell=self._shell,
                environment=environment,
                process=process,
                master_fd=master_fd,
                log_path=self._logs / f"{terminal_id}.log",
                redactor=_SecretRedactor(environment),
            )
            self._sessions[terminal_id] = session
            threading.Thread(target=self._reader, args=(session,), daemon=True, name=f"astron-{terminal_id}").start()
        return {"terminal_id": terminal_id, "cwd": str(selected_cwd), "status": "running", "shell": self._shell}

    def _reader(self, session: _TerminalSession) -> None:
        while True:
            try:
                data = os.read(session.master_fd, 16_384)
            except OSError:
                data = b""
            with session.output_ready:
                if data:
                    session.raw_output.extend(data)
                    session.last_activity = _utcnow()
                    session.output_ready.notify_all()
                else:
                    if session.process.poll() is not None:
                        session.status = "exited" if session.status == "running" else session.status
                    session.output_ready.notify_all()
                    return

    def _session_for(self, owner: str, terminal_id: object) -> _TerminalSession:
        if not isinstance(terminal_id, str) or not _TERMINAL_ID.fullmatch(terminal_id):
            raise ToolInputError("terminal id is invalid")
        with self._lock:
            session = self._sessions.get(terminal_id)
        if session is None:
            raise ToolInputError("terminal id is not found")
        if session.owner != owner:
            raise ToolInputError("terminal owner isolation denied")
        return session

    @staticmethod
    def _bound_output(text: str, max_chars: int) -> dict[str, object]:
        if len(text) <= max_chars:
            return {"output": text, "truncated": False}
        head = max_chars // 2
        tail = max_chars - head
        return {
            "output": text[:head] + "\n...[OUTPUT_TRUNCATED; full redacted log retained]...\n" + text[-tail:],
            "truncated": True,
            "output_chars": len(text),
        }

    def _consume(self, session: _TerminalSession, end: int | None = None) -> str:
        raw = bytes(session.raw_output if end is None else session.raw_output[:end])
        if end is None:
            session.raw_output.clear()
        else:
            del session.raw_output[:end]
        text = session.redactor.redact(raw.decode("utf-8", "replace"))
        if text:
            with session.log_path.open("a", encoding="utf-8") as log:
                log.write(text)
        return text

    @staticmethod
    def _marker() -> tuple[bytes, str]:
        nonce = secrets.token_hex(16)
        return f"\x1eASTRON_DONE_{nonce}:".encode("ascii"), nonce

    @staticmethod
    def _write(session: _TerminalSession, payload: bytes) -> None:
        try:
            os.write(session.master_fd, payload)
        except OSError as exc:
            raise ToolInputError("terminal process is not writable") from exc

    def _interrupt_foreground(self, session: _TerminalSession) -> None:
        # Do not consult ``tcgetpgrp(master_fd)`` here.  Depending on how a
        # host creates its controlling terminal it can identify the caller's
        # process group rather than this child session.  ``start_new_session``
        # makes the shell PID's group the capability-owned group instead.
        try:
            os.killpg(os.getpgid(session.process.pid), signal.SIGINT)
        except (OSError, ProcessLookupError):
            return

    def send(self, owner: str, terminal_id: object, command: object, *, run_in_background: object = False, timeout_seconds: object = 15) -> dict[str, object]:
        session = self._session_for(owner, terminal_id)
        command = self.policy.validate_command(command)
        if not isinstance(run_in_background, bool):
            raise ToolInputError("run_in_background must be a boolean")
        if not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 60:
            raise ToolInputError("timeout_seconds must be between 1 and 60")
        with session.output_ready:
            if session.process.poll() is not None or session.status != "running":
                session.status = "exited"
                return {"terminal_id": session.terminal_id, "running": False, "exit_code": session.process.returncode, "output": "", "truncated": False}
            # A read left no command delimiter, so return its old output before
            # beginning this ordered command response.
            if session.raw_output:
                self._consume(session)
            marker, nonce = self._marker()
            if run_in_background:
                payload = (
                    "{\n" + command + "\n} &\n"
                    "__astron_bg_pid=$!\n"
                    f"printf '\\036ASTRON_DONE_{nonce}:%s:%s\\037\\n' \"$?\" \"$__astron_bg_pid\"\n"
                )
            else:
                payload = (
                    command + "\n"
                    "__astron_status=$?\n"
                    f"printf '\\036ASTRON_DONE_{nonce}:%s\\037\\n' \"$__astron_status\"\n"
                )
            self._write(session, (payload + f"__ASTRON_EOF_{nonce}\n").encode("utf-8"))
            deadline = time.monotonic() + timeout_seconds
            timed_out = False
            marker_end: int | None = None
            while marker_end is None:
                position = bytes(session.raw_output).find(marker)
                if position >= 0:
                    terminator = bytes(session.raw_output).find(b"\x1f", position + len(marker))
                    if terminator >= 0:
                        marker_end = terminator + 1
                        fragment = bytes(session.raw_output[position + len(marker):terminator]).decode("ascii", "replace")
                        break
                remaining = deadline - time.monotonic()
                if remaining <= 0 and not timed_out:
                    timed_out = True
                    self._interrupt_foreground(session)
                    deadline = time.monotonic() + 2
                    continue
                if remaining <= 0:
                    break
                session.output_ready.wait(timeout=min(remaining, 0.2))
                if session.process.poll() is not None and not session.raw_output:
                    break
            if marker_end is None:
                output = self._consume(session)
                session.status = "exited" if session.process.poll() is not None else "running"
                bounded = self._bound_output(output, MAX_OUTPUT_CHARS)
                return {"terminal_id": session.terminal_id, **bounded, "running": session.status == "running", "exit_code": session.process.returncode, "timed_out": timed_out}
            raw_output = bytes(session.raw_output[:position])
            del session.raw_output[:marker_end]
            output = session.redactor.redact(raw_output.decode("utf-8", "replace"))
            if output:
                with session.log_path.open("a", encoding="utf-8") as log:
                    log.write(output)
            status_parts = fragment.split(":")
            exit_code = int(status_parts[0]) if status_parts and status_parts[0].lstrip("-").isdigit() else None
            bounded = self._bound_output(output, MAX_OUTPUT_CHARS)
            response: dict[str, object] = {
                "terminal_id": session.terminal_id,
                **bounded,
                "running": session.process.poll() is None,
                "exit_code": exit_code,
                "timed_out": timed_out,
            }
            if run_in_background and len(status_parts) == 2 and status_parts[1].isdigit():
                response["process_id"] = int(status_parts[1])
                response["background"] = True
            session.last_activity = _utcnow()
            return response

    def read(self, owner: str, terminal_id: object, *, max_chars: object = MAX_OUTPUT_CHARS) -> dict[str, object]:
        session = self._session_for(owner, terminal_id)
        if not isinstance(max_chars, int) or not 1 <= max_chars <= MAX_READ_CHARS:
            raise ToolInputError("max_chars is outside its bounded range")
        with session.output_ready:
            output = self._consume(session)
            session.status = "exited" if session.process.poll() is not None else session.status
            return {
                "terminal_id": session.terminal_id,
                **self._bound_output(output, max_chars),
                "running": session.status == "running",
                "exit_code": session.process.returncode,
            }

    def signal(self, owner: str, terminal_id: object, signal_name: object) -> dict[str, object]:
        session = self._session_for(owner, terminal_id)
        if signal_name != "SIGINT":
            raise ToolInputError("Terminal R1 only permits SIGINT")
        with session.output_ready:
            if session.process.poll() is None:
                self._interrupt_foreground(session)
            session.last_activity = _utcnow()
            return {"terminal_id": session.terminal_id, "signal": "SIGINT", "running": session.process.poll() is None}

    def close(self, owner: str, terminal_id: object) -> dict[str, object]:
        session = self._session_for(owner, terminal_id)
        with session.output_ready:
            self._close_session(session)
            return {"terminal_id": session.terminal_id, "status": session.status, "exit_code": session.process.returncode}

    def _close_session(self, session: _TerminalSession) -> None:
        if session.status == "closed":
            return
        if session.process.poll() is None:
            try:
                # A shell-level ``exit`` waits for active background jobs.  A
                # session close must instead terminate the owned process group
                # first so a long-running child cannot keep cleanup pending.
                os.killpg(os.getpgid(session.process.pid), signal.SIGTERM)
            except (OSError, ProcessLookupError):
                pass
            try:
                session.process.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(session.process.pid), signal.SIGKILL)
                except (OSError, ProcessLookupError):
                    pass
                session.process.wait(timeout=1.5)
        try:
            os.close(session.master_fd)
        except OSError:
            pass
        session.status = "closed"
        session.last_activity = _utcnow()

    def list(self, owner: str) -> dict[str, object]:
        if not isinstance(owner, str) or not owner:
            raise ToolInputError("terminal owner is invalid")
        with self._lock:
            sessions = [session for session in self._sessions.values() if session.owner == owner]
        result = []
        for session in sorted(sessions, key=lambda item: item.created_at):
            with session.lock:
                if session.status == "running" and session.process.poll() is not None:
                    session.status = "exited"
                result.append({
                    "terminal_id": session.terminal_id,
                    "cwd": str(session.cwd),
                    "shell": session.shell,
                    "created_at": session.created_at,
                    "last_activity": session.last_activity,
                    "status": session.status,
                    "process_id": session.process.pid,
                })
        return {"sessions": result, "count": len(result)}

    def shutdown(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
        for session in sessions:
            with session.lock:
                self._close_session(session)


class _TerminalActionJournal:
    """Redacted sidecar correlation journal; SQLite remains lifecycle authority."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def append(self, payload: Mapping[str, object]) -> None:
        record = dict(payload)
        record["recorded_at"] = _utcnow()
        encoded = json.dumps(record, sort_keys=True, ensure_ascii=True) + "\n"
        with self._lock:
            descriptor = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
            try:
                os.write(descriptor, encoded.encode("utf-8"))
                os.fsync(descriptor)
            finally:
                os.close(descriptor)


class TerminalToolRuntime:
    """Terminal operations routed through Astron's durable governance path."""

    WORKSPACE_SCOPE = "terminal_workspace"
    PROCESS_SCOPE = "terminal_session"
    _CAPABILITIES = {
        "terminal_open": "TERMINAL_OPEN",
        "terminal_send": "TERMINAL_SEND",
        "terminal_read": "TERMINAL_READ",
        "terminal_signal": "TERMINAL_SIGNAL",
        "terminal_close": "TERMINAL_CLOSE",
        "terminal_list": "TERMINAL_LIST",
    }

    def __init__(
        self,
        workspace_root: str | Path,
        state_store: SQLiteDurableStateStore,
        *,
        log_root: str | Path | None = None,
        service: TerminalService | None = None,
    ) -> None:
        if not isinstance(state_store, SQLiteDurableStateStore):
            raise ToolInputError("governed terminal requires a durable SQLite state store")
        # ``service`` may be shared by several owners (one governed runtime per
        # agent identity) so that cross-agent access attempts hit the ownership
        # check in ``TerminalService`` instead of merely missing the session.
        expected_workspace = Path(workspace_root).resolve(strict=True)
        if service is not None and service.workspace_root != expected_workspace:
            raise ToolInputError("shared terminal service workspace does not match the governed runtime")
        self._service = service if service is not None else TerminalService(workspace_root, log_root=log_root)
        self._state_store = state_store
        self._engine = PermissionEngine(
            capabilities=set(self._CAPABILITIES.values()),
            principal_id="principal:astron/terminal-default",
            scope_guard=ScopeGuard(
                fs_read_classes={self.WORKSPACE_SCOPE},
                fs_write_classes={self.WORKSPACE_SCOPE},
                process_classes={self.PROCESS_SCOPE},
            ),
            durable_state_store=state_store,
        )
        self._runtime = DurableActionRuntime(self._engine, state_store)
        self._journal = _TerminalActionJournal(self._service.log_root / "action-journal.jsonl")

    @property
    def state_store(self) -> SQLiteDurableStateStore:
        return self._state_store

    @property
    def service(self) -> TerminalService:
        return self._service

    def _normalize(self, operation: object, parameters: object, *, terminal_id: str | None = None) -> dict[str, object]:
        if not isinstance(operation, str) or operation not in self._CAPABILITIES:
            raise ToolInputError("terminal tool operation is not allowlisted")
        if not isinstance(parameters, Mapping):
            raise ToolInputError("terminal parameters must be an object")
        raw = dict(parameters)
        allowed = {
            "terminal_open": {"cwd", "env"},
            "terminal_send": {"terminal_id", "input", "run_in_background", "timeout_seconds"},
            "terminal_read": {"terminal_id", "max_chars"},
            "terminal_signal": {"terminal_id", "signal"},
            "terminal_close": {"terminal_id"},
            "terminal_list": set(),
        }[operation]
        if set(raw) - allowed:
            raise ToolInputError("terminal parameters include an unsupported field")
        if operation == "terminal_open":
            cwd = self._service.policy.normalize_cwd(raw.get("cwd"))
            env = self._service._normalize_env(raw.get("env"))
            return {"cwd": str(cwd), "env": env, "terminal_id": terminal_id or "term_" + secrets.token_hex(10)}
        if operation == "terminal_send":
            return {
                "terminal_id": raw.get("terminal_id"),
                "input": self._service.policy.validate_command(raw.get("input")),
                "run_in_background": raw.get("run_in_background", False),
                "timeout_seconds": raw.get("timeout_seconds", 15),
            }
        if operation == "terminal_read":
            return {"terminal_id": raw.get("terminal_id"), "max_chars": raw.get("max_chars", MAX_OUTPUT_CHARS)}
        if operation == "terminal_signal":
            return {"terminal_id": raw.get("terminal_id"), "signal": raw.get("signal")}
        if operation == "terminal_close":
            return {"terminal_id": raw.get("terminal_id")}
        return {}

    @staticmethod
    def _request_fingerprint(request: ActionRequest) -> str:
        payload = json.dumps({"operation": request.operation, "parameters": request.parameters}, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def execute(self, task_id: str, logical_action_id: str, owner: str, operation: str, parameters: Mapping[str, object]) -> ToolExecution:
        if not isinstance(task_id, str) or not task_id or not isinstance(logical_action_id, str) or not logical_action_id or not isinstance(owner, str) or not owner:
            raise ToolInputError("terminal task, logical action id, or owner is invalid")
        # The logical identity must determine every side-effecting parameter,
        # including the new terminal's id.  A runtime that re-submits the same
        # logical call must produce a byte-identical request so the durable
        # layer recognises it as a replay instead of as a conflicting action,
        # and so the terminal is never opened twice.
        digest = hashlib.sha256(f"{task_id}:{logical_action_id}:{owner}".encode("utf-8")).hexdigest()
        normalized = self._normalize(operation, parameters, terminal_id=f"term_{digest[:20]}")
        request = ActionRequest(
            action_id=f"term-{digest[:48]}",
            operation=operation,
            parameters=normalized,
            required_permissions=[self._CAPABILITIES[operation]],
            filesystem_scope={"mode": "read_write", "paths_class": [self.WORKSPACE_SCOPE]},
            network_scope={"mode": "none", "endpoints_class": []},
            process_scope={"allowed_executables_class": [self.PROCESS_SCOPE]},
            timeout=60,
            idempotency_key=f"term-{digest[:48]}",
            rollback_supported=False,
            approval_required=False,
        )
        fingerprint = self._request_fingerprint(request)

        def executor(_request: ActionRequest) -> ActionResult:
            terminal_id = str(normalized.get("terminal_id", ""))
            self._journal.append({
                "logical_action_id": logical_action_id,
                "tool_name": operation,
                "agent_owner": owner,
                "terminal_id": terminal_id,
                "request_fingerprint": fingerprint,
                "decision": "allow",
                "start": _utcnow(),
                "result": None,
                "error": None,
            })
            try:
                outcome = self._dispatch(owner, operation, normalized)
            except ToolInputError as exc:
                outcome = {"code": "TERMINAL_POLICY_OR_INPUT_DENIED", "detail": str(exc)}
            status = ActionStatus.SUCCESS
            # A close intentionally terminates the shell's owned process group,
            # so its shell return code can be signal-derived.  That is a
            # successful cleanup outcome, not a failed terminal command.
            if operation == "terminal_send" and outcome.get("exit_code") not in (None, 0):
                status = ActionStatus.FAILURE
            if outcome.get("code") is not None:
                status = ActionStatus.FAILURE
            self._journal.append({
                "logical_action_id": logical_action_id,
                "tool_name": operation,
                "agent_owner": owner,
                "terminal_id": terminal_id,
                "request_fingerprint": fingerprint,
                "decision": "allow",
                "start": None,
                "result": status.value,
                "error": outcome.get("code"),
            })
            return ActionResult(action_id=request.action_id, status=status, outcome=outcome, trace_id="terminal-r1")

        execution = self._runtime.execute(task_id, request, executor, principal_context=PrincipalContext(owner))
        return ToolExecution(
            action=request,
            result=execution.action_result,
            executor_invoked=execution.executor_invoked,
            needs_reconciliation=execution.needs_reconciliation,
            authorization_decision=execution.authorization.decision.value,
            state_error=execution.state_error,
        )

    def _dispatch(self, owner: str, operation: str, parameters: Mapping[str, object]) -> dict[str, object]:
        if operation == "terminal_open":
            return self._service.open(owner, cwd=parameters["cwd"], env=parameters["env"], terminal_id=str(parameters["terminal_id"]))
        if operation == "terminal_send":
            return self._service.send(owner, parameters["terminal_id"], parameters["input"], run_in_background=parameters["run_in_background"], timeout_seconds=parameters["timeout_seconds"])
        if operation == "terminal_read":
            return self._service.read(owner, parameters["terminal_id"], max_chars=parameters["max_chars"])
        if operation == "terminal_signal":
            return self._service.signal(owner, parameters["terminal_id"], parameters["signal"])
        if operation == "terminal_close":
            return self._service.close(owner, parameters["terminal_id"])
        if operation == "terminal_list":
            return self._service.list(owner)
        raise ToolInputError("terminal tool operation is not allowlisted")

    def shutdown(self) -> None:
        self._service.shutdown()


class TerminalEnabledToolRuntime:
    """Registry adapter retaining native file tools and adding the R1 terminal family."""

    terminal_capability_enabled = True

    def __init__(self, bounded_runtime: Any, terminal_runtime: TerminalToolRuntime, *, agent_owner: str) -> None:
        self._bounded = bounded_runtime
        self._terminal = terminal_runtime
        self._owner = agent_owner

    @property
    def state_store(self) -> SQLiteDurableStateStore:
        return self._bounded.state_store

    def execute(self, task_id: str, step: int, operation: str, parameters: Mapping[str, object]) -> ToolExecution:
        if operation in TerminalToolRuntime._CAPABILITIES:
            return self._terminal.execute(task_id, f"agent-step-{step}", self._owner, operation, parameters)
        return self._bounded.execute(task_id, step, operation, parameters)

    def shutdown(self) -> None:
        self._terminal.shutdown()
