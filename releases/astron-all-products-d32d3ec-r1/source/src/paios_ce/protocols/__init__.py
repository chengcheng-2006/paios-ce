"""Task/Action protocol models and enums (public contract parity).

These pydantic models are consistent with the public JSON Schemas
(task_envelope, action_request, action_result, error_envelope) and the
Task/Action Protocol structural contracts (TaskPlan, ApprovalRequest,
TaskResult, AuditEvent).

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from .enums import (
    ActionOrigin,
    ActionStatus,
    ApprovalState,
    Capability,
    ConfirmationKind,
    CostClass,
    ErrorClass,
    EventKind,
    FsScopeMode,
    NetworkScopeMode,
    RiskLevel,
    RollbackStatus,
    TaskRiskLevel,
    TaskStatus,
    WorkerType,
)
from .models import (
    ActionRequest,
    ActionResult,
    ApprovalRequest,
    AttachmentRef,
    AuditEvent,
    Constraints,
    ErrorEnvelope,
    FsScope,
    NetworkScope,
    ProcessScope,
    TaskEnvelope,
    TaskPlan,
    TaskResult,
)

__all__ = [
    "ActionOrigin",
    "ActionRequest",
    "ActionResult",
    "ActionStatus",
    "ApprovalRequest",
    "ApprovalState",
    "AttachmentRef",
    "AuditEvent",
    "Capability",
    "ConfirmationKind",
    "Constraints",
    "CostClass",
    "ErrorClass",
    "ErrorEnvelope",
    "EventKind",
    "FsScope",
    "FsScopeMode",
    "NetworkScope",
    "NetworkScopeMode",
    "ProcessScope",
    "RiskLevel",
    "RollbackStatus",
    "TaskEnvelope",
    "TaskPlan",
    "TaskResult",
    "TaskRiskLevel",
    "TaskStatus",
    "WorkerType",
]
