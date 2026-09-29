"""Phase 9A —SpeechService orchestration and audit-boundary tests.

R2: authorization is mandatory and fail-closed. Success-path tests inject an
explicit configured PermissionEngine with a real owner allowlist; adapter
behavior is tested through the adapter directly.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import json

import pytest

from paios_ce.audit import RedactedAuditLogger
from paios_ce.permissions import PermissionEngine
from paios_ce.speech.contracts import SpeechRuntimeConfig, TranscriptionRequest
from paios_ce.speech.errors import SpeechError, SpeechErrorCode
from paios_ce.speech.service import SPEECH_CAPABILITY_ID, SPEECH_OPERATION, SpeechService

from conftest import FakeModel, make_fake_model_factory, write_small_wav

OWNER = "principal:example.invalid/owner-1"


def _cfg(**kw):
    defaults = dict(enabled=True, local_files_only=True, retain_audio=False,
                    persist_transcript=False, audit_transcript=False,
                    max_file_size_mb=100, max_duration_seconds=3600)
    defaults.update(kw)
    return SpeechRuntimeConfig(**defaults)


def _request(source="sample.wav", **kw):
    defaults = dict(model="tiny", device="cpu", compute_type="int8")
    defaults.update(kw)
    return TranscriptionRequest(source=source, **defaults)


def _engine() -> PermissionEngine:
    return PermissionEngine(
        capabilities={SPEECH_CAPABILITY_ID},
        owner_allowlist=[OWNER],
        principal_id=OWNER,
    )


def test_disabled_by_default_raises():
    service = SpeechService(runtime_config=_cfg(enabled=False))
    with pytest.raises(SpeechError) as ei:
        service.transcribe(_request())
    assert ei.value.code == SpeechErrorCode.E_SPEECH_DISABLED


def test_enabled_property():
    assert SpeechService(runtime_config=_cfg(enabled=False)).enabled is False
    assert SpeechService(runtime_config=_cfg(enabled=True)).enabled is True


def test_missing_engine_denies_before_policy(tmp_path, fake_model):
    """R2-F1: enabled service without a PermissionEngine denies before file
    validation or adapter/model construction."""
    f = write_small_wav(tmp_path / "ok.wav")
    service = SpeechService(
        runtime_config=_cfg(enabled=True),
        adapter=FasterWhisperAdapterFacade(fake_model),
    )  # no engine
    with pytest.raises(SpeechError) as ei:
        service.transcribe(_request(source=str(f)))
    assert ei.value.code == SpeechErrorCode.E_SPEECH_PERMISSION_DENIED
    assert fake_model.constructor_calls == []
    assert fake_model.transcribe_calls == []


def test_missing_file_raises_policy_error(tmp_path):
    service = SpeechService(
        runtime_config=_cfg(enabled=True),
        permission_engine=_engine(),
        principal_id=OWNER,
        owner_allowlist=[OWNER],
    )
    with pytest.raises(SpeechError) as ei:
        service.transcribe(_request(source=str(tmp_path / "missing.wav")))
    assert ei.value.code == SpeechErrorCode.E_AUDIO_FILE_NOT_FOUND


def test_dependency_missing_when_no_adapter(tmp_path):
    f = write_small_wav(tmp_path / "ok.wav")
    service = SpeechService(
        runtime_config=_cfg(enabled=True),
        permission_engine=_engine(),
        principal_id=OWNER,
        owner_allowlist=[OWNER],
    )  # no adapter
    with pytest.raises(SpeechError) as ei:
        service.transcribe(_request(source=str(f)))
    assert ei.value.code == SpeechErrorCode.E_SPEECH_DEPENDENCY_MISSING


def test_success_path_with_fake_adapter(tmp_path, fake_model):
    f = write_small_wav(tmp_path / "ok.wav")
    service = SpeechService(
        runtime_config=_cfg(enabled=True),
        adapter=FasterWhisperAdapterFacade(fake_model),
        permission_engine=_engine(),
        principal_id=OWNER,
        owner_allowlist=[OWNER],
    )
    result = service.transcribe(_request(source=str(f)))
    assert result.status == "success"
    assert result.text == "helloworld"
    assert result.safe_source_label == "ok.wav"


def test_success_audit_is_metadata_only(tmp_path, fake_model):
    f = write_small_wav(tmp_path / "ok.wav")
    logger = RedactedAuditLogger()
    service = SpeechService(
        runtime_config=_cfg(enabled=True),
        adapter=FasterWhisperAdapterFacade(fake_model),
        audit_logger=logger,
        permission_engine=_engine(),
        principal_id=OWNER,
        owner_allowlist=[OWNER],
    )
    result = service.transcribe(_request(source=str(f)))
    events = logger.events()
    assert len(events) == 1
    details = events[0].redacted_details
    assert details["capability_id"] == SPEECH_CAPABILITY_ID
    assert details["operation"] == SPEECH_OPERATION
    assert details["outcome"] == "ok"
    assert details["safe_source_label"] == "ok.wav"
    assert details["segment_count"] == 2
    assert details["language"] == "en"
    # forbidden content absent
    assert "transcript" not in details
    assert "text" not in details
    assert "helloworld" not in json.dumps(details)


def test_success_audit_never_contains_absolute_path(tmp_path, fake_model):
    f = write_small_wav(tmp_path / "ok.wav")
    logger = RedactedAuditLogger()
    service = SpeechService(
        runtime_config=_cfg(enabled=True),
        adapter=FasterWhisperAdapterFacade(fake_model),
        audit_logger=logger,
        permission_engine=_engine(),
        principal_id=OWNER,
        owner_allowlist=[OWNER],
    )
    service.transcribe(_request(source=str(f)))
    dumped = json.dumps(logger.events()[0].model_dump())
    assert str(tmp_path) not in dumped
    assert "ok.wav" in dumped  # basename only


def test_failure_audit_absent_forbidden_fields(tmp_path, fake_model):
    """Even on decode failure, forbidden fields are structurally absent."""
    class Boom:
        def transcribe(self, source, language=None, vad_filter=True, word_timestamps=False):
            raise RuntimeError("boom")

    f = write_small_wav(tmp_path / "ok.wav")
    logger = RedactedAuditLogger()
    service = SpeechService(
        runtime_config=_cfg(enabled=True),
        adapter=FasterWhisperAdapterFacade(Boom()),
        audit_logger=logger,
        permission_engine=_engine(),
        principal_id=OWNER,
        owner_allowlist=[OWNER],
    )
    with pytest.raises(SpeechError) as ei:
        service.transcribe(_request(source=str(f)))
    assert ei.value.code == SpeechErrorCode.E_AUDIO_DECODE_FAILED
    events = logger.events()
    assert len(events) == 1
    details = events[0].redacted_details
    assert details["outcome"] == "failed"
    assert details["error_code"] == SpeechErrorCode.E_AUDIO_DECODE_FAILED.value
    dumped = json.dumps(details)
    assert "boom" not in dumped
    assert "transcript" not in details


def test_denied_audit_when_disabled():
    logger = RedactedAuditLogger()
    service = SpeechService(runtime_config=_cfg(enabled=False), audit_logger=logger)
    with pytest.raises(SpeechError):
        service.transcribe(_request())
    details = logger.events()[0].redacted_details
    assert details["outcome"] == "denied"
    assert details["error_code"] == SpeechErrorCode.E_SPEECH_DISABLED.value


class FasterWhisperAdapterFacade:
    """Minimal adapter wrapper for service tests (avoids importing adapter)."""

    def __init__(self, model) -> None:
        from paios_ce.speech.faster_whisper_adapter import FasterWhisperAdapter

        self._inner = FasterWhisperAdapter(model_factory=make_fake_model_factory(model))

    def transcribe(self, request):
        return self._inner.transcribe(request)
