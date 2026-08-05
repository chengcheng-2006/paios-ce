"""Faster-whisper adapter for the local speech capability (Phase 9A).

Design requirements:

- lazy optional import: ``faster_whisper`` is imported only when the adapter
  is actually used, so the base package works without the ``speech`` extra;
- dependency injection / model factory hook: tests inject a fake model so no
  weights are downloaded;
- ``local_files_only`` default true: no implicit model download;
- CPU ``int8`` is the reference release-gated mode;
- VAD is configurable;
- the segment generator is fully consumed before returning;
- model/download/decode errors map to stable public error codes;
- no auth token or model-cache path is ever exposed in messages.

The adapter is validated against the public faster-whisper 1.x API
(``WhisperModel(model_size_or_path, device=..., compute_type=...,
local_files_only=...)`` and ``model.transcribe(path, language=...,
vad_filter=..., word_timestamps=...)`` returning ``(segments_generator,
info)``).

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .base import ModelFactory, SpeechToTextAdapter
from .contracts import (
    TranscriptionInfo,
    TranscriptionRequest,
    TranscriptionResult,
    TranscriptionSegment,
)
from .errors import SpeechError, SpeechErrorCode

#: Stable model label used in audit metadata when a local path is supplied.
_LOCAL_MODEL_LABEL = "local"


class FasterWhisperAdapter(SpeechToTextAdapter):
    """Adapter around the optional ``faster_whisper`` package.

    ``model_factory`` may be injected for tests (a callable with the same
    signature as ``faster_whisper.WhisperModel``). When omitted, the real
    ``WhisperModel`` is imported lazily on first use.
    """

    def __init__(
        self,
        *,
        model_factory: Optional[ModelFactory] = None,
        dependency_error_code: SpeechErrorCode = SpeechErrorCode.E_SPEECH_DEPENDENCY_MISSING,
    ) -> None:
        self._model_factory = model_factory
        self._dependency_error_code = dependency_error_code

    # -- model construction ------------------------------------------------

    def _build_model(self, request: TranscriptionRequest) -> Any:
        if self._model_factory is not None:
            return self._model_factory(
                request.model,
                local_files_only=request.local_files_only,
            )
        factory = self._real_model_factory()
        return factory(request.model, local_files_only=request.local_files_only)

    def _real_model_factory(self) -> ModelFactory:
        """Return a factory bound to the real (lazily imported) WhisperModel."""
        try:
            from faster_whisper import WhisperModel  # type: ignore[import-not-found]
        except ImportError as exc:
            raise SpeechError(
                self._dependency_error_code,
                "speech dependency missing: install the 'speech' extra (faster-whisper)",
                safe_source_label=None,
            ) from exc

        def _factory(model_size_or_path: str, *, local_files_only: bool = True) -> Any:
            return WhisperModel(
                model_size_or_path,
                device=self._device,
                compute_type=self._compute_type,
                local_files_only=local_files_only,
            )

        return _factory

    # -- request context ---------------------------------------------------

    @property
    def _device(self) -> str:
        return "cpu"

    @property
    def _compute_type(self) -> str:
        return "int8"

    # -- transcription -----------------------------------------------------

    def transcribe(self, request: TranscriptionRequest) -> TranscriptionResult:
        label = self._safe_label(request)
        try:
            model = self._build_model(request)
        except SpeechError:
            raise
        except Exception as exc:
            # Model construction failure (download blocked, corrupt cache,
            # unsupported device) maps to the stable offline error. The
            # message must not contain absolute cache paths.
            raise SpeechError(
                SpeechErrorCode.E_SPEECH_MODEL_NOT_AVAILABLE_OFFLINE,
                "speech model not available offline",
                safe_source_label=label,
            ) from exc

        try:
            segments, info = model.transcribe(
                request.source,
                language=request.language,
                vad_filter=request.vad_filter,
                word_timestamps=request.word_timestamps,
            )
            # Fully consume the generator; transcription runs to completion.
            segment_list = list(segments)
        except SpeechError:
            raise
        except Exception as exc:
            raise SpeechError(
                SpeechErrorCode.E_AUDIO_DECODE_FAILED,
                "audio decode failed",
                safe_source_label=label,
            ) from exc

        rounded = []
        for seg in segment_list:
            try:
                start = round(float(seg.start), 2)
                end = round(float(seg.end), 2)
            except (TypeError, ValueError):  # pragma: no cover - defensive
                start = 0.0
                end = 0.0
            rounded.append(
                TranscriptionSegment(start=start, end=end, text=str(seg.text or ""))
            )

        text = "".join(seg.text or "" for seg in segment_list).strip()
        info_model = self._as_info(info)

        return TranscriptionResult(
            text=text,
            language=info_model.language,
            language_probability=info_model.language_probability,
            duration_seconds=info_model.duration_seconds,
            duration_after_vad_seconds=info_model.duration_after_vad_seconds,
            segments=rounded,
            model=self._model_label(request),
            device=request.device,
            compute_type=request.compute_type,
            safe_source_label=label,
        )

    def _as_info(self, info: Any) -> TranscriptionInfo:
        try:
            language = getattr(info, "language", None)
            language_probability = getattr(info, "language_probability", None)
            duration = getattr(info, "duration", None)
            duration_after_vad = getattr(info, "duration_after_vad", None)
            return TranscriptionInfo(
                language=str(language) if language else None,
                language_probability=(
                    float(language_probability) if language_probability is not None else None
                ),
                duration_seconds=(float(duration) if duration is not None else None),
                duration_after_vad_seconds=(
                    float(duration_after_vad) if duration_after_vad is not None else None
                ),
            )
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return TranscriptionInfo()

    def _model_label(self, request: TranscriptionRequest) -> str:
        """A safe model label for audit metadata (never a cache path)."""
        model = (request.model or "").strip()
        if not model:
            return "unknown"
        if "/" in model or "\\" in model or model.endswith((".bin", ".ct2", ".model")):
            return _LOCAL_MODEL_LABEL
        return model
