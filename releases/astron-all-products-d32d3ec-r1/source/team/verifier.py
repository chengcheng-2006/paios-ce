"""Verifier authority: the only path to a durable ``TASK_COMPLETED`` fact.

No Team role may complete a task.  The Supervisor plans, the Executor acts, the
Auditor observes, and all three are advisory.  Only the deterministic
``MaintenanceVerifier`` in ``paios_ce.agent`` can persist accepted completion,
and it does so through ``SQLiteDurableStateStore.record_task_verification``,
which is the single completion transition.

This module adds no verification logic.  It adds a *gate*: completion may only be
requested by the ``VERIFIER`` role, and the verification itself is delegated
unchanged to the existing verifier, running on the verifier role's own governed
runtime.

SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from paios_ce.agent import MaintenanceVerifier
from paios_ce.state import TaskVerification, VerificationStatus

from .authority import RoleAuthority
from .mailbox import TeamRole


class CompletionAuthorityViolation(PermissionError):
    """Raised when a role without completion authority requests completion."""


@dataclass(frozen=True, slots=True)
class RejectedCompletionAttempt:
    role: TeamRole
    task_id: str


@dataclass
class CompletionAuthority:
    """Sole gate in front of the deterministic verifier."""

    COMPLETING_ROLE = TeamRole.VERIFIER

    def __init__(
        self,
        authority: RoleAuthority,
        baseline_digest: str | None = None,
        *,
        verifier: Any = None,
    ) -> None:
        self._authority = authority
        self._store = authority.state_store
        # The verifier strategy is injectable so a benchmark arm can use the
        # benchmark's own external grader as its completion oracle.  The gate
        # itself is unchanged: whoever is injected only ever runs for the
        # VERIFIER role.
        if verifier is None:
            if baseline_digest is None:
                raise ValueError("baseline_digest or verifier is required")
            # Default: the packaged maintenance oracle, running on the VERIFIER
            # role profile (read + bounded test observation only, never a write).
            verifier = MaintenanceVerifier(
                authority.runtime_for(TeamRole.VERIFIER), baseline_digest
            )
        self._verifier = verifier
        self._rejected: list[RejectedCompletionAttempt] = []

    @property
    def rejected_attempts(self) -> tuple[RejectedCompletionAttempt, ...]:
        return tuple(self._rejected)

    def request_completion(self, role: TeamRole, task_id: str, *, step: int = 90):
        """Run deterministic verification, but only for the verifying role.

        A non-verifying role fails closed *before* any verification work: the
        existing verifier is never invoked, so no completion fact can be written.
        """

        if role is not self.COMPLETING_ROLE:
            self._rejected.append(RejectedCompletionAttempt(role=role, task_id=task_id))
            raise CompletionAuthorityViolation(
                f"{role.value} holds no completion authority; only "
                f"{self.COMPLETING_ROLE.value} may request TASK_COMPLETED"
            )
        return self._verifier.verify(task_id, step=step)

    # -- reading the one completion fact ------------------------------------

    def completion_record(self, task_id: str) -> TaskVerification | None:
        return self._store.task_verification(task_id)

    def task_completed(self, task_id: str) -> bool:
        """Whether the durable store currently records accepted completion."""

        record = self.completion_record(task_id)
        return record is not None and record.status is VerificationStatus.ACCEPTED

    def completion_evidence(self, task_id: str) -> dict[str, Any]:
        record = self.completion_record(task_id)
        if record is None:
            return {"task_completed": False, "reason_code": None, "verifier_version": None}
        return {
            "task_completed": record.status is VerificationStatus.ACCEPTED,
            "status": record.status.value,
            "reason_code": record.reason_code,
            "verifier_version": record.verifier_version,
        }


__all__ = [
    "CompletionAuthority",
    "CompletionAuthorityViolation",
    "RejectedCompletionAttempt",
]
