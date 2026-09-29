"""Phase-0 idempotency/replay defects closed by the Phase-1 contract."""

from __future__ import annotations

from paios_ce.permissions import Decision, PermissionEngine, ScopeGuard
from paios_ce.protocols import ActionRequest


def _engine() -> PermissionEngine:
    return PermissionEngine(
        capabilities={"TEXT_CHAT"},
        owner_allowlist={"principal:phase0/owner"},
        principal_id="principal:phase0/owner",
        scope_guard=ScopeGuard(fs_read_classes={"quarantine_temp"}),
    )


def _action(
    action_id: str,
    key: str,
    *,
    operation: str = "read_file_in_scope",
    parameters: dict[str, str] | None = None,
) -> ActionRequest:
    return ActionRequest(
        action_id=action_id,
        worker_type="tool",
        operation=operation,
        parameters=parameters or {"trace_id": "phase0"},
        required_permissions=["TEXT_CHAT"],
        filesystem_scope={"mode": "read", "paths_class": ["quarantine_temp"]},
        network_scope={"mode": "none", "endpoints_class": []},
        timeout=30,
        idempotency_key=key,
        rollback_supported=False,
        approval_required=False,
    )


def test_idempotency_retry_preserves_blocked_decision() -> None:
    engine = _engine()
    first = engine.authorize(_action("block-1", "block-key", operation="phase0_unknown_action"))
    retry = engine.authorize(_action("block-2", "block-key", operation="phase0_unknown_action"))

    assert first.decision is Decision.BLOCKED
    assert retry.is_replay is True
    assert retry.decision is Decision.BLOCKED
    assert retry.error_code == PermissionEngine.UNKNOWN_ACTION_ERROR_CODE
    assert retry.reason == first.reason


def test_idempotency_retry_rejects_changed_parameters() -> None:
    engine = _engine()
    first = engine.authorize(
        _action("allow-1", "parameter-key", parameters={"trace_id": "phase0", "target": "one"})
    )
    retry = engine.authorize(
        _action("allow-2", "parameter-key", parameters={"trace_id": "phase0", "target": "two"})
    )

    assert first.decision is Decision.ALLOW
    assert retry.is_replay is False
    assert retry.decision is Decision.BLOCKED
    assert retry.error_code == PermissionEngine.IDEMPOTENCY_CONFLICT_ERROR_CODE
