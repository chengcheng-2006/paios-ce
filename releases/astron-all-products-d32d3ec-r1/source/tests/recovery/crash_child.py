"""TEST_ONLY child-process fixture for deterministic Phase 2 crash windows.

It is deliberately kept under ``tests`` and is never exposed through the
Astron CLI or a model-controlled execution surface.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time

from paios_ce.permissions import PermissionEngine, ScopeGuard
from paios_ce.protocols import ActionRequest, ActionResult, ActionStatus, RollbackStatus
from paios_ce.runtime import DurableActionRuntime
from paios_ce.state import SQLiteDurableStateStore


def _action(action_id: str, key: str, target: str = "same") -> ActionRequest:
    return ActionRequest(
        action_id=action_id,
        worker_type="tool",
        operation="read_file_in_scope",
        parameters={"target": target, "trace_id": "trace-phase2-crash"},
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


def _append_ledger(path: Path, line: str) -> None:
    descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(descriptor, (line + "\n").encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _success(request: ActionRequest) -> ActionResult:
    return ActionResult(
        action_id=request.action_id,
        status=ActionStatus.SUCCESS,
        outcome={"summary_class": "test-ledger-success"},
        trace_id="trace-phase2-crash",
        rollback_status=RollbackStatus.NOT_REQUIRED,
    )


def _failure(request: ActionRequest) -> ActionResult:
    return ActionResult(
        action_id=request.action_id,
        status=ActionStatus.FAILURE,
        outcome={"summary_class": "test-ledger-failure"},
        trace_id="trace-phase2-crash",
        rollback_status=RollbackStatus.NOT_REQUIRED,
    )


def _run_crash_window(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    ledger_path = Path(args.ledger)
    if args.window == "before_journal":
        SQLiteDurableStateStore(db_path).close()
        os._exit(69)

    class ExitAfterPreparedStore(SQLiteDurableStateStore):
        def prepare_authorized_action(self, *call_args, **call_kwargs):  # type: ignore[no-untyped-def]
            result = super().prepare_authorized_action(*call_args, **call_kwargs)
            os._exit(71)

    class ExitAfterTerminalStore(SQLiteDurableStateStore):
        def record_terminal(self, *call_args, **call_kwargs):  # type: ignore[no-untyped-def]
            result = super().record_terminal(*call_args, **call_kwargs)
            os._exit(73 if args.window == "after_success" else 74)

    if args.window == "after_authorized":
        store: SQLiteDurableStateStore = ExitAfterPreparedStore(db_path)
    elif args.window in {"after_success", "after_failure"}:
        store = ExitAfterTerminalStore(db_path)
    else:
        store = SQLiteDurableStateStore(db_path)
    runtime = DurableActionRuntime(_engine(store), store)
    request = _action(args.action_id, args.key)

    def side_effect_then_exit(action: ActionRequest) -> ActionResult:
        _append_ledger(ledger_path, action.idempotency_key or "missing")
        os._exit(72)

    def side_effect_success(action: ActionRequest) -> ActionResult:
        _append_ledger(ledger_path, action.idempotency_key or "missing")
        return _success(action)

    if args.window == "after_side_effect":
        runtime.execute(args.task_id, request, side_effect_then_exit)
    elif args.window == "after_success":
        runtime.execute(args.task_id, request, side_effect_success)
    elif args.window == "after_failure":
        runtime.execute(args.task_id, request, _failure)
    else:
        runtime.execute(args.task_id, request, _success)
    raise AssertionError("crash fixture unexpectedly returned")


def _run_race(args: argparse.Namespace) -> int:
    ready = Path(args.ready)
    go = Path(args.go)
    result = Path(args.result)
    ready.write_text(str(os.getpid()), encoding="utf-8")
    deadline = time.monotonic() + 5
    while not go.exists():
        if time.monotonic() >= deadline:
            raise SystemExit("race gate timed out")
        time.sleep(0.01)
    with SQLiteDurableStateStore(args.db) as store:
        decision = _engine(store).authorize(_action(args.action_id, args.key, args.target))
    result.write_text(
        json.dumps(
            {
                "decision": decision.decision.value,
                "is_replay": decision.is_replay,
                "error_code": decision.error_code,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["crash", "race"], required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--task-id", default="task-child")
    parser.add_argument("--action-id", default="action-child")
    parser.add_argument("--key", default="child-key")
    parser.add_argument("--ledger", default="unused-ledger")
    parser.add_argument(
        "--window",
        choices=["before_journal", "after_authorized", "after_side_effect", "after_success", "after_failure"],
    )
    parser.add_argument("--ready")
    parser.add_argument("--go")
    parser.add_argument("--result")
    parser.add_argument("--target", default="same")
    args = parser.parse_args(argv)
    if args.mode == "crash":
        if args.window is None:
            parser.error("--window is required for crash mode")
        return _run_crash_window(args)
    if not args.ready or not args.go or not args.result:
        parser.error("--ready, --go and --result are required for race mode")
    return _run_race(args)


if __name__ == "__main__":
    raise SystemExit(main())
