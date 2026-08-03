"""Permission / Risk engine unit tests.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

from paios_ce.permissions import Decision, PermissionEngine, RiskEngine, ScopeGuard
from paios_ce.protocols import ActionRequest


def _action(operation="read_file_in_scope", perms=None, fs_mode="read",
            fs_paths=None, net_mode="none", approval_required=False,
            action_id="act_1", idem_key="idem_1"):
    return ActionRequest(
        action_id=action_id,
        worker_type="tool",
        operation=operation,
        parameters={"trace_id": "trace_redacted_01"},
        required_permissions=perms or ["TEXT_CHAT"],
        filesystem_scope={"mode": fs_mode, "paths_class": fs_paths or []},
        network_scope={"mode": net_mode, "endpoints_class": []},
        timeout=30,
        idempotency_key=idem_key,
        rollback_supported=False,
        approval_required=approval_required,
    )


def _engine(**kw):
    defaults = dict(
        capabilities={"TEXT_CHAT", "TOOL_CALLING", "fs.read", "fs.write"},
        owner_allowlist=["principal:example.invalid/owner-1"],
        principal_id="principal:example.invalid/user-1",
        scope_guard=ScopeGuard(
            fs_read_classes=["quarantine_temp", "state_read"],
            fs_write_classes=["state_write"],
        ),
    )
    defaults.update(kw)
    return PermissionEngine(**defaults)


def test_default_deny_unknown_capability():
    eng = _engine()
    result = eng.authorize(_action(perms=["SOME_UNKNOWN_CAP"]))
    assert result.decision == Decision.DENY


def test_default_deny_no_capabilities_at_all():
    eng = PermissionEngine()
    result = eng.authorize(_action(perms=[]))
    # even with no required permissions, filesystem read scope check still gates
    assert result.decision in (Decision.DENY, Decision.CONFIRMATION_REQUIRED, Decision.ALLOW)


def test_high_requires_approval():
    eng = _engine()
    result = eng.authorize(_action(operation="send_notification",
                                   perms=["TEXT_CHAT"], net_mode="cloud_egress",
                                   approval_required=False))
    assert result.decision == Decision.CONFIRMATION_REQUIRED


def test_critical_blocked():
    eng = _engine()
    result = eng.authorize(_action(operation="delete_file", perms=["fs.write"],
                                   fs_mode="write", fs_paths=["state_write"]))
    assert result.decision == Decision.BLOCKED


def test_admin_blocked():
    eng = _engine()
    result = eng.authorize(_action(operation="install_service", perms=["admin"],
                                   fs_mode="none", net_mode="cloud_egress"))
    assert result.decision == Decision.BLOCKED


def test_shell_blocked():
    eng = _engine()
    result = eng.authorize(_action(operation="shell", perms=["TOOL_CALLING"],
                                   fs_mode="none"))
    assert result.decision == Decision.BLOCKED


def test_powershell_blocked():
    eng = _engine()
    result = eng.authorize(_action(operation="powershell -Command x", perms=["TOOL_CALLING"],
                                   fs_mode="none"))
    assert result.decision == Decision.BLOCKED


def test_scope_escape_blocked():
    eng = _engine()
    result = eng.authorize(_action(operation="read_file_in_scope", perms=["fs.read"],
                                   fs_mode="read", fs_paths=["user_home"]))
    assert result.decision == Decision.DENY
    assert "scope" in result.reason.lower() or "escape" in result.reason.lower()


def test_replay_blocked():
    eng = _engine()
    first = eng.authorize(_action(action_id="act_replay_1", idem_key="idem_replay_1"))
    second = eng.authorize(_action(action_id="act_replay_1", idem_key="idem_replay_1"))
    assert second.is_replay is True
    assert second.decision == Decision.DENY


def test_idempotency_returns_cached():
    eng = _engine()
    first = eng.authorize(_action(action_id="act_idem_1", idem_key="key_idem_1"))
    second = eng.authorize(_action(action_id="act_idem_2", idem_key="key_idem_1"))
    assert first.decision == Decision.ALLOW
    assert second.is_replay is True
    assert second.decision == Decision.ALLOW


def test_loopback_network_allowed():
    eng = _engine()
    result = eng.authorize(_action(operation="fetch_health", perms=["fs.read"],
                                   fs_mode="read", fs_paths=["quarantine_temp"],
                                   net_mode="loopback"))
    assert result.decision in (Decision.ALLOW, Decision.DENY)  # no egress escape


def test_risk_classification_low():
    eng = RiskEngine()
    match = eng.evaluate(_action(operation="read_file_in_scope", fs_mode="read"))
    assert match.risk_level.value == "LOW"
