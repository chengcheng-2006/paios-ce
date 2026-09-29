"""paios_ce.speech — local speech-to-text capability (Phase 9A).

The first admitted speech capability accepts one existing local audio file and
returns typed text plus structured segments. It does not listen to a
microphone, receive channel messages, store raw audio, or send text
externally. The default path is local-files-only and disabled by default.

Package layout:
  contracts.py              typed public models (extra="forbid")
  errors.py                 stable structured error codes
  policy.py                 audio input policy (read-only, size/duration/type)
  base.py                   SpeechToTextAdapter contract
  faster_whisper_adapter.py optional faster-whisper adapter (lazy import)
  service.py                orchestration: policy -> capability -> adapter -> audit

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

from .contracts import (
    AudioInputPolicy,
    SpeechRuntimeConfig,
    TranscriptionInfo,
    TranscriptionRequest,
    TranscriptionResult,
    TranscriptionSegment,
)
from .errors import SpeechError, SpeechErrorCode
from .service import SpeechService

__all__ = [
    "AudioInputPolicy",
    "SpeechError",
    "SpeechErrorCode",
    "SpeechRuntimeConfig",
    "SpeechService",
    "TranscriptionInfo",
    "TranscriptionRequest",
    "TranscriptionResult",
    "TranscriptionSegment",
]
