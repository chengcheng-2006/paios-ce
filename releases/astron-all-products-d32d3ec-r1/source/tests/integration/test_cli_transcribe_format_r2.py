"""Phase 9A-R2 — CLI ``transcribe`` format contract tests (R2-F2).

Covers the exact output contract with an injected fake adapter success path
(no model download):

  --format text + stdout   -> transcript text + newline (direct write, no JSON)
  --format json + stdout   -> structured JSON envelope (permission included)
  --format text --output F -> F = transcript + newline; stdout = status envelope
  --format json --output F -> F = structured JSON result; stdout = status envelope

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from paios_ce.cli.main import main

from conftest import FakeModel, make_fake_model_factory, write_small_wav

OWNER = "principal:example.invalid/owner-1"


@pytest.fixture
def fake_adapter_patch(monkeypatch, fake_model):
    """Patch FasterWhisperAdapter so the CLI success path uses a fake model."""
    import paios_ce.speech.faster_whisper_adapter as adapter_mod

    real_cls = adapter_mod.FasterWhisperAdapter

    def patched_cls(*args, **kwargs):
        kwargs.setdefault("model_factory", make_fake_model_factory(fake_model))
        return real_cls(*args, **kwargs)

    monkeypatch.setattr(adapter_mod, "FasterWhisperAdapter", patched_cls)
    return fake_model


@pytest.fixture
def private_config(tmp_path) -> Path:
    import yaml

    cfg = {
        "schema": "https://paios.ce/schemas/private-config/v0.1.json",
        "owner_allowlist": [OWNER],
        "speech": {
            "enabled": True,
            "asr_backend": "local_faster_whisper",
            "raw_audio_storage": False,
            "temp_audio_delete": True,
            "transcript_retention_days": 0,
            "cloud_asr_opt_in": False,
            "local_files_only": True,
            "device": "cpu",
            "compute_type": "int8",
        },
    }
    p = tmp_path / "private.yaml"
    p.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    return p


@pytest.fixture
def wav_file(tmp_path) -> Path:
    return write_small_wav(tmp_path / "sample.wav", size_bytes=2048)


def _run(argv, capsys):
    code = main(argv)
    out = capsys.readouterr().out
    return code, out


# ---------------------------------------------------------------------------
# R2-F2-01..03 — text to stdout
# ---------------------------------------------------------------------------


def test_r2f2_text_stdout_normal_sentence(capsys, tmp_path, fake_adapter_patch,
                                         private_config, wav_file):
    fake_adapter_patch._segments = [
        __import__("conftest", fromlist=["FakeSegment"]).FakeSegment(0.0, 1.2, "hello"),
        __import__("conftest", fromlist=["FakeSegment"]).FakeSegment(1.2, 3.0, "world"),
    ]
    code, out = _run(["transcribe", str(wav_file), "--private-config", str(private_config),
                      "--format", "text"], capsys)
    assert code == 0
    assert out == "helloworld\n"  # transcript + one newline, no JSON envelope


def test_r2f2_text_stdout_non_json_sentence(capsys, tmp_path, fake_adapter_patch,
                                            private_config, wav_file):
    """A transcript that is not valid JSON must still print verbatim."""
    fake_adapter_patch._segments = [
        __import__("conftest", fromlist=["FakeSegment"]).FakeSegment(
            0.0, 1.5, "it's not {json} [at all]"),
    ]
    code, out = _run(["transcribe", str(wav_file), "--private-config", str(private_config),
                      "--format", "text"], capsys)
    assert code == 0
    assert out == "it's not {json} [at all]\n"


def test_r2f2_text_stdout_unicode_chinese(capsys, tmp_path, fake_adapter_patch,
                                          private_config, wav_file):
    fake_adapter_patch._segments = [
        __import__("conftest", fromlist=["FakeSegment"]).FakeSegment(0.0, 2.0, "你好，世界"),
    ]
    code, out = _run(["transcribe", str(wav_file), "--private-config", str(private_config),
                      "--format", "text"], capsys)
    assert code == 0
    assert out == "你好，世界\n"


# ---------------------------------------------------------------------------
# R2-F2-04 — json to stdout
# ---------------------------------------------------------------------------


def test_r2f2_json_stdout_valid_envelope(capsys, tmp_path, fake_adapter_patch,
                                         private_config, wav_file):
    code, out = _run(["transcribe", str(wav_file), "--private-config", str(private_config),
                      "--format", "json"], capsys)
    assert code == 0
    payload = json.loads(out)  # exactly one valid JSON envelope
    assert payload["command"] == "transcribe"
    assert payload["status"] == "ok"
    result = payload["result"]
    assert result["status"] == "success"
    assert result["text"] == "helloworld"
    assert result["safe_source_label"] == "sample.wav"


# ---------------------------------------------------------------------------
# R2-F2-05/06 — output files
# ---------------------------------------------------------------------------


def test_r2f2_text_output_file(capsys, tmp_path, fake_adapter_patch,
                               private_config, wav_file):
    out_file = tmp_path / "out.txt"
    code, out = _run(["transcribe", str(wav_file), "--private-config", str(private_config),
                      "--format", "text", "--output", str(out_file)], capsys)
    assert code == 0
    # stdout = safe write-status JSON envelope
    payload = json.loads(out)
    assert payload["command"] == "transcribe"
    assert payload["status"] == "ok"
    assert payload["output_file"] == str(out_file)
    # file = transcript text + newline
    assert out_file.read_text(encoding="utf-8") == "helloworld\n"


def test_r2f2_json_output_file(capsys, tmp_path, fake_adapter_patch,
                               private_config, wav_file):
    out_file = tmp_path / "out.json"
    code, out = _run(["transcribe", str(wav_file), "--private-config", str(private_config),
                      "--format", "json", "--output", str(out_file)], capsys)
    assert code == 0
    payload = json.loads(out)
    assert payload["status"] == "ok"
    assert payload["output_file"] == str(out_file)
    # file = structured JSON result
    result = json.loads(out_file.read_text(encoding="utf-8"))
    assert result["status"] == "success"
    assert result["text"] == "helloworld"


# ---------------------------------------------------------------------------
# R2-F2-07/08 — permission evidence and audit purity
# ---------------------------------------------------------------------------


def test_r2f2_permission_evidence_in_json_output(capsys, tmp_path, fake_adapter_patch,
                                                 private_config, wav_file):
    code, out = _run(["transcribe", str(wav_file), "--private-config", str(private_config),
                      "--format", "json"], capsys)
    assert code == 0
    payload = json.loads(out)
    permission = payload["result"].get("permission")
    assert permission is not None
    assert permission["decision"] == "allow"
    assert permission["risk_level"] == "LOW"


def test_r2f2_no_transcript_added_to_audit(capsys, tmp_path, fake_adapter_patch,
                                           private_config, wav_file, monkeypatch):
    """The success path must not place transcript text into audit events."""
    import io

    from paios_ce.audit import RedactedAuditLogger

    stream = io.StringIO()
    monkeypatch.setattr(
        "paios_ce.audit.RedactedAuditLogger",
        lambda: RedactedAuditLogger(stream=stream),
    )
    code, out = _run(["transcribe", str(wav_file), "--private-config", str(private_config),
                      "--format", "json"], capsys)
    assert code == 0
    lines = stream.getvalue().strip().splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    text = json.dumps(event)
    assert "helloworld" not in text
    assert "transcript" not in json.dumps(event.get("redacted_details", {}))
