"""Execution ordering and recovery logic built on the Phase 2 durable store.

This layer is intentionally not wired to a model, CLI flag, shell, or live
tool.  Callers supply a trusted executor in code; production capability
admission remains outside the Phase 2 scope.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from ..permissions import Decision, PermissionEngine, PermissionResult, PrincipalContext
from ..permissions.identity import AuthorizationIdentity
from ..protocols import ActionRequest, ActionResult, ActionStatus
from ..state import (
    ActionState,
    DurableAuthorizationDecision,
    JournalEntry,
    ReconciliationObservation,
    ReconciliationResult,
    RecoveryItem,
    SQLiteDurableStateStore,
    StateStoreError,
)


class Reconciler(Protocol):
    """Trusted deterministic observer for an already-uncertain action."""

    def observe(self, journal: JournalEntry) -> ReconciliationObservation:
        """Return an evidence-derived observation without executing the action."""


@dataclass(frozen=True)
class DurableExecutionResult:
    """Result after a durable boundary, never a verified-completion assertion."""

    authorization: PermissionResult
    journal: Optional[JournalEntry]
    action_result: Optional[ActionResult]
    executor_invoked: bool
    needs_reconciliation: bool = False
    state_error: Optional[str] = None


class DurableActionRuntime:
    """Execute one authorized action with durable intent/attempt/outcome facts.

    The constructor requires that its permission engine is bound to the exact
    same durable store.  That makes it impossible for this runtime to accept a
    process-local replay result and then create a journal for a different
    authority.
    """

    def __init__(self, permission_engine: PermissionEngine, state_store: SQLiteDurableStateStore) -> None:
        if permission_engine.durable_state_store is not state_store:
            raise ValueError("permission engine and durable runtime must share one state store")
        self._engine = permission_engine
        self._store = state_store

    @property
    def state_store(self) -> SQLiteDurableStateStore:
        """The exact durable authority shared by actions and task verification."""

        return self._store

    def execute(
        self,
        task_id: str,
        request: ActionRequest,
        executor: Callable[[ActionRequest], ActionResult],
        *,
        principal_context: Optional[PrincipalContext] = None,
    ) -> DurableExecutionResult:
        """Persist attempt-start before invoking the trusted executor.

        A pre-existing `UNCERTAIN` record returns without calling the executor.
        A pre-existing terminal record likewise returns without invoking it.
        Only a new/authorized/retry-eligible action reaches the executor.
        """

        if not isinstance(request.idempotency_key, str) or not request.idempotency_key:
            return DurableExecutionResult(
                authorization=self._engine.authorize(request, principal_context=principal_context),
                journal=None,
                action_result=None,
                executor_invoked=False,
                state_error="durable runtime requires a non-empty idempotency key",
            )
        authorization = self._engine.authorize(request, principal_context=principal_context)
        if authorization.decision is not Decision.ALLOW:
            return DurableExecutionResult(authorization, None, None, False)
        try:
            identity = self._identity_from_result(request, authorization)
            journal = self._store.prepare_authorized_action(
                task_id, identity, self._decision_from_result(authorization)
            )
            if journal.current_state is ActionState.UNCERTAIN:
                return DurableExecutionResult(
                    authorization, journal, None, False, needs_reconciliation=True
                )
            if journal.current_state in {ActionState.SUCCEEDED, ActionState.FAILED}:
                return DurableExecutionResult(authorization, journal, None, False)
            if journal.current_state not in {ActionState.AUTHORIZED, ActionState.RETRY_ELIGIBLE}:
                return DurableExecutionResult(
                    authorization, journal, None, False,
                    state_error="journal state is not executable",
                )
            journal = self._store.record_attempt_started(journal.journal_id)
        except StateStoreError:
            return DurableExecutionResult(
                authorization, None, None, False, state_error="durable state authority is unavailable"
            )

        try:
            action_result = executor(request)
        except Exception:
            # An exception after the durable attempt boundary provides no proof
            # that an external side effect did not happen.
            try:
                journal = self._store.mark_uncertain(journal.journal_id)
            except StateStoreError:
                return DurableExecutionResult(
                    authorization, journal, None, True,
                    needs_reconciliation=True,
                    state_error="attempt outcome and durable state are both unavailable",
                )
            return DurableExecutionResult(
                authorization, journal, None, True, needs_reconciliation=True,
                state_error="executor raised after durable attempt boundary",
            )

        try:
            terminal = (
                ActionState.SUCCEEDED
                if action_result.status is ActionStatus.SUCCESS
                else ActionState.FAILED
            )
            journal = self._store.record_terminal(journal.journal_id, terminal)
        except StateStoreError:
            # The side effect returned, but no terminal durable fact can be
            # trusted.  Do not report a safe outcome or retry it here.
            return DurableExecutionResult(
                authorization, journal, None, True,
                needs_reconciliation=True,
                state_error="terminal outcome could not be durably persisted",
            )
        return DurableExecutionResult(authorization, journal, action_result, True)

    def recover_task(self, task_id: str) -> RecoveryItem:
        """Classify durable facts after a process restart; never execute work."""

        return self._store.recover_task(task_id)

    def reconcile(self, journal_id: str, reconciler: Reconciler) -> ReconciliationResult:
        """Persist a deterministic observation without invoking an executor."""

        journal = self._store.journal_entry(journal_id)
        if journal is None:
            raise StateStoreError("action journal is missing for reconciliation")
        observation = reconciler.observe(journal)
        return self._store.reconcile(journal_id, observation)

    @staticmethod
    def _identity_from_result(
        request: ActionRequest, result: PermissionResult
    ) -> AuthorizationIdentity:
        if (
            not isinstance(request.idempotency_key, str)
            or not isinstance(result.trusted_principal_id, str)
            or not isinstance(result.request_fingerprint, str)
            or not isinstance(result.security_context_fingerprint, str)
        ):
            raise StateStoreError("allowed durable action has no valid authorization identity")
        return AuthorizationIdentity(
            idempotency_key=request.idempotency_key,
            principal_id=result.trusted_principal_id,
            request_fingerprint=result.request_fingerprint,
            security_context_fingerprint=result.security_context_fingerprint,
        )

    @staticmethod
    def _decision_from_result(result: PermissionResult) -> DurableAuthorizationDecision:
        return DurableAuthorizationDecision(
            decision=result.decision.value,
            action_class=result.action_class.value if result.action_class else None,
            risk_level=result.risk_level.value if result.risk_level else None,
            reason=result.reason,
            hard_blocked=result.hard_blocked,
            confirmation_kind=result.confirmation_kind.value,
            error_code=result.error_code,
        )
