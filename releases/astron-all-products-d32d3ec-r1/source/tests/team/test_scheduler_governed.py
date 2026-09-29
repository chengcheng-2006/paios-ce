"""C3 scheduler integration tests.

The scheduler is now the authority path, not a mock flow.  These tests pin the
six required behaviours:

1. Supervisor cannot execute tools.
2. Executor cannot execute without authorization.
3. An authorized Executor action succeeds.
4. Auditor has no mutation permission.
5. The Verifier is the only completion authority.
6. Crash recovery keeps the action UNCERTAIN.

Offline throughout: packaged fixture, deterministic provider, no network.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from team_harness import build_governed_team  # noqa: E402

from paios_ce.state import ActionState, RecoveryClassification, StateTransitionError  # noqa: E402

from team.mailbox import MessageType, TeamRole  # noqa: E402
from team.mock_provider import MaintenanceTeamProvider, MockLLMProvider  # noqa: E402
from team.scheduler import CRASH_AFTER_ATTEMPT_STARTED  # noqa: E402
from team.verifier import CompletionAuthority  # noqa: E402


@pytest.fixture
def governed(tmp_path: Path):
    team = build_governed_team(tmp_path)
    try:
        yield team
    finally:
        team.close()

SOURCE = "maintenance_config.py"
ARTIFACT = ".astron-artifacts/change_summary.json"
REPAIR_PARAMS = {
    "path": SOURCE,
    "expected_old": MaintenanceTeamProvider.REPAIR_OLD,
    "replacement": MaintenanceTeamProvider.REPAIR_NEW,
}
AUDITOR_MUTATION = {
    "path": SOURCE,
    "expected_old": MaintenanceTeamProvider.REPAIR_NEW,
    "replacement": "DEFAULT_TIMEOUT_SECONDS = 45",
}


# --------------------------------------------------------------------------
# providers that misbehave in specific, controlled ways
# --------------------------------------------------------------------------


class SupervisorExecutingProvider(MockLLMProvider):
    """The Supervisor tries to smuggle tool actions into its plan."""

    def plan(self, task_id, run_id, payload):
        plan = super().plan(task_id, run_id, payload)
        plan["actions"] = [{"operation": "workspace.patch_text", "parameters": REPAIR_PARAMS}]
        return plan

    def execute(self, task_id, run_id, plan):
        super().execute(task_id, run_id, plan)  # keeps the call record honest
        return {"status": "NO_ACTIONS", "actions": []}

    def audit(self, task_id, run_id, execution):
        super().audit(task_id, run_id, execution)
        return {"status": "PASS", "findings": [], "actions": []}


class UnauthorizedExecutorProvider(MockLLMProvider):
    """The Executor proposes an operation the certified path does not admit."""

    def execute(self, task_id, run_id, plan):
        super().execute(task_id, run_id, plan)
        return {
            "status": "PROPOSED",
            "actions": [{"operation": "workspace.delete_all", "parameters": {}}],
        }

    def audit(self, task_id, run_id, execution):
        super().audit(task_id, run_id, execution)
        return {"status": "PASS", "findings": [], "actions": []}


class MutatingAuditorProvider(MaintenanceTeamProvider):
    """The Auditor proposes a mutation it is not authorized to perform."""

    def audit(self, task_id, run_id, execution):
        return {
            "status": "PASS",
            "findings": [],
            "actions": [{"operation": "workspace.patch_text", "parameters": AUDITOR_MUTATION}],
        }


class CrashingExecutorProvider(MaintenanceTeamProvider):
    """The Executor crashes immediately after the durable attempt boundary."""

    def execute(self, task_id, run_id, plan):
        return {
            "status": "PROPOSED",
            "actions": [
                {
                    "operation": "workspace.patch_text",
                    "parameters": REPAIR_PARAMS,
                    "fault_injection": CRASH_AFTER_ATTEMPT_STARTED,
                }
            ],
        }

    def audit(self, task_id, run_id, execution):
        return {"status": "PASS", "findings": [], "actions": []}


# --------------------------------------------------------------------------
# 1. Supervisor cannot execute tools
# --------------------------------------------------------------------------


def test_01_supervisor_cannot_execute_tools(governed) -> None:
    before = governed.read(SOURCE)

    result = governed.run("task-sup", "run-1", provider=SupervisorExecutingProvider())

    # Nothing ran, and the Supervisor's attempted actions were refused outright.
    assert result.actions == ()
    assert governed.read(SOURCE) == before
    assert [refusal.role for refusal in result.refused_actions] == [TeamRole.SUPERVISOR]
    assert all(
        refusal.reason == "SUPERVISOR_HAS_NO_TOOL_AUTHORITY"
        for refusal in result.refused_actions
    )
    assert "SUPERVISOR_ACTION_REFUSED" in [e.event_type for e in result.state.event_history]
    assert governed.authority.can_execute(TeamRole.SUPERVISOR) is False


def test_01b_supervisor_actions_never_produce_a_journal_fact(governed) -> None:
    governed.run("task-sup-2", "run-1", provider=SupervisorExecutingProvider())

    recovery = governed.store.recover_task("task-sup-2")
    assert recovery.classification is RecoveryClassification.NO_ATTEMPT
    assert recovery.journal is None


# --------------------------------------------------------------------------
# 2. Executor cannot execute without authorization
# --------------------------------------------------------------------------


def test_02_executor_cannot_execute_an_unadmitted_operation(governed) -> None:
    before = governed.read(SOURCE)

    result = governed.run("task-unauth", "run-1", provider=UnauthorizedExecutorProvider())

    assert result.actions == ()
    assert [refusal.operation for refusal in result.refused_actions] == ["workspace.delete_all"]
    assert result.refused_actions[0].reason.startswith("NOT_ADMITTED")
    assert governed.read(SOURCE) == before
    assert governed.store.recover_task("task-unauth").classification is RecoveryClassification.NO_ATTEMPT


def test_02b_every_executed_action_carries_an_authorization_fact(governed) -> None:
    result = governed.run("task-authz", "run-1")

    assert result.actions, "the governed run should have executed actions"
    for record in result.actions:
        assert record.authorization_decision == "allow"
        assert record.journal_id is not None
        entry = governed.store.journal_entry(record.journal_id)
        assert entry is not None
        assert entry.authorization_decision == "allow"
        states = [event.state for event in governed.store.journal_events(record.journal_id)]
        assert ActionState.AUTHORIZED in states
        assert ActionState.ATTEMPT_STARTED in states


# --------------------------------------------------------------------------
# 3. An authorized Executor action succeeds
# --------------------------------------------------------------------------


def test_03_authorized_executor_action_succeeds(governed) -> None:
    result = governed.run("task-ok", "run-1", provider=MaintenanceTeamProvider())

    executor_actions = [r for r in result.actions if r.role is TeamRole.EXECUTOR]
    assert [r.operation for r in executor_actions] == [
        "workspace.patch_text",
        "workspace.write_artifact",
    ]
    for record in executor_actions:
        assert record.authorization_decision == "allow"
        assert record.executor_invoked is True
        assert record.durable_state == ActionState.SUCCEEDED.value
        assert record.succeeded is True
        assert record.event_types == (
            "ACTION_REQUESTED",
            "AUTHORIZATION_CHECKED",
            "ACTION_AUTHORIZED",
            "ACTION_STARTED",
            "ACTION_COMPLETED",
        )

    assert governed.read(SOURCE).strip().endswith("DEFAULT_TIMEOUT_SECONDS = 30")
    assert (governed.workspace.root / ARTIFACT).is_file()


# --------------------------------------------------------------------------
# 4. Auditor has no mutation permission
# --------------------------------------------------------------------------


def test_04_auditor_cannot_mutate(governed) -> None:
    result = governed.run("task-audit", "run-1", provider=MutatingAuditorProvider())

    auditor_actions = [r for r in result.actions if r.role is TeamRole.AUDITOR]
    assert len(auditor_actions) == 1
    attempted = auditor_actions[0]
    assert attempted.operation == "workspace.patch_text"
    assert attempted.authorization_decision != "allow"
    assert attempted.executor_invoked is False
    assert attempted.succeeded is False
    assert "ACTION_STARTED" not in attempted.event_types
    assert "ACTION_COMPLETED" not in attempted.event_types

    # The Auditor's mutation never landed.
    assert "DEFAULT_TIMEOUT_SECONDS = 45" not in governed.read(SOURCE)
    assert governed.read(SOURCE).strip().endswith("DEFAULT_TIMEOUT_SECONDS = 30")
    assert governed.authority.profile(TeamRole.AUDITOR).can_mutate_workspace is False


def test_04b_auditor_read_only_observation_is_allowed(governed) -> None:
    result = governed.run("task-audit-read", "run-1", provider=MaintenanceTeamProvider())

    read_only = [r for r in result.actions if r.role is TeamRole.AUDITOR]
    assert [r.operation for r in read_only] == ["validate.file"]
    assert read_only[0].authorization_decision == "allow"
    assert read_only[0].executor_invoked is True


# --------------------------------------------------------------------------
# 5. Verifier is the only completion authority
# --------------------------------------------------------------------------


@pytest.mark.parametrize("role", [TeamRole.SUPERVISOR, TeamRole.EXECUTOR, TeamRole.AUDITOR])
def test_05_non_verifier_roles_cannot_write_completion(governed, role: TeamRole) -> None:
    governed.store.register_task(f"task-{role.value}")
    authority = CompletionAuthority(governed.authority, governed.workspace.baseline_digest)

    from team.verifier import CompletionAuthorityViolation

    with pytest.raises(CompletionAuthorityViolation):
        authority.request_completion(role, f"task-{role.value}")

    assert governed.store.task_verification(f"task-{role.value}") is None


def test_05b_completion_fact_is_written_only_by_the_verifier(governed) -> None:
    result = governed.run("task-complete", "run-1")

    assert result.status == "VERIFIED_SUCCESS"
    assert result.verification["reason_code"] == "VERIFIER_ACCEPTED"
    record = governed.store.task_verification("task-complete")
    assert record is not None
    assert record.status.value == "ACCEPTED"
    assert record.verifier_version == "phase3-maintenance-verifier-v1"

    verify = [m for m in result.messages if m.message_type is MessageType.VERIFY]
    assert len(verify) == 1 and verify[0].sender is TeamRole.VERIFIER


def test_05c_no_completion_message_without_a_verifier_acceptance(governed) -> None:
    result = governed.run("task-incomplete", "run-1", provider=MockLLMProvider())

    assert result.status == "VERIFIED_FAILURE"
    assert result.task_completed is False
    assert governed.store.task_verification("task-incomplete") is not None
    verify = [m for m in result.messages if m.message_type is MessageType.VERIFY]
    assert verify and verify[0].payload["accepted"] is False
    assert verify[0].payload["reason_code"] != "VERIFIER_ACCEPTED"


# --------------------------------------------------------------------------
# 6. Crash recovery keeps the action UNCERTAIN
# --------------------------------------------------------------------------


def test_06_crash_recovery_keeps_the_action_uncertain(governed) -> None:
    result = governed.run(
        "task-crash",
        "run-1",
        provider=CrashingExecutorProvider(),
        allow_fault_injection=True,
    )

    assert result.status == "BLOCKED"
    assert result.task_completed is False

    crashed = [r for r in result.actions if r.needs_reconciliation]
    assert len(crashed) == 1
    assert crashed[0].durable_state == ActionState.UNCERTAIN.value
    assert crashed[0].succeeded is False
    assert "ACTION_UNCERTAIN" in crashed[0].event_types
    assert "ACTION_COMPLETED" not in crashed[0].event_types

    recovery = governed.store.recover_task("task-crash")
    assert recovery.classification is RecoveryClassification.NEEDS_RECONCILIATION
    assert recovery.journal is not None
    assert recovery.journal.current_state is ActionState.UNCERTAIN
    assert recovery.classification is not RecoveryClassification.TERMINAL_SUCCESS

    assert governed.store.task_verification("task-crash") is None


def test_06b_completion_cannot_bypass_an_unresolved_action(governed) -> None:
    governed.run(
        "task-crash-2",
        "run-1",
        provider=CrashingExecutorProvider(),
        allow_fault_injection=True,
    )
    authority = CompletionAuthority(governed.authority, governed.workspace.baseline_digest)

    with pytest.raises(StateTransitionError):
        authority.request_completion(TeamRole.VERIFIER, "task-crash-2")

    assert governed.store.task_verification("task-crash-2") is None


def test_06c_fault_injection_is_opted_in_only(governed) -> None:
    """A misbehaving provider cannot crash a run unless the caller asked for it."""

    result = governed.run("task-no-inject", "run-1", provider=CrashingExecutorProvider())

    # The marker is ignored: the action ran to a durable terminal fact instead of
    # becoming uncertain.
    assert result.actions
    assert all(not record.needs_reconciliation for record in result.actions)
    assert result.actions[0].durable_state == ActionState.SUCCEEDED.value
    assert result.status != "BLOCKED"
    assert governed.read(SOURCE).strip().endswith("DEFAULT_TIMEOUT_SECONDS = 30")

    recovery = governed.store.recover_task("task-no-inject")
    assert recovery.classification is RecoveryClassification.TERMINAL_SUCCESS
    assert recovery.classification is not RecoveryClassification.NEEDS_RECONCILIATION


# --------------------------------------------------------------------------
# boundary: the scheduler cannot reach a provider transport
# --------------------------------------------------------------------------


def test_scheduler_imports_no_network_or_provider_transport() -> None:
    import ast
    from pathlib import Path

    import team.scheduler as scheduler_module

    tree = ast.parse(Path(scheduler_module.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    roots = {name.split(".")[0] for name in imported}
    assert not (roots & {"requests", "urllib", "httpx", "socket", "ssl", "http"})
    assert not any("providers" in name for name in imported)
