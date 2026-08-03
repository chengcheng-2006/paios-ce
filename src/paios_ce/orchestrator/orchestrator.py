"""MinimalOrchestrator — runs the Phase 3 closed loop.

Flow:
  TaskEnvelope
    -> validate config
    -> Risk evaluation (task risk derived from requested capabilities)
    -> router selects Mock Provider
    -> build ChatRequest
    -> MockProvider.chat / stream_chat / tool_call / structured_output
    -> if the provider emits tool calls -> MockWorker.execute (authorized)
    -> TaskResult
    -> redacted AuditEvent written by the RedactedAuditLogger

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import List, Optional

from ..audit import RedactedAuditLogger
from ..config import RuntimeConfig
from ..permissions import Decision, PermissionEngine, PermissionResult
from ..protocols import (
    ActionRequest,
    ActionResult,
    AuditEvent,
    Capability,
    EventKind,
    RiskLevel,
    TaskEnvelope,
    TaskResult,
    TaskStatus,
)
from ..providers import ChatRequest, Provider
from ..providers.mock import MockProvider
from ..routing import MinimalRouter
from ..workers import MockWorker, Worker


@dataclass
class OrchestrationResult:
    task_result: Optional[TaskResult] = None
    decisions: List[PermissionResult] = field(default_factory=list)
    events: List[AuditEvent] = field(default_factory=list)
    trace_id: str = "trace_redacted_01"


class MinimalOrchestrator:
    """Composes config, router, provider, permission engine, worker, audit."""

    def __init__(
        self,
        config: Optional[RuntimeConfig] = None,
        provider: Optional[Provider] = None,
        worker: Optional[Worker] = None,
        permission_engine: Optional[PermissionEngine] = None,
        router: Optional[MinimalRouter] = None,
        audit_logger: Optional[RedactedAuditLogger] = None,
    ) -> None:
        self.config = config or RuntimeConfig()
        self.provider = provider or MockProvider()
        self.worker = worker or MockWorker()
        self.router = router or MinimalRouter(self.provider)
        self.audit = audit_logger or RedactedAuditLogger()
        self.permission_engine = permission_engine or PermissionEngine(
            capabilities=set(), owner_allowlist=self.config.owner_allowlist or []
        )

    # -- task risk ----------------------------------------------------------

    def _task_risk(self, task: TaskEnvelope) -> RiskLevel:
        caps = task.requested_capabilities or set()
        if Capability.TOOL_CALLING in caps:
            return RiskLevel.HIGH
        if task.intent and any(k in task.intent.lower() for k in ("delete", "write", "send", "pay", "execute")):
            return RiskLevel.HIGH
        return RiskLevel.LOW

    # -- main loop ----------------------------------------------------------

    def run_task(self, task: TaskEnvelope) -> OrchestrationResult:
        trace = task.trace_id
        events: List[AuditEvent] = []
        decisions: List[PermissionResult] = []

        # Validate config + routing
        routing = self.router.route(self.config.primary_provider, "TEXT_CHAT")
        if not routing.resolved:
            events.append(self.audit.make_event(
                event_type=EventKind.ROUTING_DECISION, task_id=task.task_id, trace_id=trace,
                outcome="denied", redacted={"reason": routing.reason},
            ))
            return OrchestrationResult(
                task_result=TaskResult(task_id=task.task_id, status=TaskStatus.FAILURE,
                                       trace_id=trace, summary="routing failed"),
                decisions=decisions, events=events, trace_id=trace,
            )

        risk = self._task_risk(task)
        events.append(self.audit.make_event(
            event_type=EventKind.MESSAGE_RECEIVED, task_id=task.task_id, trace_id=trace,
            risk_level=risk, actor_type="owner" if self.permission_engine.is_owner() else "user",
            outcome="accepted", redacted={"intent": task.intent},
        ))

        # Build provider request
        last_content = task.intent
        chat_request = ChatRequest(
            messages=[{"role": "user", "content": last_content}],
            model_id=self.config.primary_provider,
            trace_id=trace,
            capabilities=[c.value for c in task.requested_capabilities] or ["TEXT_CHAT"],
        )

        # Capability routing inside provider
        caps = self.provider.get_capabilities()
        cap_set = {c.value for c in caps}

        result: Optional[TaskResult] = None
        if "STRUCTURED_OUTPUT" in cap_set and Capability.STRUCTURED_OUTPUT in task.requested_capabilities:
            so = self.provider.structured_output(chat_request, schema={})
            result = TaskResult(
                task_id=task.task_id, status=TaskStatus.SUCCESS, trace_id=trace,
                summary="structured output produced", timestamp="",
            )
            result = TaskResult(
                task_id=task.task_id, status=TaskStatus.SUCCESS, trace_id=trace,
                summary=json.dumps(so.data, sort_keys=True),
            )
        elif "TOOL_CALLING" in cap_set and Capability.TOOL_CALLING in task.requested_capabilities:
            tc = self.provider.tool_call(chat_request)
            action = ActionRequest(
                action_id=f"act_{task.task_id[:16]}",
                worker_type="tool",
                operation="read_file_in_scope",
                parameters={"trace_id": trace},
                required_permissions=["TOOL_CALLING"],
                filesystem_scope={"mode": "read", "paths_class": ["quarantine_temp"]},
                network_scope={"mode": "none", "endpoints_class": []},
                timeout=30,
                idempotency_key=f"idem_{task.task_id[:16]}",
                rollback_supported=False,
                approval_required=False,
            )
            decision = self.permission_engine.authorize(action)
            decisions.append(decision)
            if decision.decision == Decision.ALLOW:
                ar = self.worker.execute(action)
                events.append(self.audit.make_event(
                    event_type=EventKind.ACTION_COMPLETED, task_id=task.task_id, trace_id=trace,
                    risk_level=decision.risk_level, outcome="success",
                    redacted={"action_id": action.action_id},
                ))
                result = TaskResult(
                    task_id=task.task_id, status=TaskStatus.SUCCESS, trace_id=trace,
                    action_results=[ar],
                    summary=f"mock tool call executed: {ar.outcome.get('summary_class', 'ok')}",
                )
            else:
                # Phase 3R-R1: an unknown action is recorded as
                # UNKNOWN_ACTION_REJECTED (distinct from a generic denial), with
                # the stable error code and the sanitized action id — never the
                # raw operation text (which may carry a secret).
                if decision.error_code == PermissionEngine.UNKNOWN_ACTION_ERROR_CODE:
                    events.append(self.audit.make_event(
                        event_type=EventKind.UNKNOWN_ACTION_REJECTED, task_id=task.task_id,
                        trace_id=trace, risk_level=decision.risk_level, outcome="denied",
                        redacted={"action_id": action.action_id, "error_code": decision.error_code},
                    ))
                else:
                    events.append(self.audit.make_event(
                        event_type=EventKind.ACTION_DENIED, task_id=task.task_id, trace_id=trace,
                        risk_level=decision.risk_level, outcome="denied",
                        redacted={"reason": decision.reason},
                    ))
                result = TaskResult(
                    task_id=task.task_id, status=TaskStatus.DENIED, trace_id=trace,
                    summary=f"denied: {decision.reason}",
                )
        else:
            resp = self.provider.chat(chat_request)
            result = TaskResult(
                task_id=task.task_id, status=TaskStatus.SUCCESS, trace_id=trace,
                summary=resp.content,
            )

        events.append(self.audit.make_event(
            event_type=EventKind.ACTION_COMPLETED, task_id=task.task_id, trace_id=trace,
            risk_level=risk, outcome="ok", redacted={"provider": self.config.primary_provider},
        ))
        return OrchestrationResult(task_result=result, decisions=decisions, events=events, trace_id=trace)
