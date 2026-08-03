"""paios-ce CLI entry point (argparse-based; no typer/rich dependency).

Stable exit codes:
  0  success
  2  usage error
  3  configuration error / validation failure
  4  task denied (permission/confirmation)
  5  blocked (critical / admin / shell)
  6  internal error

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from ..config import ConfigLoadError, load_runtime
from ..demo import run_demo
from ..health import health_check

_EXIT_OK = 0
_EXIT_USAGE = 2
_EXIT_CONFIG = 3
_EXIT_DENIED = 4
_EXIT_BLOCKED = 5
_EXIT_INTERNAL = 6


def _emit(payload: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n")


def _cmd_demo(args: argparse.Namespace) -> int:
    result = run_demo(user_input=args.input or "summarize my task list")
    _emit({"command": "demo", "result": result.as_dict()})
    return _EXIT_OK


def _cmd_health(args: argparse.Namespace) -> int:
    checks = health_check()
    _emit({"command": "health", "components": [c.to_dict() for c in checks]})
    return _EXIT_OK


def _cmd_validate_config(args: argparse.Namespace) -> int:
    public_path = Path(args.public_config) if args.public_config else None
    private_path = Path(args.private_config) if args.private_config else None
    errors: list[str] = []
    try:
        rt = load_runtime(public_path=public_path, private_path=private_path)
    except ConfigLoadError as exc:
        errors.append(str(exc))
        _emit({"command": "validate-config", "valid": False, "errors": errors})
        return _EXIT_CONFIG
    except Exception as exc:  # pydantic ValidationError etc.
        errors.append(f"{exc.__class__.__name__}: {exc}")
        _emit({"command": "validate-config", "valid": False, "errors": errors})
        return _EXIT_CONFIG
    _emit({"command": "validate-config", "valid": True, "errors": [],
           "effective": rt.model_dump(exclude={"owner_allowlist"})})
    return _EXIT_OK


def _cmd_run_action(data: dict) -> int:
    """Run a single ActionRequest through the PermissionEngine (Phase 3R-R1).

    Used by ``run-task`` when the fixture is an ActionRequest JSON. Emits the
    decision, stable error code (E_UNKNOWN_ACTION for unknown actions),
    execution_attempted flag, and the redacted audit event. An unknown action
    exits non-zero with UNKNOWN_ACTION_REJECTED and never attempts execution.
    """
    from ..audit import RedactedAuditLogger
    from ..permissions import ActionClass, Decision, PermissionEngine
    from ..protocols import ActionRequest, EventKind

    try:
        action = ActionRequest.model_validate(data)
    except Exception as exc:
        _emit({"command": "run-task", "status": "error", "reason": f"invalid ActionRequest: {exc}"})
        return _EXIT_CONFIG

    engine = PermissionEngine(
        capabilities={"TEXT_CHAT", "TOOL_CALLING"},
        owner_allowlist=["principal:example.invalid/owner-1"],
        principal_id=action.parameters.get("owner_identity", "principal:example.invalid/user-1"),
    )
    result = engine.authorize(action)

    if result.action_class == ActionClass.UNKNOWN_ACTION and result.hard_blocked:
        event_type = EventKind.UNKNOWN_ACTION_REJECTED
        outcome = "denied"
    elif result.decision == Decision.ALLOW:
        event_type = EventKind.ACTION_COMPLETED
        outcome = "ok"
    else:
        event_type = EventKind.ACTION_DENIED
        outcome = "denied"

    logger = RedactedAuditLogger()
    ev = logger.make_event(
        event_type, trace_id=action.parameters.get("trace_id"),
        risk_level=result.risk_level, actor_type="system", component="paios_ce",
        outcome=outcome,
        redacted={"action_id": action.action_id, "reason": result.reason},
    )
    logger.emit(ev)

    payload = {
        "command": "run-task",
        "mode": "action",
        "action_id": action.action_id,
        "decision": result.decision.value,
        "action_class": result.action_class.value if result.action_class else None,
        "risk_level": result.risk_level.value if result.risk_level else None,
        "error_code": result.error_code,
        "hard_blocked": result.hard_blocked,
        "execution_attempted": result.execution_attempted,
        "reason": result.reason,
        "audit_events": [ev.model_dump(exclude_none=True)],
    }
    _emit(payload)
    if result.decision == Decision.BLOCKED:
        return _EXIT_BLOCKED
    if result.decision in (Decision.DENY, Decision.CONFIRMATION_REQUIRED):
        return _EXIT_DENIED
    return _EXIT_OK


def _cmd_run_task(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.exists():
        _emit({"command": "run-task", "status": "error", "reason": f"file not found: {path}"})
        return _EXIT_USAGE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _emit({"command": "run-task", "status": "error", "reason": f"invalid JSON: {exc}"})
        return _EXIT_CONFIG

    # Phase 3R-R1: an ActionRequest-shaped fixture (has action_id + operation)
    # is authorized directly through the PermissionEngine, so unknown actions
    # can be exercised from the CLI and are explicitly rejected.
    if "action_id" in data and "operation" in data:
        return _cmd_run_action(data)

    from ..protocols import TaskEnvelope

    try:
        task = TaskEnvelope.model_validate(data)
    except Exception as exc:
        _emit({"command": "run-task", "status": "error", "reason": f"invalid TaskEnvelope: {exc}"})
        return _EXIT_CONFIG

    from ..orchestrator import MinimalOrchestrator
    from ..permissions import PermissionEngine

    engine = PermissionEngine(
        capabilities={"TEXT_CHAT", "TOOL_CALLING"},
        owner_allowlist=["principal:example.invalid/owner-1"],
        principal_id=task.owner_identity,
    )
    orchestrator = MinimalOrchestrator(permission_engine=engine)
    outcome = orchestrator.run_task(task)
    result = outcome.task_result
    status = result.status.value if result else "failure"
    payload = {
        "command": "run-task",
        "task_id": task.task_id,
        "status": status,
        "summary": result.summary if result else "",
        "decisions": [
            {"decision": d.decision.value, "reason": d.reason,
             "risk_level": d.risk_level.value if d.risk_level else None,
             "hard_blocked": d.hard_blocked}
            for d in outcome.decisions
        ],
    }
    _emit(payload)
    if status in ("denied",):
        return _EXIT_DENIED
    if status == "blocked":
        return _EXIT_BLOCKED
    if status == "failure":
        return _EXIT_INTERNAL
    return _EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paios-ce",
        description="PAIOS CE clean-room public core (Phase 3). Mock Provider only; no network; no real secrets.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_demo = sub.add_parser("demo", help="run the local demo closed loop with the Mock Provider")
    p_demo.add_argument("-i", "--input", default=None, help="demo input text")
    p_demo.set_defaults(func=_cmd_demo)

    p_health = sub.add_parser("health", help="run health checks (local, safe)")
    p_health.set_defaults(func=_cmd_health)

    p_val = sub.add_parser("validate-config", help="validate public/private config files")
    p_val.add_argument("--public-config", default=None)
    p_val.add_argument("--private-config", default=None)
    p_val.set_defaults(func=_cmd_validate_config)

    p_run = sub.add_parser("run-task", help="run a TaskEnvelope from a JSON file")
    p_run.add_argument("file", help="path to a TaskEnvelope JSON file")
    p_run.set_defaults(func=_cmd_run_task)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        _emit({"command": args.command, "status": "interrupted"})
        return _EXIT_USAGE
    except Exception as exc:  # defensive: never leak internals
        _emit({"command": args.command, "status": "internal_error",
               "reason": exc.__class__.__name__})
        return _EXIT_INTERNAL


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
