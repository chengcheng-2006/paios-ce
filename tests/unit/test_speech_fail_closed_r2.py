"""Phase 9A-R2 — fail-closed SpeechService authorization tests.

Covers R2-F1: an enabled SpeechService without a configured PermissionEngine,
missing principal, empty owner allowlist, missing capability or non-owner
caller must deny with E_SPEECH_PERMISSION_DENIED before file validation,
adapter call or model construction.

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
from paios_ce.speech.service import SPEECH_CAPABILITY_ID, SpeechService

from conftest import FakeModel, make_fake_model_factory, write_small_wav

OWNER = "principal:example.invalid/owner-1"
OTHER = "principal:example.invalid/user-1"


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


def _service(tmp_path, fake_model, **kw):
    """Build a SpeechService with a real file and fake adapter."""
    f = write_small_wav(tmp_path / "ok.wav")
    defaults = dict(
        runtime_config=_cfg(enabled=True),
        adapter=FasterWhisperAdapterFacade(fake_model),
    )
    defaults.update(kw)
    return f, SpeechService(**defaults)


class FasterWhisperAdapterFacade:
    """Minimal adapter wrapper for service tests (avoids importing adapter)."""

    def __init__(self, model) -> None:
        from paios_ce.speech.faster_whisper_adapter import FasterWhisperAdapter

        self._inner = FasterWhisperAdapter(model_factory=make_fake_model_factory(model))

    def transcribe(self, request):
        return self._inner.transcribe(request)


# ---------------------------------------------------------------------------
# R2-F1 fail-closed matrix (R2_ACCEPTANCE_MATRIX.csv R2-F1-01..08)
# ---------------------------------------------------------------------------


def test_r2f1_missing_engine_denies(tmp_path, fake_model):
    f, service = _service(tmp_path, fake_model)  # no engine
    with pytest.raises(SpeechError) as ei:
        service.transcribe(_request(source=str(f)))
    assert ei.value.code == SpeechErrorCode.E_SPEECH_PERMISSION_DENIED


def test_r2f1_missing_engine_does_not_call_validator(tmp_path, fake_model):
    """R2-F1-02: denial occurs before file validation (missing file still
    yields permission denial, not E_AUDIO_FILE_NOT_FOUND)."""
    service = SpeechService(runtime_config=_cfg(enabled=True))  # no engine
    with pytest.raises(SpeechError) as ei:
        service.transcribe(_request(source=str(tmp_path / "missing.wav")))
    assert ei.value.code == SpeechErrorCode.E_SPEECH_PERMISSION_DENIED


def test_r2f1_missing_engine_does_not_call_adapter(tmp_path, fake_model):
    """R2-F1-03: denial occurs before adapter/model construction."""
    f, service = _service(tmp_path, fake_model)  # no engine
    with pytest.raises(SpeechError):
        service.transcribe(_request(source=str(f)))
    assert fake_model.constructor_calls == []
    assert fake_model.transcribe_calls == []


def test_r2f1_missing_principal_denies(tmp_path, fake_model):
    """R2-F1-04: engine present but no principal -> deny."""
    engine = PermissionEngine(
        capabilities={SPEECH_CAPABILITY_ID},
        owner_allowlist=[OWNER],
        principal_id=OWNER,
    )
    f, service = _service(
        tmp_path, fake_model,
        permission_engine=engine,  # principal_id omitted -> None
        owner_allowlist=[OWNER],
    )
    with pytest.raises(SpeechError) as ei:
        service.transcribe(_request(source=str(f)))
    assert ei.value.code == SpeechErrorCode.E_SPEECH_PERMISSION_DENIED
    assert fake_model.constructor_calls == []


def test_r2f1_empty_owner_allowlist_denies(tmp_path, fake_model):
    """R2-F1-05: empty owner allowlist -> deny."""
    engine = PermissionEngine(
        capabilities={SPEECH_CAPABILITY_ID},
        owner_allowlist=[OWNER],
        principal_id=OWNER,
    )
    f, service = _service(
        tmp_path, fake_model,
        permission_engine=engine,
        principal_id=OWNER,
        owner_allowlist=[],  # empty
    )
    with pytest.raises(SpeechError) as ei:
        service.transcribe(_request(source=str(f)))
    assert ei.value.code == SpeechErrorCode.E_SPEECH_PERMISSION_DENIED
    assert fake_model.constructor_calls == []


def test_r2f1_missing_capability_denies(tmp_path, fake_model):
    """R2-F1-06: engine without SPEECH_TRANSCRIBE_LOCAL -> deny."""
    engine = PermissionEngine(
        capabilities={"TEXT_CHAT"},  # missing speech capability
        owner_allowlist=[OWNER],
        principal_id=OWNER,
    )
    f, service = _service(
        tmp_path, fake_model,
        permission_engine=engine,
        principal_id=OWNER,
        owner_allowlist=[OWNER],
    )
    with pytest.raises(SpeechError) as ei:
        service.transcribe(_request(source=str(f)))
    assert ei.value.code == SpeechErrorCode.E_SPEECH_PERMISSION_DENIED
    assert fake_model.constructor_calls == []


def test_r2f1_non_owner_denies(tmp_path, fake_model):
    """R2-F1-07: non-owner caller -> deny."""
    engine = PermissionEngine(
        capabilities={SPEECH_CAPABILITY_ID},
        owner_allowlist=[OWNER],
        principal_id=OWNER,
    )
    f, service = _service(
        tmp_path, fake_model,
        permission_engine=engine,
        principal_id=OTHER,
        owner_allowlist=[OWNER],
    )
    with pytest.raises(SpeechError) as ei:
        service.transcribe(_request(source=str(f)))
    assert ei.value.code == SpeechErrorCode.E_SPEECH_PERMISSION_DENIED
    assert fake_model.constructor_calls == []


def test_r2f1_authorized_owner_succeeds(tmp_path, fake_model):
    """R2-F1-08: explicit owner + capability -> allow."""
    engine = PermissionEngine(
        capabilities={SPEECH_CAPABILITY_ID},
        owner_allowlist=[OWNER],
        principal_id=OWNER,
    )
    f, service = _service(
        tmp_path, fake_model,
        permission_engine=engine,
        principal_id=OWNER,
        owner_allowlist=[OWNER],
    )
    result = service.transcribe(_request(source=str(f)))
    assert result.status == "success"
    assert len(fake_model.constructor_calls) == 1


def test_all_denial_audits_metadata_only(tmp_path, fake_model):
    """R2-F1-09: every denial audit event contains no transcript/path."""
    engine = PermissionEngine(
        capabilities={SPEECH_CAPABILITY_ID},
        owner_allowlist=[OWNER],
        principal_id=OWNER,
    )
    logger = RedactedAuditLogger()
    f, service = _service(
        tmp_path, fake_model,
        permission_engine=engine,
        principal_id=OTHER,  # denied
        owner_allowlist=[OWNER],
        audit_logger=logger,
    )
    with pytest.raises(SpeechError):
        service.transcribe(_request(source=str(f)))
    events = logger.events()
    assert len(events) == 1
    details = events[0].redacted_details
    assert details["outcome"] == "denied"
    assert details["error_code"] == SpeechErrorCode.E_SPEECH_PERMISSION_DENIED.value
    assert "transcript" not in details
    assert "text" not in details
    assert "helloworld" not in json.dumps(details)
    dumped = json.dumps(details)
    assert str(tmp_path) not in dumped
