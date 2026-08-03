"""Enums for the PAIOS CE Task/Action protocol (Phase 2 parity).

Values follow the Phase 2 JSON Schemas and the TASK_AND_ACTION_PROTOCOL.md
structural contracts. Risk/action taxonomy used by the Permission/Risk engine
matches ACTION_RISK_TAXONOMY.csv and the Phase 3 execution prompt.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from enum import Enum


class TaskRiskLevel(str, Enum):
    """Task envelope risk level (lowercase, Phase 2 schema parity)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNAVAILABLE = "unavailable"


class RiskLevel(str, Enum):
    """Engine risk level used by the Permission/Risk engine (uppercase).

    NOT_APPLICABLE marks decisions that carry no actionable risk — most notably
    the explicit UNKNOWN_ACTION rejection (Phase 3R-R1). It is never an
    actionable risk tier and never licenses execution.
    """

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Capability(str, Enum):
    """Provider capability enum (MODEL_PROVIDER_CONTRACT, Phase 2 schema)."""

    TEXT_CHAT = "TEXT_CHAT"
    REASONING = "REASONING"
    TOOL_CALLING = "TOOL_CALLING"
    STRUCTURED_OUTPUT = "STRUCTURED_OUTPUT"
    VISION = "VISION"
    AUDIO_INPUT = "AUDIO_INPUT"
    EMBEDDING = "EMBEDDING"
    RERANKING = "RERANKING"
    LONG_CONTEXT = "LONG_CONTEXT"
    STREAMING = "STREAMING"
    LOCAL_INFERENCE = "LOCAL_INFERENCE"


class ActionOrigin(str, Enum):
    """TaskEnvelope.origin (Phase 2 schema)."""

    VOICE = "voice"
    TEXT = "text"
    WEB = "web"
    CLI = "cli"
    WEBHOOK = "webhook"


class ApprovalState(str, Enum):
    """TaskEnvelope.approval_state (Phase 2 schema)."""

    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    TIMEOUT = "timeout"


class WorkerType(str, Enum):
    """ActionRequest.worker_type (Phase 2 schema)."""

    TOOL = "tool"
    LOCAL_LLM = "local_llm"
    LOCAL_ASR = "local_asr"
    IO_BOUNDED = "io_bounded"
    COMPUTE_BOUNDED = "compute_bounded"


class FsScopeMode(str, Enum):
    """ActionRequest.filesystem_scope.mode (Phase 2 schema)."""

    NONE = "none"
    READ = "read"
    WRITE = "write"
    READ_WRITE = "read_write"


class NetworkScopeMode(str, Enum):
    """ActionRequest.network_scope.mode (Phase 2 schema)."""

    NONE = "none"
    LOOPBACK = "loopback"
    CLOUD_EGRESS = "cloud_egress"


class ActionStatus(str, Enum):
    """ActionResult.status (Phase 2 schema)."""

    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"
    TIMEOUT = "timeout"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"


class RollbackStatus(str, Enum):
    """ActionResult.rollback_status (Phase 2 schema)."""

    NOT_REQUIRED = "not_required"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"


class ErrorClass(str, Enum):
    """ErrorEnvelope.error_class (Phase 2 schema)."""

    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXCEEDED = "quota_exceeded"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    SCOPE_VIOLATION = "scope_violation"
    PERMISSION_DENIED = "permission_denied"
    SIGNATURE_INVALID = "signature_invalid"
    REPLAY_DETECTED = "replay_detected"
    CONFIRMATION_TIMEOUT = "confirmation_timeout"
    CONFIRMATION_TOKEN_MISMATCH = "confirmation_token_mismatch"
    TEMP_AUDIO_DELETE_FAILED = "temp_audio_delete_failed"
    AUDIT_WRITE_FAILED = "audit_write_failed"
    INTERNAL = "internal"


class TaskStatus(str, Enum):
    """TaskResult.status (TASK_AND_ACTION_PROTOCOL section 7)."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"
    DENIED = "denied"
    TIMEOUT = "timeout"


class EventKind(str, Enum):
    """AuditEvent.event_type (TASK_AND_ACTION_PROTOCOL section 9)."""

    MESSAGE_RECEIVED = "message_received"
    IDENTITY_DENIED = "identity_denied"
    SIGNATURE_INVALID = "signature_invalid"
    REPLAY_DETECTED = "replay_detected"
    AUDIO_REJECTED = "audio_rejected"
    ACTION_COMPLETED = "action_completed"
    ACTION_DENIED = "action_denied"
    UNKNOWN_ACTION_REJECTED = "unknown_action_rejected"
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"
    APPROVAL_TIMEOUT = "approval_timeout"
    ROUTING_DECISION = "routing_decision"
    CREDENTIAL_REVOKED = "credential_revoked"
    TEMP_AUDIO_DELETE_FAILED = "temp_audio_delete_failed"
    HEALTH_EVENT = "health_event"
    AUDIT_WRITE_FAILED = "audit_write_failed"


class CostClass(str, Enum):
    """Advisory cost class (TaskPlan / ActionResult.usage)."""

    FREE = "free"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ConfirmationKind(str, Enum):
    """High-risk confirmation kind (HIGH_RISK_CONFIRMATION_POLICY.yaml)."""

    NONE = "none"
    CHANNEL_PROMPT = "channel_prompt"
    OWNER_APPROVAL = "owner_approval"
