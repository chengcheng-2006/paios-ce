"""SecretRef unit tests.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import pytest

from paios_ce.secrets import (
    EnvSecretRef,
    InMemorySecretRef,
    SecretRedactionError,
    SecretRef,
    SecretReferenceUnresolved,
    SecretValue,
)


def test_env_secretref_exists_and_redact(monkeypatch):
    monkeypatch.setenv("PAIOS_TEST_KEY_1", "not-a-valid-provider-token")
    ref = EnvSecretRef("PAIOS_TEST_KEY_1")
    assert ref.exists() is True
    assert "not-a-valid-provider-token" not in ref.redact()
    assert ref.redact() == "env:PAIOS_TEST_KEY_1"


def test_env_secretref_missing(monkeypatch):
    monkeypatch.delenv("PAIOS_TEST_KEY_MISSING", raising=False)
    ref = EnvSecretRef("PAIOS_TEST_KEY_MISSING")
    assert ref.exists() is False
    with pytest.raises(SecretReferenceUnresolved):
        ref.resolve()


def test_env_secretref_unresolved_message_does_not_leak_value(monkeypatch):
    monkeypatch.delenv("PAIOS_TEST_KEY_MISSING", raising=False)
    ref = EnvSecretRef("PAIOS_TEST_KEY_MISSING")
    try:
        ref.resolve()
    except SecretReferenceUnresolved as exc:
        msg = str(exc)
        assert "PAIOS_TEST_KEY_MISSING" in msg
        assert "not-a-valid-provider-token" not in msg


def test_in_memory_secretref_resolve_and_clear():
    ref = InMemorySecretRef("super-secret-value-01", ref_id="local_only")
    sv = ref.resolve()
    assert sv.value() == "super-secret-value-01"
    sv.clear()
    assert sv.value() == ""


def test_in_memory_secretref_redact_never_leaks_value():
    ref = InMemorySecretRef("super-secret-value-01", ref_id="local_only")
    r = ref.redact()
    assert r == "in_memory:local_only"
    assert "super-secret-value-01" not in r


def test_secret_value_repr_never_leaks():
    sv = SecretValue("super-secret-value-01")
    assert "super-secret-value-01" not in repr(sv)
    assert "super-secret-value-01" not in str(sv)


def test_secret_value_len_never_leaks():
    sv = SecretValue("abcdefghij")
    assert len(sv) == 0  # never leaks length


def test_ref_id_required():
    with pytest.raises(ValueError):
        InMemorySecretRef("x", ref_id="")


def test_abstract_cannot_instantiate():
    with pytest.raises(TypeError):
        SecretRef("x")  # type: ignore[abstract]
