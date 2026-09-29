"""Executor role boundary for the C1 skeleton.

The role advertises the future tool capability boundary, but this C1 task does
not implement tool integration.  Its provider response is mock-only.
"""

from __future__ import annotations

from ..mailbox import MessageType, TeamMessage, TeamRole
from .base import RoleInterface


class ExecutorRole(RoleInterface):
    role = TeamRole.EXECUTOR
    can_execute_tools = True
    can_modify_state = False

    def propose(self, message: TeamMessage) -> dict:
        """Return an execution proposal payload without building a mailbox reply.

        Round 1 arrives as SUPERVISOR/PLAN.  Round 2+ arrives as
        HARNESS/CONTINUATION carrying the governed tool results of the previous
        round, so an observation can inform the next proposal.  The harness owns
        the loop and sends one summary EXECUTION message to the Auditor when the
        continuation stops.
        """

        if message.message_type is MessageType.CONTINUATION:
            self._require(message, TeamRole.HARNESS, MessageType.CONTINUATION)
        else:
            self._require(message, TeamRole.SUPERVISOR, MessageType.PLAN)
        return self.provider.execute(message.task_id, message.run_id, message.payload)

    def handle(self, message: TeamMessage) -> TeamMessage:
        self._require(message, TeamRole.SUPERVISOR, MessageType.PLAN)
        execution = self.provider.execute(message.task_id, message.run_id, message.payload)
        return self._response(
            message,
            receiver=TeamRole.AUDITOR,
            kind=MessageType.EXECUTION,
            payload=execution,
        )
