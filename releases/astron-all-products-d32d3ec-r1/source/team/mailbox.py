"""Typed Team messages and an in-memory sequential mailbox."""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Deque, Mapping
from uuid import uuid4


class TeamRole(str, Enum):
    HARNESS = "HARNESS"
    SUPERVISOR = "SUPERVISOR"
    EXECUTOR = "EXECUTOR"
    AUDITOR = "AUDITOR"
    VERIFIER = "VERIFIER"


class MessageType(str, Enum):
    TASK = "TASK"
    PLAN = "PLAN"
    EXECUTION = "EXECUTION"
    CONTINUATION = "CONTINUATION"
    AUDIT = "AUDIT"
    VERIFY = "VERIFY"


class MailboxError(ValueError):
    """Raised for invalid Team message admission."""


class StaleMessageError(MailboxError):
    """Raised when a message does not carry the next state version."""


_ROUTES: dict[tuple[TeamRole, TeamRole], MessageType] = {
    (TeamRole.HARNESS, TeamRole.SUPERVISOR): MessageType.TASK,
    (TeamRole.SUPERVISOR, TeamRole.EXECUTOR): MessageType.PLAN,
    # R2 H2: the harness feeds governed tool results back to the Executor.
    (TeamRole.HARNESS, TeamRole.EXECUTOR): MessageType.CONTINUATION,
    (TeamRole.EXECUTOR, TeamRole.AUDITOR): MessageType.EXECUTION,
    (TeamRole.AUDITOR, TeamRole.VERIFIER): MessageType.AUDIT,
    (TeamRole.VERIFIER, TeamRole.HARNESS): MessageType.VERIFY,
}


def _coerce_enum(value: TeamRole | MessageType | str, enum_type: type[Enum], name: str) -> Enum:
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(str(value).upper())
    except ValueError as exc:
        raise MailboxError(f"invalid {name}: {value!r}") from exc


@dataclass(frozen=True, slots=True)
class TeamMessage:
    """Validated, immutable envelope shared by all Team roles."""

    task_id: str
    run_id: str
    sender: TeamRole | str
    receiver: TeamRole | str
    message_type: MessageType | str
    state_version: int
    parent_message_id: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    payload: Mapping[str, Any] = field(default_factory=dict)
    message_id: str = field(default_factory=lambda: f"tm_{uuid4().hex}")

    def __post_init__(self) -> None:
        if not isinstance(self.task_id, str) or not self.task_id.strip():
            raise MailboxError("task_id must be non-empty")
        if not isinstance(self.run_id, str) or not self.run_id.strip():
            raise MailboxError("run_id must be non-empty")
        if not isinstance(self.message_id, str) or not self.message_id.strip():
            raise MailboxError("message_id must be non-empty")
        if self.parent_message_id is not None and not self.parent_message_id.strip():
            raise MailboxError("parent_message_id must be non-empty when present")
        if not isinstance(self.state_version, int) or isinstance(self.state_version, bool):
            raise MailboxError("state_version must be an integer")
        if self.state_version < 0:
            raise MailboxError("state_version must be non-negative")
        if not isinstance(self.payload, Mapping):
            raise MailboxError("payload must be a mapping")
        try:
            json.dumps(dict(self.payload))
        except (TypeError, ValueError) as exc:
            raise MailboxError("payload must be JSON serializable") from exc
        if not isinstance(self.timestamp, datetime):
            raise MailboxError("timestamp must be a datetime")

        sender = _coerce_enum(self.sender, TeamRole, "sender")
        receiver = _coerce_enum(self.receiver, TeamRole, "receiver")
        message_type = _coerce_enum(self.message_type, MessageType, "message_type")
        object.__setattr__(self, "sender", sender)
        object.__setattr__(self, "receiver", receiver)
        object.__setattr__(self, "message_type", message_type)
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))
        if self.timestamp.tzinfo is None:
            object.__setattr__(self, "timestamp", self.timestamp.replace(tzinfo=timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible copy of the message."""

        return {
            "task_id": self.task_id,
            "run_id": self.run_id,
            "sender": self.sender.value,
            "receiver": self.receiver.value,
            "message_type": self.message_type.value,
            "state_version": self.state_version,
            "parent_message_id": self.parent_message_id,
            "timestamp": self.timestamp.astimezone(timezone.utc).isoformat(),
            "payload": dict(self.payload),
            "message_id": self.message_id,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "TeamMessage":
        if not isinstance(value, Mapping):
            raise MailboxError("message must be a mapping")
        required = {
            "task_id",
            "run_id",
            "sender",
            "receiver",
            "message_type",
            "state_version",
            "parent_message_id",
            "timestamp",
            "payload",
        }
        missing = sorted(required.difference(value))
        if missing:
            raise MailboxError(f"missing message fields: {', '.join(missing)}")
        timestamp = value["timestamp"]
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return cls(
            task_id=value["task_id"],
            run_id=value["run_id"],
            sender=value["sender"],
            receiver=value["receiver"],
            message_type=value["message_type"],
            state_version=value["state_version"],
            parent_message_id=value["parent_message_id"],
            timestamp=timestamp,
            payload=value["payload"],
            message_id=value.get("message_id", f"tm_{uuid4().hex}"),
        )


class Mailbox:
    """Strict FIFO transport used by the sequential scheduler."""

    def __init__(self, task_id: str, run_id: str) -> None:
        self.task_id = task_id
        self.run_id = run_id
        self._next_state_version = 0
        self._queue: Deque[TeamMessage] = deque()
        self._history: list[TeamMessage] = []
        self._message_ids: set[str] = set()

    @property
    def next_state_version(self) -> int:
        """The state version the next admitted message must carry."""

        return self._next_state_version

    @property
    def history(self) -> tuple[TeamMessage, ...]:
        return tuple(self._history)

    def send(self, message: TeamMessage) -> None:
        if message.task_id != self.task_id or message.run_id != self.run_id:
            raise MailboxError("message task/run does not match mailbox")
        if message.message_id in self._message_ids:
            raise MailboxError(f"duplicate message_id: {message.message_id}")
        expected_type = _ROUTES.get((message.sender, message.receiver))
        if expected_type is not message.message_type:
            raise MailboxError(
                f"unsupported route {message.sender.value}->{message.receiver.value}"
            )
        if message.state_version != self._next_state_version:
            raise StaleMessageError(
                f"expected state_version {self._next_state_version}, "
                f"got {message.state_version}"
            )
        self._queue.append(message)
        self._history.append(message)
        self._message_ids.add(message.message_id)
        self._next_state_version += 1

    def receive(self, receiver: TeamRole | str) -> TeamMessage:
        if not self._queue:
            raise MailboxError("mailbox is empty")
        expected = _coerce_enum(receiver, TeamRole, "receiver")
        message = self._queue[0]
        if message.receiver is not expected:
            raise MailboxError(f"message is addressed to {message.receiver.value}")
        return self._queue.popleft()
