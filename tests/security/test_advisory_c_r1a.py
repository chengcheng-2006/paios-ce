"""Security: Advisory-C closure -- token-based keyword matching (R1A closure).

R1 closure Advisory-C: upload_* classified to NETWORK_READ because load
matched as substring inside upload. Fixed by token-based matching.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

from paios_ce.permissions import (
    ActionClass,
    Decision,
    PermissionEngine,
    RiskEngine,
    ScopeGuard,
)
from paios_ce.protocols import ActionRequest

_KNOWN_CLASSES = {
    ActionClass.READ_LOCAL, ActionClass.WRITE_LOCAL, ActionClass.DELETE_LOCAL,
    ActionClass.NETWORK_READ, ActionClass.NETWORK_WRITE, ActionClass.PROCESS_EXEC,
    ActionClass.ADMIN_ELEVATION, ActionClass.SECRET_ACCESS,
    ActionClass.EXTERNAL_MESSAGE, ActionClass.FINANCIAL_ACTION,
    ActionClass.IDENTITY_ACTION,
}


def _action(operation="upload_data", perms=None, action_id="act_r1a_1",
            idem_key="idem_r1a_1", approval_required=False, worker_type="tool",
            parameters=None, net_mode="none"):
    return ActionRequest(
        action_id=action_id,
        worker_type=worker_type,
        operation=operation,
        parameters=parameters or {"trace_id": "trace_redacted_01"},
        required_permissions=perms or ["TEXT_CHAT"],
        filesystem_scope={"mode": "none", "paths_class": []},
        network_scope={"mode": net_mode, "endpoints_class": []},
        timeout=30,
        idempotency_key=idem_key,
        rollback_supported=False,
        approval_required=approval_required,
    )


def _engine(**kw):
    defaults = dict(
        capabilities={"TEXT_CHAT", "TOOL_CALLING", "admin", "identity.rotate", "*"},
        owner_allowlist=["principal:example.invalid/owner-1"],
        principal_id="principal:example.invalid/owner-1",
        scope_guard=ScopeGuard(
            fs_read_classes=["quarantine_temp", "state_read"],
            fs_write_classes=["state_write"],
        ),
    )
    defaults.update(kw)
    return PermissionEngine(**defaults)


def _assert_unknown(result):
    assert result.decision == Decision.BLOCKED
    assert result.hard_blocked is True
    assert result.action_class == ActionClass.UNKNOWN_ACTION
    assert result.error_code == PermissionEngine.UNKNOWN_ACTION_ERROR_CODE
    assert result.action_class not in _KNOWN_CLASSES


def test_unknown_upload_action_rejected():
    eng = RiskEngine()
    for op in ("upload_data", "upload_file", "upload_blob"):
        match = eng.evaluate(_action(operation=op, net_mode="cloud_egress"))
        assert match.action_class == ActionClass.UNKNOWN_ACTION
    eng2 = _engine()
    result = eng2.authorize(_action(operation="upload_data", net_mode="cloud_egress",
                                    action_id="act_up_1", idem_key="idem_up_1"))
    _assert_unknown(result)


def test_unknown_upload_action_not_network_read():
    eng = RiskEngine()
    for net_mode in ("none", "cloud_egress"):
        for op in ("upload_data", "upload_file", "upload_blob"):
            match = eng.evaluate(_action(operation=op, net_mode=net_mode))
            assert match.action_class != ActionClass.NETWORK_READ
            assert match.action_class != ActionClass.READ_LOCAL


def test_unknown_upload_action_not_network_write():
    eng = RiskEngine()
    for op in ("upload_data", "upload_file", "upload_blob"):
        match = eng.evaluate(_action(operation=op, net_mode="cloud_egress"))
        assert match.action_class != ActionClass.NETWORK_WRITE
        assert match.action_class != ActionClass.WRITE_LOCAL


def test_unknown_upload_action_not_approvable():
    eng = _engine()
    result = eng.authorize(_action(operation="upload_data", net_mode="cloud_egress",
                                    approval_required=True,
                                    action_id="act_up_appr", idem_key="idem_up_appr"))
    _assert_unknown(result)


def test_unknown_download_action_rejected():
    eng = RiskEngine()
    for op in ("download_data", "download_file", "download_blob"):
        match = eng.evaluate(_action(operation=op, net_mode="cloud_egress"))
        assert match.action_class == ActionClass.UNKNOWN_ACTION
    eng2 = _engine()
    result = eng2.authorize(_action(operation="download_data", net_mode="cloud_egress",
                                     action_id="act_dl_1", idem_key="idem_dl_1"))
    _assert_unknown(result)


def test_unknown_fetch_action_rejected():
    eng = RiskEngine()
    match = eng.evaluate(_action(operation="fetch_data", net_mode="cloud_egress"))
    assert match.action_class == ActionClass.NETWORK_READ
    match2 = eng.evaluate(_action(operation="fetch_data", net_mode="none"))
    assert match2.action_class == ActionClass.READ_LOCAL


def test_unknown_sync_action_rejected():
    eng = RiskEngine()
    for op in ("sync_data", "sync_remote"):
        match = eng.evaluate(_action(operation=op, net_mode="cloud_egress"))
        assert match.action_class == ActionClass.UNKNOWN_ACTION


def test_unknown_send_action_rejected():
    eng = RiskEngine()
    match = eng.evaluate(_action(operation="send_data"))
    assert match.action_class == ActionClass.EXTERNAL_MESSAGE


def test_unknown_post_action_rejected():
    eng = RiskEngine()
    match = eng.evaluate(_action(operation="post_data"))
    assert match.action_class == ActionClass.EXTERNAL_MESSAGE


def test_unknown_prefix_matrix_no_coercion():
    eng = RiskEngine()
    cases = [
        ("upload_data", "cloud_egress", ActionClass.UNKNOWN_ACTION),
        ("upload_data", "none", ActionClass.UNKNOWN_ACTION),
        ("upload_file", "cloud_egress", ActionClass.UNKNOWN_ACTION),
        ("download_data", "cloud_egress", ActionClass.UNKNOWN_ACTION),
        ("download_data", "none", ActionClass.UNKNOWN_ACTION),
        ("sync_data", "cloud_egress", ActionClass.UNKNOWN_ACTION),
        ("sync_data", "none", ActionClass.UNKNOWN_ACTION),
        ("fetch_data", "cloud_egress", ActionClass.NETWORK_READ),
        ("fetch_data", "none", ActionClass.READ_LOCAL),
        ("send_data", "none", ActionClass.EXTERNAL_MESSAGE),
        ("post_data", "none", ActionClass.EXTERNAL_MESSAGE),
        ("get_data", "cloud_egress", ActionClass.NETWORK_READ),
        ("get_data", "none", ActionClass.READ_LOCAL),
        ("cloud_write", "cloud_egress", ActionClass.NETWORK_WRITE),
        ("cloud_read", "cloud_egress", ActionClass.NETWORK_READ),
        ("net_write", "cloud_egress", ActionClass.NETWORK_WRITE),
        ("net_read", "none", ActionClass.READ_LOCAL),
        ("remote_write", "cloud_egress", ActionClass.NETWORK_WRITE),
        ("remote_read", "none", ActionClass.READ_LOCAL),
        ("read_file_in_scope", "none", ActionClass.READ_LOCAL),
        ("fetch_health", "none", ActionClass.READ_LOCAL),
        ("send_notification", "none", ActionClass.EXTERNAL_MESSAGE),
        ("delete_file", "none", ActionClass.DELETE_LOCAL),
        ("shell", "none", ActionClass.PROCESS_EXEC),
        ("pay_invoice", "none", ActionClass.FINANCIAL_ACTION),
        ("rotate_credential", "none", ActionClass.IDENTITY_ACTION),
        ("update_owner_allowlist", "none", ActionClass.IDENTITY_ACTION),
    ]
    for op, net_mode, expected in cases:
        match = eng.evaluate(_action(operation=op, net_mode=net_mode))
        assert match.action_class == expected, (
            f"MATRIX FAIL: op={op} mode={net_mode} -> {match.action_class}, expected {expected}"
        )

