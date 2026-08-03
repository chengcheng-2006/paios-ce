"""Security: redaction defense-in-depth (Phase 3R F-W01 closure).

Covers deep, cycle-safe, depth-limited redaction of arbitrary Python values:
mappings, sequences, bytes, unknown objects, exception chains, case-insensitive
keys, and unified entry points (audit logger, health, diagnostics).

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import json

from paios_ce.audit import (
    RedactedAuditLogger,
    redact_mapping,
    redact_text,
    redact_value,
    safe_exception,
)
from paios_ce.health import ComponentHealth, diagnostics, health_check
from paios_ce.protocols import EventKind

from tests._keyshape_fixtures import BEARER_LONG, GHP_LONG, SK_LONG


def test_redact_nested_mapping():
    data = {"outer": {"inner": {"api_key": SK_LONG}}}
    out = redact_value(data)
    assert out["outer"]["inner"]["api_key"] == "***"
    assert SK_LONG not in json.dumps(out)
    assert data["outer"]["inner"]["api_key"] == SK_LONG  # input untouched


def test_redact_nested_sequence():
    data = {"items": [SK_LONG, [BEARER_LONG, 1, None]]}
    out = redact_value(data)
    assert out["items"][0] == "***"
    assert out["items"][1][0] == "***"
    assert out["items"][1][1] == 1
    assert out["items"][1][2] is None


def test_redact_bytes():
    assert redact_value(SK_LONG.encode()) == "<redacted:bytes>"
    out = redact_value({"payload": b"\x00\x01secret"})
    assert out["payload"] == "<redacted:bytes>"


class _LeakyRepr:
    def __repr__(self):  # pragma: no cover - leak trap
        return "LEAKED-SECRET-VALUE-1234"

    def __str__(self):  # pragma: no cover - leak trap
        return "LEAKED-SECRET-VALUE-1234"


def test_redact_unknown_object_safe_repr():
    out = redact_value({"x": _LeakyRepr()})
    assert "LEAKED-SECRET-VALUE-1234" not in str(out)
    assert "***" in str(out) and "object:" in str(out)


def test_redact_cycle():
    lst: list = []
    lst.append(lst)
    out = redact_value({"lst": lst})
    assert out["lst"] == ["<redacted:cycle>"]
    d: dict = {}
    d["self"] = d
    out2 = redact_value(d)
    assert out2["self"] == "<redacted:cycle>"


def test_redact_max_depth():
    deep = {}
    node = deep
    for _ in range(14):
        nxt = {}
        node["child"] = nxt
        node = nxt
    node["leaf"] = "x"
    out = redact_value(deep)
    # Depth is bounded; some leaf should have been replaced by the depth placeholder.
    assert "max_depth" in json.dumps(out) or out != deep


def test_redact_exception_chain():
    cause = KeyError("inner cause " + SK_LONG)
    context = LookupError("inner context " + GHP_LONG)
    outer = RuntimeError("outer " + SK_LONG)
    outer.__cause__ = cause
    outer.__context__ = context
    s = safe_exception(outer)
    assert SK_LONG not in s
    assert GHP_LONG not in s
    assert "RuntimeError" in s


def test_redact_case_insensitive_keys():
    data = {"API_KEY": "x", "Api-Key": "y", "Authorization": "z",
            "SECRET_TOKEN": "w", "Private.Key": "v"}
    out = redact_mapping(data)
    for v in out.values():
        assert v == "***"


def test_redact_authorization_header():
    data = {"authorization": BEARER_LONG,
            "authorization_header": "Bearer xyz", "Authorization": "token"}
    out = redact_value(data)
    for k in ("authorization", "authorization_header", "Authorization"):
        assert out[k] == "***"


def test_redact_cookie_session():
    data = {"cookie": "session=abc123", "session": "xyz", "session_token": "tok",
            "session-id": "sess"}
    out = redact_value(data)
    for k in data:
        assert out[k] == "***"


def test_redact_literal_value_mapping_fw01():
    # F-W01: arbitrary secret value under a NON-secret key is redacted when the
    # caller passes the known literal value.
    out = redact_mapping({"user": "alice", "note": "phase3r-validator-secret-value"},
                         mapping={"phase3r-validator-secret-value": "***"})
    assert out["note"] == "***"
    assert "phase3r-validator-secret-value" not in json.dumps(out)


def test_audit_logger_secret_mapping_injected():
    logger = RedactedAuditLogger(secret_mapping={"phase3r-validator-secret-value": "***"})
    ev = logger.make_event(EventKind.MESSAGE_RECEIVED,
                           redacted={"note": "phase3r-validator-secret-value"})
    logger.emit(ev)
    assert "phase3r-validator-secret-value" not in logger.getvalue()


def test_health_diagnostics_redact_injected():
    _SECRET = "phase3r-validator-secret-value"
    comp = ComponentHealth("mock_provider", "ok", _SECRET, {"t": _SECRET},
                           secret_mapping={_SECRET: "***"})
    payload = json.dumps(comp.to_dict())
    assert _SECRET not in payload
    checks = health_check(secret_mapping={_SECRET: "***"})
    assert all(_SECRET not in json.dumps(c.to_dict()) for c in checks)
    diag = diagnostics(secret_mapping={_SECRET: "***"})
    assert _SECRET not in json.dumps(diag)


def test_redact_text_literal_mapping_fw01():
    s = redact_text("prefix phase3r-validator-secret-value suffix",
                    mapping={"phase3r-validator-secret-value": "***"})
    assert "phase3r-validator-secret-value" not in s
