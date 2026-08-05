"""Phase 9A — speech contract model tests.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from paios_ce.speech.contracts import (
    AudioInputPolicy,
    SpeechRuntimeConfig,
    TranscriptionRequest,
    TranscriptionResult,
    TranscriptionSegment,
)


def test_transcription_request_defaults():
    req = TranscriptionRequest(source="sample.wav")
    assert req.model == "tiny"
    assert req.language is None
    assert req.device == "cpu"
    assert req.compute_type == "int8"
    assert req.vad_filter is True
    assert req.local_files_only is True
    assert req.word_timestamps is False


def test_transcription_request_rejects_extra_fields():
    with pytest.raises(ValidationError):
        TranscriptionRequest(source="sample.wav", transcript="leak")


def test_transcription_request_rejects_empty_source():
    with pytest.raises(ValidationError):
        TranscriptionRequest(source="")


def test_transcription_request_rejects_bad_device():
    with pytest.raises(ValidationError):
        TranscriptionRequest(source="sample.wav", device="gpu")


def test_transcription_segment_rounds_and_validates():
    seg = TranscriptionSegment(start=0.0, end=1.25, text="hello")
    assert seg.start == 0.0
    assert seg.end == 1.25
    with pytest.raises(ValidationError):
        TranscriptionSegment(start=-1.0, end=1.0, text="x")


def test_transcription_result_minimal_fields():
    result = TranscriptionResult()
    assert result.status == "success"
    assert result.text == ""
    assert result.segments == []
    assert result.device == "cpu"
    assert result.compute_type == "int8"
    assert result.safe_source_label == ""


def test_transcription_result_rejects_extra_fields():
    with pytest.raises(ValidationError):
        TranscriptionResult(text="x", absolute_path="C:\\secret.wav")


def test_transcription_result_rejects_negative_duration():
    with pytest.raises(ValidationError):
        TranscriptionResult(duration_seconds=-1.0)


def test_speech_runtime_config_privacy_defaults():
    cfg = SpeechRuntimeConfig()
    assert cfg.enabled is False
    assert cfg.local_files_only is True
    assert cfg.retain_audio is False
    assert cfg.persist_transcript is False
    assert cfg.audit_transcript is False
    assert cfg.max_file_size_mb == 100
    assert cfg.max_duration_seconds == 3600
    assert "wav" in cfg.allowed_extensions
    assert cfg.device == "cpu"
    assert cfg.compute_type == "int8"


def test_audio_input_policy_allowlist_default():
    policy = AudioInputPolicy()
    assert policy.allowed_extensions == [
        "wav", "mp3", "m4a", "flac", "ogg", "opus", "webm",
    ]
    assert policy.max_file_size_mb == 100
    assert policy.max_duration_seconds == 3600


def test_audio_input_policy_rejects_extra_fields():
    with pytest.raises(ValidationError):
        AudioInputPolicy(max_file_size_mb=100, raw_audio="bytes")
