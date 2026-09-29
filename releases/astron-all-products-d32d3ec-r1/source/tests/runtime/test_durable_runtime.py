"""Action journal, checkpoint, and reconciliation semantics."""

from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any

import pytest

from paios_ce.permissions import PermissionEngine, ScopeGuard
from paios_ce.protocols import ActionRequest, ActionResult, ActionStatus, RollbackStatus
from paios_ce.runtime import DurableActionRuntime
from paios_ce.state import (
    ActionState,
    ReconciliationObservation,
    RecoveryClassification,
    SQLiteDurableStateStore,
    StateTransitionError,
)


def _action(action_id: str = "action-phase2", key: str = "phase2-key", *, parameters: dict[str, Any] | None = None) -> ActionRequest:
    return ActionRequest(
        action_id=action_id,
        worker_type="tool",
        operation="read_file_in_scope",
        parameters={"trace_id": "trace-phase2"} if parameters is None else parameters,
        required_permissions=["TEXT_CHAT"],
        filesystem_scope={"mode": "read", "paths_class": ["quarantine_temp"]},
        network_scope={"mode": "none", "endpoints_class": []},
        timeout=30,
        idempotency_key=key,
        rollback_supported=False,
        approval_required=False,
    )


def _engine(store: SQLiteDurableStateStore) -> PermissionEngine:
    return PermissionEngine(
        capabilities={"TEXT_CHAT"},
        principal_id="principal:phase2/user",
        scope_guard=ScopeGuard(fs_read_classes={"quarantine_temp"}),
        durable_state_store=store,
    )


def _success(request: ActionRequest) -> ActionResult:
    return ActionResult(
        action_id=request.action_id,
        status=ActionStatus.SUCCESS,
        outcome={"summary_class": "phase2-test-success"},
        trace_id="trace-phase2",
        rollback_status=RollbackStatus.NOT_REQUIRED,
    )


def test_runtime_journal_events_checkpoints_and_terminal_monotonicity(tmp_path: Path) -> None:
    with SQLiteDurableStateStore(tmp_path / "runtime.sqlite") as store:
        runtime = DurableActionRuntime(_engine(store), store)
        result = runtime.execute("task-runtime", _action(), _success)
        assert result.executor_invoked is True
        assert result.journal is not None
        assert result.journal.current_state is ActionState.SUCCEEDED
        assert result.action_result is not None and result.action_result.status is ActionStatus.SUCCESS
        checkpoint = store.checkpoint("task-runtime")
        assert checkpoint is not None
        assert checkpoint.runtime_state == "ACTION_TERMINAL"
        assert checkpoint.journal_sequence == result.journal.journal_sequence
        assert [event.state for event in store.journal_events(result.journal.journal_id)] == [
            ActionState.RECORDED,
            ActionState.AUTHORIZED,
            ActionState.ATTEMPT_STARTED,
            ActionState.SUCCEEDED,
        ]
        with pytest.raises(StateTransitionError):
            store.record_attempt_started(result.journal.journal_id)
        with pytest.raises(StateTransitionError):
            store.record_terminal(result.journal.journal_id, ActionState.FAILED)


def test_pre_attempt_recovery_is_safe_but_attempt_without_result_is_uncertain(tmp_path: Path) -> None:
    path = tmp_path / "recover.sqlite"
    with SQLiteDurableStateStore(path) as initial_store:
        engine = _engine(initial_store)
        request = _action("safe", "safe-key")
        allowed = engine.authorize(request)
        identity = DurableActionRuntime._identity_from_result(request, allowed)
        journal = initial_store.prepare_authorized_action(
            "task-safe", identity, DurableActionRuntime._decision_from_result(allowed)
        )
        assert journal.current_state is ActionState.AUTHORIZED
    with SQLiteDurableStateStore(path) as restarted_store:
        assert restarted_store.recover_task("task-safe").classification is RecoveryClassification.SAFE_TO_CONTINUE
        started = restarted_store.record_attempt_started(journal.journal_id)
        assert started.current_state is ActionState.ATTEMPT_STARTED
    with SQLiteDurableStateStore(path) as restarted_again:
        recovery = restarted_again.recover_task("task-safe")
        assert recovery.classification is RecoveryClassification.NEEDS_RECONCILIATION
        assert recovery.journal is not None and recovery.journal.current_state is ActionState.UNCERTAIN
        checkpoint = restarted_again.checkpoint("task-safe")
        assert checkpoint is not None and checkpoint.runtime_state == "RECOVERY_REQUIRED"


@pytest.mark.parametrize(
    ("observation", "expected"),
    [
        (ReconciliationObservation.CONFIRMED_SUCCEEDED, ActionState.SUCCEEDED),
        (ReconciliationObservation.CONFIRMED_FAILED, ActionState.FAILED),
        (ReconciliationObservation.CONFIRMED_NOT_APPLIED, ActionState.RETRY_ELIGIBLE),
        (ReconciliationObservation.NO_EVIDENCE, ActionState.UNCERTAIN),
    ],
)
def test_reconciliation_contract_is_explicit_and_persisted(
    tmp_path: Path, observation: ReconciliationObservation, expected: ActionState
) -> None:
    with SQLiteDurableStateStore(tmp_path / f"reconcile-{observation.value}.sqlite") as store:
        engine = _engine(store)
        request = _action("reconcile", f"reconcile-{observation.value}")
        allowed = engine.authorize(request)
        identity = DurableActionRuntime._identity_from_result(request, allowed)
        journal = store.prepare_authorized_action(
            "task-reconcile", identity, DurableActionRuntime._decision_from_result(allowed)
        )
        store.record_attempt_started(journal.journal_id)
        uncertain = store.mark_uncertain(journal.journal_id)
        reconciled = store.reconcile(uncertain.journal_id, observation)
        assert reconciled.journal.current_state is expected
        events = store.journal_events(journal.journal_id)
        assert events[-1].state is expected
        if observation is ReconciliationObservation.NO_EVIDENCE:
            assert events[-1].event_kind == "RECONCILIATION_NO_EVIDENCE"


def test_uncertain_action_never_invokes_executor_without_reconciliation(tmp_path: Path) -> None:
    with SQLiteDurableStateStore(tmp_path / "no-retry.sqlite") as store:
        runtime = DurableActionRuntime(_engine(store), store)
        request = _action("uncertain", "no-retry-key")
        allowed = runtime._engine.authorize(request)
        identity = DurableActionRuntime._identity_from_result(request, allowed)
        journal = store.prepare_authorized_action(
            "task-no-retry", identity, DurableActionRuntime._decision_from_result(allowed)
        )
        store.record_attempt_started(journal.journal_id)
        store.mark_uncertain(journal.journal_id)
        calls = 0

        def must_not_run(action: ActionRequest) -> ActionResult:
            nonlocal calls
            calls += 1
            return _success(action)

        result = runtime.execute("task-no-retry", _action("retry", "no-retry-key"), must_not_run)
        assert result.needs_reconciliation is True
        assert result.executor_invoked is False
        assert calls == 0


def test_multiple_constructed_unresolved_actions_fail_closed_on_recovery(tmp_path: Path) -> None:
    path = tmp_path / "multiple-unresolved.sqlite"
    with SQLiteDurableStateStore(path) as store:
        engine = _engine(store)
        first_request = _action("first", "first-key")
        first_allowed = engine.authorize(first_request)
        first_identity = DurableActionRuntime._identity_from_result(first_request, first_allowed)
        first = store.prepare_authorized_action(
            "task-multiple", first_identity, DurableActionRuntime._decision_from_result(first_allowed)
        )
        store.record_attempt_started(first.journal_id)
        # This creates a valid second authorization record but, by design, no
        # second action journal while the first attempt remains unresolved.
        second_request = _action("second", "second-key")
        assert engine.authorize(second_request).decision.value == "allow"
    # Construct a second unresolved row at the storage boundary to prove that
    # recovery refuses to choose an ordering even for a malformed DB history.
    with sqlite3.connect(path) as connection:
        authorization = connection.execute(
            "SELECT * FROM authorization_replays WHERE idempotency_key = 'second-key'"
        ).fetchone()
        assert authorization is not None
        connection.execute(
            """
            INSERT INTO action_journal (
                journal_id, task_id, action_identity, idempotency_key, principal_id,
                request_fingerprint, security_context_fingerprint, authorization_decision,
                current_state, journal_sequence, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "f" * 64, "task-multiple", "f" * 64, "second-key",
                authorization[1], authorization[2], authorization[3], "allow",
                "UNCERTAIN", 1, "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00",
            ),
        )
    with SQLiteDurableStateStore(path) as store:
        with pytest.raises(StateTransitionError, match="multiple unresolved"):
            store.recover_task("task-multiple")
