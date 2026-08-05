"""Phase 9A-R1 — permission gate and privacy mapping tests.

Covers R1 blockers F2 (PermissionEngine gate) and F3 (retain_audio /
persist_transcript mapping). The real execution path must authorize through
the existing PermissionEngine before any adapter/model construction, and the
runtime privacy state must follow the configured values directly.

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


def _engine(capabilities=None, owners=None, principal=None) -> PermissionEngine:
    return PermissionEngine(
        capabilities=set(capabilities or {SPEECH_CAPABILITY_ID}),
        owner_allowlist=owners or [OWNER],
        principal_id=principal or OWNER,
    )


# ---------------------------------------------------------------------------
# F2 — permission gate
# ---------------------------------------------------------------------------


def test_disabled_speech_denies_before_model_construction(tmp_path, fake_model):
    """Disabled speech denies before the adapter/model is constructed."""
    f = write_small_wav(tmp_path / "ok.wav")
    service = SpeechService(
        runtime_config=_cfg(enabled=False),
        adapter=FasterWhisperAdapterFacade(fake_model),
        permission_engine=_engine(),
    )
    with pytest.raises(SpeechError) as ei:
        service.transcribe(_request(source=str(f)))
    assert ei.value.code == SpeechErrorCode.E_SPEECH_DISABLED
    assert fake_model.constructor_calls == []  # never constructed


def test_missing_capability_denies_before_model_construction(tmp_path, fake_model):
    f = write_small_wav(tmp_path / "ok.wav")
    service = SpeechService(
        runtime_config=_cfg(enabled=True),
        adapter=FasterWhisperAdapterFacade(fake_model),
        permission_engine=_engine(capabilities={"TEXT_CHAT"}),  # no SPEECH cap
    )
    with pytest.raises(SpeechError) as ei:
        service.transcribe(_request(source=str(f)))
    assert ei.value.code == SpeechErrorCode.E_SPEECH_PERMISSION_DENIED
    assert fake_model.constructor_calls == []


def test_non_owner_principal_denies_before_model_construction(tmp_path, fake_model):
    f = write_small_wav(tmp_path / "ok.wav")
    service = SpeechService(
        runtime_config=_cfg(enabled=True),
        adapter=FasterWhisperAdapterFacade(fake_model),
        permission_engine=_engine(principal=OTHER),
        principal_id=OTHER,
        owner_allowlist=[OWNER],
    )
    with pytest.raises(SpeechError) as ei:
        service.transcribe(_request(source=str(f)))
    assert ei.value.code == SpeechErrorCode.E_SPEECH_PERMISSION_DENIED
    assert fake_model.constructor_calls == []


def test_single_owner_inference_succeeds(tmp_path, fake_model):
    f = write_small_wav(tmp_path / "ok.wav")
    service = SpeechService(
        runtime_config=_cfg(enabled=True),
        adapter=FasterWhisperAdapterFacade(fake_model),
        permission_engine=_engine(),  # principal defaults to the sole owner
        principal_id=OWNER,
        owner_allowlist=[OWNER],
    )
    result = service.transcribe(_request(source=str(f)))
    assert result.status == "success"
    assert len(fake_model.constructor_calls) == 1


def test_explicit_owner_principal_succeeds(tmp_path, fake_model):
    f = write_small_wav(tmp_path / "ok.wav")
    service = SpeechService(
        runtime_config=_cfg(enabled=True),
        adapter=FasterWhisperAdapterFacade(fake_model),
        permission_engine=_engine(principal=OWNER),
        principal_id=OWNER,
        owner_allowlist=[OWNER],
    )
    result = service.transcribe(_request(source=str(f)))
    assert result.status == "success"


def test_authorized_request_reaches_adapter_once(tmp_path, fake_model):
    f = write_small_wav(tmp_path / "ok.wav")
    service = SpeechService(
        runtime_config=_cfg(enabled=True),
        adapter=FasterWhisperAdapterFacade(fake_model),
        permission_engine=_engine(),
        principal_id=OWNER,
        owner_allowlist=[OWNER],
    )
    service.transcribe(_request(source=str(f)))
    assert len(fake_model.transcribe_calls) == 1
    assert len(fake_model.constructor_calls) == 1


def test_denied_request_emits_metadata_only_denial_audit(tmp_path, fake_model):
    f = write_small_wav(tmp_path / "ok.wav")
    logger = RedactedAuditLogger()
    service = SpeechService(
        runtime_config=_cfg(enabled=True),
        adapter=FasterWhisperAdapterFacade(fake_model),
        audit_logger=logger,
        permission_engine=_engine(capabilities={"TEXT_CHAT"}),  # denied
    )
    with pytest.raises(SpeechError):
        service.transcribe(_request(source=str(f)))
    events = logger.events()
    assert len(events) == 1
    details = events[0].redacted_details
    assert details["outcome"] == "denied"
    assert details["error_code"] == SpeechErrorCode.E_SPEECH_PERMISSION_DENIED.value
    # metadata only: no transcript, no absolute path
    assert "transcript" not in details
    assert "text" not in details
    dumped = json.dumps(details)
    assert str(tmp_path) not in dumped


def test_permission_decision_and_risk_in_audit(tmp_path, fake_model):
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
    details = logger.events()[0].redacted_details
    assert details["permission_decision"] == "allow"
    assert details["risk_level"] == "LOW"
    assert service.last_permission["decision"] == "allow"
    assert service.last_permission["risk_level"] == "LOW"


def test_permission_decision_present_in_result_evidence(tmp_path, fake_model):
    f = write_small_wav(tmp_path / "ok.wav")
    service = SpeechService(
        runtime_config=_cfg(enabled=True),
        adapter=FasterWhisperAdapterFacade(fake_model),
        permission_engine=_engine(),
        principal_id=OWNER,
        owner_allowlist=[OWNER],
    )
    result = service.transcribe(_request(source=str(f)))
    assert service.last_permission["decision"] == "allow"
    assert result.status == "success"


# ---------------------------------------------------------------------------
# F3 — privacy mapping
# ---------------------------------------------------------------------------


def test_retain_audio_false_when_raw_audio_storage_false(tmp_path, fake_model):
    cfg = _cfg(enabled=True, retain_audio=False)
    f = write_small_wav(tmp_path / "ok.wav")
    service = SpeechService(
        runtime_config=cfg,
        adapter=FasterWhisperAdapterFacade(fake_model),
        permission_engine=_engine(),
        principal_id=OWNER,
        owner_allowlist=[OWNER],
    )
    service.transcribe(_request(source=str(f)))
    assert cfg.retain_audio is False


def test_retain_audio_true_when_raw_audio_storage_true(tmp_path, fake_model):
    cfg = _cfg(enabled=True, retain_audio=True)
    f = write_small_wav(tmp_path / "ok.wav")
    service = SpeechService(
        runtime_config=cfg,
        adapter=FasterWhisperAdapterFacade(fake_model),
        permission_engine=_engine(),
        principal_id=OWNER,
        owner_allowlist=[OWNER],
    )
    service.transcribe(_request(source=str(f)))
    assert cfg.retain_audio is True


def test_persist_transcript_false_when_retention_zero(tmp_path, fake_model):
    cfg = _cfg(enabled=True, persist_transcript=False)
    f = write_small_wav(tmp_path / "ok.wav")
    service = SpeechService(
        runtime_config=cfg,
        adapter=FasterWhisperAdapterFacade(fake_model),
        permission_engine=_engine(),
        principal_id=OWNER,
        owner_allowlist=[OWNER],
    )
    service.transcribe(_request(source=str(f)))
    assert cfg.persist_transcript is False


def test_persist_transcript_true_when_retention_positive(tmp_path, fake_model):
    cfg = _cfg(enabled=True, persist_transcript=True)
    f = write_small_wav(tmp_path / "ok.wav")
    service = SpeechService(
        runtime_config=cfg,
        adapter=FasterWhisperAdapterFacade(fake_model),
        permission_engine=_engine(),
        principal_id=OWNER,
        owner_allowlist=[OWNER],
    )
    service.transcribe(_request(source=str(f)))
    assert cfg.persist_transcript is True


class FasterWhisperAdapterFacade:
    """Minimal adapter wrapper for service tests (avoids importing adapter)."""

    def __init__(self, model) -> None:
        from paios_ce.speech.faster_whisper_adapter import FasterWhisperAdapter

        self._inner = FasterWhisperAdapter(model_factory=make_fake_model_factory(model))

    def transcribe(self, request):
        return self._inner.transcribe(request)
