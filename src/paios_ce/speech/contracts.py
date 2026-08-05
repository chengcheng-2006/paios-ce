"""Typed public contracts for the local speech capability (Phase 9A).

All models use ``extra="forbid"``. Absolute source paths must never enter
audit events or error messages; the result may expose only a safe source
label (basename). Transcript text is returned to the calling CLI user but is
never placed in an AuditEvent by default.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

SpeechDevice = Literal["cpu", "cuda", "auto"]


class TranscriptionRequest(BaseModel):
    """A single local-file transcription request.

    ``source`` is the local audio file path as provided by the caller. It is
    validated by ``AudioInputPolicy`` and never logged verbatim; audit and
    errors carry only ``safe_source_label`` (basename).
    """

    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, max_length=4096)
    model: str = Field(default="tiny", min_length=1, max_length=256)
    language: Optional[str] = Field(default=None, min_length=1, max_length=16)
    device: SpeechDevice = "cpu"
    compute_type: str = Field(default="int8", min_length=1, max_length=32)
    vad_filter: bool = True
    local_files_only: bool = True
    word_timestamps: bool = False


class TranscriptionSegment(BaseModel):
    """One transcribed segment with floating timestamps."""

    model_config = ConfigDict(extra="forbid")

    start: float = Field(ge=0.0)
    end: float = Field(ge=0.0)
    text: str = ""


class TranscriptionInfo(BaseModel):
    """Detected-language and duration metadata from the model."""

    model_config = ConfigDict(extra="forbid")

    language: Optional[str] = None
    language_probability: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    duration_seconds: Optional[float] = Field(default=None, ge=0.0)
    duration_after_vad_seconds: Optional[float] = Field(default=None, ge=0.0)


class TranscriptionResult(BaseModel):
    """Structured result of a successful local transcription.

    ``safe_source_label`` is the basename of the source file only. The full
    absolute path is intentionally absent from the public result.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["success"] = "success"
    text: str = ""
    language: Optional[str] = None
    language_probability: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    duration_seconds: Optional[float] = Field(default=None, ge=0.0)
    duration_after_vad_seconds: Optional[float] = Field(default=None, ge=0.0)
    segments: List[TranscriptionSegment] = Field(default_factory=list)
    model: str = ""
    device: str = "cpu"
    compute_type: str = "int8"
    safe_source_label: str = ""


class SpeechRuntimeConfig(BaseModel):
    """Effective runtime configuration for the speech capability.

    Defaults are privacy-first: disabled, local-files-only, read-only input,
    no audio copy, no transcript persistence and no transcript audit.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    local_files_only: bool = True
    retain_audio: bool = False
    persist_transcript: bool = False
    audit_transcript: bool = False
    max_file_size_mb: int = Field(default=100, ge=1, le=10240)
    max_duration_seconds: int = Field(default=3600, ge=1, le=86400)
    allowed_extensions: List[str] = Field(
        default_factory=lambda: ["wav", "mp3", "m4a", "flac", "ogg", "opus", "webm"]
    )
    vad_filter: bool = True
    device: SpeechDevice = "cpu"
    compute_type: str = "int8"
    default_model: str = "tiny"


class AudioInputPolicy(BaseModel):
    """Static input-policy parameters for a local audio file.

    Mirrors ``SpeechRuntimeConfig`` limits but is validated independently so
    the policy object can be tested without a full runtime config.
    """

    model_config = ConfigDict(extra="forbid")

    allowed_extensions: List[str] = Field(
        default_factory=lambda: ["wav", "mp3", "m4a", "flac", "ogg", "opus", "webm"]
    )
    max_file_size_mb: int = Field(default=100, ge=1, le=10240)
    max_duration_seconds: int = Field(default=3600, ge=1, le=86400)
