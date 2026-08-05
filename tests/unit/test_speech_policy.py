"""Phase 9A 鈥?speech input policy tests (extension/size/duration/read-only).

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

from pathlib import Path

import pytest

from paios_ce.speech.contracts import AudioInputPolicy
from paios_ce.speech.errors import SpeechError, SpeechErrorCode
from paios_ce.speech.policy import AudioFileValidator, safe_source_label

from conftest import write_small_wav


def test_safe_source_label_never_absolute():
    assert safe_source_label("D:\\data\\secret\\audio.wav") == "audio.wav"
    assert safe_source_label("/home/owner/audio.wav") == "audio.wav"
    assert safe_source_label("audio.wav") == "audio.wav"
    assert safe_source_label("") == "audio"


def test_missing_file_raises_stable_code(tmp_path):
    validator = AudioFileValidator()
    with pytest.raises(SpeechError) as ei:
        validator.validate(str(tmp_path / "missing.wav"))
    assert ei.value.code == SpeechErrorCode.E_AUDIO_FILE_NOT_FOUND


def test_directory_rejected(tmp_path):
    validator = AudioFileValidator()
    with pytest.raises(SpeechError) as ei:
        validator.validate(str(tmp_path))
    assert ei.value.code == SpeechErrorCode.E_AUDIO_FILE_NOT_FOUND


def test_unsupported_extension_rejected(tmp_path):
    f = tmp_path / "audio.exe"
    f.write_bytes(b"MZ")
    validator = AudioFileValidator()
    with pytest.raises(SpeechError) as ei:
        validator.validate(str(f))
    assert ei.value.code == SpeechErrorCode.E_AUDIO_TYPE_NOT_ALLOWED


def test_extension_check_case_insensitive(tmp_path):
    f = tmp_path / "audio.WAV"
    write_small_wav(f, size_bytes=2048)
    validator = AudioFileValidator()
    validator.validate(str(f))  # no raise


def test_oversize_file_rejected(tmp_path):
    # A policy with a 1 MB limit rejects a file that is larger than 1 MB.
    # Write a file that exceeds 1 MB using the helper (header + payload).
    f = tmp_path / "big.wav"
    write_small_wav(f, size_bytes=1024 * 1024 + 64)  # ~1 MB + 64 B
    policy = AudioInputPolicy(max_file_size_mb=1)
    validator = AudioFileValidator(policy)
    with pytest.raises(SpeechError) as ei:
        validator.validate(str(f))
    assert ei.value.code == SpeechErrorCode.E_AUDIO_TOO_LARGE


def test_size_limit_respects_configured_mb(tmp_path):
    f = tmp_path / "mid.wav"
    write_small_wav(f, size_bytes=2048)
    validator = AudioFileValidator(AudioInputPolicy(max_file_size_mb=10))
    validator.validate(str(f))  # 2 KB < 10 MB: pass


def test_small_file_passes(tmp_path):
    f = tmp_path / "ok.wav"
    write_small_wav(f, size_bytes=2048)
    validator = AudioFileValidator()
    validator.validate(str(f))


def test_symlink_resolved_for_size(tmp_path):
    """A symlink to an allowed file must pass the same policy checks."""
    target = tmp_path / "target.wav"
    write_small_wav(target, size_bytes=2048)
    link = tmp_path / "link.wav"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported on this filesystem")
    validator = AudioFileValidator()
    validator.validate(str(link))


def test_windows_junction_path_boundary(tmp_path):
    """A directory junction (no admin rights needed) resolves to the target.

    Covers the path-boundary behaviour on Windows where plain symlinks
    require elevation: the validator must follow the link and apply the same
    size/type checks to the real file.
    """
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    write_small_wav(real_dir / "audio.wav", size_bytes=2048)
    junction = tmp_path / "junction"
    try:
        import subprocess

        r = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(junction), str(real_dir)],
            capture_output=True, text=True,
        )
        if r.returncode != 0 or not junction.exists():
            pytest.skip("junction creation not supported")
    except (OSError, FileNotFoundError):
        pytest.skip("junction creation not supported")
    validator = AudioFileValidator()
    validator.validate(str(junction / "audio.wav"))  # resolves and passes


def test_duration_probe_without_decoder_is_skipped(tmp_path, monkeypatch):
    """When PyAV is absent, duration check is skipped (no second decoder)."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "av":
            raise ImportError("av not installed (test)")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    f = tmp_path / "ok.wav"
    write_small_wav(f, size_bytes=2048)
    validator = AudioFileValidator()
    validator.validate(str(f))  # no raise; duration skipped
