"""Security: secrets never leak into logs, exceptions, config, envelopes.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import json

import pytest

from paios_ce.audit import RedactedAuditLogger, redact_mapping, redact_text, safe_exception
from paios_ce.protocols import AuditEvent, EventKind, TaskEnvelope
from paios_ce.secrets import InMemorySecretRef

from tests._keyshape_fixtures import SK_SHORT


def test_secret_never_in_logs():
    ref = InMemorySecretRef("super-secret-xyz-001")
    logger = RedactedAuditLogger()
    ev = logger.make_event(EventKind.MESSAGE_RECEIVED, redacted={"ref": ref.redact()})
    logger.emit(ev)
    assert "super-secret-xyz-001" not in logger.getvalue()


def test_secret_never_in_exception():
    ref = InMemorySecretRef("super-secret-xyz-001")
    try:
        ref.resolve()
    except Exception:
        pass
    exc = ValueError("cannot resolve " + ref.redact())
    s = safe_exception(exc)
    assert "super-secret-xyz-001" not in s


def test_secret_never_in_serialized_config():
    from paios_ce.config import load_runtime

    rt = load_runtime()
    # RuntimeConfig never carries a value; only a SecretRefDecl reference.
    dumped = json.dumps(rt.model_dump())
    assert "super-secret" not in dumped


def test_secret_redaction_never_leaks_length():
    short = InMemorySecretRef("ab")
    long = InMemorySecretRef("abcdefghijklmnop")
    assert short.redact() == long.redact() == "in_memory:local_only"


def test_secret_never_in_task_envelope():
    # Valid envelope must not contain any secret value.
    env = TaskEnvelope.model_validate({"manifest_version": "0.1.0", "task_id": "t",
                                       "request_id": "r", "origin": "cli",
                                       "owner_identity": "owner:x", "intent": "x",
                                       "risk_level": "low", "requested_capabilities": [],
                                       "attachments": [], "constraints": {},
                                       "approval_state": "not_required", "trace_id": "tr"})
    assert "secret_value" not in env.model_dump()
    # Extra forbidden field must be rejected, never silently stored.
    with pytest.raises(Exception):
        TaskEnvelope.model_validate({"manifest_version": "0.1.0", "task_id": "t",
                                     "request_id": "r", "origin": "cli",
                                     "owner_identity": "owner:x", "intent": "x",
                                     "risk_level": "low", "requested_capabilities": [],
                                     "attachments": [], "constraints": {},
                                     "approval_state": "not_required", "trace_id": "tr",
                                     "secret_value": "super-secret-xyz-001"})


def test_redact_mapping_leaves_no_secret_key():
    data = {"api_key": "super-secret-xyz-001", "nested": {"authorization_header": "Bearer xyz"}}
    out = redact_mapping(data)
    assert "super-secret-xyz-001" not in json.dumps(out)
    assert out["nested"]["authorization_header"] == "***"


def test_redact_text_leaves_no_secret():
    s = redact_text("Bearer abcdefgh1234 and " + SK_SHORT)
    assert "abcdefgh1234" not in s


def test_audit_event_forbidden_fields_absent():
    ev = AuditEvent(event_id="evt_1", event_type=EventKind.MESSAGE_RECEIVED)
    payload = ev.model_dump()
    for field in ("secret_value", "raw_token", "cookie", "authorization_header",
                  "raw_audio", "full_private_path", "owner_identity_detail"):
        assert field not in payload
