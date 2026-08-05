"""Audio input policy for the local speech capability (Phase 9A).

The policy validates a local audio file before any model work:

- the file must exist and be a regular file (read-only inspection);
- the extension must be allowlisted;
- the file size must be within ``max_file_size_mb``;
- the duration (when a decoder is available) must be within
  ``max_duration_seconds``;
- no audio copy, no temporary persistence, no raw bytes in logs;
- symbolic links are resolved for size checks; the source file is opened
  read-only by the adapter.

Duration inspection uses the same optional PyAV decoder boundary as the
faster-whisper adapter (never a second unsafe decoder path). When the
optional decoder is not installed the duration check is skipped and the
adapter reports E_SPEECH_DEPENDENCY_MISSING instead.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .contracts import AudioInputPolicy
from .errors import SpeechError, SpeechErrorCode

#: Extension allowlist (lowercase, no leading dot) mirroring the contract.
DEFAULT_ALLOWED_EXTENSIONS = ["wav", "mp3", "m4a", "flac", "ogg", "opus", "webm"]


def safe_source_label(source: str) -> str:
    """Return only the basename of a source path (never an absolute path).

    Handles both POSIX (``/``) and Windows (``\\``) separators so the same
    code behaves identically on Windows and Ubuntu CI.
    """
    if not isinstance(source, str) or not source:
        return "audio"
    # Strip any trailing separators first so a bare separator yields "audio".
    text = source.rstrip("/\\")
    # POSIX: Path(...).name handles "/" natively.
    name = Path(text).name
    # Windows separators: Path on a POSIX host does not split on "\\".
    if "\\" in name:
        name = name.split("\\")[-1]
    return name if name else "audio"


class AudioFileValidator:
    """Validates a local audio file against an :class:`AudioInputPolicy`.

    The validator never opens the file for writing and never copies audio. It
    performs stat-based checks (existence, regular file, size) and an
    extension check, then optionally a duration check through a decoder
    factory (default: PyAV, the same optional dependency boundary used by the
    faster-whisper adapter).
    """

    def __init__(self, policy: Optional[AudioInputPolicy] = None) -> None:
        self._policy = policy or AudioInputPolicy()

    @property
    def policy(self) -> AudioInputPolicy:
        return self._policy

    def validate(self, source: str) -> None:
        """Raise a stable :class:`SpeechError` if the file is not admissible."""
        label = safe_source_label(source)
        path = Path(source)

        if not path.exists():
            raise SpeechError(
                SpeechErrorCode.E_AUDIO_FILE_NOT_FOUND,
                "audio file not found",
                safe_source_label=label,
            )
        if not path.is_file():
            raise SpeechError(
                SpeechErrorCode.E_AUDIO_FILE_NOT_FOUND,
                "audio path is not a regular file",
                safe_source_label=label,
            )

        ext = path.suffix.lower().lstrip(".")
        allowed = [e.lower().lstrip(".") for e in self._policy.allowed_extensions]
        if ext not in allowed:
            raise SpeechError(
                SpeechErrorCode.E_AUDIO_TYPE_NOT_ALLOWED,
                f"audio type not allowed (extension not in allowlist)",
                safe_source_label=label,
            )

        # Resolve symlinks so the size check applies to the real file.
        try:
            resolved = path.resolve()
            size_bytes = resolved.stat().st_size
        except OSError as exc:  # pragma: no cover - defensive
            raise SpeechError(
                SpeechErrorCode.E_AUDIO_DECODE_FAILED,
                "cannot stat audio file",
                safe_source_label=label,
            ) from exc

        max_bytes = self._policy.max_file_size_mb * 1024 * 1024
        if size_bytes > max_bytes:
            raise SpeechError(
                SpeechErrorCode.E_AUDIO_TOO_LARGE,
                f"audio file exceeds max size ({self._policy.max_file_size_mb} MB)",
                safe_source_label=label,
            )

        # Duration check via the same optional decoder boundary. If the
        # decoder is unavailable, leave the duration check to the adapter's
        # dependency-missing error (no second unsafe decoder path).
        duration = self._probe_duration(path)
        if duration is not None and duration > self._policy.max_duration_seconds:
            raise SpeechError(
                SpeechErrorCode.E_AUDIO_DURATION_LIMIT,
                f"audio duration exceeds limit ({self._policy.max_duration_seconds}s)",
                safe_source_label=label,
            )

    def _probe_duration(self, path: Path) -> Optional[float]:
        """Return the audio duration in seconds, or None when undecodable.

        Uses the optional ``av`` (PyAV) decoder only — the same dependency
        boundary as the faster-whisper adapter. Never falls back to a second
        unsafe decoder path.
        """
        try:
            import av  # type: ignore[import-not-found]  # optional dependency
        except ImportError:
            return None
        try:
            with av.open(str(path)) as container:
                duration_us = container.duration
                if duration_us is None:
                    return None
                return duration_us / 1_000_000.0
        except Exception:
            # Decode failure maps to the stable decode error at the adapter
            # layer; policy does not need to re-raise here.
            return None


def validate_audio_input(source: str, policy: Optional[AudioInputPolicy] = None) -> None:
    """Convenience wrapper around :class:`AudioFileValidator`."""
    AudioFileValidator(policy).validate(source)
