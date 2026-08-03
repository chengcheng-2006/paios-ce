"""Pydantic models for the PAIOS CE Task/Action protocol.

These models are consistent with the Phase 2 JSON Schemas
(task_envelope / action_request / action_result / error_envelope) and the
structural contracts in TASK_AND_ACTION_PROTOCOL.md (TaskPlan,
ApprovalRequest, TaskResult, AuditEvent). All models use extra="forbid".

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Set

from pydantic import BaseModel, ConfigDict, Field

from .enums import (
    ActionOrigin,
    ActionStatus,
    ApprovalState,
    Capability,
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

MANIFEST_VERSION = "0.1.0"


class Constraints(BaseModel):
    """TaskEnvelope.constraints."""

    model_config = ConfigDict(extra="forbid")

    max_actions: Optional[int] = Field(default=None, ge=1)
    max_cost_class: Optional[CostClass] = None
    scope_hints: List[str] = Field(default_factory=list)


class AttachmentRef(BaseModel):
    """TaskEnvelope.attachments[] — opaque handle only, never bytes."""

    model_config = ConfigDict(extra="forbid")

    ref: str = Field(min_length=1, max_length=256)
    mime_class: str = Field(min_length=1, max_length=64)
    size_class: str = Field(min_length=1, max_length=64)


class TaskEnvelope(BaseModel):
    """Top-level task container (task_envelope.schema.json)."""

    model_config = ConfigDict(extra="forbid")

    manifest_version: Literal["0.1.0"] = MANIFEST_VERSION
    task_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    origin: ActionOrigin
    owner_identity: str = Field(min_length=1, max_length=256)
    intent: str = Field(min_length=1, max_length=128)
    risk_level: TaskRiskLevel = TaskRiskLevel.LOW
    requested_capabilities: Set[Capability] = Field(default_factory=set)
    attachments: List[AttachmentRef] = Field(default_factory=list)
    constraints: Constraints = Field(default_factory=Constraints)
    deadline_optional: Optional[str] = None
    approval_state: ApprovalState = ApprovalState.NOT_REQUIRED
    trace_id: str = Field(min_length=1, max_length=128)


class FsScope(BaseModel):
    """ActionRequest.filesystem_scope."""

    model_config = ConfigDict(extra="forbid")

    mode: FsScopeMode = FsScopeMode.NONE
    paths_class: List[str] = Field(default_factory=list)


class NetworkScope(BaseModel):
    """ActionRequest.network_scope."""

    model_config = ConfigDict(extra="forbid")

    mode: NetworkScopeMode = NetworkScopeMode.NONE
    endpoints_class: List[str] = Field(default_factory=list)


class ProcessScope(BaseModel):
    """ActionRequest.process_scope — bounded named set, never arbitrary shell."""

    model_config = ConfigDict(extra="forbid")

    allowed_executables_class: List[str] = Field(default_factory=list)


class ActionRequest(BaseModel):
    """Single executable unit (action_request.schema.json)."""

    model_config = ConfigDict(extra="forbid")

    manifest_version: Literal["0.1.0"] = MANIFEST_VERSION
    action_id: str = Field(min_length=1, max_length=128)
    worker_type: WorkerType = WorkerType.TOOL
    operation: str = Field(min_length=1, max_length=128)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    required_permissions: List[str] = Field(default_factory=list)
    filesystem_scope: FsScope = Field(default_factory=FsScope)
    network_scope: NetworkScope = Field(default_factory=NetworkScope)
    process_scope: Optional[ProcessScope] = None
    timeout: int = Field(default=30, ge=1, le=86400)
    idempotency_key: str = Field(min_length=1, max_length=128)
    rollback_supported: bool = False
    approval_required: bool = False
    admin_token: Optional[str] = None


class ErrorEnvelope(BaseModel):
    """Redacted structured error (error_envelope.schema.json)."""

    model_config = ConfigDict(extra="forbid")

    manifest_version: Literal["0.1.0"] = MANIFEST_VERSION
    error_id: str = Field(min_length=1, max_length=128)
    error_class: ErrorClass = ErrorClass.INTERNAL
    message: str = Field(min_length=1, max_length=512)
    retryable: bool = False
    trace_id: str = Field(min_length=1, max_length=128)
    timestamp: str = Field(default_factory=lambda: _utcnow_iso())


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ActionResult(BaseModel):
    """Result of executing an ActionRequest (action_result.schema.json)."""

    model_config = ConfigDict(extra="forbid")

    manifest_version: Literal["0.1.0"] = MANIFEST_VERSION
    action_id: str = Field(min_length=1, max_length=128)
    status: ActionStatus = ActionStatus.FAILURE
    outcome: Dict[str, Any] = Field(default_factory=dict)
    usage: Optional[Dict[str, str]] = None
    rollback_attempted: bool = False
    rollback_status: RollbackStatus = RollbackStatus.NOT_REQUIRED
    trace_id: str = Field(min_length=1, max_length=128)
    error: Optional[ErrorEnvelope] = None


class TaskPlan(BaseModel):
    """Plan produced by routing/Permission Engine (structural contract)."""

    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    actions: List[ActionRequest] = Field(default_factory=list)
    rollback_strategy: str = "none"  # none | compensating | best_effort
    estimated_cost_class: CostClass = CostClass.FREE
    routing_decisions: List[Dict[str, str]] = Field(default_factory=list)
    approval_required_count: int = 0
    trace_id: str = Field(min_length=1, max_length=128)


class ApprovalRequest(BaseModel):
    """Confirmation prompt for high-risk actions (structural contract).

    Single-use; replay of an approval_request_id is rejected.
    """

    model_config = ConfigDict(extra="forbid")

    approval_request_id: str = Field(min_length=1, max_length=128)
    action_id: str = Field(min_length=1, max_length=128)
    action_summary: str = Field(min_length=1, max_length=512)
    risk_class: str = "external_write"  # destructive | admin | financial | external_write
    origin: ActionOrigin = ActionOrigin.CLI
    channel_id_origin: str = "cli"
    confirmation_channel_id: str = "cli"
    ttl_seconds: int = Field(default=300, ge=1, le=86400)
    required_token: str = "confirm"
    state: ApprovalState = ApprovalState.PENDING


class TaskResult(BaseModel):
    """Aggregated result of a TaskEnvelope (structural contract)."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1, max_length=128)
    status: TaskStatus = TaskStatus.FAILURE
    action_results: List[ActionResult] = Field(default_factory=list)
    trace_id: str = Field(min_length=1, max_length=128)
    summary: str = Field(default="", max_length=2048)
    timestamp: str = Field(default_factory=lambda: _utcnow_iso())


class AuditEvent(BaseModel):
    """Redacted audit record (Phase 3 prompt section 16 + protocol section 9).

    Mandatory fields follow the Phase 3 execution prompt. Forbidden content
    (secret values, raw tokens, cookies, authorization headers, raw audio,
    private paths, owner identity detail) is structurally absent: no such
    field exists on this model and extra="forbid" rejects any attempt to add one.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1, max_length=128)
    timestamp: str = Field(default_factory=lambda: _utcnow_iso())
    trace_id: Optional[str] = None
    task_id: Optional[str] = None
    event_type: EventKind = EventKind.MESSAGE_RECEIVED
    risk_level: Optional[RiskLevel] = None
    actor_type: str = Field(default="system", min_length=1, max_length=64)
    component: str = Field(default="paios_ce", min_length=1, max_length=128)
    outcome: str = Field(default="ok", min_length=1, max_length=64)
    redacted_details: Dict[str, Any] = Field(default_factory=dict)
