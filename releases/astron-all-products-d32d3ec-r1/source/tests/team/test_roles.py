from __future__ import annotations

from team.mailbox import MessageType, TeamMessage, TeamRole
from team.mock_provider import MockLLMProvider
from team.roles import AuditorRole, ExecutorRole, SupervisorRole


def _task() -> TeamMessage:
    return TeamMessage(
        task_id="task-1",
        run_id="run-1",
        sender=TeamRole.HARNESS,
        receiver=TeamRole.SUPERVISOR,
        message_type=MessageType.TASK,
        state_version=0,
        payload={"objective": "offline"},
        message_id="task-message",
    )


def test_role_permission_boundary() -> None:
    provider = MockLLMProvider()

    assert SupervisorRole(provider).can_execute_tools is False
    assert ExecutorRole(provider).can_execute_tools is True
    assert AuditorRole(provider).can_execute_tools is False
    assert SupervisorRole(provider).can_modify_state is False
    assert AuditorRole(provider).can_modify_state is False


def test_supervisor_cannot_execute_tool() -> None:
    supervisor = SupervisorRole(MockLLMProvider())

    assert not hasattr(supervisor, "execute_tool")
    assert supervisor.handle(_task()).message_type is MessageType.PLAN


def test_auditor_cannot_modify_state() -> None:
    auditor = AuditorRole(MockLLMProvider())

    assert auditor.can_modify_state is False
    assert not hasattr(auditor, "modify_state")
