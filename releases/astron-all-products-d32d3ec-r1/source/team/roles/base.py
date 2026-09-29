"""Common interface and envelope helper for Team roles."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping

from ..mailbox import MessageType, TeamMessage, TeamRole
from ..mock_provider import MockLLMProvider


class RoleProtocolError(ValueError):
    """Raised when a role receives a message outside its contract."""


class RoleInterface(ABC):
    role: TeamRole
    can_execute_tools: bool = False
    can_modify_state: bool = False

    def __init__(self, provider: MockLLMProvider) -> None:
        self.provider = provider

    @abstractmethod
    def handle(self, message: TeamMessage) -> TeamMessage:
        """Consume exactly one message and emit exactly one message."""

    def _require(self, message: TeamMessage, sender: TeamRole, kind: MessageType) -> None:
        if message.receiver is not self.role:
            raise RoleProtocolError(f"{self.role.value} is not the receiver")
        if message.sender is not sender or message.message_type is not kind:
            raise RoleProtocolError(
                f"{self.role.value} expected {sender.value}/{kind.value}, "
                f"got {message.sender.value}/{message.message_type.value}"
            )

    def _response(
        self,
        message: TeamMessage,
        *,
        receiver: TeamRole,
        kind: MessageType,
        payload: Mapping[str, Any],
    ) -> TeamMessage:
        return TeamMessage(
            task_id=message.task_id,
            run_id=message.run_id,
            sender=self.role,
            receiver=receiver,
            message_type=kind,
            state_version=message.state_version + 1,
            parent_message_id=message.message_id,
            payload=dict(payload),
        )
