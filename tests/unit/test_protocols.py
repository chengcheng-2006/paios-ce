"""Protocol model unit tests + JSON Schema parity.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from paios_ce.protocols import (
    ActionRequest,
    ActionResult,
    AuditEvent,
    ErrorEnvelope,
    TaskEnvelope,
)


def test_task_envelope_valid():
    env = TaskEnvelope.model_validate({
        "manifest_version": "0.1.0",
        "task_id": "task_1",
        "request_id": "req_1",
        "origin": "cli",
        "owner_identity": "owner:placeholder",
        "intent": "summarize_document",
        "risk_level": "low",
        "requested_capabilities": ["TEXT_CHAT"],
        "attachments": [{"ref": "att:01", "mime_class": "text/plain", "size_class": "small"}],
        "constraints": {"max_actions": 3},
        "deadline_optional": None,
        "approval_state": "not_required",
        "trace_id": "trace_redacted_01",
    })
    assert env.manifest_version == "0.1.0"
    assert env.risk_level.value == "low"


def test_task_envelope_extra_forbidden():
    with pytest.raises(Exception):
        TaskEnvelope.model_validate({
            "manifest_version": "0.1.0", "task_id": "t", "request_id": "r",
            "origin": "cli", "owner_identity": "owner:x", "intent": "x",
            "risk_level": "low", "requested_capabilities": [], "attachments": [],
            "constraints": {}, "approval_state": "not_required", "trace_id": "tr",
            "secret_value": "not-a-real-secret-value",
        })


def test_action_request_valid():
    ar = ActionRequest.model_validate({
        "manifest_version": "0.1.0",
        "action_id": "act_1",
        "worker_type": "tool",
        "operation": "read_file_in_scope",
        "parameters": {"trace_id": "trace_redacted_01"},
        "required_permissions": ["TEXT_CHAT"],
        "filesystem_scope": {"mode": "read", "paths_class": ["quarantine_temp"]},
        "network_scope": {"mode": "none", "endpoints_class": []},
        "timeout": 30,
        "idempotency_key": "idem_1",
        "rollback_supported": False,
        "approval_required": False,
    })
    assert ar.operation == "read_file_in_scope"


def test_action_result_valid():
    ar = ActionResult.model_validate({
        "manifest_version": "0.1.0", "action_id": "act_1", "status": "success",
        "outcome": {"summary_class": "summary_produced"},
        "usage": {"cost_class": "free", "tokens_class": "small"},
        "rollback_attempted": False, "rollback_status": "not_required",
        "trace_id": "trace_redacted_01", "error": None,
    })
    assert ar.status.value == "success"


def test_error_envelope_valid():
    err = ErrorEnvelope.model_validate({
        "manifest_version": "0.1.0", "error_id": "err_1",
        "error_class": "permission_denied", "message": "action denied",
        "retryable": False, "trace_id": "trace_redacted_01",
        "timestamp": "2026-08-01T12:00:00Z",
    })
    assert err.error_class.value == "permission_denied"


def test_audit_event_extra_forbidden():
    with pytest.raises(Exception):
        AuditEvent.model_validate({
            "event_id": "evt_1", "event_type": "message_received",
            "secret_value": "not-a-real-secret-value",
        })


def test_generated_schema_accepts_valid_example(read_schema):
    schema = read_schema("task_envelope.schema.json")
    jsonschema.validate({
        "manifest_version": "0.1.0", "task_id": "task_1", "request_id": "req_1",
        "origin": "cli", "owner_identity": "owner:placeholder", "intent": "summarize",
        "risk_level": "low", "requested_capabilities": ["TEXT_CHAT"],
        "attachments": [], "constraints": {}, "approval_state": "not_required",
        "trace_id": "trace_redacted_01",
    }, schema)


def test_generated_schema_rejects_invalid_example(read_schema):
    schema = read_schema("task_envelope.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({
            "manifest_version": "0.1.0", "task_id": "", "request_id": "r",
            "origin": "fax", "owner_identity": "x", "intent": "",
            "risk_level": "extreme", "requested_capabilities": ["TELEPATHY"],
            "attachments": [], "constraints": {}, "approval_state": "maybe",
            "trace_id": "t",
        }, schema)


def test_audit_event_schema_has_no_forbidden_fields(read_schema):
    schema = read_schema("audit_event.schema.json")
    props = set(schema["properties"].keys())
    forbidden = {"secret_value", "raw_token", "cookie", "authorization_header",
                 "raw_audio", "full_private_path", "owner_identity_detail"}
    assert forbidden.isdisjoint(props)
