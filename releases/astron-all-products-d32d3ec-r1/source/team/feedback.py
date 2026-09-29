"""Governed tool-result feedback projection (R2 H2).

Turns the durable outcome of governed actions into what the Executor may see in
its next round.  This lives in the runtime layer, not the benchmark layer: the
scheduler must not import ``team.benchmark``, which would create the circular
import ``scheduler -> team.benchmark -> adapter -> scheduler``.

SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Sequence

#: Minimal bounded-result policy for Executor feedback (R2 H2).
#:
#: No tool-result payload bound existed before R2 because no tool result was ever
#: fed back to a model.  The ceiling is set at 8 KiB: the largest file in any
#: frozen fixture is 1,065 bytes, so a real ``workspace.read_text`` is never
#: truncated in practice, while a pathological output cannot grow the context
#: without bound.  Truncation is always explicit.
TOOL_RESULT_MAX_BYTES = 8_192
TOOL_RESULT_TRUNCATION_POLICY = "NEW_MINIMAL_POLICY"
TRUNCATION_MARKER = "TRUNCATED=true"


class TaskContextError(RuntimeError):
    """A task context is malformed, or a parity assertion failed."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def assert_no_hidden_material(payload: Any, *, where: str = "task context") -> None:
    """Fail closed if hidden grading material appears in a model-visible payload."""

    found: list[str] = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                name = str(key)
                if name in FORBIDDEN_CONTEXT_KEYS:
                    found.append(f"{path}.{name}")
                walk(item, f"{path}.{name}")
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")

    walk(payload, where)
    if found:
        raise TaskContextError("TASK_CONTEXT_HIDDEN_MATERIAL", ", ".join(sorted(found)))


def truncate_tool_result(payload: Any, *, limit: int = TOOL_RESULT_MAX_BYTES) -> Any:
    """Bound one tool result without ever truncating silently."""

    text = payload if isinstance(payload, str) else json.dumps(payload, sort_keys=True, default=str)
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return payload
    clipped = raw[:limit].decode("utf-8", errors="ignore")
    return f"{clipped}\n{TRUNCATION_MARKER} original_bytes={len(raw)} limit_bytes={limit}"


def build_feedback(
    records: Iterable[Any],
    *,
    refused: Sequence[Any] = (),
    limit: int = TOOL_RESULT_MAX_BYTES,
) -> list[dict[str, Any]]:
    """Turn governed execution records into an Executor-visible feedback block.

    Every entry is bound to the durable identity of the action that produced it,
    so the model sees the result of *its governed action* rather than unattached
    text.  Only genuinely executed actions carry a payload; a refused or denied
    action reports the refusal instead.
    """

    feedback: list[dict[str, Any]] = []
    for record in records:
        entry = {
            "action_id": getattr(record, "action_id", None),
            "journal_id": getattr(record, "journal_id", None),
            "operation": getattr(record, "operation", None),
            "role": _role_value(getattr(record, "role", None)),
            "authorization_decision": getattr(record, "authorization_decision", None),
            "durable_state": getattr(record, "durable_state", None),
            "executor_invoked": bool(getattr(record, "executor_invoked", False)),
            "needs_reconciliation": bool(getattr(record, "needs_reconciliation", False)),
        }
        if entry["executor_invoked"]:
            entry["result"] = truncate_tool_result(
                dict(getattr(record, "outcome", {}) or {}), limit=limit
            )
        else:
            entry["result"] = None
        feedback.append(entry)

    for refusal in refused:
        feedback.append(
            {
                "action_id": None,
                "journal_id": None,
                "operation": getattr(refusal, "operation", None),
                "role": _role_value(getattr(refusal, "role", None)),
                "authorization_decision": "deny",
                "durable_state": None,
                "executor_invoked": False,
                "needs_reconciliation": False,
                "refused_reason": getattr(refusal, "reason", None),
                "result": None,
            }
        )
    return feedback


def _role_value(role: Any) -> Any:
    return getattr(role, "value", role)


__all__ = [
    "TOOL_RESULT_MAX_BYTES",
    "TOOL_RESULT_TRUNCATION_POLICY",
    "TRUNCATION_MARKER",
    "build_feedback",
    "truncate_tool_result",
]
