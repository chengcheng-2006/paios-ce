"""Action lifecycle: the single governed path a Team action may travel.

    proposal
      -> role authority gate        (team/authority.py)
      -> DurableActionRuntime       (existing src/)
        -> authorization            (existing PermissionEngine)
        -> journal RECORDED/AUTHORIZED
        -> ATTEMPT_STARTED
        -> bounded executor         (existing BoundedToolRuntime)
        -> SUCCEEDED / FAILED / UNCERTAIN
      -> Team journal projection    (team/journal.py)

Every terminal claim the Team layer makes is read back out of the durable
journal, so the Team layer can never report an outcome the authority core does
not already record.

SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from paios_ce.protocols import ActionRequest
from paios_ce.runtime.durable_runtime import DurableExecutionResult
from paios_ce.state import ActionState, RecoveryClassification, RecoveryItem

from . import journal as journal_module
from .authority import AuthorityViolation, RoleAuthority
from .journal import (
    ACTION_ALREADY_TERMINAL,
    ACTION_REQUESTED,
    ACTION_UNCERTAIN,
    AUTHORIZATION_CHECKED,
    AUTHORIZATION_DENIED,
    LIFECYCLE_EVENT_FOR_DURABLE_STATE,
    TeamActionJournal,
)
from .mailbox import TeamRole


class LifecycleError(RuntimeError):
    """Raised when a lifecycle invariant is violated."""


@dataclass(frozen=True, slots=True)
class LifecycleRecord:
    """Immutable outcome of one Team action attempt."""

    task_id: str
    role: TeamRole
    operation: str
    step: int
    action_id: str
    idempotency_key: str
    authorization_decision: str
    executor_invoked: bool
    needs_reconciliation: bool
    denied: bool
    state_error: str | None
    journal_id: str | None
    durable_state: str | None
    outcome: Mapping[str, Any] = field(default_factory=dict)
    event_types: tuple[str, ...] = ()

    @property
    def succeeded(self) -> bool:
        """Success is read from the durable state, never asserted by the Team layer."""

        return self.durable_state == ActionState.SUCCEEDED.value


class ActionLifecycle:
    """Drive one action through authority, runtime and journal."""

    def __init__(self, authority: RoleAuthority, journal: TeamActionJournal, task_id: str) -> None:
        self._authority = authority
        self._journal = journal
        self._task_id = task_id

    @property
    def authority(self) -> RoleAuthority:
        return self._authority

    @property
    def journal(self) -> TeamActionJournal:
        return self._journal

    @property
    def task_id(self) -> str:
        return self._task_id

    # -- public operations --------------------------------------------------

    def submit(
        self,
        role: TeamRole,
        step: int,
        operation: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> LifecycleRecord:
        """Authorize and execute one proposed action on behalf of ``role``."""

        parameters = dict(parameters or {})
        runtime = self._authority.runtime_for(role)
        request = runtime.build_request(self._task_id, step, operation, parameters)
        self._journal.record(
            ACTION_REQUESTED,
            action_id=request.action_id,
            role=role,
            data={"operation": operation, "step": step},
        )
        # Layer 1: a role with no tool authority never reaches the engine.
        try:
            self._authority.require_tool_authority(role)
        except AuthorityViolation:
            self._journal.record(
                AUTHORIZATION_DENIED,
                action_id=request.action_id,
                role=role,
                data={"gate": "role_authority", "reason": "NO_TOOL_AUTHORITY"},
            )
            raise
        execution = runtime.execute_governed(self._task_id, step, operation, parameters)
        return self._project(role, request, execution)

    def simulate_crash_after_attempt_started(
        self,
        role: TeamRole,
        step: int,
        operation: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> LifecycleRecord:
        """Deterministically simulate a process crash after the attempt boundary.

        Authorization and the durable ``ATTEMPT_STARTED`` write really happen;
        only the innermost executor is replaced by one that raises.  The durable
        runtime must therefore classify the action as ``UNCERTAIN`` and never as
        a success.
        """

        parameters = dict(parameters or {})
        runtime = self._authority.require_tool_authority(role)
        request = runtime.build_request(self._task_id, step, operation, parameters)
        self._journal.record(
            ACTION_REQUESTED,
            action_id=request.action_id,
            role=role,
            data={"operation": operation, "step": step, "fault_injection": True},
        )

        def _crash(_request: ActionRequest):
            raise RuntimeError("simulated executor crash after the durable attempt boundary")

        execution = runtime.execute_with_executor(
            self._task_id, step, operation, parameters, _crash
        )
        return self._project(role, request, execution)

    def recover(self) -> RecoveryItem:
        """Classify durable facts after a restart.  Never executes anything."""

        return self._authority.state_store.recover_task(self._task_id)

    def assert_recovery_never_reports_success(self) -> RecoveryItem:
        """Fail closed if recovery claims success for an unresolved Team action."""

        item = self.recover()
        unresolved = any(
            event.event_type == ACTION_UNCERTAIN for event in self._journal.events
        )
        if unresolved and item.classification is RecoveryClassification.TERMINAL_SUCCESS:
            raise LifecycleError(
                "recovery reported TERMINAL_SUCCESS for an action the Team journal "
                "records as UNCERTAIN"
            )
        return item

    # -- projection ---------------------------------------------------------

    def _project(
        self,
        role: TeamRole,
        request: ActionRequest,
        execution: DurableExecutionResult,
    ) -> LifecycleRecord:
        action_id = request.action_id
        decision = execution.authorization.decision.value
        entry = execution.journal
        journal_id = None if entry is None else entry.journal_id

        terminal_before = self._journal.terminal_event_for(action_id)

        self._journal.record(
            AUTHORIZATION_CHECKED,
            action_id=action_id,
            role=role,
            journal_id=journal_id,
            data={"decision": decision, "reason": execution.authorization.reason[:200]},
        )

        if decision != "allow":
            self._journal.record(
                AUTHORIZATION_DENIED,
                action_id=action_id,
                role=role,
                journal_id=journal_id,
                data={"decision": decision},
            )
            return self._record(
                role, request, execution, action_id, journal_id, denied=True
            )

        if journal_id is None:
            # No durable fact exists (for example the state authority was
            # unavailable).  The Team layer must not guess an outcome.
            return self._record(role, request, execution, action_id, None)

        if not execution.executor_invoked and terminal_before is not None:
            # A pre-existing terminal record: the duplicate was refused and the
            # side effect was not replayed.  This is an observation, not a state.
            self._journal.record(
                ACTION_ALREADY_TERMINAL,
                action_id=action_id,
                role=role,
                journal_id=journal_id,
                data={"durable_state": entry.current_state.value},
            )

        self._project_durable_events(action_id, role, journal_id)
        self._journal.assert_projection_consistent(action_id)
        return self._record(role, request, execution, action_id, journal_id)

    def _project_durable_events(self, action_id: str, role: TeamRole, journal_id: str) -> None:
        """Mirror the durable event stream into the Team lifecycle, in sequence order.

        The Team layer never invents a lifecycle transition.  Each event it
        records corresponds to a durable ``ActionState`` transition that the
        authority core already committed, which is what makes the Team record a
        projection rather than a second journal.
        """

        already = set(self._journal.event_types_for(action_id))
        for durable_event in self._journal.durable_events(action_id):
            event_type = LIFECYCLE_EVENT_FOR_DURABLE_STATE.get(durable_event.state)
            if event_type is None or event_type in already:
                continue
            already.add(event_type)
            self._journal.record(
                event_type,
                action_id=action_id,
                role=role,
                journal_id=journal_id,
                data={
                    "durable_sequence": durable_event.sequence,
                    "durable_event_kind": durable_event.event_kind,
                },
            )

    def _record(
        self,
        role: TeamRole,
        request: ActionRequest,
        execution: DurableExecutionResult,
        action_id: str,
        journal_id: str | None,
        *,
        denied: bool = False,
    ) -> LifecycleRecord:
        entry = execution.journal
        outcome: dict[str, Any] = {}
        if execution.action_result is not None:
            outcome = dict(execution.action_result.outcome)
        return LifecycleRecord(
            task_id=self._task_id,
            role=role,
            operation=request.operation,
            step=self._step_of(request),
            action_id=action_id,
            idempotency_key=request.idempotency_key or "",
            authorization_decision=execution.authorization.decision.value,
            executor_invoked=execution.executor_invoked,
            needs_reconciliation=execution.needs_reconciliation,
            denied=denied,
            state_error=execution.state_error,
            journal_id=journal_id,
            durable_state=None if entry is None else entry.current_state.value,
            outcome=outcome,
            event_types=tuple(self._journal.event_types_for(action_id)),
        )

    @staticmethod
    def _step_of(request: ActionRequest) -> int:
        # action_id has the certified shape f"p3-{step}-{digest}".
        parts = request.action_id.split("-")
        if len(parts) >= 2 and parts[1].isdigit():
            return int(parts[1])
        return 0


__all__ = [
    "ActionLifecycle",
    "AuthorityViolation",
    "LifecycleError",
    "LifecycleRecord",
    "journal_module",
]
