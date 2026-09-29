"""Append-only Team state projection for the C1 skeleton."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping

from .mailbox import TeamRole


class TeamPhase(str, Enum):
    CREATED = "CREATED"
    SUPERVISOR = "SUPERVISOR"
    EXECUTOR = "EXECUTOR"
    AUDITOR = "AUDITOR"
    VERIFIER = "VERIFIER"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class TeamEvent:
    event_type: str
    state_version: int
    role: TeamRole
    message_id: str | None
    timestamp: datetime
    data: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TeamState:
    task_id: str
    run_id: str
    task_state: TeamPhase = TeamPhase.CREATED
    current_role: TeamRole = TeamRole.HARNESS
    state_version: int = 0
    _events: list[TeamEvent] = field(default_factory=list, repr=False)

    @property
    def event_history(self) -> tuple[TeamEvent, ...]:
        """Read-only view; events are never edited or removed."""

        return tuple(self._events)

    def append_event(
        self,
        event_type: str,
        *,
        role: TeamRole,
        message_id: str | None = None,
        task_state: TeamPhase | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> TeamEvent:
        if not event_type.strip():
            raise ValueError("event_type must be non-empty")
        self.state_version += 1
        if task_state is not None:
            self.task_state = task_state
        self.current_role = role
        event = TeamEvent(
            event_type=event_type,
            state_version=self.state_version,
            role=role,
            message_id=message_id,
            timestamp=datetime.now(timezone.utc),
            data=dict(data or {}),
        )
        self._events.append(event)
        return event

    def fail(self, reason: str) -> TeamEvent:
        return self.append_event(
            "TEAM_FAILED",
            role=TeamRole.HARNESS,
            task_state=TeamPhase.FAILED,
            data={"reason": reason[:512]},
        )
