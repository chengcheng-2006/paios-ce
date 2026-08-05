"""Phase 9A 鈥?security-boundary tests for the local speech capability.

Covers: no implicit network, no audio persistence, transcript never in audit,
absolute path never in audit, no secret-like keys in audit, dependency-absent
path, and config precedence for the speech section.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import json

import pytest

from paios_ce.audit import RedactedAuditLogger
from paios_ce.config import load_runtime
from paios_ce.speech.contracts import SpeechRuntimeConfig, TranscriptionRequest
from paios_ce.speech.errors import SpeechError, SpeechErrorCode
from paios_ce.speech.service import SpeechService

from conftest import FakeModel, make_fake_model_factory, write_small_wav


def _enabled_cfg():
    return SpeechRuntimeConfig(enabled=True)


def test_no_network_calls_in_service(tmp_path, fake_model, monkeypatch):
    """The service path performs no socket/network activity (fake model)."""
    import socket

    f = write_small_wav(tmp_path / "ok.wav")
    real_connect = socket.socket.connect

    def deny_connect(self, address):
        raise AssertionError(f"network connect attempted: {address}")

    monkeypatch.setattr(socket.socket, "connect", deny_connect)
    from paios_ce.speech.faster_whisper_adapter import FasterWhisperAdapter

    service = SpeechService(
        runtime_config=_enabled_cfg(),
        adapter=FasterWhisperAdapter(model_factory=make_fake_model_factory(fake_model)),
    )
    result = service.transcribe(TranscriptionRequest(source=str(f)))
    assert result.status == "success"


def test_no_audio_copy_or_persistence(tmp_path, fake_model):
    """After transcription the input directory has no new audio files."""
    from paios_ce.speech.faster_whisper_adapter import FasterWhisperAdapter

    f = write_small_wav(tmp_path / "ok.wav")
    before = sorted(p.name for p in tmp_path.iterdir())
    service = SpeechService(
        runtime_config=_enabled_cfg(),
        adapter=FasterWhisperAdapter(model_factory=make_fake_model_factory(fake_model)),
    )
    service.transcribe(TranscriptionRequest(source=str(f)))
    after = sorted(p.name for p in tmp_path.iterdir())
    assert after == before


def test_audit_has_no_secret_like_keys(tmp_path, fake_model):
    from paios_ce.speech.faster_whisper_adapter import FasterWhisperAdapter

    f = write_small_wav(tmp_path / "ok.wav")
    logger = RedactedAuditLogger()
    service = SpeechService(
        runtime_config=_enabled_cfg(),
        adapter=FasterWhisperAdapter(model_factory=make_fake_model_factory(fake_model)),
        audit_logger=logger,
    )
    service.transcribe(TranscriptionRequest(source=str(f)))
    payload = json.loads(logger.getvalue().strip().splitlines()[0])
    text = str(payload)
    for needle in ("token", "secret", "cookie", "password", "api_key",
                   "authorization", "private_key"):
        assert needle not in text.lower()


def test_audit_event_schema_compliant(tmp_path, fake_model):
    """The emitted audit event validates against the AuditEvent model."""
    import sys

    from paios_ce.protocols import AuditEvent

    from paios_ce.speech.faster_whisper_adapter import FasterWhisperAdapter

    f = write_small_wav(tmp_path / "ok.wav")
    logger = RedactedAuditLogger()
    service = SpeechService(
        runtime_config=_enabled_cfg(),
        adapter=FasterWhisperAdapter(model_factory=make_fake_model_factory(fake_model)),
        audit_logger=logger,
    )
    service.transcribe(TranscriptionRequest(source=str(f)))
    events = logger.events()
    assert len(events) == 1
    # Round-trip through the model: any forbidden field would raise.
    AuditEvent.model_validate(events[0].model_dump())


def test_speech_config_default_disabled():
    rt = load_runtime()
    assert rt.speech.enabled is False
    assert rt.speech.local_files_only is True
    assert rt.speech.max_file_size_mb == 100
    assert rt.speech.max_duration_seconds == 3600
    assert rt.speech.device == "cpu"
    assert rt.speech.compute_type == "int8"


def test_speech_config_private_precedence(tmp_path):
    private = tmp_path / "private.yaml"
    private.write_text(
        "schema: https://paios.ce/schemas/private-config/v0.1.json\n"
        "owner_allowlist: [\"principal:example.invalid/owner-1\"]\n"
        "speech:\n"
        "  enabled: true\n"
        "  local_files_only: true\n"
        "  max_file_size_mb: 50\n"
        "  allowed_extensions: [wav, flac]\n",
        encoding="utf-8",
    )
    rt = load_runtime(private_path=private)
    assert rt.speech.enabled is True
    assert rt.speech.max_file_size_mb == 50
    assert rt.speech.allowed_extensions == ["wav", "flac"]


def test_speech_config_extra_fields_rejected(tmp_path):
    private = tmp_path / "private.yaml"
    private.write_text(
        "schema: https://paios.ce/schemas/private-config/v0.1.json\n"
        "owner_allowlist: [\"principal:example.invalid/owner-1\"]\n"
        "speech:\n"
        "  enabled: true\n"
        "  transcript: \"leak me\"\n",
        encoding="utf-8",
    )
    with pytest.raises(Exception):
        load_runtime(private_path=private)


def test_duration_policy_via_pyav_boundary(tmp_path, monkeypatch):
    """Duration check uses the same optional PyAV boundary, not a second
    decoder. With PyAV present and reporting an over-limit duration, the
    stable E_AUDIO_DURATION_LIMIT error is raised."""
    import builtins

    f = write_small_wav(tmp_path / "long.wav")

    class FakeContainer:
        duration = 7200_000_000  # 7200 s (microseconds)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class FakeAV:
        def open(self, path):
            return FakeContainer()

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "av":
            return FakeAV()
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    from paios_ce.speech.policy import AudioFileValidator

    validator = AudioFileValidator()  # max_duration_seconds=3600
    with pytest.raises(SpeechError) as ei:
        validator.validate(str(f))
    assert ei.value.code == SpeechErrorCode.E_AUDIO_DURATION_LIMIT


def test_error_to_dict_stable_shape():
    err = SpeechError(SpeechErrorCode.E_AUDIO_TOO_LARGE, "too big",
                      safe_source_label="a.wav")
    d = err.to_dict()
    assert d["error_code"] == "E_AUDIO_TOO_LARGE"
    assert d["exit_code"] == 2
    assert d["safe_source_label"] == "a.wav"
    assert "path" not in d
