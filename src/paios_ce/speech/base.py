"""SpeechToTextAdapter contract (Phase 9A).

An adapter turns one local audio file into a typed :class:`TranscriptionResult`.
Adapters must:

- be constructible without downloading model weights (local_files_only
  default true);
- raise stable :class:`SpeechError` codes instead of leaking internals;
- never expose absolute source paths or model-cache paths in messages;
- consume the full segment stream before returning.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .contracts import TranscriptionRequest, TranscriptionResult
from .errors import SpeechError, SpeechErrorCode


class SpeechToTextAdapter(ABC):
    """Abstract speech-to-text adapter."""

    @abstractmethod
    def transcribe(self, request: TranscriptionRequest) -> TranscriptionResult:
        """Transcribe one local audio file.

        ``request.source`` is the local file path. The returned result exposes
        only ``safe_source_label`` (basename); the absolute path never appears.
        """

    def _safe_label(self, request: TranscriptionRequest) -> str:
        from .policy import safe_source_label

        return safe_source_label(request.source)

    def _error(self, code: SpeechErrorCode, message: str,
               request: TranscriptionRequest) -> SpeechError:
        return SpeechError(code, message, safe_source_label=self._safe_label(request))


class ModelFactory:
    """Callable that builds a model object from a model identifier/path.

    ``model_size_or_path`` may be a model identifier (e.g. ``tiny``) or a
    local converted model directory. ``local_files_only`` forces the use of a
    local cache and prevents download.
    """

    def __call__(self, model_size_or_path: str, *, local_files_only: bool = True):
        raise NotImplementedError  # pragma: no cover - abstract
