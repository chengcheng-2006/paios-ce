"""Real-subprocess recovery evidence for the Phase 2 durable runtime."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from paios_ce.permissions import PermissionEngine, ScopeGuard
from paios_ce.protocols import ActionRequest, ActionResult, ActionStatus, RollbackStatus
from paios_ce.runtime import DurableActionRuntime
from paios_ce.state import (
    ReconciliationObservation,
    RecoveryClassification,
    SQLiteDurableStateStore,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHILD = _REPO_ROOT / "tests" / "recovery" / "crash_child.py"


def _action(action_id: str, key: str) -> ActionRequest:
    return ActionRequest(
        action_id=action_id,
        worker_type="tool",
        operation="read_file_in_scope",
        parameters={"target": "same", "trace_id": "trace-phase2-crash"},
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
        principal_id="principal:phase2/child",
        scope_guard=ScopeGuard(fs_read_classes={"quarantine_temp"}),
        durable_state_store=store,
    )


def _environment() -> dict[str, str]:
    env = dict(os.environ)
    source = str(_REPO_ROOT / "src")
    env["PYTHONPATH"] = source if not env.get("PYTHONPATH") else source + os.pathsep + env["PYTHONPATH"]
    return env


def _crash(tmp_path: Path, window: str, *, task_id: str, key: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable, str(_CHILD), "--mode", "crash", "--db", str(tmp_path / "state.sqlite"),
            "--ledger", str(tmp_path / "ledger.txt"), "--window", window,
            "--task-id", task_id, "--action-id", "child-action", "--key", key,
        ],
        cwd=_REPO_ROOT,
        env=_environment(),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def _ledger_count(path: Path) -> int:
    return 0 if not path.exists() else len([line for line in path.read_text(encoding="utf-8").splitlines() if line])


def _success(request: ActionRequest) -> ActionResult:
    return ActionResult(
        action_id=request.action_id,
        status=ActionStatus.SUCCESS,
        outcome={"summary_class": "restart-test-success"},
        trace_id="trace-phase2-crash",
        rollback_status=RollbackStatus.NOT_REQUIRED,
    )


@pytest.mark.parametrize(
    ("window", "returncode", "expected"),
    [
        ("before_journal", 69, RecoveryClassification.NO_ATTEMPT),
        ("after_authorized", 71, RecoveryClassification.SAFE_TO_CONTINUE),
    ],
)
def test_real_child_pre_attempt_windows_classify_without_fabricating_execution(
    tmp_path: Path, window: str, returncode: int, expected: RecoveryClassification
) -> None:
    task_id = f"task-{window}"
    key = f"key-{window}"
    child = _crash(tmp_path, window, task_id=task_id, key=key)
    assert child.returncode == returncode
    assert child.stderr == ""
    with SQLiteDurableStateStore(tmp_path / "state.sqlite") as store:
        runtime = DurableActionRuntime(_engine(store), store)
        recovery = runtime.recover_task(task_id)
        assert recovery.classification is expected
        if expected is RecoveryClassification.SAFE_TO_CONTINUE:
            result = runtime.execute(task_id, _action("restart-action", key), _success)
            assert result.executor_invoked is True


def test_real_side_effect_before_result_crash_reconciles_without_duplicate(tmp_path: Path) -> None:
    task_id = "task-side-effect"
    key = "key-side-effect"
    ledger = tmp_path / "ledger.txt"
    child = _crash(tmp_path, "after_side_effect", task_id=task_id, key=key)
    assert child.returncode == 72
    assert _ledger_count(ledger) == 1

    class LedgerReconciler:
        def observe(self, journal):  # type: ignore[no-untyped-def]
            return (
                ReconciliationObservation.CONFIRMED_SUCCEEDED
                if _ledger_count(ledger) == 1
                else ReconciliationObservation.NO_EVIDENCE
            )

    with SQLiteDurableStateStore(tmp_path / "state.sqlite") as store:
        runtime = DurableActionRuntime(_engine(store), store)
        recovered = runtime.recover_task(task_id)
        assert recovered.classification is RecoveryClassification.NEEDS_RECONCILIATION
        assert recovered.journal is not None
        reconciled = runtime.reconcile(recovered.journal.journal_id, LedgerReconciler())
        assert reconciled.journal.current_state.value == "SUCCEEDED"
        calls = 0

        def must_not_execute(request: ActionRequest) -> ActionResult:
            nonlocal calls
            calls += 1
            return _success(request)

        repeated = runtime.execute(task_id, _action("restart-action", key), must_not_execute)
        assert repeated.executor_invoked is False
        assert calls == 0
    assert _ledger_count(ledger) == 1


def test_real_success_before_response_crash_is_terminal_without_duplicate(tmp_path: Path) -> None:
    task_id = "task-success"
    key = "key-success"
    ledger = tmp_path / "ledger.txt"
    child = _crash(tmp_path, "after_success", task_id=task_id, key=key)
    assert child.returncode == 73
    assert _ledger_count(ledger) == 1
    with SQLiteDurableStateStore(tmp_path / "state.sqlite") as store:
        runtime = DurableActionRuntime(_engine(store), store)
        recovered = runtime.recover_task(task_id)
        assert recovered.classification is RecoveryClassification.TERMINAL_SUCCESS
        result = runtime.execute(task_id, _action("restart-action", key), _success)
        assert result.executor_invoked is False
    assert _ledger_count(ledger) == 1


def test_real_failure_before_response_crash_remains_terminal_failure(tmp_path: Path) -> None:
    task_id = "task-failure"
    key = "key-failure"
    child = _crash(tmp_path, "after_failure", task_id=task_id, key=key)
    assert child.returncode == 74
    with SQLiteDurableStateStore(tmp_path / "state.sqlite") as store:
        runtime = DurableActionRuntime(_engine(store), store)
        recovered = runtime.recover_task(task_id)
        assert recovered.classification is RecoveryClassification.TERMINAL_FAILURE
        result = runtime.execute(task_id, _action("restart-action", key), _success)
        assert result.executor_invoked is False


@pytest.mark.parametrize(
    ("targets", "expected_decisions", "expected_replays", "expected_error_codes"),
    [
        (("same", "same"), {"allow"}, 1, {None}),
        (
            ("one", "two"),
            {"allow", "blocked"},
            0,
            {None, PermissionEngine.IDEMPOTENCY_CONFLICT_ERROR_CODE},
        ),
    ],
)
def test_cross_process_same_key_race_has_one_authoritative_record(
    tmp_path: Path,
    targets: tuple[str, str],
    expected_decisions: set[str],
    expected_replays: int,
    expected_error_codes: set[str | None],
) -> None:
    db = tmp_path / "race.sqlite"
    # Materialize schema before releasing the two owned child processes.
    SQLiteDurableStateStore(db).close()
    go = tmp_path / "go"
    commands: list[list[str]] = []
    for index, target in enumerate(targets, start=1):
        commands.append([
            sys.executable, str(_CHILD), "--mode", "race", "--db", str(db),
            "--key", "cross-process-key", "--action-id", f"race-{index}",
            "--target", target, "--ready", str(tmp_path / f"ready-{index}"),
            "--go", str(go), "--result", str(tmp_path / f"result-{index}.json"),
        ])
    children = [
        subprocess.Popen(command, cwd=_REPO_ROOT, env=_environment(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for command in commands
    ]
    deadline = time.monotonic() + 5
    while not all((tmp_path / f"ready-{index}").exists() for index in (1, 2)):
        if time.monotonic() >= deadline:
            for child in children:
                if child.poll() is None:
                    child.terminate()
            for child in children:
                try:
                    child.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.communicate(timeout=5)
            pytest.fail("owned authorization-race children did not become ready")
        time.sleep(0.01)
    go.write_text("release", encoding="utf-8")
    outputs = [child.communicate(timeout=10) for child in children]
    assert all(child.returncode == 0 for child in children)
    assert all(stderr == "" for _, stderr in outputs)
    assert all(child.poll() is not None for child in children)
    results = [
        json.loads((tmp_path / f"result-{index}.json").read_text(encoding="utf-8"))
        for index in (1, 2)
    ]
    assert {result["decision"] for result in results} == expected_decisions
    assert [result["is_replay"] for result in results].count(True) == expected_replays
    assert {result["error_code"] for result in results} == expected_error_codes
    with SQLiteDurableStateStore(db) as store:
        assert store.authorization_record("cross-process-key") is not None
