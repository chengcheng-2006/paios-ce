"""Health / diagnostics unit tests.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

from paios_ce.health import diagnostics, health_check
from paios_ce.providers import MockProvider


def test_health_check_components():
    checks = health_check(provider=MockProvider())
    names = {c.component for c in checks}
    assert "mock" in names
    assert "config" in names
    assert "audit" in names
    assert "permission_engine" in names


def test_health_check_no_secrets():
    checks = health_check(provider=MockProvider())
    text = repr([c.to_dict() for c in checks])
    assert "not-a-valid-provider-token" not in text
    assert "sk-" not in text


def test_diagnostics_no_full_env():
    diag = diagnostics(provider=MockProvider())
    assert "components" in diag
    env = diag["environment"]
    assert "secret_like_env_present" in env
    # values must not be dumped
    text = str(diag)
    assert "=" not in text  # no KEY=value dumps


def test_diagnostics_network_defaults():
    diag = diagnostics()
    assert diag["network_default"]["loopback_only"] is True
    assert diag["network_default"]["public_bind"] is False
    assert diag["network_default"]["live_connections"] == 0
