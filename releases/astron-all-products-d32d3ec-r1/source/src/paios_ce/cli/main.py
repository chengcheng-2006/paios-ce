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


def _cmd_maintenance_demo(args: argparse.Namespace) -> int:
    """Run the one fixed Phase 3 fixture; live mode never falls back to mock."""

    from ..agent import MaintenanceVerifier, NativeAgent, offline_maintenance_provider
    from ..agent.fixture import FixtureError, FixtureWorkspace
    from ..maintenance_artifact import MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT
    from ..providers import (
        ChatRequest,
        LiveProviderError,
        OpenAICompatibleProvider,
        OpenAICompatibleProviderConfig,
    )
    from ..state import SQLiteDurableStateStore
    from ..tools import BoundedToolRuntime, TerminalEnabledToolRuntime, TerminalToolRuntime

    task_id = args.task_id or "phase3-maintenance-task"
    try:
        if args.mode == "mock":
            provider = offline_maintenance_provider(task_id)
            model_id = "mock-1"
        else:
            required = (args.base_url, args.api_key_env, args.model)
            if not all(required):
                _emit({"command": "maintenance-demo", "mode": "live", "status": "BLOCKED_EXTERNAL_CREDENTIAL"})
                return _EXIT_CONFIG
            provider = OpenAICompatibleProvider(OpenAICompatibleProviderConfig(
                base_url=args.base_url,
                api_key_env=args.api_key_env,
                model=args.model,
                timeout_seconds=args.provider_timeout,
                max_output_tokens=args.max_output_tokens,
            ))
            if provider.health_check().status != "ok":
                _emit({"command": "maintenance-demo", "mode": "live", "status": "BLOCKED_EXTERNAL_CREDENTIAL"})
                return _EXIT_DENIED
            # A bounded preflight is separate from the fresh fixture task. Its
            # response carries no execution authority and is never persisted.
            provider.chat(ChatRequest(
                messages=[{"role": "user", "content": "Return READY."}],
                model_id=args.model,
                max_tokens=min(args.max_output_tokens, 16),
                trace_id="phase3-preflight",
            ))
            model_id = args.model
        fixture = (
            FixtureWorkspace.open_existing(Path(args.workspace))
            if args.reuse_fixture
            else FixtureWorkspace.create(Path(args.workspace))
        )
        with SQLiteDurableStateStore(Path(args.state_db)) as store:
            bounded_tools = BoundedToolRuntime(fixture.root, store)
            terminal_tools = TerminalToolRuntime(fixture.root, store)
            tools = TerminalEnabledToolRuntime(
                bounded_tools,
                terminal_tools,
                agent_owner=BoundedToolRuntime.PRINCIPAL_ID,
            )
            try:
                result = NativeAgent(
                    provider,
                    tools,
                    MaintenanceVerifier(bounded_tools, fixture.baseline_digest),
                    model_id=model_id,
                ).run(task_id)
            finally:
                # Shutdown is a terminal lifecycle boundary, not a successful
                # task claim; it only guarantees that R1 child processes go.
                tools.shutdown()
        semantic_validations = [
            item["semantic_validation"]
            for item in result.actions
            if item.get("semantic_validation") in {"PASSED", "FAILED"}
        ]
        _emit({
            "command": "maintenance-demo",
            "mode": args.mode,
            "task_id": task_id,
            "status": "PASS" if result.accepted else "REJECTED",
            "verifier": result.verifier.reason_code,
            "actions": [item["operation"] for item in result.actions],
            "provider_error": result.provider_error,
            "provider_diagnostics": result.provider_diagnostics,
            "request_contract_snapshot": result.request_contract_snapshot,
            "response_tool_call_metadata": result.response_tool_call_metadata,
            "completion_artifact_contract": (
                MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT.safe_metadata()
            ),
            "artifact_semantic_validation": (
                semantic_validations[-1] if semantic_validations else "NOT_RUN"
            ),
        })
        return _EXIT_OK if result.accepted else _EXIT_INTERNAL
    except LiveProviderError as exc:
        _emit({
            "command": "maintenance-demo",
            "mode": "live",
            "status": exc.code.value,
            "provider_diagnostics": exc.safe_diagnostics,
            "request_contract_snapshot": exc.safe_diagnostics.get("request_contract_snapshot", {}),
            "response_tool_call_metadata": None,
        })
        return _EXIT_DENIED
    except (FixtureError, ValueError, OSError):
        _emit({"command": "maintenance-demo", "mode": args.mode, "status": "CONFIGURATION_ERROR"})
        return _EXIT_CONFIG


def _cmd_maintenance_baseline(args: argparse.Namespace) -> int:
    """Certify that a new fixed fixture fails through the bounded test tool.

    This is deliberately a trusted CLI entry point rather than a generic test
    runner.  It has one operation, no model-controlled arguments, and reuses
    the same ``BoundedToolRuntime`` implementation as the native agent.
    """

    from ..agent.fixture import FixtureError, FixtureWorkspace
    from ..state import SQLiteDurableStateStore
    from ..tools import BoundedToolRuntime

    task_id = args.task_id or "phase3-maintenance-baseline"
    try:
        fixture = FixtureWorkspace.create(Path(args.workspace))
        with SQLiteDurableStateStore(Path(args.state_db)) as store:
            tools = BoundedToolRuntime(fixture.root, store)
            store.register_task(task_id)
            execution = tools.execute(task_id, 1, "test.run_pytest_bounded", {})
        result = execution.result
        expected_failure = (
            execution.executor_invoked
            and not execution.needs_reconciliation
            and result is not None
            and result.status.value == "failure"
            and result.outcome.get("status") == "FAILED"
        )
        _emit({
            "command": "maintenance-baseline",
            "task_id": task_id,
            "baseline_status": "FAIL_AS_EXPECTED" if expected_failure else "UNEXPECTED_BASELINE_RESULT",
            "fixture_baseline_digest": fixture.baseline_digest,
            "fixture_baseline_exit": None if result is None else result.outcome.get("exit_code"),
            "bounded_execution_path": "test.run_pytest_bounded",
            "executor_invoked": execution.executor_invoked,
            "needs_reconciliation": execution.needs_reconciliation,
        })
        return _EXIT_OK if expected_failure else _EXIT_CONFIG
    except (FixtureError, ValueError, OSError):
        _emit({"command": "maintenance-baseline", "status": "CONFIGURATION_ERROR"})
        return _EXIT_CONFIG


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


def _cmd_run_action(data: dict, *, principal_id: str) -> int:
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

    # ``principal_id`` comes from the CLI/runtime adapter, never the untrusted
    # ActionRequest payload. A JSON parameter named owner_identity, principal,
    # actor, or user has no authority to select the trusted principal.
    engine = PermissionEngine(
        capabilities={"TEXT_CHAT", "TOOL_CALLING"},
        owner_allowlist=["principal:example.invalid/owner-1"],
        principal_id=principal_id,
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
    audit_details = {"action_id": action.action_id, "reason": result.reason}
    if result.request_fingerprint:
        audit_details["authorization_fingerprint"] = result.request_fingerprint
    if result.is_replay:
        audit_details["authorization_replay"] = True
    if result.error_code == PermissionEngine.IDEMPOTENCY_CONFLICT_ERROR_CODE:
        audit_details["idempotency_conflict"] = True
    ev = logger.make_event(
        event_type, trace_id=action.parameters.get("trace_id"),
        risk_level=result.risk_level, actor_type="system", component="paios_ce",
        outcome=outcome,
        redacted=audit_details,
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
        return _cmd_run_action(
            data,
            principal_id=args.principal_id or "principal:example.invalid/user-1",
        )

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
        principal_id=args.principal_id or "principal:example.invalid/user-1",
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

    # R2-F2 output contract:
    #   --format text + stdout   -> transcript text + newline (direct write)
    #   --format json + stdout   -> structured JSON envelope (permission included)
    #   --format text --output F -> F = transcript + newline; stdout = status envelope
    #   --format json --output F -> F = structured JSON result; stdout = status envelope
    if args.format == "text":
        payload = result.text
    else:
        payload = result.model_dump()
        if service.last_permission is not None:
            payload["permission"] = service.last_permission

    if args.output:
        try:
            if args.format == "text":
                Path(args.output).write_text(str(payload) + "\n", encoding="utf-8")
            else:
                Path(args.output).write_text(
                    json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
        except OSError as exc:
            _emit({"command": "transcribe", "status": "error",
                   "error_code": "E_OUTPUT_WRITE_FAILED",
                   "message": "cannot write output file",
                   "safe_source_label": safe_source_label(args.file)})
            return _EXIT_INTERNAL
        _emit({"command": "transcribe", "status": "ok",
               "output_file": args.output,
               "safe_source_label": result.safe_source_label})
        return _EXIT_OK

    if args.format == "text":
        # Direct stdout write; never wrap the transcript in a JSON envelope.
        sys.stdout.write(str(payload) + "\n")
        sys.stdout.flush()
        return _EXIT_OK

    _emit({"command": "transcribe", "status": "ok", "result": payload})
    return _EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="astron",
        description="Astron execution-control runtime. Live provider use is explicit and bounded.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_demo = sub.add_parser("demo", help="run the local demo closed loop with the Mock Provider")
    p_demo.add_argument("-i", "--input", default=None, help="demo input text")
    p_demo.set_defaults(func=_cmd_demo)

    p_maintenance = sub.add_parser(
        "maintenance-demo",
        help="run the fixed Phase 3 repository-maintenance fixture on a fresh workspace",
    )
    p_maintenance.add_argument("--mode", choices=["mock", "live"], default="mock")
    p_maintenance.add_argument("--workspace", required=True, help="new fresh-copy workspace path")
    p_maintenance.add_argument("--state-db", required=True, help="new or owner-private SQLite durable state path")
    p_maintenance.add_argument(
        "--reuse-fixture",
        action="store_true",
        help="reopen only the exact trusted fixture after baseline certification",
    )
    p_maintenance.add_argument("--task-id", default=None, help="bounded durable task identifier")
    p_maintenance.add_argument("--base-url", default=None, help="explicit live provider base URL (live mode only)")
    p_maintenance.add_argument("--api-key-env", default=None, help="explicit credential environment-variable name (live mode only)")
    p_maintenance.add_argument("--model", default=None, help="explicit provider model identifier (live mode only)")
    p_maintenance.add_argument("--provider-timeout", type=int, default=20)
    p_maintenance.add_argument("--max-output-tokens", type=int, default=512)
    p_maintenance.set_defaults(func=_cmd_maintenance_demo)

    p_baseline = sub.add_parser(
        "maintenance-baseline",
        help="create the fixed fixture and certify its expected failure through the bounded test tool",
    )
    p_baseline.add_argument("--workspace", required=True, help="new fresh-copy workspace path")
    p_baseline.add_argument("--state-db", required=True, help="new owner-private SQLite durable state path")
    p_baseline.add_argument("--task-id", default=None, help="bounded durable baseline task identifier")
    p_baseline.set_defaults(func=_cmd_maintenance_baseline)

    p_health = sub.add_parser("health", help="run health checks (local, safe)")
    p_health.set_defaults(func=_cmd_health)

    p_val = sub.add_parser("validate-config", help="validate public/private config files")
    p_val.add_argument("--public-config", default=None)
    p_val.add_argument("--private-config", default=None)
    p_val.set_defaults(func=_cmd_validate_config)

    p_run = sub.add_parser("run-task", help="run a TaskEnvelope from a JSON file")
    p_run.add_argument("file", help="path to a TaskEnvelope JSON file")
    p_run.add_argument(
        "--principal-id",
        default=None,
        help="trusted local runtime principal; never read from action JSON",
    )
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
