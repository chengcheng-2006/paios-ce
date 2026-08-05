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
    """Run a single ActionRequest through the PermissionEngine (R1 closure).

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

    # R1 closure: an ActionRequest-shaped fixture (has action_id + operation)
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


def _cmd_transcribe(args: argparse.Namespace) -> int:
    """Transcribe one local audio file through the optional Local ASR path.

    Stable structured error codes (Phase 9A contract):
      E_SPEECH_DISABLED / E_SPEECH_DEPENDENCY_MISSING /
      E_SPEECH_MODEL_NOT_AVAILABLE_OFFLINE / E_AUDIO_FILE_NOT_FOUND /
      E_AUDIO_TYPE_NOT_ALLOWED / E_AUDIO_TOO_LARGE /
      E_AUDIO_DURATION_LIMIT / E_AUDIO_DECODE_FAILED / E_TRANSCRIPTION_FAILED

    Errors never expose stack traces or full private paths; only the basename
    (safe_source_label) is reported.
    """
    from ..audit import RedactedAuditLogger
    from ..config import load_runtime
    from ..permissions import PermissionEngine
    from ..speech import (
        SpeechError,
        SpeechErrorCode,
        SpeechRuntimeConfig,
        SpeechService,
        TranscriptionRequest,
    )
    from ..speech.faster_whisper_adapter import FasterWhisperAdapter
    from ..speech.policy import safe_source_label

    public_path = Path(args.public_config) if args.public_config else None
    private_path = Path(args.private_config) if args.private_config else None

    def _fail(exc: SpeechError) -> int:
        payload = {"command": "transcribe", "status": "error"}
        payload.update(exc.to_dict())
        _emit(payload)
        return exc.exit_code

    try:
        rt = load_runtime(public_path=public_path, private_path=private_path)
    except Exception as exc:
        _emit({"command": "transcribe", "status": "error",
               "error_code": "E_CONFIG_INVALID",
               "message": f"configuration error: {exc.__class__.__name__}"})
        return _EXIT_CONFIG

    speech_cfg = rt.speech
    if not speech_cfg.enabled:
        return _fail(SpeechError(
            SpeechErrorCode.E_SPEECH_DISABLED,
            "speech capability is disabled (set speech.enabled=true in private config)",
            safe_source_label=safe_source_label(args.file),
            exit_code=_EXIT_DENIED,
        ))

    # Permission gate: owner-only local CLI rule. The caller must be a single
    # explicit owner (--principal-id) or the sole owner from the allowlist.
    owners = list(rt.owner_allowlist or [])
    if args.principal_id:
        principal_id = args.principal_id
    elif len(owners) == 1:
        principal_id = owners[0]
    else:
        return _fail(SpeechError(
            SpeechErrorCode.E_SPEECH_PERMISSION_DENIED,
            "ambiguous caller: pass --principal-id or configure exactly one owner_allowlist entry",
            safe_source_label=safe_source_label(args.file),
            exit_code=_EXIT_DENIED,
        ))

    # --vad-filter / --no-vad-filter default to None; fall back to config.
    vad_filter = args.vad_filter if args.vad_filter is not None else speech_cfg.vad_filter

    request = TranscriptionRequest(
        source=args.file,
        model=args.model or speech_cfg.default_model,
        language=args.language,
        device=args.device or speech_cfg.device,
        compute_type=args.compute_type or speech_cfg.compute_type,
        vad_filter=vad_filter,
        word_timestamps=args.word_timestamps,
        local_files_only=speech_cfg.local_files_only,
    )

    adapter = FasterWhisperAdapter()
    # Privacy mapping (R1): retain_audio follows raw_audio_storage directly;
    # persist_transcript follows transcript_retention_days.
    runtime_config = SpeechRuntimeConfig(
        enabled=speech_cfg.enabled,
        local_files_only=speech_cfg.local_files_only,
        retain_audio=speech_cfg.raw_audio_storage,
        persist_transcript=speech_cfg.transcript_retention_days > 0,
        audit_transcript=False,
        max_file_size_mb=speech_cfg.max_file_size_mb,
        max_duration_seconds=speech_cfg.max_duration_seconds,
        allowed_extensions=speech_cfg.allowed_extensions,
        vad_filter=speech_cfg.vad_filter,
        device=speech_cfg.device,
        compute_type=speech_cfg.compute_type,
        default_model=speech_cfg.default_model,
    )
    permission_engine = PermissionEngine(
        capabilities={"SPEECH_TRANSCRIBE_LOCAL"},
        owner_allowlist=owners,
        principal_id=principal_id,
    )
    service = SpeechService(
        runtime_config=runtime_config,
        adapter=adapter,
        audit_logger=RedactedAuditLogger(),
        permission_engine=permission_engine,
        principal_id=principal_id,
        owner_allowlist=owners,
    )

    try:
        result = service.transcribe(request)
    except SpeechError as exc:
        return _fail(exc)
    except Exception as exc:  # defensive: never leak internals
        _emit({"command": "transcribe", "status": "error",
               "error_code": "E_TRANSCRIPTION_FAILED",
               "message": "transcription failed",
               "safe_source_label": safe_source_label(args.file)})
        return _EXIT_INTERNAL

    if args.format == "text":
        output = result.text
    else:
        payload = result.model_dump()
        if service.last_permission is not None:
            payload["permission"] = service.last_permission
        output = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)

    if args.output:
        try:
            Path(args.output).write_text(output + "\n", encoding="utf-8")
        except OSError as exc:
            _emit({"command": "transcribe", "status": "error",
                   "error_code": "E_OUTPUT_WRITE_FAILED",
                   "message": "cannot write output file",
                   "safe_source_label": safe_source_label(args.file)})
            return _EXIT_INTERNAL
        _emit({"command": "transcribe", "status": "ok",
               "output_file": args.output,
               "safe_source_label": result.safe_source_label})
    else:
        _emit({"command": "transcribe", "status": "ok", "result": json.loads(output)})
    return _EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paios-ce",
        description="PAIOS CE clean-room public core (the release candidate). Mock Provider only; no network; no real secrets.",
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

    p_tr = sub.add_parser(
        "transcribe",
        help="transcribe a local audio file through the optional Local ASR adapter (Phase 9A)",
    )
    p_tr.add_argument("file", help="path to a local audio file (wav/mp3/m4a/flac/ogg/opus/webm)")
    p_tr.add_argument("--model", default=None, help="model identifier or local converted model path (default: speech.default_model)")
    p_tr.add_argument("--language", default=None, help="ISO-639-1 language hint (default: auto-detect)")
    p_tr.add_argument("--device", choices=["cpu", "cuda", "auto"], default=None, help="inference device (default: speech.device=cpu)")
    p_tr.add_argument("--compute-type", default=None, help="compute type (default: speech.compute_type=int8)")
    p_tr.add_argument("--vad-filter", dest="vad_filter", action="store_true", default=None, help="enable VAD filter (default: speech.vad_filter)")
    p_tr.add_argument("--no-vad-filter", dest="vad_filter", action="store_false", help="disable VAD filter")
    p_tr.add_argument("--word-timestamps", action="store_true", default=False, help="include word-level timestamps when supported")
    p_tr.add_argument("--format", choices=["json", "text"], default="json", help="output format (default: json)")
    p_tr.add_argument("--output", default=None, help="write output to a file instead of stdout")
    p_tr.add_argument("--public-config", default=None, help="path to public config YAML")
    p_tr.add_argument("--private-config", default=None, help="path to private config YAML")
    p_tr.add_argument("--principal-id", default=None,
                      help="caller principal (default: sole owner_allowlist entry)")
    p_tr.set_defaults(func=_cmd_transcribe)

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
