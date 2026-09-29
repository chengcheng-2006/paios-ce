"""Team lifecycle journal: a projection over the durable action journal.

This module deliberately does **not** introduce a second journal authority.

Astron already has exactly one append-only authority for action facts:
``SQLiteDurableStateStore``, whose ``action_journal`` / ``action_events`` tables
are written only through ``DurableActionRuntime`` (RECORDED -> AUTHORIZED ->
ATTEMPT_STARTED -> SUCCEEDED / FAILED / UNCERTAIN).

``TeamActionJournal`` records Team-level lifecycle observations for coordination
and evidence, and it can always prove them against that durable record.  If the
projection and the durable journal ever disagree, the projection is wrong by
definition and ``assert_projection_consistent`` fails closed.

SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from paios_ce.state import ActionState, JournalEntry, SQLiteDurableStateStore

from .mailbox import TeamRole


class JournalProjectionError(RuntimeError):
    """Raised when the Team projection disagrees with the durable journal."""


# Lifecycle vocabulary requested by the C2 contract.
ACTION_REQUESTED = "ACTION_REQUESTED"
AUTHORIZATION_CHECKED = "AUTHORIZATION_CHECKED"
ACTION_AUTHORIZED = "ACTION_AUTHORIZED"
AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"
ACTION_STARTED = "ACTION_STARTED"
ACTION_COMPLETED = "ACTION_COMPLETED"
ACTION_FAILED = "ACTION_FAILED"
ACTION_UNCERTAIN = "ACTION_UNCERTAIN"
ACTION_ALREADY_TERMINAL = "ACTION_ALREADY_TERMINAL"

#: How a Team lifecycle event corresponds to the one durable action state it
#: claims.  ``None`` means the event asserts no durable action state at all.
DURABLE_STATE_FOR_EVENT: Mapping[str, ActionState | None] = {
    ACTION_REQUESTED: None,
    AUTHORIZATION_CHECKED: None,
    ACTION_AUTHORIZED: ActionState.AUTHORIZED,
    AUTHORIZATION_DENIED: None,
    ACTION_STARTED: ActionState.ATTEMPT_STARTED,
    ACTION_COMPLETED: ActionState.SUCCEEDED,
    ACTION_FAILED: ActionState.FAILED,
    ACTION_UNCERTAIN: ActionState.UNCERTAIN,
    ACTION_ALREADY_TERMINAL: None,
}

_TERMINAL_EVENTS = frozenset({ACTION_COMPLETED, ACTION_FAILED, ACTION_UNCERTAIN})

#: How each durable journal state is projected into the Team lifecycle.
#: ``None`` means the durable state adds no distinct Team lifecycle event.
LIFECYCLE_EVENT_FOR_DURABLE_STATE: Mapping[ActionState, str | None] = {
    ActionState.RECORDED: None,
    ActionState.AUTHORIZED: ACTION_AUTHORIZED,
    ActionState.ATTEMPT_STARTED: ACTION_STARTED,
    ActionState.SUCCEEDED: ACTION_COMPLETED,
    ActionState.FAILED: ACTION_FAILED,
    ActionState.UNCERTAIN: ACTION_UNCERTAIN,
    ActionState.RETRY_ELIGIBLE: None,
}


@dataclass(frozen=True, slots=True)
class LifecycleEvent:
    """One Team-observed lifecycle fact about one action."""

    event_type: str
    action_id: str
    role: TeamRole
    sequence: int
    durable_state: str | None
    at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    data: Mapping[str, Any] = field(default_factory=dict)


class TeamActionJournal:
    """Append-only Team coordination record, provably derived from the journal."""

    def __init__(self, task_id: str, run_id: str, state_store: SQLiteDurableStateStore) -> None:
        self.task_id = task_id
        self.run_id = run_id
        self._store = state_store
        self._events: list[LifecycleEvent] = []
        self._journal_ids: dict[str, str] = {}

    # -- recording ----------------------------------------------------------

    def record(
        self,
        event_type: str,
        *,
        action_id: str,
        role: TeamRole,
        journal_id: str | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> LifecycleEvent:
        if event_type not in DURABLE_STATE_FOR_EVENT:
            raise JournalProjectionError(f"unknown lifecycle event: {event_type}")
        if not isinstance(action_id, str) or not action_id.strip():
            raise JournalProjectionError("action_id must be non-empty")
        if journal_id is not None:
            self._journal_ids[action_id] = journal_id
        event = LifecycleEvent(
            event_type=event_type,
            action_id=action_id,
            role=role,
            sequence=len(self._events) + 1,
            durable_state=(
                None
                if DURABLE_STATE_FOR_EVENT[event_type] is None
                else DURABLE_STATE_FOR_EVENT[event_type].value
            ),
            data=dict(data or {}),
        )
        self._events.append(event)
        return event

    # -- reading ------------------------------------------------------------

    @property
    def events(self) -> tuple[LifecycleEvent, ...]:
        return tuple(self._events)

    def events_for(self, action_id: str) -> tuple[LifecycleEvent, ...]:
        return tuple(event for event in self._events if event.action_id == action_id)

    def event_types_for(self, action_id: str) -> list[str]:
        return [event.event_type for event in self.events_for(action_id)]

    def terminal_event_for(self, action_id: str) -> LifecycleEvent | None:
        terminal = [e for e in self.events_for(action_id) if e.event_type in _TERMINAL_EVENTS]
        return terminal[-1] if terminal else None

    def journal_id_for(self, action_id: str) -> str | None:
        return self._journal_ids.get(action_id)

    # -- proving the projection against the one authority -------------------

    def durable_entry(self, action_id: str) -> JournalEntry | None:
        journal_id = self._journal_ids.get(action_id)
        if journal_id is None:
            return None
        return self._store.journal_entry(journal_id)

    def durable_events(self, action_id: str) -> list[Any]:
        journal_id = self._journal_ids.get(action_id)
        if journal_id is None:
            return []
        return self._store.journal_events(journal_id)

    def assert_projection_consistent(self, action_id: str) -> None:
        """Fail closed if a Team claim is not backed by the durable journal.

        This is the guard that keeps Astron at one authority source: the Team
        layer may only report a terminal outcome that the durable journal already
        records.
        """

        terminal = self.terminal_event_for(action_id)
        if terminal is None:
            return
        entry = self.durable_entry(action_id)
        if entry is None:
            raise JournalProjectionError(
                f"Team reported {terminal.event_type} for {action_id} "
                "with no durable journal record"
            )
        claimed = DURABLE_STATE_FOR_EVENT[terminal.event_type]
        if claimed is None:
            return
        if entry.current_state is not claimed:
            raise JournalProjectionError(
                f"Team reported {terminal.event_type} ({claimed.value}) for {action_id} "
                f"but the durable journal records {entry.current_state.value}"
            )

    def assert_no_unbacked_success(self) -> None:
        """No action may be reported successful without a durable SUCCEEDED fact."""

        for event in self._events:
            if event.event_type != ACTION_COMPLETED:
                continue
            self.assert_projection_consistent(event.action_id)
