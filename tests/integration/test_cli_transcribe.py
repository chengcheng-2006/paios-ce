"""Phase 9A — CLI ``transcribe`` integration tests.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from paios_ce.cli.main import build_parser, main

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "unit"))


def _run(argv, capsys):
    code = main(argv)
    out = capsys.readouterr().out
    return code, out


def _make_private_config(tmp_path, **speech_overrides) -> Path:
    """Write a minimal private config enabling speech with safe placeholders."""
    speech = {
        "enabled": True,
        "asr_backend": "local_faster_whisper",
        "raw_audio_storage": False,
        "temp_audio_delete": True,
        "transcript_retention_days": 0,
        "cloud_asr_opt_in": False,
    }
    speech.update(speech_overrides)
    cfg = {
        "schema": "https://paios.ce/schemas/private-config/v0.1.json",
        "owner_allowlist": ["principal:example.invalid/owner-1"],
        "speech": speech,
    }
    p = tmp_path / "private_config.yaml"
    import yaml

    p.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    return p


def _small_wav(tmp_path) -> Path:
    from conftest import write_small_wav

    return write_small_wav(tmp_path / "sample.wav", size_bytes=2048)


def test_cli_transcribe_disabled_by_default(capsys, tmp_path):
    f = _small_wav(tmp_path)
    code, out = _run(["transcribe", str(f)], capsys)
    assert code == 4
    payload = json.loads(out)
    assert payload["error_code"] == "E_SPEECH_DISABLED"
    assert payload["safe_source_label"] == "sample.wav"


def test_cli_transcribe_dependency_missing(capsys, tmp_path, monkeypatch):
    """Enabled speech without the faster-whisper extra fails with the stable
    dependency error. The faster_whisper import is explicitly blocked so the
    test proves the dependency-absent path deterministically (CI and local)."""
    import builtins

    f = _small_wav(tmp_path)
    cfg = _make_private_config(tmp_path, enabled=True)

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "faster_whisper":
            raise ImportError("no module named faster_whisper")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    code, out = _run(["transcribe", str(f), "--private-config", str(cfg)], capsys)
    assert code == 6
    payload = json.loads(out)
    assert payload["error_code"] == "E_SPEECH_DEPENDENCY_MISSING"


def test_cli_transcribe_missing_file(capsys, tmp_path):
    cfg = _make_private_config(tmp_path, enabled=True)
    code, out = _run(
        ["transcribe", str(tmp_path / "nope.wav"), "--private-config", str(cfg)],
        capsys,
    )
    assert code == 2
    payload = json.loads(out)
    assert payload["error_code"] == "E_AUDIO_FILE_NOT_FOUND"
    assert "nope.wav" in payload["safe_source_label"]


def test_cli_transcribe_unsupported_extension(capsys, tmp_path):
    bad = tmp_path / "audio.exe"
    bad.write_bytes(b"MZ")
    cfg = _make_private_config(tmp_path, enabled=True)
    code, out = _run(["transcribe", str(bad), "--private-config", str(cfg)], capsys)
    assert code == 2
    payload = json.loads(out)
    assert payload["error_code"] == "E_AUDIO_TYPE_NOT_ALLOWED"


def test_cli_transcribe_parser_registered():
    parser = build_parser()
    sub_actions = parser._subparsers._group_actions[0].choices
    assert "transcribe" in sub_actions


def test_cli_transcribe_error_never_leaks_absolute_path(capsys, tmp_path):
    cfg = _make_private_config(tmp_path, enabled=True)
    missing = tmp_path / "secret_audio.wav"
    code, out = _run(["transcribe", str(missing), "--private-config", str(cfg)], capsys)
    assert code == 2
    assert str(tmp_path) not in out
    assert "secret_audio.wav" in out  # basename only


def _make_private_config_multi_owner(tmp_path) -> Path:
    cfg = {
        "schema": "https://paios.ce/schemas/private-config/v0.1.json",
        "owner_allowlist": [
            "principal:example.invalid/owner-1",
            "principal:example.invalid/owner-2",
        ],
        "speech": {
            "enabled": True,
            "asr_backend": "local_faster_whisper",
            "local_files_only": True,
            "device": "cpu",
            "compute_type": "int8",
        },
    }
    p = tmp_path / "private_multi.yaml"
    import yaml

    p.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    return p


def test_cli_transcribe_ambiguous_multi_owner_denied(capsys, tmp_path):
    """R1-F2: with multiple owners and no --principal-id, the caller is
    ambiguous and the command denies before any model construction."""
    f = _small_wav(tmp_path)
    cfg = _make_private_config_multi_owner(tmp_path)
    code, out = _run(["transcribe", str(f), "--private-config", str(cfg)], capsys)
    assert code == 4
    payload = json.loads(out)
    assert payload["error_code"] == "E_SPEECH_PERMISSION_DENIED"


def test_cli_transcribe_explicit_principal_single_owner_inference(capsys, tmp_path, monkeypatch):
    """R1-F2: a single-owner allowlist infers the owner; with the speech
    dependency absent the request then fails at the dependency step (proving
    the permission gate passed)."""
    import builtins

    f = _small_wav(tmp_path)
    cfg = _make_private_config(tmp_path, enabled=True)
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "faster_whisper":
            raise ImportError("no module named faster_whisper")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    code, out = _run(["transcribe", str(f), "--private-config", str(cfg)], capsys)
    # Permission passes (single owner inferred); dependency missing is next.
    assert code == 6
    payload = json.loads(out)
    assert payload["error_code"] == "E_SPEECH_DEPENDENCY_MISSING"


def test_cli_transcribe_explicit_principal_id_accepted(capsys, tmp_path, monkeypatch):
    """R1-F2: --principal-id is accepted for a multi-owner config; the
    permission gate passes and the dependency step is reached."""
    import builtins

    f = _small_wav(tmp_path)
    cfg = _make_private_config_multi_owner(tmp_path)
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "faster_whisper":
            raise ImportError("no module named faster_whisper")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    code, out = _run(
        ["transcribe", str(f), "--private-config", str(cfg),
         "--principal-id", "principal:example.invalid/owner-1"],
        capsys,
    )
    assert code == 6
    payload = json.loads(out)
    assert payload["error_code"] == "E_SPEECH_DEPENDENCY_MISSING"


def test_cli_transcribe_non_owner_principal_denied(capsys, tmp_path):
    """R1-F2: an explicit non-owner principal is denied."""
    f = _small_wav(tmp_path)
    cfg = _make_private_config(tmp_path, enabled=True)
    code, out = _run(
        ["transcribe", str(f), "--private-config", str(cfg),
         "--principal-id", "principal:example.invalid/user-1"],
        capsys,
    )
    assert code == 4
    payload = json.loads(out)
    assert payload["error_code"] == "E_SPEECH_PERMISSION_DENIED"
