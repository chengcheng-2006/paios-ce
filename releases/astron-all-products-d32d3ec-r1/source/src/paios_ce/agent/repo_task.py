"""Generic governed repository-task runner.

This compatibility layer intentionally knows nothing about SWE-bench grading.
It receives a public problem statement plus a prepared clean Git checkout,
lets the model use Astron's existing bounded and Terminal R1 tools, and records
the resulting repository state.  A downstream evaluator is the sole authority
on whether a task was solved.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
from typing import Any, Mapping, Sequence

from ..providers import ChatRequest, Provider
from ..state import SQLiteDurableStateStore
from ..tools import BoundedToolRuntime, TerminalEnabledToolRuntime, TerminalToolRuntime, ToolInputError, terminal_tool_schemas


_TASK_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}")
_FORBIDDEN_METADATA = frozenset({"fail_to_pass", "pass_to_pass", "gold_patch", "expected_diff", "test_patch", "patch"})
_MAX_TOOL_ARGUMENT_BYTES = 16_384
_MAX_DIFF_BYTES = 1_000_000
_BASE_TOOLS: tuple[dict[str, object], ...] = (
    {"type": "function", "function": {"name": "workspace.list_files", "description": "List files in the repository checkout.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "workspace.read_text", "description": "Read one UTF-8 repository file.", "parameters": {"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "workspace.patch_text", "description": "Replace exactly one matching string in one repository file.", "parameters": {"type": "object", "required": ["path", "expected_old", "replacement"], "properties": {"path": {"type": "string"}, "expected_old": {"type": "string"}, "replacement": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "test.run_pytest_bounded", "description": "Run pytest against the repository tests directory when present.", "parameters": {"type": "object", "properties": {}}}},
)


@dataclass(frozen=True)
class RepoTaskBudget:
    max_model_turns: int
    max_wall_clock_seconds: int
    max_model_calls: int
    max_output_tokens: int

    def __post_init__(self) -> None:
        if not 1 <= self.max_model_turns <= 60:
            raise ValueError("max_model_turns must be between 1 and 60")
        if not 1 <= self.max_wall_clock_seconds <= 3_600:
            raise ValueError("max_wall_clock_seconds must be between 1 and 3600")
        if not 1 <= self.max_model_calls <= self.max_model_turns:
            raise ValueError("max_model_calls must be between 1 and max_model_turns")
        if not 1 <= self.max_output_tokens <= 4_096:
            raise ValueError("max_output_tokens must be between 1 and 4096")


@dataclass(frozen=True)
class RepoTask:
    task_id: str
    workspace_root: Path
    problem_statement: str
    budget: RepoTaskBudget
    success_context: str | None = None
    allowed_tools: tuple[str, ...] = ()
    metadata_public: Mapping[str, object] = field(default_factory=dict)
    base_commit: str | None = None

    def __post_init__(self) -> None:
        if not _TASK_ID.fullmatch(self.task_id):
            raise ValueError("task_id is invalid")
        if not isinstance(self.problem_statement, str) or not self.problem_statement or len(self.problem_statement.encode("utf-8")) > 65_536:
            raise ValueError("problem_statement must be non-empty and bounded")
        root = Path(self.workspace_root)
        if not root.is_dir() or root.is_symlink():
            raise ValueError("workspace_root must be an existing non-symlink directory")
        lowered = {str(key).lower() for key in self.metadata_public}
        if lowered & _FORBIDDEN_METADATA:
            raise ValueError("metadata_public contains evaluator-only field names")


@dataclass(frozen=True)
class RepoTaskResult:
    task_id: str
    base_commit: str
    status_before: str
    status_after: str
    final_diff: str
    files_changed: tuple[str, ...]
    model_calls: int
    turns: int
    tool_calls: int
    runtime_status: str
    latency_ms: int
    final_answer: str
    trajectory: tuple[dict[str, object], ...]
    usage_metrics: Mapping[str, int]
    problem_statement_sha256: str

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["files_changed"] = list(self.files_changed)
        payload["trajectory"] = list(self.trajectory)
        return payload


class RepoTaskRunner:
    """One-task/one-workspace generic runner; it deliberately performs no grading."""

    def __init__(self, provider: Provider, *, model_id: str, runtime_root: str | Path, python_executable: str | Path | None = None) -> None:
        self._provider = provider
        self._model_id = model_id
        self._runtime_root = Path(runtime_root)
        self._python = python_executable

    def run(self, task: RepoTask) -> RepoTaskResult:
        workspace = Path(task.workspace_root).resolve(strict=True)
        status_before = self._git(workspace, "status", "--porcelain=v1")
        if status_before:
            raise ValueError("repository checkout must be clean before a RepoTask")
        base_commit = self._git(workspace, "rev-parse", "HEAD").strip()
        if task.base_commit is not None and task.base_commit != base_commit:
            raise ValueError("prepared checkout base_commit does not match RepoTask")
        run_dir = self._runtime_root / task.task_id
        if run_dir.exists():
            raise ValueError("one task requires one fresh runtime directory")
        run_dir.mkdir(parents=True, mode=0o700)
        started = time.monotonic()
        messages: list[dict[str, object]] = [{"role": "system", "content": self._system_prompt(task)}]
        messages.append({"role": "user", "content": task.problem_statement})
        trajectory: list[dict[str, object]] = []
        model_calls = turns = tool_calls = 0
        usage: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        final_answer = ""
        runtime_status = "BUDGET_EXHAUSTED"
        with SQLiteDurableStateStore(run_dir / "state.sqlite") as store:
            bounded = BoundedToolRuntime(workspace, store, python_executable=self._python)
            terminal = TerminalToolRuntime(workspace, store, log_root=run_dir / "terminal-logs")
            tools = TerminalEnabledToolRuntime(bounded, terminal, agent_owner=f"repo-task:{task.task_id}")
            store.register_task(task.task_id)
            try:
                for turn in range(1, task.budget.max_model_turns + 1):
                    if model_calls >= task.budget.max_model_calls or time.monotonic() - started >= task.budget.max_wall_clock_seconds:
                        break
                    model_calls += 1
                    turns = turn
                    try:
                        proposal = self._provider.tool_call(ChatRequest(messages=messages, model_id=self._model_id, max_tokens=task.budget.max_output_tokens, tools=self._tool_schemas(task), trace_id=f"repo-task-{task.task_id}"))
                    except Exception as exc:
                        runtime_status = f"PROVIDER_ERROR:{self._safe_error(exc)}"
                        break
                    self._add_usage(usage, getattr(proposal, "usage", {}))
                    final_answer = str(getattr(proposal, "content", "") or "")[:16_384]
                    calls = getattr(proposal, "tool_calls", [])
                    if not isinstance(calls, list) or not calls:
                        runtime_status = "AGENT_STOPPED"
                        break
                    if len(calls) != 1:
                        runtime_status = "INVALID_MODEL_OUTPUT"
                        break
                    call_id = "invalid"
                    try:
                        call_id, operation, parameters = self._parse_call(calls[0])
                        if task.allowed_tools and operation not in task.allowed_tools:
                            raise ToolInputError("tool operation is not enabled for this RepoTask")
                        # Terminal replay identity is the provider's logical call id,
                        # not a turn counter. Re-submission cannot open or dispatch a
                        # second session/command.
                        execution = (
                            terminal.execute(task.task_id, call_id, f"repo-task:{task.task_id}", operation, parameters)
                            if operation.startswith("terminal_")
                            else bounded.execute(task.task_id, tool_calls + 1, operation, parameters)
                        )
                        tool_calls += 1
                        context = self._tool_context(execution)
                        trajectory.append({"turn": turn, "call_id": call_id, "operation": operation, "status": context["status"]})
                    except ToolInputError as exc:
                        tool_calls += 1
                        context = {"status": "failure", "code": "SCOPE_OR_INPUT_VIOLATION"}
                        trajectory.append({"turn": turn, "call_id": "invalid", "operation": "invalid", "status": "failure"})
                    messages.append({"role": "assistant", "content": "", "tool_calls": [calls[0]]})
                    messages.append({"role": "tool", "tool_call_id": call_id, "content": json.dumps(context, sort_keys=True)[:4096]})
            finally:
                tools.shutdown()
        status_after = self._git(workspace, "status", "--porcelain=v1")
        diff = self._git(workspace, "diff", "--no-ext-diff", "--binary")
        if len(diff.encode("utf-8")) > _MAX_DIFF_BYTES:
            diff = diff.encode("utf-8")[:_MAX_DIFF_BYTES].decode("utf-8", "replace") + "\n[DIFF_TRUNCATED]"
        files_changed = tuple(filter(None, self._git(workspace, "diff", "--no-ext-diff", "--name-only").splitlines()))
        return RepoTaskResult(task.task_id, base_commit, status_before, status_after, diff, files_changed, model_calls, turns, tool_calls, runtime_status, round((time.monotonic() - started) * 1000), final_answer, tuple(trajectory), usage, hashlib.sha256(task.problem_statement.encode("utf-8")).hexdigest())

    @staticmethod
    def _git(workspace: Path, *args: str) -> str:
        completed = subprocess.run(["git", *args], cwd=workspace, check=False, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if completed.returncode != 0:
            raise ValueError("prepared workspace is not a usable Git checkout")
        return completed.stdout

    @staticmethod
    def _parse_call(raw: object) -> tuple[str, str, dict[str, object]]:
        function = raw.get("function") if isinstance(raw, dict) else None
        call_id = raw.get("id") if isinstance(raw, dict) else None
        if not isinstance(function, dict) or not isinstance(call_id, str) or not call_id:
            raise ToolInputError("tool proposal is invalid")
        name, arguments = function.get("name"), function.get("arguments")
        if not isinstance(name, str) or not isinstance(arguments, str) or len(arguments.encode("utf-8")) > _MAX_TOOL_ARGUMENT_BYTES:
            raise ToolInputError("tool proposal is invalid")
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError as exc:
            raise ToolInputError("tool arguments are not JSON") from exc
        if not isinstance(parsed, dict):
            raise ToolInputError("tool arguments must be an object")
        return call_id, name, parsed

    @staticmethod
    def _tool_context(execution: object) -> dict[str, object]:
        result = getattr(execution, "result", None)
        if result is None:
            return {"status": "failure", "code": "EXECUTION_NOT_COMPLETED"}
        outcome = getattr(result, "outcome", {})
        return {"status": result.status.value, "outcome": outcome if isinstance(outcome, dict) else {}}

    @staticmethod
    def _add_usage(total: dict[str, int], raw: object) -> None:
        if isinstance(raw, Mapping):
            for key in total:
                value = raw.get(key)
                if isinstance(value, int) and value >= 0:
                    total[key] += value

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        return str(getattr(getattr(exc, "code", None), "value", exc.__class__.__name__))[:64]

    @staticmethod
    def _system_prompt(task: RepoTask) -> str:
        context = f"\nPublic context: {task.success_context}" if task.success_context else ""
        return "You are working in one prepared repository checkout. Use only supplied native tools. Make changes only when justified by the problem statement and tool results. A later independent evaluator determines success; never claim the task is solved." + context

    @staticmethod
    def _tool_schemas(task: RepoTask) -> list[dict[str, object]]:
        all_schemas = list(_BASE_TOOLS) + terminal_tool_schemas()
        if not task.allowed_tools:
            return all_schemas
        allowed = set(task.allowed_tools)
        return [schema for schema in all_schemas if str(schema["function"]["name"]) in allowed]


__all__ = ["RepoTask", "RepoTaskBudget", "RepoTaskResult", "RepoTaskRunner"]
