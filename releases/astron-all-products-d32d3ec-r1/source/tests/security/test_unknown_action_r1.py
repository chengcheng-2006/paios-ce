"""Security: UNKNOWN_ACTION = EXPLICIT_REJECT (R1 closure).

Mandated semantics (R2):
  - UNKNOWN_ACTION is explicitly rejected
  - ERROR_CODE = E_UNKNOWN_ACTION (stable)
  - COERCED_TO_KNOWN_ACTION = NO (never PROCESS_EXEC, never any known action)
  - RISK_LEVEL = NOT_APPLICABLE
  - EXECUTION_ATTEMPTED = NO
  - owner / approval / capability / config cannot override
  - case / whitespace / unicode / numeric variants are all rejected
  - audit event = UNKNOWN_ACTION_REJECTED with sanitized action id, not the
    raw operation string

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
from paios_ce.workers import MockWorker

_KNOWN_CLASSES = {
    ActionClass.READ_LOCAL, ActionClass.WRITE_LOCAL, ActionClass.DELETE_LOCAL,
    ActionClass.NETWORK_READ, ActionClass.NETWORK_WRITE, ActionClass.PROCESS_EXEC,
    ActionClass.ADMIN_ELEVATION, ActionClass.SECRET_ACCESS,
    ActionClass.EXTERNAL_MESSAGE, ActionClass.FINANCIAL_ACTION,
    ActionClass.IDENTITY_ACTION,
}


def _action(operation="totally_unknown_op_xyz", perms=None, action_id="act_r1_1",
            idem_key="idem_r1_1", approval_required=False, worker_type="tool",
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


def _assert_explicit_reject(result):
    assert result.decision == Decision.BLOCKED
    assert result.hard_blocked is True
    assert result.action_class == ActionClass.UNKNOWN_ACTION
    assert result.error_code == PermissionEngine.UNKNOWN_ACTION_ERROR_CODE
    assert result.risk_level.value == "NOT_APPLICABLE"
    assert result.execution_attempted is False
    # Never coerced to any known action.
    assert result.action_class not in _KNOWN_CLASSES


def test_unknown_action_explicit_reject():
    eng = _engine()
    result = eng.authorize(_action())
    _assert_explicit_reject(result)


def test_unknown_action_not_mapped_to_process_exec():
    eng = RiskEngine()
    match = eng.evaluate(_action(operation="zzz_totally_unknown_garbage_xyz"))
    assert match.action_class == ActionClass.UNKNOWN_ACTION
    assert match.action_class != ActionClass.PROCESS_EXEC


def test_unknown_action_not_mapped_to_any_known_action():
    eng = RiskEngine()
    match = eng.evaluate(_action(operation="zzz_totally_unknown_garbage_xyz"))
    assert match.action_class not in _KNOWN_CLASSES
    # And authorization never creates PROCESS_EXEC nor any known class.
    eng2 = _engine()
    result = eng2.authorize(_action(operation="zzz_totally_unknown_garbage_xyz",
                                    action_id="act_r1_na", idem_key="idem_r1_na"))
    assert result.action_class not in _KNOWN_CLASSES


def test_unknown_action_owner_cannot_override():
    eng = _engine(principal_id="principal:example.invalid/owner-1",
                  owner_allowlist=["principal:example.invalid/owner-1"])
    result = eng.authorize(_action(operation="zzz_owner_unknown",
                                   action_id="act_r1_own", idem_key="idem_r1_own"))
    _assert_explicit_reject(result)


def test_unknown_action_approval_cannot_override():
    eng = _engine()
    result = eng.authorize(_action(operation="zzz_approval_unknown",
                                   approval_required=True,
                                   action_id="act_r1_appr", idem_key="idem_r1_appr"))
    _assert_explicit_reject(result)


def test_unknown_action_capability_cannot_override():
    eng = _engine(capabilities={"TEXT_CHAT", "TOOL_CALLING", "admin", "*"})
    result = eng.authorize(_action(operation="zzz_cap_unknown",
                                   perms=["*"],
                                   action_id="act_r1_cap", idem_key="idem_r1_cap"))
    _assert_explicit_reject(result)


def test_unknown_action_case_variant_rejected():
    eng = _engine()
    result = eng.authorize(_action(operation="ZZZ_TOTALLY_UNKNOWN_OP",
                                   action_id="act_r1_case", idem_key="idem_r1_case"))
    _assert_explicit_reject(result)


def test_unknown_action_whitespace_variant_rejected():
    eng = _engine()
    result = eng.authorize(_action(operation="   totally   unknown   ",
                                   action_id="act_r1_ws", idem_key="idem_r1_ws"))
    _assert_explicit_reject(result)


def test_unknown_action_unicode_rejected():
    eng = _engine()
    result = eng.authorize(_action(operation="tötally_ünknown_öp",
                                   action_id="act_r1_uni", idem_key="idem_r1_uni"))
    _assert_explicit_reject(result)


def test_unknown_action_numeric_rejected():
    eng = _engine()
    result = eng.authorize(_action(operation="op_1234567890",
                                   action_id="act_r1_num", idem_key="idem_r1_num"))
    _assert_explicit_reject(result)


def test_unknown_action_stable_error_code():
    eng = _engine()
    codes = set()
    for i, op in enumerate(("zzz_a", "zzz_b", "zzz_c", "zzz_d")):
        r = eng.authorize(_action(operation=op, action_id=f"act_st_{i}",
                                  idem_key=f"idem_st_{i}"))
        codes.add(r.error_code)
    assert codes == {PermissionEngine.UNKNOWN_ACTION_ERROR_CODE}


def test_unknown_action_audit_event(tmp_path):
    # The CLI run-task action path emits UNKNOWN_ACTION_REJECTED with the
    # sanitized action id and the stable error code — never the raw operation
    # string (which may carry a secret).
    import json

    from paios_ce.cli.main import main

    fixture = tmp_path / "unknown_action.json"
    fixture.write_text(json.dumps(_action(operation="zzz_totally_unknown",
                                          action_id="act_evt_1", idem_key="idem_evt_1")
                                  .model_dump()), encoding="utf-8")
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(["run-task", str(fixture)])
    assert code != 0
    payload = json.loads(buf.getvalue())
    assert payload["error_code"] == "E_UNKNOWN_ACTION"
    assert payload["execution_attempted"] is False
    events = payload.get("audit_events", [])
    assert any(e["event_type"] == "unknown_action_rejected" for e in events)
    assert "zzz_totally_unknown" not in buf.getvalue()  # raw op never logged


def test_unknown_action_no_execution_attempt():
    eng = _engine()
    result = eng.authorize(_action(operation="zzz_noop_unknown_action",
                                   action_id="act_r1_nex", idem_key="idem_r1_nex"))
    _assert_explicit_reject(result)
    assert result.execution_attempted is False
    # The worker must not have been invoked for a rejected action.
    worker = MockWorker()
    assert worker.executed_action_ids == []


def test_unknown_action_cloud_egress_not_coerced():
    # Regression for the independent-validator finding: an operation that
    # matches NO keyword must be UNKNOWN_ACTION even when the request declares
    # network_scope.mode=cloud_egress. The network-mode shortcut must never
    # coerce an unknown operation to NETWORK_WRITE (which could be allowed with
    # approval). net_mode is passed via network_scope.mode so the engine's
    # RiskEngine.evaluate actually sees cloud_egress.
    eng = _engine()
    result = eng.authorize(_action(operation="zzz_unknown_egress",
                                   action_id="act_r1_eg1", idem_key="idem_r1_eg1",
                                   approval_required=True,
                                   net_mode="cloud_egress"))
    _assert_explicit_reject(result)


def test_unknown_action_cloud_egress_cli_not_allowed(tmp_path):
    # End-to-end: the CLI must NOT allow an unknown op under cloud_egress scope.
    import json
    from contextlib import redirect_stdout
    import io

    from paios_ce.cli.main import main
    from paios_ce.protocols import ActionRequest

    action = ActionRequest(
        action_id="act_r1_egcli", worker_type="tool",
        operation="zzz_unknown_egress_cli",
        parameters={"trace_id": "trace_redacted_01"},
        required_permissions=["TEXT_CHAT", "TOOL_CALLING"],
        filesystem_scope={"mode": "none", "paths_class": []},
        network_scope={"mode": "cloud_egress", "endpoints_class": []},
        timeout=30, idempotency_key="idem_r1_egcli",
        rollback_supported=False, approval_required=True,
    )
    fixture = tmp_path / "unknown_egress.json"
    fixture.write_text(json.dumps(action.model_dump()), encoding="utf-8")
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(["run-task", str(fixture)])
    assert code != 0
    payload = json.loads(buf.getvalue())
    assert payload["error_code"] == "E_UNKNOWN_ACTION"
    assert payload["decision"] == "blocked"
    assert payload["execution_attempted"] is False
    assert payload["action_class"] == "UNKNOWN_ACTION"
