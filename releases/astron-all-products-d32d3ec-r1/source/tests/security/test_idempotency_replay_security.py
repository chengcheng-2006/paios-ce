"""Phase-1 authorization replay security contract.

These tests cover in-memory authorization records only. They do not claim
durable execution idempotency or exactly-once side effects.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any

import pytest
from pydantic import BaseModel

from paios_ce.permissions import Decision, PermissionEngine, PrincipalContext, ScopeGuard
from paios_ce.protocols import ActionRequest
from paios_ce.secrets import SecretRef, SecretValue


def _engine(**overrides: Any) -> PermissionEngine:
    defaults = {
        "capabilities": {"TEXT_CHAT", "fs.read"},
        "owner_allowlist": {"principal:phase1/owner"},
        "principal_id": "principal:phase1/user",
        "scope_guard": ScopeGuard(fs_read_classes={"quarantine_temp"}),
    }
    defaults.update(overrides)
    return PermissionEngine(**defaults)


def _action(
    action_id: str,
    key: str | None,
    *,
    operation: str = "read_file_in_scope",
    parameters: dict[str, Any] | None = None,
    permissions: list[str] | None = None,
    fs_paths: list[str] | None = None,
) -> ActionRequest:
    return ActionRequest(
        action_id=action_id,
        worker_type="tool",
        operation=operation,
        parameters={"trace_id": "trace_phase1"} if parameters is None else parameters,
        required_permissions=["TEXT_CHAT"] if permissions is None else permissions,
        filesystem_scope={"mode": "read", "paths_class": ["quarantine_temp"] if fs_paths is None else fs_paths},
        network_scope={"mode": "none", "endpoints_class": []},
        timeout=30,
        idempotency_key=key,
        rollback_supported=False,
        approval_required=False,
    )


def test_exact_allow_replay_preserves_full_decision() -> None:
    engine = _engine()
    first = engine.authorize(_action("allow-1", "allow-key"))
    retry = engine.authorize(_action("allow-2", "allow-key"))

    assert first.decision is Decision.ALLOW
    assert retry.decision is Decision.ALLOW
    assert retry.is_replay is True
    assert retry.reason == first.reason
    assert retry.action_class == first.action_class
    assert retry.risk_level == first.risk_level
    assert retry.request_fingerprint == first.request_fingerprint


def test_exact_deny_replay_preserves_full_decision() -> None:
    engine = _engine()
    first = engine.authorize(_action("deny-1", "deny-key", permissions=["MISSING_CAPABILITY"]))
    retry = engine.authorize(_action("deny-2", "deny-key", permissions=["MISSING_CAPABILITY"]))

    assert first.decision is Decision.DENY
    assert retry.decision is Decision.DENY
    assert retry.is_replay is True
    assert retry.reason == first.reason
    assert retry.error_code == first.error_code


def test_exact_block_replay_preserves_full_decision() -> None:
    engine = _engine()
    first = engine.authorize(_action("block-1", "block-key", operation="unregistered_phase1_action"))
    retry = engine.authorize(_action("block-2", "block-key", operation="unregistered_phase1_action"))

    assert first.decision is Decision.BLOCKED
    assert retry.decision is Decision.BLOCKED
    assert retry.is_replay is True
    assert retry.reason == first.reason
    assert retry.error_code == PermissionEngine.UNKNOWN_ACTION_ERROR_CODE


@pytest.mark.parametrize(
    ("first_parameters", "retry_parameters"),
    [
        ({"target": "one"}, {"target": "two"}),
        ({"target": "one"}, {"target": "one", "added": True}),
        ({"target": "one", "remove_me": None}, {"target": "one"}),
    ],
)
def test_parameter_changes_fail_closed_and_retain_original(
    first_parameters: dict[str, Any], retry_parameters: dict[str, Any]
) -> None:
    engine = _engine()
    first = engine.authorize(_action("params-1", "params-key", parameters=first_parameters))
    original_record = engine._authorization_replays["params-key"]
    retry = engine.authorize(_action("params-2", "params-key", parameters=retry_parameters))

    assert first.decision is Decision.ALLOW
    assert retry.decision is Decision.BLOCKED
    assert retry.error_code == PermissionEngine.IDEMPOTENCY_CONFLICT_ERROR_CODE
    assert engine._authorization_replays["params-key"] is original_record


@pytest.mark.parametrize(
    ("operation", "permissions"),
    [
        ("fetch_health", ["TEXT_CHAT"]),
        ("read_file_in_scope", ["fs.read"]),
    ],
)
def test_action_or_capability_changes_fail_closed(operation: str, permissions: list[str]) -> None:
    engine = _engine()
    first = engine.authorize(_action("action-1", "action-key"))
    retry = engine.authorize(
        _action("action-2", "action-key", operation=operation, permissions=permissions)
    )

    assert first.decision is Decision.ALLOW
    assert retry.decision is Decision.BLOCKED
    assert retry.error_code == PermissionEngine.IDEMPOTENCY_CONFLICT_ERROR_CODE


def test_changed_trusted_principal_fails_closed() -> None:
    engine = _engine()
    principal_a = PrincipalContext("principal:phase1/a")
    principal_b = PrincipalContext("principal:phase1/b")
    first = engine.authorize(_action("principal-1", "principal-key"), principal_context=principal_a)
    original_record = engine._authorization_replays["principal-key"]
    retry = engine.authorize(_action("principal-2", "principal-key"), principal_context=principal_b)

    assert first.decision is Decision.ALLOW
    assert first.trusted_principal_id == principal_a.principal_id
    assert retry.decision is Decision.BLOCKED
    assert retry.error_code == PermissionEngine.IDEMPOTENCY_CONFLICT_ERROR_CODE
    assert engine._authorization_replays["principal-key"] is original_record


def test_spoofed_payload_principal_never_overrides_runtime_context() -> None:
    engine = _engine()
    runtime_principal = PrincipalContext("principal:phase1/runtime-user")
    request = _action(
        "spoof-1",
        "spoof-key",
        parameters={
            "principal": "principal:phase1/admin",
            "principal_id": "principal:phase1/admin",
            "actor": "admin",
            "user": "admin",
        },
    )
    result = engine.authorize(request, principal_context=runtime_principal)
    record = engine._authorization_replays["spoof-key"]

    assert result.decision is Decision.ALLOW
    assert result.trusted_principal_id == runtime_principal.principal_id
    assert record.identity.principal_id == runtime_principal.principal_id


class _NestedPayload(BaseModel):
    settings: dict[str, Any]


def test_nested_canonicalization_ignores_mapping_order_but_detects_value_change() -> None:
    engine = _engine()
    first_payload = _NestedPayload(
        settings={"nested": {"b": [True, 2, None], "a": "same"}}
    )
    equal_payload = _NestedPayload(
        settings={"nested": {"a": "same", "b": [True, 2.0, None]}}
    )
    changed_payload = _NestedPayload(
        settings={"nested": {"a": "changed", "b": [True, 2, None]}}
    )

    first = engine.authorize(_action("nested-1", "nested-key", parameters={"payload": first_payload}))
    equal_retry = engine.authorize(_action("nested-2", "nested-key", parameters={"payload": equal_payload}))
    changed_retry = engine.authorize(_action("nested-3", "nested-key", parameters={"payload": changed_payload}))

    assert first.decision is Decision.ALLOW
    assert equal_retry.decision is Decision.ALLOW
    assert equal_retry.is_replay is True
    assert changed_retry.decision is Decision.BLOCKED
    assert changed_retry.error_code == PermissionEngine.IDEMPOTENCY_CONFLICT_ERROR_CODE


def test_mutating_caller_parameters_after_first_authorization_cannot_mutate_record() -> None:
    engine = _engine()
    parameters = {"nested": {"target": "one"}}
    first = engine.authorize(_action("mutable-1", "mutable-key", parameters=parameters))
    original_record = engine._authorization_replays["mutable-key"]
    parameters["nested"]["target"] = "two"
    retry = engine.authorize(_action("mutable-2", "mutable-key", parameters=parameters))

    assert first.decision is Decision.ALLOW
    assert retry.decision is Decision.BLOCKED
    assert retry.error_code == PermissionEngine.IDEMPOTENCY_CONFLICT_ERROR_CODE
    assert engine._authorization_replays["mutable-key"] is original_record


def test_security_context_change_cannot_reuse_cached_allow() -> None:
    scope = ScopeGuard(fs_read_classes={"quarantine_temp"})
    engine = _engine(scope_guard=scope)
    first = engine.authorize(_action("context-1", "context-key"))
    original_record = engine._authorization_replays["context-key"]
    scope.fs_read.clear()
    retry = engine.authorize(_action("context-2", "context-key"))

    assert first.decision is Decision.ALLOW
    assert retry.decision is Decision.BLOCKED
    assert retry.error_code == PermissionEngine.IDEMPOTENCY_CONFLICT_ERROR_CODE
    assert engine._authorization_replays["context-key"] is original_record


class _SpySecretRef(SecretRef):
    backend_id = "spy"

    def __init__(self, ref_id: str) -> None:
        super().__init__(ref_id)
        self.resolve_calls = 0

    def exists(self) -> bool:
        return True

    def resolve(self) -> SecretValue:
        self.resolve_calls += 1
        return SecretValue("phase1-secret-value")


def test_secretref_fingerprint_uses_reference_without_resolution() -> None:
    engine = _engine()
    first_ref = _SpySecretRef("credential-slot")
    second_ref = _SpySecretRef("credential-slot")
    first = engine.authorize(_action("secret-1", "secret-key", parameters={"credential": first_ref}))
    retry = engine.authorize(_action("secret-2", "secret-key", parameters={"credential": second_ref}))

    assert first.decision is Decision.ALLOW
    assert retry.decision is Decision.ALLOW
    assert retry.is_replay is True
    assert first_ref.resolve_calls == 0
    assert second_ref.resolve_calls == 0


def test_keyless_request_keeps_normal_flow_and_duplicate_action_protection() -> None:
    engine = _engine()
    first = engine.authorize(_action("keyless-1", None))
    duplicate = engine.authorize(_action("keyless-1", None))

    assert first.decision is Decision.ALLOW
    assert first.is_replay is False
    assert duplicate.decision is Decision.DENY
    assert duplicate.is_replay is True


def test_empty_idempotency_key_remains_invalid_at_public_contract_boundary() -> None:
    with pytest.raises(Exception):
        _action("empty-key", "")


def test_uncanonicalizable_request_and_corrupt_record_fail_closed() -> None:
    engine = _engine()
    bad = engine.authorize(_action("bad-1", "bad-key", parameters={"unsupported": object()}))
    engine._authorization_replays["corrupt-key"] = object()  # type: ignore[assignment]
    corrupt = engine.authorize(_action("corrupt-1", "corrupt-key"))

    assert bad.decision is Decision.BLOCKED
    assert bad.error_code == PermissionEngine.IDEMPOTENCY_FINGERPRINT_ERROR_CODE
    assert "bad-key" not in engine._authorization_replays
    assert corrupt.decision is Decision.BLOCKED
    assert corrupt.error_code == PermissionEngine.IDEMPOTENCY_RECORD_INVALID_ERROR_CODE


def test_concurrent_first_authorizations_are_serialized_into_one_record() -> None:
    engine = _engine()
    barrier = Barrier(2)

    def _authorize(action_id: str):
        barrier.wait()
        return engine.authorize(_action(action_id, "concurrent-key"))

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(_authorize, ["concurrent-1", "concurrent-2"]))

    assert {result.decision for result in results} == {Decision.ALLOW}
    assert sorted(result.is_replay for result in results) == [False, True]
    assert len(engine._authorization_replays) == 1


def test_unknown_action_remains_deny_by_default() -> None:
    engine = _engine()
    result = engine.authorize(_action("unknown-1", "unknown-key", operation="unknown_phase1_action"))

    assert result.decision is Decision.BLOCKED
    assert result.error_code == PermissionEngine.UNKNOWN_ACTION_ERROR_CODE
