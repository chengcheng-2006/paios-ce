"""Config loader unit tests: precedence, defaults, validation.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from paios_ce.config import ConfigLoadError, load_runtime
from paios_ce.config.models import PrivateConfig, PublicConfig, RuntimeConfig


def test_defaults_are_safe(tmp_path):
    rt = load_runtime()
    assert rt.defaults.listen == "127.0.0.1"
    assert rt.defaults.public_bind is False
    assert rt.defaults.dm_only is True
    assert rt.defaults.group_execution is False
    assert rt.defaults.owner_allowlist_required is True
    assert rt.defaults.high_risk_confirmation is True
    assert rt.defaults.raw_audio_storage is False
    assert rt.defaults.remote_execution is False
    assert rt.primary_provider == "mock"


def test_public_config_precedence_over_defaults(public_example):
    rt = load_runtime(public_path=public_example)
    # public config keeps safe defaults, still loopback
    assert rt.defaults.listen == "127.0.0.1"
    assert rt.defaults.public_bind is False


def test_private_config_applies_owner_allowlist(public_example, private_example):
    rt = load_runtime(public_path=public_example, private_path=private_example)
    assert "principal:example.invalid/owner-1" in rt.owner_allowlist


def test_env_overrides_precedence(public_example, private_example):
    env = {
        "PAIOS_CE_DEFAULTS_LISTEN": "0.0.0.0",
        "PAIOS_CE_DEFAULTS_PUBLIC_BIND": "true",
        "PAIOS_CE_PRIMARY_PROVIDER": "openai_compatible",
    }
    rt = load_runtime(
        public_path=public_example, private_path=private_example, environ=env
    )
    assert rt.defaults.listen == "0.0.0.0"
    assert rt.defaults.public_bind is True
    assert rt.primary_provider == "openai_compatible"


def test_cli_overrides_highest_precedence(public_example, private_example):
    env = {"PAIOS_CE_PRIMARY_PROVIDER": "openai_compatible"}
    cli = {"primary_provider": "mock"}
    rt = load_runtime(
        public_path=public_example, private_path=private_example,
        environ=env, cli_overrides=cli,
    )
    assert rt.primary_provider == "mock"


def test_precedence_chain_full(tmp_path):
    public = tmp_path / "public.yaml"
    private = tmp_path / "private.yaml"
    public.write_text(
        "schema: https://paios.ce/schemas/public-config/v0.1.json\n"
        "profile: minimal\n"
        "defaults:\n  listen: 127.0.0.1\n  public_bind: false\n",
        encoding="utf-8",
    )
    private.write_text(
        "schema: https://paios.ce/schemas/private-config/v0.1.json\n"
        "owner_allowlist: [\"principal:example.invalid/owner-1\"]\n",
        encoding="utf-8",
    )
    rt = load_runtime(public_path=public, private_path=private)
    assert rt.defaults.listen == "127.0.0.1"
    assert rt.owner_allowlist == ["principal:example.invalid/owner-1"]


def test_invalid_yaml_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("schema: [unclosed\n", encoding="utf-8")
    with pytest.raises(ConfigLoadError):
        load_runtime(public_path=bad)


def test_public_config_model_rejects_secret_field():
    with pytest.raises(Exception):
        PublicConfig.model_validate({"schema": "https://paios.ce/schemas/public-config/v0.1.json",
                                     "profile": "minimal",
                                     "api_key": "not-a-real-secret-value"})


def test_private_config_model_rejects_secret_field():
    with pytest.raises(Exception):
        PrivateConfig.model_validate({
            "schema": "https://paios.ce/schemas/private-config/v0.1.json",
            "owner_allowlist": ["principal:example.invalid/owner-1"],
            "providers": {"primary": {"id": "x", "api_key": "not-a-real-secret-value"}},
        })


def test_runtime_config_never_contains_secret_values(public_example, private_example):
    rt = load_runtime(public_path=public_example, private_path=private_example)
    dumped = rt.model_dump()
    text = str(dumped)
    assert "sk-" not in text
    assert "ghp_" not in text
    assert "AIza" not in text
    assert "AKIA" not in text
