"""Audit redaction and logger unit tests.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import json

from paios_ce.audit import RedactedAuditLogger, redact_mapping, redact_text, safe_exception
from paios_ce.protocols import EventKind, RiskLevel

from tests._keyshape_fixtures import GHP_LONG, SK_LONG


def test_redact_text_secret_patterns():
    assert redact_text("key is " + SK_LONG) == "key is ***"
    assert redact_text("Bearer abcdefgh12345678") == "***"
    assert redact_text(GHP_LONG + " x") == "*** x"


def test_redact_text_mapping():
    out = redact_text("secret literal ABC value", mapping={"ABC": "***"})
    assert "ABC" not in out


def test_redact_mapping_secret_keys():
    data = {"api_key": "sk-abc", "nested": {"token": "xyz", "ok": "fine"}}
    out = redact_mapping(data)
    assert out["api_key"] == "***"
    assert out["nested"]["token"] == "***"
    assert out["nested"]["ok"] == "fine"
    # input not mutated
    assert data["api_key"] == "sk-abc"


def test_redact_mapping_paths():
    out = redact_mapping({"path": "C:\\Users\\owner\\secret.txt"})
    assert "<USER_HOME>" in out["path"]
    assert "owner" not in out["path"]


def test_safe_exception_redacts():
    exc = ValueError("key was " + SK_LONG)
    s = safe_exception(exc)
    assert SK_LONG not in s
    assert "***" in s
    assert "ValueError" in s


def test_audit_logger_writes_jsonl():
    logger = RedactedAuditLogger()
    logger.emit(logger.make_event(EventKind.MESSAGE_RECEIVED, task_id="task_1",
                                  trace_id="tr_1", risk_level=RiskLevel.LOW))
    text = logger.getvalue()
    line = text.strip().splitlines()[0]
    obj = json.loads(line)
    assert obj["event_type"] == "message_received"
    assert obj["task_id"] == "task_1"
    assert "secret_value" not in obj


def test_audit_logger_forbidden_fields_rejected():
    logger = RedactedAuditLogger()
    ev = logger.make_event(EventKind.MESSAGE_RECEIVED)
    ev.redacted_details = {"api_key": "sk-abc"}  # will be redacted via redact_mapping
    logger.emit(ev)
    text = logger.getvalue()
    assert "sk-abc" not in text
    assert "***" in text


def test_audit_logger_events_captured():
    logger = RedactedAuditLogger()
    logger.emit(logger.make_event(EventKind.HEALTH_EVENT))
    assert len(logger.events()) == 1
    assert logger.events()[0].event_type == EventKind.HEALTH_EVENT
