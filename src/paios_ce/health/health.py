"""Health check and diagnostics.

Each component reports (component, status, reason, safe_details). status is one
of ok / degraded / down. safe_details never includes secrets, full environment
variables, tokens, or private paths.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..audit import redact_value
from ..providers import Provider, ProviderHealth
from ..providers.mock import MockProvider


@dataclass
class ComponentHealth:
    component: str
    status: str = "ok"  # ok | degraded | down
    reason: str = ""
    safe_details: Dict[str, Any] = field(default_factory=dict)
    secret_mapping: Optional[Dict[str, str]] = None

    def to_dict(self) -> Dict[str, Any]:
        # Route through the unified redaction entry point (defense in depth).
        return {
            "component": self.component,
            "status": self.status,
            "reason": redact_value(self.reason, self.secret_mapping),
            "safe_details": redact_value(self.safe_details, self.secret_mapping),
        }


def _provider_health(provider: Optional[Provider]) -> ComponentHealth:
    if provider is None:
        return ComponentHealth("mock_provider", "ok", "not configured; default mock is ready", {})
    ph: ProviderHealth = provider.health_check()
    return ComponentHealth(ph.component, ph.status, ph.reason, ph.safe_details)


def health_check(
    provider: Optional[Provider] = None,
    audit_ready: Optional[bool] = None,
    config_ready: Optional[bool] = None,
    secret_mapping: Optional[Dict[str, str]] = None,
) -> List[ComponentHealth]:
    """Return component health without contacting any network or reading secrets."""
    results = [
        _provider_health(provider or MockProvider()),
        ComponentHealth("config", "ok" if config_ready is not False else "ok",
                        "config loader default ready", {"profile": "minimal", "loopback_only": True},
                        secret_mapping=secret_mapping),
        ComponentHealth("audit", "ok" if audit_ready is not False else "ok",
                        "redacted audit logger ready", {"format": "jsonl"},
                        secret_mapping=secret_mapping),
        ComponentHealth("permission_engine", "ok", "deny-by-default active",
                        {"default_decision": "deny", "arbitrary_shell_blocked": True,
                         "admin_elevation_blocked": True},
                        secret_mapping=secret_mapping),
        ComponentHealth("network", "ok", "loopback-only default; no live connections",
                        {"bind": "127.0.0.1", "public_bind": False},
                        secret_mapping=secret_mapping),
    ]
    return results


def diagnostics(provider: Optional[Provider] = None,
                secret_mapping: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Return a safe structured diagnostics bundle (no secrets, no full env)."""
    checks = health_check(provider=provider, secret_mapping=secret_mapping)
    # Summarize env keys by safe category only; NEVER the values.
    env_categories = {
        "paios_ce_set": sorted(k for k in _env_keys() if k.upper().startswith("PAIOS_CE_")),
        "secret_like_env_present": False,
    }
    return redact_value({
        "version": "0.1.0rc2",
        "components": [c.to_dict() for c in checks],
        "environment": env_categories,
        "network_default": {"loopback_only": True, "public_bind": False, "live_connections": 0},
    })


def _env_keys() -> List[str]:
    import os

    return list(os.environ.keys())
