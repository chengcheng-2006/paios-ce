"""MockWorker — deterministic local worker for the Phase 3 closed loop.

The MockWorker NEVER executes real shell, PowerShell, file deletion, or
network writes. It simulates operations in-process and returns redacted
ActionResult records, so the orchestrator / demo loop can be validated
end-to-end on a clean machine.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import hashlib

from ..permissions import Decision
from ..protocols import (
    ActionRequest,
    ActionResult,
    ActionStatus,
    ErrorClass,
    ErrorEnvelope,
    RollbackStatus,
)
from .base import Worker


class MockWorker(Worker):
    """Simulated worker; validates and reports without real side effects."""

    worker_type = "tool"

    def __init__(self) -> None:
        self._executed: list[str] = []

    def execute(self, request: ActionRequest) -> ActionResult:
        if request.approval_required and not request.admin_token:
            return ActionResult(
                action_id=request.action_id,
                status=ActionStatus.DENIED,
                outcome={"summary_class": "approval_missing"},
                rollback_attempted=False,
                rollback_status=RollbackStatus.NOT_REQUIRED,
                trace_id=request.parameters.get("trace_id", "trace_redacted_01"),
                error=ErrorEnvelope(
                    error_id="err_mock_approval",
                    error_class=ErrorClass.PERMISSION_DENIED,
                    message="high-risk action requires confirmation",
                    retryable=False,
                    trace_id=request.parameters.get("trace_id", "trace_redacted_01"),
                ),
            )
        self._executed.append(request.action_id)
        digest = hashlib.sha256(request.operation.encode("utf-8")).hexdigest()[:8]
        return ActionResult(
            action_id=request.action_id,
            status=ActionStatus.SUCCESS,
            outcome={"summary_class": f"mock_executed_{request.operation}_[{digest}]"},
            usage={"cost_class": "free", "tokens_class": "small"},
            rollback_attempted=False,
            rollback_status=RollbackStatus.NOT_REQUIRED,
            trace_id=request.parameters.get("trace_id", "trace_redacted_01"),
        )

    @property
    def executed_action_ids(self) -> list[str]:
        return list(self._executed)
