"""Supervisor role: planning only."""

from __future__ import annotations

from ..mailbox import MessageType, TeamMessage, TeamRole
from .base import RoleInterface


class SupervisorRole(RoleInterface):
    role = TeamRole.SUPERVISOR
    can_execute_tools = False
    can_modify_state = False

    def handle(self, message: TeamMessage) -> TeamMessage:
        self._require(message, TeamRole.HARNESS, MessageType.TASK)
        plan = self.provider.plan(message.task_id, message.run_id, message.payload)
        return self._response(
            message,
            receiver=TeamRole.EXECUTOR,
            kind=MessageType.PLAN,
            payload=plan,
        )
