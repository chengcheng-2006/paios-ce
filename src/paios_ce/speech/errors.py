"""Stable structured error codes for the local speech capability (Phase 9A).

Errors carry a stable machine-readable code and a redacted human message.
Absolute source paths never appear in messages; only ``safe_source_label``
(basename) is allowed.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

from enum import Enum
from typing import Optional


class SpeechErrorCode(str, Enum):
    """Stable error codes for the ``paios-ce transcribe`` command and service."""

    E_SPEECH_DISABLED = "E_SPEECH_DISABLED"
    E_SPEECH_PERMISSION_DENIED = "E_SPEECH_PERMISSION_DENIED"
    E_SPEECH_DEPENDENCY_MISSING = "E_SPEECH_DEPENDENCY_MISSING"
    E_SPEECH_MODEL_NOT_AVAILABLE_OFFLINE = "E_SPEECH_MODEL_NOT_AVAILABLE_OFFLINE"
    E_AUDIO_FILE_NOT_FOUND = "E_AUDIO_FILE_NOT_FOUND"
    E_AUDIO_TYPE_NOT_ALLOWED = "E_AUDIO_TYPE_NOT_ALLOWED"
    E_AUDIO_TOO_LARGE = "E_AUDIO_TOO_LARGE"
    E_AUDIO_DURATION_LIMIT = "E_AUDIO_DURATION_LIMIT"
    E_AUDIO_DECODE_FAILED = "E_AUDIO_DECODE_FAILED"
    E_TRANSCRIPTION_FAILED = "E_TRANSCRIPTION_FAILED"


# Stable CLI exit-code mapping (keeps the existing paios-ce exit-code
# contract: 0 ok / 2 usage / 3 config / 4 denied / 5 blocked / 6 internal).
_SPEECH_EXIT_CODES = {
    SpeechErrorCode.E_SPEECH_DISABLED: 4,
    SpeechErrorCode.E_SPEECH_PERMISSION_DENIED: 4,
    SpeechErrorCode.E_SPEECH_DEPENDENCY_MISSING: 6,
    SpeechErrorCode.E_SPEECH_MODEL_NOT_AVAILABLE_OFFLINE: 6,
    SpeechErrorCode.E_AUDIO_FILE_NOT_FOUND: 2,
    SpeechErrorCode.E_AUDIO_TYPE_NOT_ALLOWED: 2,
    SpeechErrorCode.E_AUDIO_TOO_LARGE: 2,
    SpeechErrorCode.E_AUDIO_DURATION_LIMIT: 2,
    SpeechErrorCode.E_AUDIO_DECODE_FAILED: 6,
    SpeechErrorCode.E_TRANSCRIPTION_FAILED: 6,
}


def _default_exit_code(code: SpeechErrorCode) -> int:
    return _SPEECH_EXIT_CODES.get(code, 6)


class SpeechError(Exception):
    """A speech-capability error with a stable code and redacted message.

    ``safe_source_label`` is the basename of the source file when known; it is
    never an absolute path. ``exit_code`` defaults to the stable mapping so
    the CLI preserves its documented exit-code contract.
    """

    def __init__(
        self,
        code: SpeechErrorCode,
        message: str,
        *,
        safe_source_label: Optional[str] = None,
        exit_code: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.safe_source_label = safe_source_label
        self.exit_code = exit_code if exit_code is not None else _default_exit_code(code)

    def to_dict(self) -> dict:
        payload = {
            "error_code": self.code.value,
            "message": self.message,
            "exit_code": self.exit_code,
        }
        if self.safe_source_label:
            payload["safe_source_label"] = self.safe_source_label
        return payload
