"""SpeechService — orchestration for the local speech capability (Phase 9A).

Flow for one transcription:

    local audio file
    → capability/permission decision (PermissionEngine)
    → AudioFileValidator (policy)
    → SpeechToTextAdapter
    → typed TranscriptionResult
    → metadata-only AuditEvent

Privacy guarantees enforced here:

- transcript text is returned to the caller but is never placed in the
  AuditEvent (``audit_transcript`` defaults to false);
- absolute source path is never placed in the AuditEvent (only
  ``safe_source_label`` basename);
- no raw audio is copied or persisted;
- model-cache absolute paths never appear in audit or error messages;
- permission decision and risk level are present in audit evidence.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Set

from ..audit import RedactedAuditLogger
from ..permissions import Decision, PermissionEngine
from ..protocols import ActionRequest, EventKind, FsScopeMode, NetworkScopeMode, RiskLevel
from .base import SpeechToTextAdapter
from .contracts import (
    AudioInputPolicy,
    SpeechRuntimeConfig,
    TranscriptionRequest,
    TranscriptionResult,
)
from .errors import SpeechError, SpeechErrorCode
from .policy import AudioFileValidator, safe_source_label

#: Capability id registered for this operation (Phase 9A contract).
SPEECH_CAPABILITY_ID = "SPEECH_TRANSCRIBE_LOCAL"
SPEECH_OPERATION = "speech.transcribe_local"


class SpeechService:
    """Admits and orchestrates local-file transcription.

    ``runtime_config`` supplies effective defaults (enabled, limits,
    local_files_only, ...). ``adapter`` is the speech backend (real
    faster-whisper or a test fake). ``audit_logger`` is optional; when
    provided, one metadata-only AuditEvent is emitted per attempt (success or
    failure).

    ``permission_engine`` (optional) is the existing
    :class:`~paios_ce.permissions.PermissionEngine`; when provided, every
    transcription passes a fail-closed capability/owner decision *before*
    the adapter or model is constructed. ``principal_id`` and
    ``owner_allowlist`` are used only to build that gate. When no engine is
    provided (unit-level adapter tests), the gate is skipped.
    """

    def __init__(
        self,
        runtime_config: Optional[SpeechRuntimeConfig] = None,
        adapter: Optional[SpeechToTextAdapter] = None,
        audit_logger: Optional[RedactedAuditLogger] = None,
        validator: Optional[AudioFileValidator] = None,
        permission_engine: Optional[PermissionEngine] = None,
        principal_id: str = "principal:example.invalid/user-1",
        owner_allowlist: Sequence[str] = ("principal:example.invalid/owner-1",),
    ) -> None:
        self._config = runtime_config or SpeechRuntimeConfig()
        self._adapter = adapter
        self._audit = audit_logger
        self._validator = validator or AudioFileValidator(
            AudioInputPolicy(
                allowed_extensions=self._config.allowed_extensions,
                max_file_size_mb=self._config.max_file_size_mb,
                max_duration_seconds=self._config.max_duration_seconds,
            )
        )
        self._permission_engine = permission_engine
        self._principal_id = principal_id
        self._owner_allowlist = list(owner_allowlist)
        self._last_permission: Optional[Dict[str, str]] = None

    # -- public API --------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    @property
    def last_permission(self) -> Optional[Dict[str, str]]:
        """Last permission decision evidence (decision + risk + reason)."""
        return self._last_permission

    def transcribe(self, request: TranscriptionRequest) -> TranscriptionResult:
        """Authorize, validate, transcribe, and audit one local audio file.

        The permission decision occurs before any adapter/model construction.
        """
        label = safe_source_label(request.source)

        if not self._config.enabled:
            self._audit_event("denied", label, None,
                              error_code=SpeechErrorCode.E_SPEECH_DISABLED)
            raise SpeechError(
                SpeechErrorCode.E_SPEECH_DISABLED,
                "speech capability is disabled",
                safe_source_label=label,
            )

        self._authorize(label)

        self._validator.validate(request.source)
        file_size_bytes = self._file_size_of(request.source)

        if self._adapter is None:
            self._audit_event("denied", label, None,
                              error_code=SpeechErrorCode.E_SPEECH_DEPENDENCY_MISSING)
            raise SpeechError(
                SpeechErrorCode.E_SPEECH_DEPENDENCY_MISSING,
                "speech dependency missing: install the 'speech' extra (faster-whisper)",
                safe_source_label=label,
            )

        try:
            result = self._adapter.transcribe(request)
        except SpeechError as exc:
            self._audit_event("failed", label, None, error_code=exc.code)
            raise

        self._audit_event(
            "ok",
            label,
            result,
            file_size_bytes=file_size_bytes,
        )
        return result

    # -- permission gate ---------------------------------------------------

    def _authorize(self, label: str) -> None:
        """Fail-closed capability/owner decision before model construction.

        Uses the existing :class:`PermissionEngine`; no parallel policy system
        is introduced. The operation is classified READ_LOCAL / LOW and is
        owner-gated: the caller must be in the owner allowlist (enforced
        here, since READ_LOCAL policy is not owner_only by itself) and must
        hold the SPEECH_TRANSCRIBE_LOCAL capability (enforced by the engine).
        """
        if self._permission_engine is None:
            return  # adapter-level unit tests without a gate

        # Owner-only local CLI rule: the caller must be an allowlisted owner.
        if self._principal_id not in self._owner_allowlist:
            self._last_permission = {
                "decision": "deny",
                "risk_level": "LOW",
                "reason": "caller not in owner allowlist",
                "hard_blocked": "false",
            }
            self._audit_event("denied", label, None,
                              error_code=SpeechErrorCode.E_SPEECH_PERMISSION_DENIED)
            raise SpeechError(
                SpeechErrorCode.E_SPEECH_PERMISSION_DENIED,
                "speech permission denied: caller not in owner allowlist",
                safe_source_label=label,
            )

        request = ActionRequest(
            action_id="speech_" + label.replace(".", "_")[:48],
            worker_type="local_asr",
            operation=SPEECH_OPERATION,
            parameters={},
            required_permissions=[SPEECH_CAPABILITY_ID],
            filesystem_scope={"mode": FsScopeMode.READ.value, "paths_class": []},
            network_scope={"mode": NetworkScopeMode.NONE.value, "endpoints_class": []},
            timeout=30,
            idempotency_key="speech_" + label.replace(".", "_")[:48],
            rollback_supported=False,
            approval_required=False,
        )
        result = self._permission_engine.authorize(request)
        self._last_permission = {
            "decision": result.decision.value,
            "risk_level": result.risk_level.value if result.risk_level else "LOW",
            "reason": result.reason,
            "hard_blocked": str(result.hard_blocked).lower(),
        }
        if result.decision != Decision.ALLOW:
            self._audit_event("denied", label, None,
                              error_code=SpeechErrorCode.E_SPEECH_PERMISSION_DENIED)
            raise SpeechError(
                SpeechErrorCode.E_SPEECH_PERMISSION_DENIED,
                "speech permission denied",
                safe_source_label=label,
            )

    # -- audit -------------------------------------------------------------

    def _audit_event(
        self,
        outcome: str,
        label: str,
        result: Optional[TranscriptionResult],
        error_code: Optional[SpeechErrorCode] = None,
        file_size_bytes: Optional[int] = None,
    ) -> None:
        """Emit a metadata-only AuditEvent.

        Forbidden fields (transcript, segment text, raw audio, absolute source
        path, model-cache path, secret values) are structurally absent.
        """
        if self._audit is None:
            return
        details: Dict[str, Any] = {
            "capability_id": SPEECH_CAPABILITY_ID,
            "operation": SPEECH_OPERATION,
            "outcome": outcome,
            "safe_source_label": label,
        }
        if self._last_permission is not None:
            details["permission_decision"] = self._last_permission["decision"]
            details["risk_level"] = self._last_permission["risk_level"]
        if file_size_bytes is not None:
            details["file_size_bytes"] = file_size_bytes
        if result is not None:
            details["duration_seconds"] = result.duration_seconds
            details["language"] = result.language
            details["segment_count"] = len(result.segments)
            details["model_label"] = result.model
            details["device"] = result.device
            details["compute_type"] = result.compute_type
        if error_code is not None:
            details["error_code"] = error_code.value
        event = self._audit.make_event(
            EventKind.ACTION_COMPLETED if outcome == "ok" else EventKind.AUDIO_REJECTED,
            risk_level=RiskLevel.LOW,
            actor_type="system",
            component="paios_ce.speech",
            outcome=outcome,
            redacted=details,
        )
        self._audit.emit(event)

    @staticmethod
    def _file_size_of(source: str) -> Optional[int]:
        """Read-only stat of the source file (no bytes are read into memory)."""
        try:
            return Path(source).resolve().stat().st_size
        except OSError:  # pragma: no cover - defensive
            return None
