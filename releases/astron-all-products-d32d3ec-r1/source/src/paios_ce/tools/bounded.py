"""Trusted local repository tools with an explicit finite surface.

The model supplies only a named proposal and JSON-like arguments.  This module
owns all path checks, `ActionRequest` construction, permission admission, and
the durable runtime handoff.  It deliberately exposes no generic command or
subprocess interface.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
from typing import Any, Callable, Dict, Mapping

from ..maintenance_artifact import MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT
from ..permissions import PermissionEngine, PrincipalContext, ScopeGuard
from ..protocols import ActionRequest, ActionResult, ActionStatus
from ..runtime import DurableActionRuntime
from ..state import SQLiteDurableStateStore


class ToolInputError(ValueError):
    """A proposal violates the finite Phase 3 tool contract."""


@dataclass(frozen=True)
class ToolExecution:
    action: ActionRequest
    result: ActionResult | None
    executor_invoked: bool
    needs_reconciliation: bool
    authorization_decision: str
    state_error: str | None = None


class BoundedToolRuntime:
    """Execute one allowlisted tool in one canonical workspace root.

    The class is intentionally instantiated by trusted application code with a
    copied fixture root and a durable store.  Paths supplied by the model are
    never used as filesystem roots or process arguments.
    """

    WORKSPACE_SCOPE = "phase3_workspace"
    ARTIFACT_SCOPE = "phase3_artifacts"
    PRINCIPAL_ID = "principal:astron/phase3-native-agent"
    MAX_READ_BYTES = 65_536
    MAX_ARTIFACT_BYTES = MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT.max_artifact_bytes
    MAX_LISTED_FILES = 512
    MAX_TEST_OUTPUT_BYTES = 16_384
    _OPERATIONS = {
        "workspace.list_files",
        "workspace.read_text",
        "workspace.patch_text",
        "workspace.write_artifact",
        "validate.json",
        "validate.file",
        "test.run_pytest_bounded",
    }
    _CAPABILITIES = {
        "workspace.list_files": "WORKSPACE_READ",
        "workspace.read_text": "WORKSPACE_READ",
        "workspace.patch_text": "WORKSPACE_WRITE",
        "workspace.write_artifact": "ARTIFACT_WRITE",
        "validate.json": "WORKSPACE_READ",
        "validate.file": "WORKSPACE_READ",
        "test.run_pytest_bounded": "TEST_RUN_PYTEST",
    }

    def __init__(
        self,
        workspace_root: str | Path,
        state_store: SQLiteDurableStateStore | None,
        *,
        python_executable: str | Path | None = None,
        pytest_timeout_seconds: int = 15,
    ) -> None:
        root = Path(workspace_root)
        if not root.exists() or not root.is_dir() or root.is_symlink():
            raise ToolInputError("workspace root must be an existing non-symlink directory")
        self._root = root.resolve(strict=True)
        self._artifact_root = self._root / ".astron-artifacts"
        if not isinstance(pytest_timeout_seconds, int) or not 1 <= pytest_timeout_seconds <= 60:
            raise ValueError("pytest_timeout_seconds must be between 1 and 60")
        # Preserve the interpreter entrypoint rather than resolving a virtual
        # environment's Python symlink: resolving it can lose the venv's
        # site-packages and thereby change the trusted test environment.
        executable = Path(python_executable or sys.executable).absolute()
        if not executable.is_file():
            raise ToolInputError("trusted Python executable is not a regular file")
        self._python = executable
        self._pytest_timeout_seconds = pytest_timeout_seconds
        self._runtime: DurableActionRuntime | None = None
        if state_store is not None:
            self._engine = PermissionEngine(
                capabilities=set(self._CAPABILITIES.values()),
                owner_allowlist=set(),
                principal_id=self.PRINCIPAL_ID,
                scope_guard=ScopeGuard(
                    fs_read_classes={self.WORKSPACE_SCOPE},
                    fs_write_classes={self.WORKSPACE_SCOPE, self.ARTIFACT_SCOPE},
                ),
                durable_state_store=state_store,
            )
            self._runtime = DurableActionRuntime(self._engine, state_store)

    @property
    def workspace_root(self) -> Path:
        return self._root

    @property
    def state_store(self) -> SQLiteDurableStateStore:
        """The exact store shared with the durable runtime and verifier."""

        if self._runtime is None:
            raise ToolInputError("direct bounded runtime has no durable state store")
        return self._runtime.state_store

    def execute(self, task_id: str, step: int, operation: str, parameters: Mapping[str, Any]) -> ToolExecution:
        """Build and durably execute one finite proposal."""

        if self._runtime is None:
            raise ToolInputError("governed execution requires a durable state store")
        request = self._build_request(task_id, step, operation, parameters)
        execution = self._runtime.execute(
            task_id,
            request,
            self._execute_request,
            principal_context=PrincipalContext(principal_id=self.PRINCIPAL_ID),
        )
        return ToolExecution(
            action=request,
            result=execution.action_result,
            executor_invoked=execution.executor_invoked,
            needs_reconciliation=execution.needs_reconciliation,
            authorization_decision=execution.authorization.decision.value,
            state_error=execution.state_error,
        )

    def execute_direct(
        self,
        task_id: str,
        step: int,
        operation: str,
        parameters: Mapping[str, Any],
    ) -> ToolExecution:
        """Execute the same normalized bounded operation without governance."""

        if self._runtime is not None:
            raise ToolInputError("direct execution requires a runtime without durable state")
        request = self._build_request(task_id, step, operation, parameters)
        result = self._execute_request(request)
        return ToolExecution(
            action=request,
            result=result,
            executor_invoked=True,
            needs_reconciliation=False,
            authorization_decision="not_applicable",
        )

    def _build_request(
        self,
        task_id: str,
        step: int,
        operation: str,
        parameters: Mapping[str, Any],
    ) -> ActionRequest:
        if operation not in self._OPERATIONS:
            raise ToolInputError("tool operation is not allowlisted")
        if not isinstance(step, int) or not 1 <= step <= 99:
            raise ToolInputError("step must be a bounded positive integer")
        if not isinstance(parameters, Mapping):
            raise ToolInputError("tool parameters must be an object")
        normalized = self._normalize_parameters(operation, parameters, task_id=task_id)
        scope_mode, scopes = self._scope_for(operation)
        digest = hashlib.sha256(f"{task_id}:{step}:{operation}".encode("utf-8")).hexdigest()[:24]
        request = ActionRequest(
            action_id=f"p3-{step}-{digest}",
            worker_type="tool",
            operation=operation,
            parameters=normalized,
            required_permissions=[self._CAPABILITIES[operation]],
            filesystem_scope={"mode": scope_mode, "paths_class": scopes},
            network_scope={"mode": "none", "endpoints_class": []},
            timeout=self._pytest_timeout_seconds if operation == "test.run_pytest_bounded" else 15,
            idempotency_key=f"p3-{digest}",
            rollback_supported=False,
            approval_required=False,
        )
        return request

    def _scope_for(self, operation: str) -> tuple[str, list[str]]:
        if operation == "workspace.patch_text":
            return "read_write", [self.WORKSPACE_SCOPE]
        if operation == "workspace.write_artifact":
            return "write", [self.ARTIFACT_SCOPE]
        return "read", [self.WORKSPACE_SCOPE]

    def _normalize_parameters(
        self,
        operation: str,
        parameters: Mapping[str, Any],
        *,
        task_id: str,
    ) -> dict[str, Any]:
        allowed: dict[str, set[str]] = {
            "workspace.list_files": {"path"},
            "workspace.read_text": {"path"},
            "workspace.patch_text": {"path", "expected_old", "replacement"},
            "workspace.write_artifact": {"path", "content"},
            "validate.json": {"path", "schema_id"},
            "validate.file": {"path"},
            "test.run_pytest_bounded": set(),
        }
        raw = dict(parameters)
        if set(raw) - allowed[operation]:
            raise ToolInputError("tool parameters include an unsupported field")
        if operation == "test.run_pytest_bounded":
            if raw:
                raise ToolInputError("bounded pytest accepts no model-controlled arguments")
            return {}
        if operation == "workspace.list_files":
            path = raw.get("path", ".")
            normalized_path = self._relative_path(path, allow_root=True)
            self._safe_path(normalized_path, must_exist=True, regular_file=False)
            return {"path": normalized_path}
        path = self._relative_path(raw.get("path"), allow_root=False)
        self._safe_path(
            path,
            must_exist=operation != "workspace.write_artifact",
            regular_file=operation != "workspace.write_artifact",
        )
        if operation == "workspace.patch_text":
            expected, replacement = raw.get("expected_old"), raw.get("replacement")
            if not isinstance(expected, str) or not isinstance(replacement, str):
                raise ToolInputError("patch requires text expected_old and replacement")
            if not expected or len(expected.encode("utf-8")) > self.MAX_READ_BYTES:
                raise ToolInputError("patch expected_old is invalid or exceeds bound")
            if len(replacement.encode("utf-8")) > self.MAX_READ_BYTES:
                raise ToolInputError("patch replacement exceeds bound")
            return {"path": path, "expected_old": expected, "replacement": replacement}
        if operation == "workspace.write_artifact":
            content = raw.get("content")
            if not isinstance(content, str) or len(content.encode("utf-8")) > self.MAX_ARTIFACT_BYTES:
                raise ToolInputError("artifact content is invalid or exceeds bound")
            if not path.startswith(".astron-artifacts/"):
                raise ToolInputError("artifact path must be inside .astron-artifacts")
            return {"path": path, "content": content}
        if operation == "validate.json":
            schema_id = raw.get("schema_id")
            if schema_id is None:
                return {"path": path}
            contract = MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT
            if schema_id != contract.schema_id:
                raise ToolInputError("named JSON schema is not in the trusted registry")
            if path != contract.artifact_path:
                raise ToolInputError("completion schema is fixed to the completion artifact path")
            return {
                "path": path,
                "schema_id": contract.schema_id,
                "trusted_task_id": task_id,
            }
        return {"path": path}

    @staticmethod
    def _relative_path(value: Any, *, allow_root: bool) -> str:
        if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
            raise ToolInputError("path must be a non-empty relative POSIX path")
        pure = PurePosixPath(value)
        if pure.is_absolute() or ".." in pure.parts or any(part in {"", "."} for part in pure.parts if part != "."):
            raise ToolInputError("path escapes the workspace")
        if value == ".":
            if allow_root:
                return value
            raise ToolInputError("root is not a file target")
        normalized = pure.as_posix()
        if normalized in {"", "."}:
            raise ToolInputError("path is invalid")
        return normalized

    def _safe_path(self, relative: str, *, must_exist: bool, regular_file: bool = True) -> Path:
        candidate = self._root if relative == "." else self._root.joinpath(*PurePosixPath(relative).parts)
        parent_chain = [self._root]
        current = self._root
        for part in PurePosixPath(relative).parts[:-1]:
            current = current / part
            parent_chain.append(current)
        for item in parent_chain:
            if item.is_symlink():
                raise ToolInputError("symlink path is not permitted")
            if item.exists() and not item.is_dir():
                raise ToolInputError("path ancestor is not a directory")
        if must_exist and not candidate.exists():
            raise ToolInputError("workspace path does not exist")
        if candidate.is_symlink():
            raise ToolInputError("symlink path is not permitted")
        resolved = candidate.resolve(strict=must_exist)
        try:
            resolved.relative_to(self._root)
        except ValueError as exc:
            raise ToolInputError("resolved path escapes workspace") from exc
        if regular_file and candidate.exists() and not candidate.is_file():
            raise ToolInputError("workspace target must be a regular file")
        return candidate

    def _execute_request(self, request: ActionRequest) -> ActionResult:
        handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "workspace.list_files": self._list_files,
            "workspace.read_text": self._read_text,
            "workspace.patch_text": self._patch_text,
            "workspace.write_artifact": self._write_artifact,
            "validate.json": self._validate_json,
            "validate.file": self._validate_file,
            "test.run_pytest_bounded": self._run_pytest,
        }
        try:
            outcome = handlers[request.operation](request.parameters)
            if request.operation == "test.run_pytest_bounded" and outcome.get("status") != "PASSED":
                return ActionResult(action_id=request.action_id, status=ActionStatus.FAILURE, outcome=outcome, trace_id="phase3")
            if request.operation == "validate.json" and outcome.get("semantic_validation") == "FAILED":
                return ActionResult(action_id=request.action_id, status=ActionStatus.FAILURE, outcome=outcome, trace_id="phase3")
            return ActionResult(action_id=request.action_id, status=ActionStatus.SUCCESS, outcome=outcome, trace_id="phase3")
        except ToolInputError as exc:
            return ActionResult(action_id=request.action_id, status=ActionStatus.FAILURE,
                                outcome={"code": "SCOPE_OR_INPUT_VIOLATION", "detail": str(exc)}, trace_id="phase3")
        except OSError:
            return ActionResult(action_id=request.action_id, status=ActionStatus.FAILURE,
                                outcome={"code": "TOOL_IO_FAILURE"}, trace_id="phase3")

    def _list_files(self, parameters: dict[str, Any]) -> dict[str, Any]:
        start = self._safe_path(parameters["path"], must_exist=True, regular_file=False)
        if not start.is_dir():
            raise ToolInputError("list target must be a directory")
        files: list[str] = []
        for candidate in sorted(start.rglob("*")):
            if candidate.is_symlink():
                raise ToolInputError("workspace contains a symlink")
            if candidate.is_file():
                files.append(candidate.relative_to(self._root).as_posix())
                if len(files) > self.MAX_LISTED_FILES:
                    raise ToolInputError("workspace listing exceeds bound")
        return {"files": files, "count": len(files)}

    def _read_text(self, parameters: dict[str, Any]) -> dict[str, Any]:
        path = self._safe_path(parameters["path"], must_exist=True)
        if path.stat().st_size > self.MAX_READ_BYTES:
            raise ToolInputError("text file exceeds read bound")
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ToolInputError("text file is not valid UTF-8") from exc
        return {"path": parameters["path"], "content": content, "bytes": len(content.encode("utf-8"))}

    def _patch_text(self, parameters: dict[str, Any]) -> dict[str, Any]:
        path = self._safe_path(parameters["path"], must_exist=True)
        if path.stat().st_size > self.MAX_READ_BYTES:
            raise ToolInputError("patch target exceeds bound")
        try:
            old = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ToolInputError("patch target is not valid UTF-8") from exc
        expected = parameters["expected_old"]
        if old.count(expected) != 1:
            raise ToolInputError("patch precondition did not match exactly once")
        updated = old.replace(expected, parameters["replacement"], 1)
        self._atomic_write(path, updated)
        return {"path": parameters["path"], "changed": True, "bytes": len(updated.encode("utf-8"))}

    def _write_artifact(self, parameters: dict[str, Any]) -> dict[str, Any]:
        path = self._safe_path(parameters["path"], must_exist=False)
        if not path.parent.is_relative_to(self._artifact_root):
            raise ToolInputError("artifact destination escapes artifact directory")
        self._artifact_root.mkdir(mode=0o700, exist_ok=True)
        self._atomic_write(path, parameters["content"])
        return {"path": parameters["path"], "bytes": len(parameters["content"].encode("utf-8"))}

    def _validate_json(self, parameters: dict[str, Any]) -> dict[str, Any]:
        read = self._read_text(parameters)
        try:
            parsed = json.loads(read["content"])
        except json.JSONDecodeError as exc:
            raise ToolInputError("file is not valid JSON") from exc
        outcome = {
            "path": parameters["path"],
            "json_type": type(parsed).__name__,
            "semantic_validation": "NOT_REQUESTED",
        }
        schema_id = parameters.get("schema_id")
        if schema_id is None:
            return outcome
        contract = MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT
        validation = contract.validate(
            parsed,
            parameters["trusted_task_id"],
            artifact_bytes=read["bytes"],
        )
        outcome.update({
            "schema_id": contract.schema_id,
            "semantic_validation": "PASSED" if validation.valid else "FAILED",
            "reason_code": validation.reason_code,
        })
        return outcome

    def _validate_file(self, parameters: dict[str, Any]) -> dict[str, Any]:
        path = self._safe_path(parameters["path"], must_exist=True)
        size = path.stat().st_size
        if size > self.MAX_READ_BYTES:
            raise ToolInputError("file exceeds validation bound")
        return {"path": parameters["path"], "regular_file": True, "bytes": size}

    def _run_pytest(self, parameters: dict[str, Any]) -> dict[str, Any]:
        tests = self._safe_path("tests", must_exist=True, regular_file=False)
        if not tests.is_dir():
            raise ToolInputError("fixture tests directory is missing")
        env = {"PATH": os.environ.get("PATH", ""), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
        command = [str(self._python), "-m", "pytest", "tests", "-q"]
        process = subprocess.Popen(
            command,
            cwd=str(self._root),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=False,
        )
        try:
            output, _ = process.communicate(timeout=self._pytest_timeout_seconds)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                output, _ = process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                output, _ = process.communicate(timeout=2)
            return {"status": "TIMEOUT", "exit_code": process.returncode, "output": output[:self.MAX_TEST_OUTPUT_BYTES].decode("utf-8", "replace")}
        bounded = output[:self.MAX_TEST_OUTPUT_BYTES].decode("utf-8", "replace")
        if process.returncode != 0:
            return {"status": "FAILED", "exit_code": process.returncode, "output": bounded}
        return {"status": "PASSED", "exit_code": 0, "output": bounded}

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".astron-write-", dir=str(path.parent), text=True)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except Exception:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise
