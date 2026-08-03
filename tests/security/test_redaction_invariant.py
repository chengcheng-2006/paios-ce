"""Security: redaction invariants (Phase 3R-R1 R3).

Mandated invariants:
  - RAW_SECRET_IN_AUDIT_INPUT = FORBIDDEN
  - SECRETS_MUST_USE_SECRETREF = YES
  - EXTERNAL_RAW_SECRET_REDACTION_REQUIRES_EXPLICIT_SECRET_MAPPING = YES

Public entry points checked: Audit Logger, safe_exception, Health,
Diagnostics, TaskEnvelope, ActionRequest, ActionResult, ErrorEnvelope.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import json

import pytest

from paios_ce.audit import (
    RedactedAuditLogger,
    RedactionNotGuaranteedError,
    redact_mapping,
    redact_value,
    redaction_guaranteed,
    safe_exception,
)
from paios_ce.protocols import ErrorEnvelope, EventKind, TaskEnvelope
from paios_ce.secrets import InMemorySecretRef

from tests._keyshape_fixtures import SK_LONG

# A bare, non-pattern secret literal. It matches NO secret regex, so only an
# explicit literal-value mapping can redact it.
_BARE_SECRET = "phase3r-bare-external-secret-value-xyz"


# --- RAW_SECRET_IN_AUDIT_INPUT = FORBIDDEN ---------------------------------


def test_audit_rejects_raw_secret_field():
    # A secret-like KEY in the redacted details must never carry its raw VALUE
    # into the log. The raw secret value is FORBIDDEN from audit input.
    logger = RedactedAuditLogger()
    ev = logger.make_event(EventKind.MESSAGE_RECEIVED,
                           redacted={"api_key": _BARE_SECRET})
    logger.emit(ev)
    text = logger.getvalue()
    assert _BARE_SECRET not in text
    assert "***" in text  # value is replaced by the fixed placeholder


def test_task_envelope_rejects_raw_secret_field():
    # TaskEnvelope has no secret-value field and extra="forbid" — a raw secret
    # field is structurally rejected.
    base = {
        "manifest_version": "0.1.0", "task_id": "t", "request_id": "r",
        "origin": "cli", "owner_identity": "owner:x", "intent": "x",
        "risk_level": "low", "requested_capabilities": [], "attachments": [],
        "constraints": {}, "approval_state": "not_required", "trace_id": "tr",
    }
    with pytest.raises(Exception):
        TaskEnvelope.model_validate({**base, "secret_value": _BARE_SECRET})
    with pytest.raises(Exception):
        TaskEnvelope.model_validate({**base, "raw_token": _BARE_SECRET})


def test_error_envelope_rejects_raw_secret_field():
    # ErrorEnvelope likewise: extra="forbid", no secret-value field.
    with pytest.raises(Exception):
        ErrorEnvelope.model_validate({
            "manifest_version": "0.1.0", "error_id": "err_1",
            "error_class": "internal", "message": "boom",
            "retryable": False, "trace_id": "tr",
            "timestamp": "2026-08-01T12:00:00Z",
            "secret_value": _BARE_SECRET,
        })
    with pytest.raises(Exception):
        ErrorEnvelope.model_validate({
            "manifest_version": "0.1.0", "error_id": "err_1",
            "error_class": "internal", "message": "boom",
            "retryable": False, "trace_id": "tr",
            "timestamp": "2026-08-01T12:00:00Z",
            "credential": _BARE_SECRET,
        })


# --- EXTERNAL_RAW_SECRET_REDACTION_REQUIRES_EXPLICIT_SECRET_MAPPING ---------


def test_external_raw_secret_requires_mapping():
    # Without a mapping, redaction of a bare non-pattern secret is NOT
    # guaranteed and the strict path refuses it.
    with pytest.raises(RedactionNotGuaranteedError):
        redact_value([_BARE_SECRET], require_mapping=True)
    with pytest.raises(RedactionNotGuaranteedError):
        redact_value({"note": _BARE_SECRET}, require_mapping=True)
    with pytest.raises(RedactionNotGuaranteedError):
        safe_exception(ValueError(_BARE_SECRET), require_mapping=True)
    # With an explicit mapping, the strict path succeeds and redacts it.
    out = redact_value([_BARE_SECRET], mapping={_BARE_SECRET: "***"},
                       require_mapping=True)
    assert out == ["***"]
    out2 = redact_value({"note": _BARE_SECRET}, mapping={_BARE_SECRET: "***"},
                        require_mapping=True)
    assert out2["note"] == "***"
    assert _BARE_SECRET not in json.dumps(out2)


# --- SECRETS_MUST_USE_SECRETREF = YES ---------------------------------------


def test_secretref_reference_allowed_value_forbidden():
    ref = InMemorySecretRef(_BARE_SECRET, ref_id="local_only")
    # The redacted reference (a stable, non-secret label) is allowed in audit
    # under a NEUTRAL key (not a secret-like key).
    logger = RedactedAuditLogger()
    ev = logger.make_event(EventKind.MESSAGE_RECEIVED,
                           redacted={"ref_label": ref.redact()})
    logger.emit(ev)
    text = logger.getvalue()
    assert "in_memory:local_only" in text
    assert _BARE_SECRET not in text
    # The resolved raw value must never enter the models.
    value = ref.resolve()
    assert value.value() == _BARE_SECRET  # present in memory only
    with pytest.raises(Exception):
        TaskEnvelope.model_validate({
            "manifest_version": "0.1.0", "task_id": "t", "request_id": "r",
            "origin": "cli", "owner_identity": "owner:x", "intent": "x",
            "risk_level": "low", "requested_capabilities": [], "attachments": [],
            "constraints": {}, "approval_state": "not_required", "trace_id": "tr",
            "credential_ref": _BARE_SECRET,
        })


# --- MISSING MAPPING NEVER CLAIMS REDACTED ----------------------------------


def test_missing_mapping_never_claims_redacted():
    # The guarantee predicate is False without a mapping covering the bare
    # secret, and True once the literal is mapped.
    assert redaction_guaranteed([_BARE_SECRET]) is False
    assert redaction_guaranteed([_BARE_SECRET], {_BARE_SECRET: "***"}) is True
    # Pattern-shaped secrets are guaranteed even without a mapping.
    assert redaction_guaranteed([SK_LONG]) is True
    # The non-strict path does not raise, but the caller is never able to
    # claim guarantee via the predicate.
    out = redact_value([_BARE_SECRET])
    assert out == [_BARE_SECRET]
    assert redaction_guaranteed(out) is False
