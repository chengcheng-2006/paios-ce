"""A finite native task loop for the single Phase 3 maintenance task.

The loop accepts model proposals but has no path from a model response to a
filesystem effect except through :class:`BoundedToolRuntime`.  Completion is
delegated exclusively to :class:`MaintenanceVerifier`.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
import time
from typing import Any

from ..maintenance_artifact import MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT
from ..providers import ChatRequest, MockProvider, Provider
from ..tools import BoundedToolRuntime, ToolInputError, terminal_tool_schemas
from .verifier import MaintenanceVerifier, VerificationResult


AGENT_CONTRACT_VERSION = "AIC2026_READ_BATCH_VERIFIED_ARTIFACT_V4"
READ_ONLY_BATCH_ALLOWLIST = frozenset({"workspace.list_files", "workspace.read_text"})
MAX_READ_ONLY_TOOL_CALLS_PER_TURN = 4
_MAX_RECORDED_RESPONSE_TOOL_NAMES = 32
_SAFE_PROVIDER_FUNCTION_NAME = re.compile(r"[A-Za-z0-9_-]{1,64}")
_SAFE_INTERNAL_OPERATION_NAME = re.compile(r"[A-Za-z0-9_.-]{1,128}")

_TASK_PROMPT = (
    "Diagnose the failing trusted maintenance fixture. Use only the supplied "
    "bounded tools to inspect files, make the smallest permitted source "
    "correction, run tests, and write the required structured change summary. "
    "You are operating in a controlled tool-execution environment. "
    "Tool-use protocol (AIC2026_READ_BATCH_VERIFIED_ARTIFACT_V4): a turn may have "
    "no tool call, one tool call, or at most four read-only inspection calls. "
    "Only workspace.list_files and workspace.read_text may appear together in "
    "a multi-call response. If a turn needs a file modification, artifact "
    "write, test run, validation, or any other operation, issue exactly one "
    "tool call in that turn. Never mix a read-only call with another kind of "
    "call, issue multiple modifying or testing calls, predict a result, or "
    "bundle actions into a fictional tool. After a read-only batch, wait for "
    "all real tool results before deciding the next step. Every write, test, "
    "or other potentially active operation must wait for the preceding real "
    "result and be proposed on a later turn. When you believe the task is complete, do "
    "not call another tool merely to announce completion; return a candidate "
    "completion explanation. Do not claim success; the verifier decides completion."
)

_TOOL_SCHEMAS = [
    {"type": "function", "function": {"name": "workspace.list_files", "description": "List files within the trusted fixture workspace.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "workspace.read_text", "description": "Read one trusted UTF-8 text file in the fixture workspace.", "parameters": {"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "workspace.patch_text", "description": "Atomically replace exact expected text in one trusted fixture source file.", "parameters": {"type": "object", "required": ["path", "expected_old", "replacement"], "properties": {"path": {"type": "string"}, "expected_old": {"type": "string"}, "replacement": {"type": "string"}}}}},
    {
        "type": "function",
        "function": {
            "name": "workspace.write_artifact",
            "description": (
                "Write one bounded structured artifact under the trusted artifact directory. "
                "The maintenance completion artifact must follow trusted schema "
                f"{MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT.schema_id} at "
                f"{MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT.artifact_path}; the system "
                "instruction supplies its current task-bound requirements."
            ),
            "parameters": {
                "type": "object",
                "required": ["path", "content"],
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "validate.json",
            "description": (
                "Validate JSON syntax without modifying the file. Syntax-only PASS is not "
                "completion-artifact acceptance. Supply the trusted schema_id to additionally "
                "validate the maintenance artifact semantically; the independent verifier "
                "remains the only completion authority."
            ),
            "parameters": {
                "type": "object",
                "required": ["path"],
                "properties": {
                    "path": {"type": "string"},
                    "schema_id": {
                        "type": "string",
                        "enum": [MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT.schema_id],
                    },
                },
            },
        },
    },
    {"type": "function", "function": {"name": "validate.file", "description": "Validate one trusted workspace file without modifying it.", "parameters": {"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "test.run_pytest_bounded", "description": "Run the fixed trusted fixture pytest target with bounded execution.", "parameters": {"type": "object", "properties": {}}}},
]


@dataclass(frozen=True)
class NativeTaskResult:
    task_id: str
    accepted: bool
    verifier: VerificationResult
    actions: tuple[dict[str, object], ...]
    provider_error: str | None
    provider_diagnostics: dict[str, object] | None
    request_contract_snapshot: dict[str, object] | None
    response_tool_call_metadata: dict[str, object] | None
    exhausted: bool


class NativeAgent:
    """Bounded proposal loop with sequential reads and one-at-a-time effects."""

    def __init__(
        self,
        provider: Provider,
        tools: BoundedToolRuntime,
        verifier: MaintenanceVerifier,
        *,
        model_id: str = "mock-1",
        max_steps: int = 6,
        task_timeout_seconds: int = 60,
    ) -> None:
        if not 1 <= max_steps <= 12 or not 1 <= task_timeout_seconds <= 300:
            raise ValueError("Phase 3 task bounds are invalid")
        self._provider = provider
        self._tools = tools
        self._verifier = verifier
        self._model_id = model_id
        self._max_steps = max_steps
        self._task_timeout_seconds = task_timeout_seconds
        self._tool_schemas = list(_TOOL_SCHEMAS)
        self._terminal_capability_enabled = bool(
            getattr(tools, "terminal_capability_enabled", False)
        )
        if self._terminal_capability_enabled:
            self._tool_schemas.extend(terminal_tool_schemas())

    def run(self, task_id: str) -> NativeTaskResult:
        """Persist a task, execute bounded proposals, then always invoke verifier."""

        self._tools.state_store.register_task(task_id)
        started = time.monotonic()
        messages: list[dict[str, Any]] = [{
            "role": "system",
            "content": (
                _TASK_PROMPT
                + (
                    " Terminal R1 is available only through its six governed "
                    "terminal_* schemas; it retains the same one-action-per-turn "
                    "rule and returns bounded, redacted tool results."
                    if self._terminal_capability_enabled else ""
                )
                + " "
                + MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT.agent_instructions(task_id)
            ),
        }]
        history: list[dict[str, object]] = []
        provider_error: str | None = None
        provider_diagnostics: dict[str, object] | None = None
        request_contract_snapshot: dict[str, object] | None = None
        response_tool_call_metadata: dict[str, object] | None = None
        exhausted = True
        action_step = 0
        for _model_turn in range(1, self._max_steps + 1):
            if time.monotonic() - started >= self._task_timeout_seconds:
                provider_error = "TASK_TIMEOUT"
                break
            try:
                proposal = self._provider.tool_call(
                    ChatRequest(
                        messages=messages,
                        model_id=self._model_id,
                        max_tokens=512,
                        tools=self._tool_schemas,
                        trace_id="phase3-native",
                    )
                )
            except Exception as exc:
                provider_error = self._safe_provider_error(exc)
                safe = getattr(exc, "safe_diagnostics", None)
                provider_diagnostics = dict(safe) if isinstance(safe, dict) else None
                break
            snapshot = getattr(proposal, "request_contract_snapshot", None)
            request_contract_snapshot = dict(snapshot) if isinstance(snapshot, dict) else None
            response_tool_call_metadata = self._safe_response_tool_call_metadata(proposal)
            calls = proposal.tool_calls
            classification = response_tool_call_metadata["response_batch_classification"]
            if not calls:
                exhausted = False
                break
            if classification in {"REJECTED_MIXED_BATCH", "REJECTED_TOO_MANY_CALLS"}:
                provider_error = "INVALID_MODEL_OUTPUT"
                break
            try:
                parsed_calls = [self._parse_proposal(call) for call in calls]
                call_ids = [self._tool_call_id(call) for call in calls]
            except ToolInputError:
                provider_error = "INVALID_MODEL_OUTPUT"
                break
            if len(set(call_ids)) != len(call_ids):
                provider_error = "INVALID_MODEL_OUTPUT"
                break
            if len(parsed_calls) > 1 and any(
                operation not in READ_ONLY_BATCH_ALLOWLIST for operation, _ in parsed_calls
            ):
                provider_error = "INVALID_MODEL_OUTPUT"
                break

            messages.append(self._assistant_tool_call_message(calls))
            batch_continues_after_failure = len(parsed_calls) > 1
            stop_after_turn = False
            for call_id, (operation, parameters) in zip(call_ids, parsed_calls):
                action_step += 1
                try:
                    execution = self._tools.execute(task_id, action_step, operation, parameters)
                except ToolInputError:
                    if not batch_continues_after_failure:
                        provider_error = "INVALID_MODEL_OUTPUT"
                        break
                    messages.append(self._tool_result_message(
                        call_id,
                        {"status": "failure", "code": "SCOPE_OR_INPUT_VIOLATION"},
                    ))
                    continue

                action_history: dict[str, object] = {
                    "operation": execution.action.operation,
                    "status": None if execution.result is None else execution.result.status.value,
                    "executor_invoked": execution.executor_invoked,
                    "needs_reconciliation": execution.needs_reconciliation,
                }
                if execution.result is not None:
                    semantic_validation = execution.result.outcome.get("semantic_validation")
                    if semantic_validation in {"PASSED", "FAILED", "NOT_REQUESTED"}:
                        action_history["semantic_validation"] = semantic_validation
                history.append(action_history)
                messages.append(self._tool_result_message(
                    call_id,
                    self._safe_execution_context(execution),
                ))
                if (
                    not execution.executor_invoked
                    or execution.needs_reconciliation
                    or execution.result is None
                    or execution.result.status.value != "success"
                ) and not batch_continues_after_failure:
                    exhausted = False
                    stop_after_turn = True
                    break
            if provider_error is not None or stop_after_turn:
                break
        verification = self._verifier.verify(task_id)
        return NativeTaskResult(
            task_id=task_id,
            accepted=verification.accepted,
            verifier=verification,
            actions=tuple(history),
            provider_error=provider_error,
            provider_diagnostics=provider_diagnostics,
            request_contract_snapshot=request_contract_snapshot,
            response_tool_call_metadata=response_tool_call_metadata,
            exhausted=exhausted,
        )

    @staticmethod
    def _parse_proposal(raw: Any) -> tuple[str, dict[str, Any]]:
        if not isinstance(raw, dict) or not isinstance(raw.get("function"), dict):
            raise ToolInputError("tool proposal is invalid")
        function = raw["function"]
        operation = function.get("name")
        arguments = function.get("arguments")
        if not isinstance(operation, str) or not isinstance(arguments, str) or len(arguments.encode("utf-8")) > 16_384:
            raise ToolInputError("tool proposal is invalid")
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError as exc:
            raise ToolInputError("tool arguments are not JSON") from exc
        if not isinstance(parsed, dict):
            raise ToolInputError("tool arguments must be an object")
        return operation, parsed

    @staticmethod
    def _tool_call_id(raw: Any) -> str:
        call_id = raw.get("id") if isinstance(raw, dict) else None
        if not isinstance(call_id, str) or not call_id or len(call_id.encode("utf-8")) > 128:
            raise ToolInputError("tool call identifier is invalid")
        return call_id

    @staticmethod
    def _assistant_tool_call_message(calls: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": call["id"],
                    "type": "function",
                    "function": {
                        "name": call["function"]["name"],
                        "arguments": call["function"]["arguments"],
                    },
                }
                for call in calls
            ],
        }

    @classmethod
    def _tool_result_message(cls, call_id: str, outcome: dict[str, Any]) -> dict[str, str]:
        return {
            "role": "tool",
            "tool_call_id": call_id,
            "content": cls._bounded_context(outcome),
        }

    @staticmethod
    def _safe_execution_context(execution: Any) -> dict[str, Any]:
        if execution.result is not None:
            return {
                "status": execution.result.status.value,
                "outcome": dict(execution.result.outcome),
            }
        if execution.needs_reconciliation:
            code = "NEEDS_RECONCILIATION"
        elif execution.authorization_decision != "allow":
            code = "AUTHORIZATION_DENIED"
        else:
            code = "EXECUTION_NOT_COMPLETED"
        return {"status": "failure", "code": code}

    @staticmethod
    def _bounded_context(outcome: dict[str, Any]) -> str:
        payload = json.dumps(outcome, sort_keys=True, ensure_ascii=True)
        return payload[:2_048]

    @staticmethod
    def _safe_response_tool_call_metadata(proposal: Any) -> dict[str, object]:
        """Keep cardinality and safe names, never tool arguments or content."""

        calls = proposal.tool_calls if isinstance(getattr(proposal, "tool_calls", None), list) else []
        count = len(calls)
        recorded_count = min(count, _MAX_RECORDED_RESPONSE_TOOL_NAMES)
        raw_metadata = getattr(proposal, "response_tool_call_metadata", None)
        raw_provider_names = (
            raw_metadata.get("response_provider_function_names")
            if isinstance(raw_metadata, dict)
            else None
        )
        if isinstance(raw_provider_names, list) and len(raw_provider_names) == count:
            provider_names = [
                name if isinstance(name, str) and _SAFE_PROVIDER_FUNCTION_NAME.fullmatch(name)
                else "UNSAFE_NAME_REDACTED"
                for name in raw_provider_names[:recorded_count]
            ]
        else:
            provider_names = ["NOT_REPORTED"] * recorded_count
        internal_names: list[str] = []
        for call in calls[:recorded_count]:
            function = call.get("function") if isinstance(call, dict) else None
            name = function.get("name") if isinstance(function, dict) else None
            internal_names.append(
                name if isinstance(name, str) and _SAFE_INTERNAL_OPERATION_NAME.fullmatch(name)
                else "UNSAFE_NAME_REDACTED"
            )
        return {
            "response_tool_call_count": count,
            "response_provider_function_names": provider_names,
            "response_internal_operation_names": internal_names,
            "response_tool_call_names_truncated": count > _MAX_RECORDED_RESPONSE_TOOL_NAMES,
            "response_batch_classification": NativeAgent._batch_classification(calls),
        }

    @staticmethod
    def _batch_classification(calls: list[dict[str, Any]]) -> str:
        count = len(calls)
        if count == 0:
            return "NO_CALL"
        if count == 1:
            return "SINGLE_ACTION"
        if count > MAX_READ_ONLY_TOOL_CALLS_PER_TURN:
            return "REJECTED_TOO_MANY_CALLS"
        operations: list[object] = []
        for call in calls:
            function = call.get("function") if isinstance(call, dict) else None
            operations.append(function.get("name") if isinstance(function, dict) else None)
        if all(operation in READ_ONLY_BATCH_ALLOWLIST for operation in operations):
            return "READ_ONLY_BATCH"
        return "REJECTED_MIXED_BATCH"

    @staticmethod
    def _safe_provider_error(exc: Exception) -> str:
        code = getattr(exc, "code", None)
        return str(getattr(code, "value", code) or exc.__class__.__name__)[:96]


def offline_maintenance_provider(task_id: str) -> MockProvider:
    """Return a deterministic offline proposal sequence for integration tests/demo."""

    def call(name: str, arguments: dict[str, Any], index: int) -> dict[str, Any]:
        return {
            "id": f"offline-{index}",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments, sort_keys=True)},
        }

    contract = MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT
    summary = json.dumps(
        {
            "task_id": task_id,
            "changed_files": list(contract.required_changed_files),
            "summary": "Corrected the fixture default timeout and verified the trusted test suite.",
        },
        sort_keys=True,
    )
    return MockProvider(tool_call_batches=[
        [
            call("workspace.read_text", {"path": "README.md"}, 1),
            call("workspace.read_text", {"path": "maintenance_config.py"}, 2),
            call("workspace.read_text", {"path": "tests/test_maintenance_config.py"}, 3),
        ],
        [call("workspace.patch_text", {"path": "maintenance_config.py", "expected_old": "DEFAULT_TIMEOUT_SECONDS = 0", "replacement": "DEFAULT_TIMEOUT_SECONDS = 30"}, 4)],
        [call("test.run_pytest_bounded", {}, 5)],
        [call("workspace.write_artifact", {"path": contract.artifact_path, "content": summary}, 6)],
        [call("validate.json", {"path": contract.artifact_path, "schema_id": contract.schema_id}, 7)],
        [],
    ])
