"""Versioned SQLite state, durable replay, and recovery contract tests.

These tests use only temporary local databases.  They do not invoke a shell,
network service, or production bounded tool.
"""

from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import stat
from typing import Any

import pytest

from paios_ce.permissions import Decision, PermissionEngine, PrincipalContext, ScopeGuard
from paios_ce.protocols import ActionRequest
from paios_ce.secrets import SecretRef, SecretValue
from paios_ce.state import (
    SQLiteDurableStateStore,
    StateStoreSchemaError,
    StateStoreUnavailable,
    VerificationStatus,
)
from paios_ce.state.private_files import (
    PrivateFileSecurityStatus,
    harden_private_file,
    verify_private_file,
)


def _action(
    action_id: str = "action-phase2",
    key: str = "phase2-key",
    *,
    operation: str = "read_file_in_scope",
    parameters: dict[str, Any] | None = None,
    permissions: list[str] | None = None,
) -> ActionRequest:
    return ActionRequest(
        action_id=action_id,
        worker_type="tool",
        operation=operation,
        parameters={"trace_id": "trace-phase2"} if parameters is None else parameters,
        required_permissions=["TEXT_CHAT"] if permissions is None else permissions,
        filesystem_scope={"mode": "read", "paths_class": ["quarantine_temp"]},
        network_scope={"mode": "none", "endpoints_class": []},
        timeout=30,
        idempotency_key=key,
        rollback_supported=False,
        approval_required=False,
    )


def _engine(store: SQLiteDurableStateStore, *, principal: str = "principal:phase2/user") -> PermissionEngine:
    return PermissionEngine(
        capabilities={"TEXT_CHAT"},
        owner_allowlist={"principal:phase2/owner"},
        principal_id=principal,
        scope_guard=ScopeGuard(fs_read_classes={"quarantine_temp"}),
        durable_state_store=store,
    )


def test_fresh_database_is_versioned_private_and_has_required_schema(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite"
    with SQLiteDurableStateStore(path) as store:
        assert store.settings.journal_mode == "WAL"
        assert store.settings.synchronous_mode == "FULL"
        assert store.settings.foreign_keys is True
        assert store.settings.busy_timeout_ms == 1000
        snapshot = store.schema_snapshot()
        assert {"schema_metadata", "authorization_replays", "action_journal", "checkpoints"}.issubset(snapshot)
        assert "reconciliation_events" in snapshot
        assert _engine(store).authorize(_action("permission-check", "permission-check")).decision is Decision.ALLOW
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(path) + suffix)
            if sidecar.exists():
                assert verify_private_file(
                    sidecar,
                    require_protected_windows_dacl=False,
                ) is PrivateFileSecurityStatus.VERIFIED_OWNER_PRIVATE
    assert verify_private_file(path) is PrivateFileSecurityStatus.VERIFIED_OWNER_PRIVATE
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT value FROM schema_metadata WHERE key = 'schema_version'"
        ).fetchone()[0] == "2"


def test_supported_v0_marker_migrates_deterministically_to_v2(tmp_path: Path) -> None:
    path = tmp_path / "v0.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE schema_metadata (key TEXT PRIMARY KEY NOT NULL, value TEXT NOT NULL)")
        connection.execute("INSERT INTO schema_metadata (key, value) VALUES ('schema_version', '0')")
    harden_private_file(path)
    with SQLiteDurableStateStore(path) as store:
        assert "action_events" in store.schema_snapshot()
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT value FROM schema_metadata WHERE key = 'schema_version'"
        ).fetchone()[0] == "2"


def test_complete_v1_database_is_validated_then_migrated_to_v2(tmp_path: Path) -> None:
    path = tmp_path / "v1.sqlite"
    with SQLiteDurableStateStore(path):
        pass
    with sqlite3.connect(path) as connection:
        connection.execute("DROP INDEX idx_task_verification_events_task")
        connection.execute("DROP TABLE task_verification_events")
        connection.execute("DROP TABLE task_verifications")
        connection.execute("UPDATE schema_metadata SET value = '1' WHERE key = 'schema_version'")
    with SQLiteDurableStateStore(path) as store:
        assert {"task_verifications", "task_verification_events"}.issubset(store.schema_snapshot())
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT value FROM schema_metadata WHERE key = 'schema_version'"
        ).fetchone()[0] == "2"


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode-bit implementation detail")
def test_existing_group_or_world_accessible_posix_database_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "insecure.sqlite"
    with sqlite3.connect(path):
        pass
    os.chmod(path, 0o640)
    with pytest.raises(StateStoreUnavailable, match="owner-private"):
        SQLiteDurableStateStore(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o640


@pytest.mark.parametrize("version", ["3", "not-a-version", "-1"])
def test_unsupported_or_malformed_schema_fails_closed_without_reset(tmp_path: Path, version: str) -> None:
    path = tmp_path / f"unsupported-{version}.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE schema_metadata (key TEXT PRIMARY KEY NOT NULL, value TEXT NOT NULL)")
        connection.execute("INSERT INTO schema_metadata (key, value) VALUES ('schema_version', ?)", (version,))
    harden_private_file(path)
    before = path.read_bytes()
    with pytest.raises(StateStoreSchemaError):
        SQLiteDurableStateStore(path)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    ("first", "retry", "expected"),
    [
        (_action("allow-1", "allow"), _action("allow-2", "allow"), Decision.ALLOW),
        (
            _action("deny-1", "deny", permissions=["MISSING"]),
            _action("deny-2", "deny", permissions=["MISSING"]),
            Decision.DENY,
        ),
        (
            _action("block-1", "block", operation="unregistered_phase2_action"),
            _action("block-2", "block", operation="unregistered_phase2_action"),
            Decision.BLOCKED,
        ),
    ],
)
def test_complete_authorization_decision_survives_real_store_restart(
    tmp_path: Path, first: ActionRequest, retry: ActionRequest, expected: Decision
) -> None:
    path = tmp_path / f"{first.idempotency_key}.sqlite"
    with SQLiteDurableStateStore(path) as first_store:
        original = _engine(first_store).authorize(first)
    with SQLiteDurableStateStore(path) as restarted_store:
        restored = _engine(restarted_store).authorize(retry)
    assert original.decision is expected
    assert restored.decision is expected
    assert restored.is_replay is True
    assert restored.reason == original.reason
    assert restored.error_code == original.error_code


@pytest.mark.parametrize(
    "changed",
    [
        _action("changed-param", "conflict", parameters={"target": "changed"}),
        _action("changed-action", "conflict", operation="fetch_health"),
    ],
)
def test_replay_mismatch_survives_restart_and_retains_original_record(
    tmp_path: Path, changed: ActionRequest
) -> None:
    path = tmp_path / "conflict.sqlite"
    with SQLiteDurableStateStore(path) as first_store:
        first = _engine(first_store).authorize(_action("original", "conflict"))
    with SQLiteDurableStateStore(path) as restarted_store:
        mismatch = _engine(restarted_store).authorize(changed)
        original = restarted_store.authorization_record("conflict")
    assert first.decision is Decision.ALLOW
    assert mismatch.decision is Decision.BLOCKED
    assert mismatch.error_code == PermissionEngine.IDEMPOTENCY_CONFLICT_ERROR_CODE
    assert original is not None and original.decision == "allow"


def test_invalid_durable_replay_record_fails_closed_with_stable_error(tmp_path: Path) -> None:
    path = tmp_path / "invalid-record.sqlite"
    with SQLiteDurableStateStore(path) as store:
        assert _engine(store).authorize(_action("original", "invalid-record")).decision is Decision.ALLOW
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE authorization_replays SET decision = 'invalid-decision' WHERE idempotency_key = 'invalid-record'"
        )
    with SQLiteDurableStateStore(path) as store:
        result = _engine(store).authorize(_action("retry", "invalid-record"))
    assert result.decision is Decision.BLOCKED
    assert result.error_code == PermissionEngine.IDEMPOTENCY_RECORD_INVALID_ERROR_CODE


def test_principal_and_security_context_mismatches_fail_closed_after_restart(tmp_path: Path) -> None:
    path = tmp_path / "identity-conflict.sqlite"
    with SQLiteDurableStateStore(path) as first_store:
        first = _engine(first_store).authorize(
            _action("first", "identity-conflict"), principal_context=PrincipalContext("principal:phase2/a")
        )
    with SQLiteDurableStateStore(path) as restarted_store:
        principal_mismatch = _engine(restarted_store).authorize(
            _action("second", "identity-conflict"), principal_context=PrincipalContext("principal:phase2/b")
        )
        changed_context_engine = PermissionEngine(
            capabilities={"TEXT_CHAT"},
            principal_id="principal:phase2/a",
            scope_guard=ScopeGuard(fs_read_classes={"different-scope"}),
            durable_state_store=restarted_store,
        )
        context_mismatch = changed_context_engine.authorize(_action("third", "identity-conflict"))
    assert first.decision is Decision.ALLOW
    assert principal_mismatch.error_code == PermissionEngine.IDEMPOTENCY_CONFLICT_ERROR_CODE
    assert context_mismatch.error_code == PermissionEngine.IDEMPOTENCY_CONFLICT_ERROR_CODE


def test_database_lock_blocks_authorization_without_memory_fallback(tmp_path: Path) -> None:
    path = tmp_path / "locked.sqlite"
    with SQLiteDurableStateStore(path, busy_timeout_ms=25) as store:
        locker = sqlite3.connect(path, isolation_level=None)
        try:
            locker.execute("BEGIN EXCLUSIVE")
            blocked = _engine(store).authorize(_action("locked", "locked-key"))
        finally:
            locker.execute("ROLLBACK")
            locker.close()
    assert blocked.decision is Decision.BLOCKED
    assert blocked.error_code == PermissionEngine.DURABLE_STATE_UNAVAILABLE_ERROR_CODE


def test_corrupt_database_is_preserved_and_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.sqlite"
    original = b"not a sqlite database phase2 evidence"
    path.write_bytes(original)
    harden_private_file(path)
    with pytest.raises(StateStoreUnavailable):
        SQLiteDurableStateStore(path)
    assert path.read_bytes() == original


class _NoResolveSecretRef(SecretRef):
    backend_id = "phase2-test"

    def __init__(self) -> None:
        super().__init__("secret-reference-should-not-persist")
        self.resolve_calls = 0

    def exists(self) -> bool:
        return True

    def resolve(self) -> SecretValue:
        self.resolve_calls += 1
        return SecretValue("actual-phase2-secret-value")


def test_sqlite_state_never_persists_secretref_reference_or_secret_value(tmp_path: Path) -> None:
    path = tmp_path / "secret.sqlite"
    secret = _NoResolveSecretRef()
    with SQLiteDurableStateStore(path) as store:
        result = _engine(store).authorize(
            _action("secret", "secret-key", parameters={"credential": secret})
        )
        assert result.decision is Decision.ALLOW
    contents = path.read_bytes()
    assert b"actual-phase2-secret-value" not in contents
    assert b"secret-reference-should-not-persist" not in contents
    assert secret.resolve_calls == 0
