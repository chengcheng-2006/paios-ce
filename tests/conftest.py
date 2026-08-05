"""Shared pytest fixtures for the PAIOS CE test suite.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

EXAMPLES = REPO_ROOT / "examples"
SCHEMAS = REPO_ROOT / "schemas"


@pytest.fixture
def public_example() -> Path:
    return EXAMPLES / "public_config.example.yaml"


@pytest.fixture
def private_example() -> Path:
    return EXAMPLES / "private_config.example.yaml"


@pytest.fixture
def demo_task_file() -> Path:
    return EXAMPLES / "demo_task.json"


@pytest.fixture
def schemas_dir() -> Path:
    return SCHEMAS


@pytest.fixture
def load_public_example(public_example):
    def _load():
        with open(public_example, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    return _load


@pytest.fixture
def load_private_example(private_example):
    def _load():
        with open(private_example, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    return _load


@pytest.fixture
def read_schema(schemas_dir):
    def _read(name: str) -> dict:
        with open(schemas_dir / name, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return _read


# ---------------------------------------------------------------------------
# Phase 9A Local ASR shared helpers (available to every test directory).
# ---------------------------------------------------------------------------


def write_small_wav(path: Path, *, size_bytes: int = 2048) -> Path:
    """Write a tiny placeholder WAV file (header + silence padding)."""
    # Minimal RIFF/WAVE header (44 bytes) + zero payload padded to size_bytes.
    header = bytearray(44)
    header[0:4] = b"RIFF"
    header[8:12] = b"WAVE"
    header[12:16] = b"fmt "
    header[16:20] = (16).to_bytes(4, "little")
    header[20:22] = (1).to_bytes(2, "little")  # PCM
    header[22:24] = (1).to_bytes(2, "little")  # mono
    header[24:28] = (8000).to_bytes(4, "little")  # sample rate
    header[28:32] = (8000).to_bytes(4, "little")  # byte rate
    header[32:34] = (1).to_bytes(2, "little")  # block align
    header[34:36] = (8).to_bytes(2, "little")  # bits per sample
    header[36:40] = b"data"
    payload = max(size_bytes - 44, 0)
    header[40:44] = (payload).to_bytes(4, "little")
    path.write_bytes(bytes(header) + b"\x00" * payload)
    return path


class FakeSegment:
    """Shape-compatible fake of a faster-whisper segment object."""

    def __init__(self, start: float, end: float, text: str) -> None:
        self.start = start
        self.end = end
        self.text = text


class FakeInfo:
    """Shape-compatible fake of a faster-whisper transcription info object."""

    def __init__(self, language="en", language_probability=0.95,
                 duration=3.2, duration_after_vad=3.0) -> None:
        self.language = language
        self.language_probability = language_probability
        self.duration = duration
        self.duration_after_vad = duration_after_vad


class FakeModel:
    """Fake faster-whisper model for deterministic tests (no weights)."""

    def __init__(self, *, text: str = "hello world", segments=None,
                 info=None, raise_on_transcribe: Exception | None = None) -> None:
        self.text = text
        self._segments = segments or [
            FakeSegment(0.0, 1.2, "hello"),
            FakeSegment(1.2, 3.0, "world"),
        ]
        self._info = info or FakeInfo()
        self._raise_on_transcribe = raise_on_transcribe
        self.transcribe_calls: list[dict] = []

    def transcribe(self, source, language=None, vad_filter=True, word_timestamps=False):
        self.transcribe_calls.append({
            "source": source,
            "language": language,
            "vad_filter": vad_filter,
            "word_timestamps": word_timestamps,
        })
        if self._raise_on_transcribe is not None:
            raise self._raise_on_transcribe
        return iter(self._segments), self._info


def make_fake_model_factory(model):
    """Return a ModelFactory callable returning ``model``."""

    def factory(model_size_or_path: str, *, local_files_only: bool = True):
        return model

    return factory


@pytest.fixture
def fake_model() -> FakeModel:
    return FakeModel()


@pytest.fixture
def fake_model_factory(fake_model):
    return make_fake_model_factory(fake_model)
