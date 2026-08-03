"""Security: unknown-action explicit reject (Phase 3R-R1 correction).

Phase 3R-R1 reverses the Phase 3R F-W03 adjudication (ACCEPTED_SAFE_STRICTNESS):
UNKNOWN_ACTION must be EXPLICIT_REJECT, never mapped to PROCESS_EXEC, never
mapped to any known action, with the stable error code E_UNKNOWN_ACTION, risk
NOT_APPLICABLE, and no execution attempt.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

from paios_ce.permissions import ActionClass, Decision, PermissionEngine, RiskEngine
from paios_ce.protocols import ActionRequest


def _action(operation="unknown_weird_op_zz", perms=None, action_id="act_unk_1",
            idem_key="idem_unk_1"):
    return ActionRequest(
        action_id=action_id,
        worker_type="tool",
        operation=operation,
        parameters={"trace_id": "trace_redacted_01"},
        required_permissions=perms or ["TEXT_CHAT"],
        filesystem_scope={"mode": "none", "paths_class": []},
        network_scope={"mode": "none", "endpoints_class": []},
        timeout=30,
        idempotency_key=idem_key,
        rollback_supported=False,
        approval_required=False,
    )


def _engine(**kw):
    defaults = dict(
        capabilities={"TEXT_CHAT", "TOOL_CALLING"},
        owner_allowlist=["principal:example.invalid/owner-1"],
        principal_id="principal:example.invalid/owner-1",
        scope_guard=__import__("paios_ce.permissions", fromlist=["ScopeGuard"]).ScopeGuard(),
    )
    defaults.update(kw)
    return PermissionEngine(**defaults)


def test_unknown_action_rejected():
    eng = _engine()
    result = eng.authorize(_action(operation="weird_future_op_42"))
    assert result.decision == Decision.BLOCKED
    assert result.hard_blocked is True
    assert result.action_class == ActionClass.UNKNOWN_ACTION


def test_unknown_action_not_coerced():
    # Unknown operations classify to UNKNOWN_ACTION (explicit reject), never to
    # PROCESS_EXEC or any other known class.
    eng = RiskEngine()
    match = eng.evaluate(_action(operation="totally_unknown_op_xyz"))
    assert match.action_class == ActionClass.UNKNOWN_ACTION
    assert match.hard_blocked is True


def test_unknown_action_audited():
    eng = _engine()
    result = eng.authorize(_action(operation="weird_future_op_42",
                                   action_id="act_unk_2", idem_key="idem_unk_2"))
    # Reason is deterministic and non-empty; decision is recorded as blocked.
    assert result.reason
    assert result.decision == Decision.BLOCKED
    assert result.action_class == ActionClass.UNKNOWN_ACTION
    assert result.error_code == PermissionEngine.UNKNOWN_ACTION_ERROR_CODE


def test_unknown_action_never_silently_downgraded_to_low():
    eng = RiskEngine()
    match = eng.evaluate(_action(operation="mystery_operation"))
    assert match.risk_level.value != "LOW"
    assert match.hard_blocked is True
    assert match.action_class == ActionClass.UNKNOWN_ACTION
