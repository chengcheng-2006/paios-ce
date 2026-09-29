"""Team scheduler flow tests.

C1 ran a mock-only scheduler with an inline completion decision.  C3 replaced
that with the governed authority path, so these tests now assert the governed
flow: the same fixed role/message ordering, an append-only state history, and a
completion decision that comes only from the deterministic verifier.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from team_harness import build_governed_team  # noqa: E402

from team.mailbox import MessageType, TeamRole  # noqa: E402
from team.mock_provider import MaintenanceTeamProvider, MockLLMProvider  # noqa: E402
from team.state import TeamPhase, TeamState  # noqa: E402


@pytest.fixture
def governed(tmp_path: Path):
    team = build_governed_team(tmp_path)
    try:
        yield team
    finally:
        team.close()


def test_scheduler_order(governed) -> None:
    provider = MaintenanceTeamProvider()
    result = governed.scheduler(provider).run("task-1", "run-1", {"objective": "offline"})

    assert result.status == "VERIFIED_SUCCESS"
    assert result.task_completed is True
    assert type(governed.scheduler()).parallel is False

    assert [(m.sender, m.receiver, m.message_type) for m in result.messages] == [
        (TeamRole.HARNESS, TeamRole.SUPERVISOR, MessageType.TASK),
        (TeamRole.SUPERVISOR, TeamRole.EXECUTOR, MessageType.PLAN),
        (TeamRole.EXECUTOR, TeamRole.AUDITOR, MessageType.EXECUTION),
        (TeamRole.AUDITOR, TeamRole.VERIFIER, MessageType.AUDIT),
        (TeamRole.VERIFIER, TeamRole.HARNESS, MessageType.VERIFY),
    ]
    assert [call.role for call in provider.calls] == [
        TeamRole.SUPERVISOR,
        TeamRole.EXECUTOR,
        TeamRole.AUDITOR,
    ]


def test_state_version_increment() -> None:
    state = TeamState("task-1", "run-1")

    assert state.state_version == 0
    state.append_event("ONE", role=TeamRole.SUPERVISOR, task_state=TeamPhase.SUPERVISOR)
    state.append_event("TWO", role=TeamRole.EXECUTOR, task_state=TeamPhase.EXECUTOR)

    assert state.state_version == 2
    assert [event.state_version for event in state.event_history] == [1, 2]
    assert [event.event_type for event in state.event_history] == ["ONE", "TWO"]
    assert state.task_state is TeamPhase.EXECUTOR


def test_scheduler_state_and_event_history_are_append_only(governed) -> None:
    result = governed.run("task-1", "run-1")

    assert result.state.task_state is TeamPhase.COMPLETED
    assert result.state.current_role is TeamRole.VERIFIER
    assert [event.event_type for event in result.state.event_history] == [
        "TASK_RECEIVED",
        "SUPERVISOR_COMPLETED",
        "ACTION_GOVERNED",
        "ACTION_GOVERNED",
        "EXECUTOR_COMPLETED",
        "ACTION_GOVERNED",
        "AUDITOR_COMPLETED",
        "VERIFIER_COMPLETED",
    ]
    assert [event.state_version for event in result.state.event_history] == list(range(1, 9))
    assert [message.state_version for message in result.messages] == [0, 1, 2, 3, 4]


def test_scheduler_governs_every_proposed_action(governed) -> None:
    """No proposed action reaches a tool without the authority path."""

    result = governed.run("task-governed", "run-1", provider=MaintenanceTeamProvider())

    assert [record.operation for record in result.actions] == [
        "workspace.patch_text",
        "workspace.write_artifact",
        "validate.file",
    ]
    for record in result.actions:
        assert record.authorization_decision == "allow"
        assert record.durable_state == "SUCCEEDED"
        assert record.executor_invoked is True
        assert "ACTION_AUTHORIZED" in record.event_types
        assert "ACTION_STARTED" in record.event_types
        assert "ACTION_COMPLETED" in record.event_types


def test_scheduler_has_no_inline_completion_decision(governed) -> None:
    """An advisory Auditor PASS cannot complete anything on its own."""

    # The plain mock provider executes nothing, so the fixture stays broken and
    # the Auditor still reports PASS.  Completion must not follow from that.
    result = governed.run("task-advisory", "run-1", provider=MockLLMProvider())

    assert result.actions == ()
    assert result.status == "VERIFIED_FAILURE"
    assert result.verification["accepted"] is False
    assert result.task_completed is False
    audit = [m for m in result.messages if m.message_type is MessageType.AUDIT]
    assert audit and audit[0].payload["status"] == "PASS"


def test_scheduler_emits_a_verifier_message_after_a_real_completion(governed) -> None:
    result = governed.run("task-verify", "run-1")

    verify = [m for m in result.messages if m.message_type is MessageType.VERIFY]
    assert len(verify) == 1
    assert verify[0].sender is TeamRole.VERIFIER
    assert verify[0].payload["status"] == "ACCEPTED"
    assert verify[0].payload["reason_code"] == "VERIFIER_ACCEPTED"
    assert verify[0].payload["accepted"] is True
