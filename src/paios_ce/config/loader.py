"""ConfigLoader — merge public/private config with strict precedence.

Precedence (highest wins):
  1. CLI flags (explicit overrides dict)
  2. process environment (PAIOS_CE_* variables)
  3. private local config (PrivateConfig YAML)
  4. public project config (PublicConfig YAML)
  5. built-in safe defaults

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

import yaml

from .models import (
    AuditConfig,
    DefaultsConfig,
    PrivateConfig,
    PrivateChannels,
    PrivateSpeech,
    PrivateState,
    PublicConfig,
    RuntimeConfig,
)

_ENV_PREFIX = "PAIOS_CE_"
_ENV_KEY = re.compile(r"^PAIOS_CE_[A-Z0-9_]+$")


class ConfigLoadError(ValueError):
    """Raised when a config file cannot be parsed or validated."""


def _load_yaml(path: Path) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except OSError as exc:  # pragma: no cover - defensive
        raise ConfigLoadError(f"cannot read config file: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigLoadError(f"config file is not valid YAML: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigLoadError("config file root must be a mapping")
    return data


def _env_overrides(environ: Mapping[str, str]) -> Dict[str, Any]:
    """Translate PAIOS_CE_* env vars into a nested override dict.

    Supported keys follow the runtime config tree:
      PAIOS_CE_DEFAULTS_LISTEN, PAIOS_CE_DEFAULTS_PUBLIC_BIND,
      PAIOS_CE_DEFAULTS_GROUP_EXECUTION, PAIOS_CE_DEFAULTS_REMOTE_EXECUTION,
      PAIOS_CE_DEFAULTS_RAW_AUDIO_STORAGE, PAIOS_CE_DEFAULTS_CLOUD_ASR,
      PAIOS_CE_PROFILE, PAIOS_CE_RUNTIME_PROFILE,
      PAIOS_CE_PRIMARY_PROVIDER, PAIOS_CE_PROVIDER_ENDPOINT,
      PAIOS_CE_PROVIDER_CREDENTIAL_REF_BACKEND,
      PAIOS_CE_PROVIDER_CREDENTIAL_REF_ENV_VAR,
      PAIOS_CE_OWNER_ALLOWLIST (comma-separated)
    Unknown PAIOS_CE_* keys are ignored to keep the surface explicit.
    """
    out: Dict[str, Any] = {}
    lower = {k.lower(): v for k, v in environ.items()}

    def _set(path: str, value: Any) -> None:
        node = out
        parts = path.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    bool_keys = {
        "defaults.public_bind": "defaults.public_bind",
        "defaults.group_execution": "defaults.group_execution",
        "defaults.raw_audio_storage": "defaults.raw_audio_storage",
        "defaults.remote_execution": "defaults.remote_execution",
        "defaults.dm_only": "defaults.dm_only",
    }
    for env_key, target in bool_keys.items():
        full = _ENV_PREFIX + env_key.replace(".", "_").upper()
        if full in environ:
            _set(target, _to_bool(environ[full]))

    for env_key, target in {
        "PAIOS_CE_DEFAULTS_LISTEN": "defaults.listen",
        "PAIOS_CE_DEFAULTS_CLOUD_ASR": "defaults.cloud_asr",
        "PAIOS_CE_PROFILE": "profile",
        "PAIOS_CE_RUNTIME_PROFILE": "runtime_profile",
        "PAIOS_CE_PRIMARY_PROVIDER": "primary_provider",
        "PAIOS_CE_PROVIDER_ENDPOINT": "provider_endpoint",
    }.items():
        if env_key in environ:
            _set(target, environ[env_key])

    if "PAIOS_CE_PROVIDER_CREDENTIAL_REF_BACKEND" in environ:
        cred: Dict[str, Any] = {}
        if environ.get("PAIOS_CE_PROVIDER_CREDENTIAL_REF_ENV_VAR"):
            cred = {"ref": {"env_var": environ["PAIOS_CE_PROVIDER_CREDENTIAL_REF_ENV_VAR"]}}
        else:
            cred = {"ref": {"ref_id": "env_from_process"}}
        _set("provider_credential_ref", cred)

    if "PAIOS_CE_OWNER_ALLOWLIST" in environ:
        _set("owner_allowlist", [s for s in environ["PAIOS_CE_OWNER_ALLOWLIST"].split(",") if s])

    return out


def _to_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _apply_public(target: Dict[str, Any], public: PublicConfig) -> None:
    target["profile"] = public.profile
    target["runtime_profile"] = public.runtime_profile
    target.setdefault("defaults", {})
    target["defaults"].update(public.defaults.model_dump())
    target.setdefault("audit", {})
    target["audit"].update(public.audit.model_dump())
    caps = public.capabilities
    if caps.providers:
        target["capabilities"] = {"providers": [p.model_dump() for p in caps.providers]}


def _apply_private(target: Dict[str, Any], private: PrivateConfig) -> None:
    if private.owner_allowlist:
        target["owner_allowlist"] = list(private.owner_allowlist)
    for key, entry in private.providers.items():
        if key == "primary":
            target["primary_provider"] = entry.id
            if entry.endpoint:
                target["provider_endpoint"] = entry.endpoint
            if entry.credential_ref:
                target["provider_credential_ref"] = entry.credential_ref.model_dump()
        elif key == "fallback":
            target["fallback_provider"] = entry.id
    if private.channels is not None:
        target["channels"] = private.channels.model_dump()
    if private.speech is not None:
        target["speech"] = private.speech.model_dump()
    if private.state is not None:
        target["state"] = private.state.model_dump()
    if private.group_execution is not None:
        target["group_execution"] = private.group_execution.model_dump()


class ConfigLoader:
    """Merges public + private config with env and CLI overrides."""

    def __init__(
        self,
        public_path: Optional[Path] = None,
        private_path: Optional[Path] = None,
        environ: Optional[Mapping[str, str]] = None,
    ) -> None:
        self.public_path = public_path
        self.private_path = private_path
        self.environ = dict(environ) if environ is not None else dict(os.environ)

    def load(self, cli_overrides: Optional[Dict[str, Any]] = None) -> RuntimeConfig:
        """Build the effective RuntimeConfig applying precedence order."""
        merged: Dict[str, Any] = {}

        # 5. built-in safe defaults (implicit via RuntimeConfig defaults)
        # 4. public project config
        if self.public_path is not None and self.public_path.exists():
            data = _load_yaml(self.public_path)
            public = PublicConfig.model_validate(data)
            _apply_public(merged, public)
        # 3. private local config
        if self.private_path is not None and self.private_path.exists():
            data = _load_yaml(self.private_path)
            private = PrivateConfig.model_validate(data)
            _apply_private(merged, private)
        # 2. process environment
        merged = _deep_merge(merged, _env_overrides(self.environ))
        # 1. CLI flags
        if cli_overrides:
            merged = _deep_merge(merged, cli_overrides)

        # channel/speech/state need their nested defaults even when private config absent
        merged.setdefault("channels", {})
        merged.setdefault("speech", {})
        merged.setdefault("state", {})
        merged.setdefault("audit", {})
        merged.setdefault("defaults", {})
        merged.setdefault("owner_allowlist", [])

        defaults = DefaultsConfig.model_validate(merged["defaults"])
        if merged.get("group_execution", {}).get("enabled") and not defaults.group_execution:
            defaults = defaults.model_copy(
                update={"group_execution": True}
            )

        rt = RuntimeConfig(
            profile=merged.get("profile", "minimal"),
            runtime_profile=merged.get("runtime_profile", "lite"),
            defaults=defaults,
            owner_allowlist=list(merged.get("owner_allowlist", [])),
            primary_provider=merged.get("primary_provider", "mock"),
            fallback_provider=merged.get("fallback_provider"),
            provider_endpoint=merged.get("provider_endpoint", "https://example.invalid/v1"),
            provider_credential_ref=merged.get("provider_credential_ref"),
            channels=PrivateChannels.model_validate(merged["channels"]),
            speech=PrivateSpeech.model_validate(merged["speech"]),
            state=PrivateState.model_validate(merged["state"]),
            audit=AuditConfig.model_validate(merged["audit"]),
            group_execution=(
                merged.get("group_execution")
                or {"enabled": False, "risk_acknowledged": False}
            ),
        )
        return rt


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge override into base (override wins)."""
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_runtime(
    public_path: Optional[Path] = None,
    private_path: Optional[Path] = None,
    cli_overrides: Optional[Dict[str, Any]] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> RuntimeConfig:
    """Convenience wrapper over ConfigLoader."""
    loader = ConfigLoader(public_path=public_path, private_path=private_path, environ=environ)
    return loader.load(cli_overrides=cli_overrides)
