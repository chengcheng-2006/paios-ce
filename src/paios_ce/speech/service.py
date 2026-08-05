"""SpeechService — orchestration for the local speech capability (Phase 9A).

Flow for one transcription:

    local audio file
    → AudioFileValidator (policy)
    → capability check (SPEECH_TRANSCRIBE_LOCAL)
    → SpeechToTextAdapter
    → typed TranscriptionResult
    → metadata-only AuditEvent

Privacy guarantees enforced here:

- transcript text is returned to the caller but is never placed in the
  AuditEvent (``audit_transcript`` defaults to false);
- absolute source path is never placed in the AuditEvent (only
  ``safe_source_label`` basename);
- no raw audio is copied or persisted;
- model-cache absolute paths never appear in audit or error messages.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from ..audit import RedactedAuditLogger
from ..protocols import EventKind, RiskLevel
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
    """

    def __init__(
        self,
        runtime_config: Optional[SpeechRuntimeConfig] = None,
        adapter: Optional[SpeechToTextAdapter] = None,
        audit_logger: Optional[RedactedAuditLogger] = None,
        validator: Optional[AudioFileValidator] = None,
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

    # -- public API --------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    def transcribe(self, request: TranscriptionRequest) -> TranscriptionResult:
        """Validate, authorize, transcribe, and audit one local audio file."""
        label = safe_source_label(request.source)

        if not self._config.enabled:
            self._audit_event("denied", label, None,
                              error_code=SpeechErrorCode.E_SPEECH_DISABLED)
            raise SpeechError(
                SpeechErrorCode.E_SPEECH_DISABLED,
                "speech capability is disabled",
                safe_source_label=label,
            )

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
