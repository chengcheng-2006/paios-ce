"""Demo workflow implementation.

End-to-end local closed loop, fully local and deterministic. The demo
accepts a user input string, builds a TaskEnvelope, runs the orchestrator with
the Mock Provider, and returns a structured result plus redacted audit output.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..audit import RedactedAuditLogger
from ..config import RuntimeConfig
from ..orchestrator import MinimalOrchestrator
from ..permissions import PermissionEngine, ScopeGuard
from ..protocols import (
    ActionOrigin,
    ApprovalState,
    Capability,
    Constraints,
    TaskEnvelope,
    TaskRiskLevel,
)
from ..providers.mock import MockProvider
from ..routing import MinimalRouter
from ..workers.mock import MockWorker

_DEMO_OWNER = "principal:example.invalid/owner-1"


@dataclass
class DemoResult:
    input_text: str
    task_id: str
    trace_id: str
    task_result_status: str
    summary: str
    decisions: List[Dict[str, Any]] = field(default_factory=list)
    audit_events: List[Dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, ensure_ascii=True, sort_keys=True)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "demo_input": self.input_text,
            "task_id": self.task_id,
            "trace_id": self.trace_id,
            "task_result_status": self.task_result_status,
            "summary": self.summary,
            "decisions": self.decisions,
            "audit_event_count": len(self.audit_events),
        }


def _build_task(user_input: str, trace_id: str, task_id: str) -> TaskEnvelope:
    intent = user_input.strip()[:120] or "demo"
    caps = {Capability.TEXT_CHAT}
    if "tool" in user_input.lower() or "summarize" in user_input.lower():
        caps.add(Capability.TOOL_CALLING)
    return TaskEnvelope(
        manifest_version="0.1.0",
        task_id=task_id,
        request_id="req_demo_01",
        origin=ActionOrigin.CLI,
        owner_identity=_DEMO_OWNER,
        intent=intent,
        risk_level=TaskRiskLevel.LOW,
        requested_capabilities=caps,
        attachments=[],
        constraints=Constraints(scope_hints=["read_only"]),
        approval_state=ApprovalState.NOT_REQUIRED,
        trace_id=trace_id,
    )


def run_demo(
    user_input: str = "summarize my task list",
    audit_stream=None,
) -> DemoResult:
    """Run the demo closed loop. Fully local; no network; no secret."""
    trace_id = "trace_demo_0001"
    task_id = "task_demo_0001"

    audit = RedactedAuditLogger(stream=audit_stream)
    config = RuntimeConfig()
    provider = MockProvider(
        fixed_responses={"summarize": "mock summary: 3 tasks, all low risk."}
    )
    worker = MockWorker()
    router = MinimalRouter(provider)
    engine = PermissionEngine(
        capabilities={"TOOL_CALLING", "TEXT_CHAT"},
        owner_allowlist=[_DEMO_OWNER],
        principal_id=_DEMO_OWNER,
        scope_guard=ScopeGuard(
            fs_read_classes=["quarantine_temp", "state_read"],
            fs_write_classes=["state_write"],
        ),
    )
    orchestrator = MinimalOrchestrator(
        config=config, provider=provider, worker=worker,
        permission_engine=engine, router=router, audit_logger=audit,
    )

    task = _build_task(user_input, trace_id, task_id)
    outcome = orchestrator.run_task(task)

    # Flush orchestrator events through the logger (JSONL, redacted)
    for event in outcome.events:
        audit.emit(event)

    result = outcome.task_result
    return DemoResult(
        input_text=user_input,
        task_id=task_id,
        trace_id=trace_id,
        task_result_status=result.status.value if result else "failure",
        summary=result.summary if result else "",
        decisions=[
            {"decision": d.decision.value, "reason": d.reason, "risk_level": d.risk_level.value if d.risk_level else None}
            for d in outcome.decisions
        ] if outcome.decisions else [],
        audit_events=[ev.model_dump(exclude_none=True) for ev in audit.events()],
    )
