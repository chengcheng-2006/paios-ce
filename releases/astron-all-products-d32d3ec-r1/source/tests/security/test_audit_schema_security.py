"""Security: audit event schema, forbidden fields, no owner identity.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import json

from paios_ce.audit import RedactedAuditLogger
from paios_ce.protocols import AuditEvent, EventKind, RiskLevel

from tests._keyshape_fixtures import BEARER_SK_ABC123, SK_ABC123


def test_audit_no_secret():
    logger = RedactedAuditLogger()
    ev = logger.make_event(EventKind.ACTION_COMPLETED, redacted={"secret_value": "sk-abc"})
    logger.emit(ev)
    assert "sk-abc" not in logger.getvalue()


def test_audit_no_owner_path():
    logger = RedactedAuditLogger()
    ev = logger.make_event(EventKind.ACTION_COMPLETED,
                           redacted={"path": "C:\\Users\\owner\\secret.txt"})
    logger.emit(ev)
    assert "C:\\Users\\owner" not in logger.getvalue()


def test_audit_no_authorization_header():
    logger = RedactedAuditLogger()
    ev = logger.make_event(EventKind.ACTION_COMPLETED,
                           redacted={"authorization": BEARER_SK_ABC123})
    logger.emit(ev)
    assert "Bearer" not in logger.getvalue()
    assert SK_ABC123 not in logger.getvalue()


def test_audit_schema():
    ev = AuditEvent(event_id="evt_1", timestamp="2026-08-01T00:00:00Z",
                    event_type=EventKind.MESSAGE_RECEIVED,
                    risk_level=RiskLevel.LOW, actor_type="user",
                    component="paios_ce", outcome="ok")
    schema = AuditEvent.model_json_schema()
    assert "event_id" in schema["properties"]
    assert "timestamp" in schema["properties"]
    assert "event_type" in schema["properties"]
    assert "redacted_details" in schema["properties"]


def test_audit_no_owner_identity_detail():
    logger = RedactedAuditLogger()
    ev = logger.make_event(EventKind.MESSAGE_RECEIVED,
                           redacted={"owner_identity_detail": "alice@example.invalid"})
    logger.emit(ev)
    # redact_mapping redacts the forbidden key entirely
    assert "alice@example.invalid" not in logger.getvalue()


def test_audit_jsonl_structure():
    logger = RedactedAuditLogger()
    ev = logger.make_event(EventKind.HEALTH_EVENT)
    logger.emit(ev)
    lines = [l for l in logger.getvalue().strip().splitlines() if l]
    assert all(json.loads(l)["manifest_version"] == "0.1.0" for l in lines)


def test_audit_no_full_private_path_in_schema():
    schema = AuditEvent.model_json_schema()
    text = json.dumps(schema)
    assert "full_private_path" not in text
    assert "owner_identity_detail" not in text
