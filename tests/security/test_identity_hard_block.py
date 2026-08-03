"""Security: IDENTITY_ACTION explicit hard block (security closure F-W02 closure).

The risk policy declares IDENTITY_ACTION as hard_blocked=True. This suite proves
the engine's single authoritative hard-block entry (_hard_block_reason) blocks
identity actions explicitly — regardless of owner status, approval flag,
capability grant, or confirmation channel — with a stable, auditable reason and
error code. Parity for FINANCIAL_ACTION / ADMIN_ELEVATION / ARBITRARY_SHELL /
CRITICAL is also re-checked.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

from paios_ce.permissions import Decision, PermissionEngine, ScopeGuard
from paios_ce.protocols import ActionRequest


def _action(operation="rotate_credential", perms=None, fs_mode="none",
            fs_paths=None, net_mode="none", approval_required=False,
            action_id="act_id_1", idem_key="idem_id_1", worker_type="tool"):
    return ActionRequest(
        action_id=action_id,
        worker_type=worker_type,
        operation=operation,
        parameters={"trace_id": "trace_redacted_01"},
        required_permissions=perms or ["TOOL_CALLING"],
        filesystem_scope={"mode": fs_mode, "paths_class": fs_paths or []},
        network_scope={"mode": net_mode, "endpoints_class": []},
        timeout=30,
        idempotency_key=idem_key,
        rollback_supported=False,
        approval_required=approval_required,
    )


def _engine(**kw):
    defaults = dict(
        capabilities={"TEXT_CHAT", "TOOL_CALLING", "admin", "identity.rotate"},
        owner_allowlist=["principal:example.invalid/owner-1"],
        principal_id="principal:example.invalid/owner-1",  # IS the owner
        scope_guard=ScopeGuard(
            fs_read_classes=["quarantine_temp", "state_read"],
            fs_write_classes=["state_write"],
        ),
    )
    defaults.update(kw)
    return PermissionEngine(**defaults)


def test_identity_action_explicit_hard_block():
    eng = _engine()
    result = eng.authorize(_action(operation="rotate_credential"))
    assert result.decision == Decision.BLOCKED
    assert result.hard_blocked is True
    assert "identity" in result.reason.lower()


def test_identity_action_cannot_be_overridden_by_approval():
    eng = _engine()
    result = eng.authorize(_action(operation="update_owner_allowlist",
                                   approval_required=True))
    assert result.decision == Decision.BLOCKED
    assert result.hard_blocked is True


def test_identity_action_cannot_be_enabled_by_capability():
    eng = _engine()
    # Capability allowlist includes the identity capability; still hard-blocked.
    result = eng.authorize(_action(operation="rotate_credential",
                                   perms=["identity.rotate"]))
    assert result.decision == Decision.BLOCKED
    assert result.hard_blocked is True


def test_identity_action_audit_reason():
    eng = _engine()
    result = eng.authorize(_action(operation="rotate_credential"))
    assert PermissionEngine.IDENTITY_HARD_BLOCK_ERROR_CODE in result.reason


def test_identity_action_error_code_stable():
    eng = _engine()
    reasons = set()
    for i, op in enumerate(("rotate_credential", "update_allowlist", "identity_edit")):
        r = eng.authorize(_action(operation=op, action_id=f"x{i}", idem_key=f"y{i}"))
        reasons.add(r.reason.split(":")[0])
    assert len(reasons) == 1
    assert reasons == {PermissionEngine.IDENTITY_HARD_BLOCK_ERROR_CODE}


def test_identity_action_denied_even_for_owner():
    eng = _engine(principal_id="principal:example.invalid/owner-1",
                  owner_allowlist=["principal:example.invalid/owner-1"])
    result = eng.authorize(_action(operation="rotate_credential"))
    assert result.decision == Decision.BLOCKED


def test_financial_action_hard_blocked():
    eng = _engine()
    result = eng.authorize(_action(operation="pay_invoice", perms=["financial.pay"]))
    assert result.decision == Decision.BLOCKED
    assert result.hard_blocked is True


def test_admin_elevation_hard_blocked():
    eng = _engine()
    result = eng.authorize(_action(operation="install_service", perms=["admin"],
                                   net_mode="cloud_egress"))
    assert result.decision == Decision.BLOCKED
    assert result.hard_blocked is True


def test_arbitrary_shell_hard_blocked():
    eng = _engine()
    result = eng.authorize(_action(operation="shell", perms=["TOOL_CALLING"]))
    assert result.decision == Decision.BLOCKED
    assert result.hard_blocked is True


def test_critical_action_hard_blocked():
    eng = _engine()
    result = eng.authorize(_action(operation="delete_file", perms=["fs.write"],
                                   fs_mode="write", fs_paths=["state_write"]))
    assert result.decision == Decision.BLOCKED
    assert result.hard_blocked is True
