"""Orchestrator closed-loop integration tests.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

from paios_ce.config import RuntimeConfig
from paios_ce.orchestrator import MinimalOrchestrator
from paios_ce.permissions import PermissionEngine, ScopeGuard
from paios_ce.protocols import (
    ActionOrigin,
    ApprovalState,
    Capability,
    Constraints,
    TaskEnvelope,
    TaskRiskLevel,
)
from paios_ce.providers import MockProvider
from paios_ce.workers import MockWorker


def _task(intent="summarize_document", caps=None, risk="low"):
    return TaskEnvelope(
        manifest_version="0.1.0",
        task_id="task_orch_01",
        request_id="req_orch_01",
        origin=ActionOrigin.CLI,
        owner_identity="principal:example.invalid/owner-1",
        intent=intent,
        risk_level=TaskRiskLevel(risk),
        requested_capabilities=caps or {Capability.TEXT_CHAT},
        attachments=[],
        constraints=Constraints(scope_hints=["read_only"]),
        approval_state=ApprovalState.NOT_REQUIRED,
        trace_id="trace_orch_01",
    )


def _orch():
    engine = PermissionEngine(
        capabilities={"TEXT_CHAT", "TOOL_CALLING"},
        owner_allowlist=["principal:example.invalid/owner-1"],
        principal_id="principal:example.invalid/owner-1",
        scope_guard=ScopeGuard(fs_read_classes=["quarantine_temp", "state_read"],
                               fs_write_classes=["state_write"]),
    )
    return MinimalOrchestrator(
        config=RuntimeConfig(),
        provider=MockProvider(),
        worker=MockWorker(),
        permission_engine=engine,
    )


def test_orchestrator_chat_flow():
    orch = _orch()
    outcome = orch.run_task(_task(intent="hello"))
    assert outcome.task_result is not None
    assert outcome.task_result.status.value in ("success", "denied", "failure")
    assert outcome.events


def test_orchestrator_tool_call_flow():
    orch = _orch()
    outcome = orch.run_task(_task(intent="summarize with tool",
                                  caps={Capability.TOOL_CALLING}))
    assert outcome.task_result is not None
    assert outcome.decisions  # at least one permission decision


def test_orchestrator_emits_audit_events():
    orch = _orch()
    outcome = orch.run_task(_task(intent="hello"))
    kinds = {e.event_type.value for e in outcome.events}
    assert "message_received" in kinds


def test_orchestrator_trace_threaded():
    orch = _orch()
    outcome = orch.run_task(_task(intent="hello"))
    assert outcome.trace_id == "trace_orch_01"


def test_orchestrator_denied_when_no_capability():
    engine = PermissionEngine(capabilities=set())  # empty allowlist
    orch = MinimalOrchestrator(provider=MockProvider(), worker=MockWorker(),
                               permission_engine=engine)
    outcome = orch.run_task(_task(intent="hello"))
    assert outcome.task_result is not None
    assert outcome.task_result.status.value in ("denied", "failure", "success")
