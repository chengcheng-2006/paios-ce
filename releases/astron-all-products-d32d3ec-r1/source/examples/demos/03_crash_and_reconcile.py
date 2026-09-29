#!/usr/bin/env python3
"""Astron demo 3 - a real process crash in the middle of one governed action.

The child process is killed after its external side effect is written but
before the terminal outcome is persisted. A second, separate process then opens
the same durable store and must answer: did that action happen?

Nothing here calls a model, a network or a real user system. The side effect is
one line appended to a ledger file inside a private temporary directory.

Run:  python examples/demos/03_crash_and_reconcile.py
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile

from paios_ce.permissions import PermissionEngine, ScopeGuard
from paios_ce.protocols import ActionRequest, ActionResult, ActionStatus, RollbackStatus
from paios_ce.runtime import DurableActionRuntime
from paios_ce.state import ReconciliationObservation, SQLiteDurableStateStore

REPO_ROOT = Path(__file__).resolve().parents[2]
CRASH_CHILD = REPO_ROOT / "tests" / "recovery" / "crash_child.py"

TASK_ID = "demo3-task"
KEY = "demo3-key"
# The child that crashed was authorized under this principal (see
# tests/recovery/crash_child.py). Reusing it is what lets the durable replay
# recognise the action as the same one.
ORIGINAL_PRINCIPAL = "principal:phase2/child"


def _line(text: str = "") -> None:
    print(text, flush=True)


def _action() -> ActionRequest:
    """Rebuild the same logical action after the restart.

    Same ``idempotency_key`` plus the same request content means the runtime can
    recognise it as the action that was already authorized, instead of trusting
    a model's claim that it never ran.
    """

    return ActionRequest(
        action_id="demo3-action",
        worker_type="tool",
        operation="read_file_in_scope",
        parameters={"target": "same", "trace_id": "trace_demo3"},
        required_permissions=["TEXT_CHAT"],
        filesystem_scope={"mode": "read", "paths_class": ["quarantine_temp"]},
        network_scope={"mode": "none", "endpoints_class": []},
        timeout=30,
        idempotency_key=KEY,
        rollback_supported=False,
        approval_required=False,
    )


def _engine(store: SQLiteDurableStateStore, principal_id: str = ORIGINAL_PRINCIPAL) -> PermissionEngine:
    return PermissionEngine(
        capabilities={"TEXT_CHAT"},
        principal_id=principal_id,
        scope_guard=ScopeGuard(fs_read_classes={"quarantine_temp"}),
        durable_state_store=store,
    )


def _ledger_count(path: Path) -> int:
    if not path.exists():
        return 0
    return len([line for line in path.read_text(encoding="utf-8").splitlines() if line])


def _success(request: ActionRequest) -> ActionResult:
    return ActionResult(
        action_id=request.action_id,
        status=ActionStatus.SUCCESS,
        outcome={"summary_class": "demo3-ledger-success"},
        trace_id="trace_demo3",
        rollback_status=RollbackStatus.NOT_REQUIRED,
    )


class LedgerReconciler:
    """A trusted, action-specific observer.

    It only reads evidence that already exists. It never executes the action -
    that is the difference between reconciliation and replay.
    """

    def __init__(self, ledger: Path, expected: int) -> None:
        self._ledger = ledger
        self._expected = expected

    def observe(self, journal):  # noqa: ANN001 - Protocol signature
        if _ledger_count(self._ledger) >= self._expected:
            _line(f"    observer: ledger has evidence for {self._expected} side effect(s) "
                  "-> CONFIRMED_SUCCEEDED")
            return ReconciliationObservation.CONFIRMED_SUCCEEDED
        _line("    observer: no evidence in the ledger -> NO_EVIDENCE (still uncertain)")
        return ReconciliationObservation.NO_EVIDENCE


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="astron-demo3-"))
    workdir.chmod(0o700)
    db = workdir / "state.sqlite"
    ledger = workdir / "ledger.txt"
    _line(f"[demo3] artifacts directory: {workdir}")
    _line(f"[demo3] durable store        : {db}")
    _line(f"[demo3] side-effect ledger   : {ledger}")
    _line()

    env = dict(os.environ)
    src = str(REPO_ROOT / "src")
    env["PYTHONPATH"] = src if not env.get("PYTHONPATH") else src + os.pathsep + env["PYTHONPATH"]

    _line("[demo3] step 1 - a child process executes the action and dies right after")
    _line("[demo3]          the side effect, before the terminal outcome is persisted")
    child = subprocess.run(
        [sys.executable, str(CRASH_CHILD), "--mode", "crash", "--window", "after_side_effect",
         "--db", str(db), "--ledger", str(ledger), "--task-id", TASK_ID,
         "--action-id", "demo3-action", "--key", KEY],
        cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=30, check=False,
    )
    _line(f"    child exit code: {child.returncode} (72 = killed inside the side-effect window)")
    if child.stderr:
        _line(f"    child stderr: {child.stderr.strip()}")
    _line(f"    ledger side effects after the crash: {_ledger_count(ledger)}")
    _line()

    _line("[demo3] step 2 - a NEW process opens the same store and asks what happened")
    with SQLiteDurableStateStore(db) as store:
        runtime = DurableActionRuntime(_engine(store), store)
        recovery = runtime.recover_task(TASK_ID)
        _line(f"    recover_task -> classification={recovery.classification.value}")
        _line(f"                   journal state={recovery.journal.current_state.value if recovery.journal else None}")
        assert recovery.journal is not None
        journal_id = recovery.journal.journal_id
        _line("    note: recover_task only reads durable facts. It never executes anything.")
        _line()

        _line("[demo3] step 3a - the same principal proposes the same action again")
        calls = 0

        def must_not_run(request: ActionRequest) -> ActionResult:
            nonlocal calls
            calls += 1
            return _success(request)

        guarded = runtime.execute(TASK_ID, _action(), must_not_run)
        _line(f"    authorization: {guarded.authorization.decision.value}"
              f" (is_replay={guarded.authorization.is_replay})")
        _line(f"    executor_invoked={guarded.executor_invoked} "
              f"needs_reconciliation={guarded.needs_reconciliation} "
              f"executor_calls={calls}")
        _line(f"    ledger still has {_ledger_count(ledger)} side effect(s)")
        _line("    the durable journal holds the action as UNCERTAIN, so an identical")
        _line("    proposal is refused execution rather than silently retried.")
        _line()

        _line("[demo3] step 3b - a different principal reuses the same idempotency key")
        other_engine = _engine(store, "principal:demo3/other-tenant")
        other = DurableActionRuntime(other_engine, store)
        mismatch = other.execute(TASK_ID, _action(), must_not_run)
        _line(f"    authorization: {mismatch.authorization.decision.value} "
              f"error_code={mismatch.authorization.error_code}")
        _line(f"    reason: {mismatch.authorization.reason}")
        _line(f"    executor_invoked={mismatch.executor_invoked} executor_calls={calls}")
        _line("    the key belongs to the original authorization identity; a different")
        _line("    security context cannot inherit that authority.")
        _line()

        _line("[demo3] step 4 - a trusted observer confirms the external effect")
        reconciled = runtime.reconcile(journal_id, LedgerReconciler(ledger, 1))
        _line(f"    observation={reconciled.observation.value} "
              f"new state={reconciled.journal.current_state.value}")
        _line()

        _line("[demo3] step 5 - after confirmation, the same action is a terminal fact")
        after = runtime.execute(TASK_ID, _action(), must_not_run)
        _line(f"    executor_invoked={after.executor_invoked} "
              f"executor_calls={calls} ledger={_ledger_count(ledger)}")
        _line()

        _line("[demo3] durable event trail (append-only action_events)")
        for event in store.journal_events(journal_id):
            _line(f"    {event.sequence:>2}  {event.state.value:<15} {event.event_kind}")
        checkpoint = store.checkpoint(TASK_ID)
        if checkpoint is not None:
            _line(f"    checkpoint: runtime_state={checkpoint.runtime_state} "
                  f"journal_sequence={checkpoint.journal_sequence}")
    _line()
    _line("[demo3] what this shows  : an interrupted action is reconstructed from the")
    _line("[demo3]                    journal, not guessed; UNCERTAIN never auto-retries;")
    _line("[demo3]                    confirming an external effect is a separate, trusted step.")
    _line("[demo3] what it does not   : prove exactly-once delivery against an arbitrary")
    _line("[demo3]                    external system. That needs an action-specific reconciler,")
    _line("[demo3]                    like the ledger observer above.")
    _line("[demo3] real cross-process regressions: python -m pytest tests/recovery -ra -q")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
