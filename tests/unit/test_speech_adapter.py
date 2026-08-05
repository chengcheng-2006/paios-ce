"""Phase 9A 鈥?faster-whisper adapter tests (fake model, no network).

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import pytest

from paios_ce.speech.contracts import TranscriptionRequest
from paios_ce.speech.errors import SpeechError, SpeechErrorCode
from paios_ce.speech.faster_whisper_adapter import FasterWhisperAdapter

from conftest import (  # noqa: E402  (Phase 9A shared helpers)
    FakeInfo,
    FakeModel,
    FakeSegment,
    make_fake_model_factory,
)


def _request(**kw):
    defaults = dict(source="sample.wav", model="tiny", device="cpu",
                    compute_type="int8", vad_filter=True, local_files_only=True)
    defaults.update(kw)
    return TranscriptionRequest(**defaults)


def test_fake_model_success_result(fake_model):
    adapter = FasterWhisperAdapter(model_factory=make_fake_model_factory(fake_model))
    result = adapter.transcribe(_request())
    assert result.status == "success"
    assert result.text == "helloworld"
    assert len(result.segments) == 2
    assert result.language == "en"
    assert result.language_probability == 0.95
    assert result.duration_seconds == 3.2
    assert result.duration_after_vad_seconds == 3.0
    assert result.safe_source_label == "sample.wav"
    assert result.device == "cpu"
    assert result.compute_type == "int8"


def test_local_files_only_forwarded_to_factory(fake_model):
    calls = []

    def factory(model_size_or_path, *, local_files_only=True):
        calls.append((model_size_or_path, local_files_only))
        return fake_model

    adapter = FasterWhisperAdapter(model_factory=factory)
    adapter.transcribe(_request(local_files_only=True))
    assert calls == [("tiny", True)]


def test_vad_and_language_forwarded(fake_model):
    adapter = FasterWhisperAdapter(model_factory=make_fake_model_factory(fake_model))
    adapter.transcribe(_request(language="zh", vad_filter=False))
    call = fake_model.transcribe_calls[0]
    assert call["language"] == "zh"
    assert call["vad_filter"] is False


def test_word_timestamps_forwarded(fake_model):
    adapter = FasterWhisperAdapter(model_factory=make_fake_model_factory(fake_model))
    adapter.transcribe(_request(word_timestamps=True))
    assert fake_model.transcribe_calls[0]["word_timestamps"] is True


def test_segment_generator_fully_consumed():
    """The adapter must consume the generator (list()) before returning."""
    consumed = []

    class TrackingModel:
        def transcribe(self, source, language=None, vad_filter=True, word_timestamps=False):
            def gen():
                yield FakeSegment(0.0, 1.0, "a")
                consumed.append("consumed")
                yield FakeSegment(1.0, 2.0, "b")
            return gen(), FakeInfo()

    adapter = FasterWhisperAdapter(model_factory=make_fake_model_factory(TrackingModel()))
    result = adapter.transcribe(_request())
    assert consumed == ["consumed"]
    assert len(result.segments) == 2


def test_absolute_source_path_not_in_result(fake_model):
    adapter = FasterWhisperAdapter(model_factory=make_fake_model_factory(fake_model))
    result = adapter.transcribe(_request(source="D:\\data\\owner\\secret\\audio.wav"))
    dumped = result.model_dump()
    assert "D:\\data\\owner" not in str(dumped)
    assert result.safe_source_label == "audio.wav"


def test_dependency_missing_stable_error(monkeypatch):
    """When faster_whisper is not importable, a stable error is raised."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "faster_whisper":
            raise ImportError("no module named faster_whisper")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    adapter = FasterWhisperAdapter()  # no injected factory -> lazy real import
    with pytest.raises(SpeechError) as ei:
        adapter.transcribe(_request())
    assert ei.value.code == SpeechErrorCode.E_SPEECH_DEPENDENCY_MISSING


def test_lazy_import_keeps_base_usable_without_extra():
    """The module imports fine even when faster_whisper is absent."""
    import paios_ce.speech.faster_whisper_adapter as mod

    assert hasattr(mod, "FasterWhisperAdapter")


def test_model_construction_error_maps_to_offline(monkeypatch):
    def bad_factory(model_size_or_path, *, local_files_only=True):
        raise RuntimeError("download blocked")

    adapter = FasterWhisperAdapter(model_factory=bad_factory)
    with pytest.raises(SpeechError) as ei:
        adapter.transcribe(_request())
    assert ei.value.code == SpeechErrorCode.E_SPEECH_MODEL_NOT_AVAILABLE_OFFLINE


def test_decode_error_maps_to_stable_code():
    class RaisingModel:
        def transcribe(self, source, language=None, vad_filter=True, word_timestamps=False):
            raise RuntimeError("decode boom")

    adapter = FasterWhisperAdapter(model_factory=make_fake_model_factory(RaisingModel()))
    with pytest.raises(SpeechError) as ei:
        adapter.transcribe(_request())
    assert ei.value.code == SpeechErrorCode.E_AUDIO_DECODE_FAILED


def test_model_label_safe_for_local_path():
    class Recorder:
        def __init__(self):
            self.label = None

    adapter = FasterWhisperAdapter(model_factory=make_fake_model_factory(FakeModel()))
    # local path model -> "local" label, never the path
    result = adapter.transcribe(_request(model="D:\\models\\whisper-tiny-ct2"))
    assert result.model == "local"
    assert "C:\\models" not in result.model_dump().get("model", "")


def test_timestamps_rounded_consistently(fake_model):
    fake_model._segments = [FakeSegment(0.0, 1.234567, "x")]
    adapter = FasterWhisperAdapter(model_factory=make_fake_model_factory(fake_model))
    result = adapter.transcribe(_request())
    assert result.segments[0].end == 1.23
