"""Auditor role: read-only observation of the mock execution result."""

from __future__ import annotations

from ..mailbox import MessageType, TeamMessage, TeamRole
from .base import RoleInterface


class AuditorRole(RoleInterface):
    role = TeamRole.AUDITOR
    can_execute_tools = False
    can_modify_state = False

    def handle(self, message: TeamMessage) -> TeamMessage:
        self._require(message, TeamRole.EXECUTOR, MessageType.EXECUTION)
        audit = self.provider.audit(message.task_id, message.run_id, message.payload)
        return self._response(
            message,
            receiver=TeamRole.VERIFIER,
            kind=MessageType.AUDIT,
            payload=audit,
        )
