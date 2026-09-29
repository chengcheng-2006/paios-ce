"""Governed sequential Team flow: Supervisor -> Executor -> Authority -> Auditor -> Verifier.

C1 ran a mock-only flow and decided completion inline:

    accepted = audit_input.payload.get("status") == "PASS" and not findings

C3 removes that.  The scheduler now drives the C2 authority path:

    Supervisor            plan only, no task tools
      -> Executor         proposes actions, executes nothing
      -> Authority check  role gate + PermissionEngine
      -> ActionLifecycle  durable runtime + journal
      -> Auditor          read-only observation, advisory only
      -> CompletionAuthority / deterministic verifier   <- the only TASK_COMPLETED

Two invariants hold by construction:

* the scheduler contains **no** completion decision; ``accepted`` is read from
  the verifier's durable result via ``CompletionAuthority``;
* no action reaches a tool without passing authorization and the durable
  attempt boundary, because every action goes through ``ActionLifecycle``.

SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Mapping

from paios_ce.state import StateTransitionError
from paios_ce.tools import ToolInputError

from .authority import AuthorityViolation, RoleAuthority
from .journal import LifecycleEvent, TeamActionJournal
from .lifecycle import ActionLifecycle, LifecycleRecord
from .feedback import build_feedback
from .mailbox import Mailbox, MessageType, TeamMessage, TeamRole
from .mock_provider import MockLLMProvider
from .roles import AuditorRole, ExecutorRole, SupervisorRole
from .state import TeamPhase, TeamState

# ---------------------------------------------------------------------------
# R2 H2 — bounded Executor continuation (frozen by ASTRON_TEAM_R2_EXPERIMENTAL_DESIGN)
# ---------------------------------------------------------------------------

MAX_EXECUTOR_ROUNDS = 4
MAX_ACTIONS_PER_ROUND = 4
MAX_TOTAL_ACTIONS = 12
MAX_TOTAL_TOKENS = 32_000
MAX_SUPERVISOR_CALLS = 1
MAX_AUDITOR_CALLS = 1
SUPERVISOR_REINVOKE_ON_ACTIONLESS_STOP = False
UNRESOLVED_UNCERTAIN_STOPS_EXECUTOR = True

_EXECUTOR_DONE_WORDS = frozenset({"DONE", "COMPLETE", "COMPLETED", "FINISHED"})
from .verifier import CompletionAuthority, CompletionAuthorityViolation

#: Fault-injection marker understood by the scheduler.  Used by tests to place a
#: crash exactly after the durable attempt boundary.
CRASH_AFTER_ATTEMPT_STARTED = "crash_after_attempt_started"


@dataclass(frozen=True, slots=True)
class RefusedAction:
    """An action the authority path refused before any side effect."""

    role: TeamRole
    operation: str
    reason: str


@dataclass(frozen=True, slots=True)
class TeamRunResult:
    task_id: str
    run_id: str
    status: str
    state: TeamState
    messages: tuple[TeamMessage, ...]
    verification: Mapping[str, Any]
    actions: tuple[LifecycleRecord, ...] = ()
    refused_actions: tuple[RefusedAction, ...] = ()
    lifecycle_events: tuple[LifecycleEvent, ...] = ()
    task_completed: bool = False

    @property
    def verified(self) -> bool:
        return self.status == "VERIFIED_SUCCESS"


class _RunContext:
    """Per-run governance bindings; keeps ``run()`` free of hidden state."""

    def __init__(
        self,
        authority: RoleAuthority,
        task_id: str,
        run_id: str,
        baseline_digest: str | None,
        completion: CompletionAuthority | None = None,
    ):
        self.authority = authority
        self.task_id = task_id
        self.journal = TeamActionJournal(task_id, run_id, authority.state_store)
        self.lifecycle = ActionLifecycle(authority, self.journal, task_id)
        self.completion = completion or CompletionAuthority(authority, baseline_digest)
        self.actions: list[LifecycleRecord] = []
        self.refused: list[RefusedAction] = []
        self._step = 0

    def next_step(self) -> int:
        self._step += 1
        return self._step

    def run_proposals(
        self,
        proposals: Any,
        *,
        role: TeamRole,
        state: TeamState,
        allow_fault_injection: bool = False,
    ) -> list[LifecycleRecord]:
        """Execute proposed actions through the governed path.

        A proposal the authority path refuses is recorded and skipped; it never
        reaches a tool.
        """

        if not isinstance(proposals, (list, tuple)):
            return []
        produced: list[LifecycleRecord] = []
        for proposal in proposals:
            if not isinstance(proposal, Mapping):
                self.refused.append(RefusedAction(role, "<malformed>", "PROPOSAL_NOT_A_MAPPING"))
                continue
            operation = str(proposal.get("operation", ""))
            parameters = proposal.get("parameters") or {}
            step = proposal.get("step")
            step = step if isinstance(step, int) and 1 <= step <= 99 else self.next_step()
            fault = proposal.get("fault_injection")
            try:
                if allow_fault_injection and fault == CRASH_AFTER_ATTEMPT_STARTED:
                    record = self.lifecycle.simulate_crash_after_attempt_started(
                        role, step, operation, parameters
                    )
                else:
                    record = self.lifecycle.submit(role, step, operation, parameters)
            except AuthorityViolation as exc:
                self.refused.append(RefusedAction(role, operation, f"AUTHORITY_VIOLATION: {exc}"))
                state.append_event(
                    "ACTION_REFUSED",
                    role=role,
                    data={"operation": operation, "reason": "NO_TOOL_AUTHORITY"},
                )
                continue
            except ToolInputError as exc:
                self.refused.append(RefusedAction(role, operation, f"NOT_ADMITTED: {exc}"))
                state.append_event(
                    "ACTION_REFUSED",
                    role=role,
                    data={"operation": operation, "reason": "OPERATION_NOT_ADMITTED"},
                )
                continue
            self.actions.append(record)
            produced.append(record)
            state.append_event(
                "ACTION_GOVERNED",
                role=role,
                data={
                    "operation": record.operation,
                    "action_id": record.action_id,
                    "authorization_decision": record.authorization_decision,
                    "durable_state": record.durable_state,
                    "executor_invoked": record.executor_invoked,
                },
            )
            if record.needs_reconciliation:
                # The task now holds an unresolved action.  No further action may
                # be proposed: the durable runtime would refuse it, and the run
                # belongs in RECOVERY_REQUIRED rather than execution.
                state.append_event(
                    "ACTION_RECONCILIATION_REQUIRED",
                    role=role,
                    data={"action_id": record.action_id},
                )
                break
        return produced


def _round_result(record: Any, parameters: Mapping[str, Any], observations: list) -> dict:
    """One executed action's evidence, with argument hashes and read lineage."""

    entry = {
        "operation": record.operation,
        # Lower-cased deliberately: the Auditor sees this payload, and an R1 test
        # transport routes role responses on the bare uppercase role token.  R1
        # tests may not be edited, so the trace avoids it.
        "role": record.role.value.lower(),
        "authorization_decision": record.authorization_decision,
        "durable_state": record.durable_state,
        "executor_invoked": record.executor_invoked,
        "journal_id": record.journal_id,
        "needs_reconciliation": record.needs_reconciliation,
        "action_id": record.action_id,
    }
    if isinstance(parameters, Mapping) and parameters:
        entry.update(_arg_hashes(parameters))
        expected_old = parameters.get("expected_old")
        if record.operation == "workspace.patch_text" and isinstance(expected_old, str):
            # Observational consistency, NOT a causal claim: the fragment was
            # present in a prior governed read.  It does not prove the model could
            # not have obtained it elsewhere.
            match = next(
                (o for o in observations if expected_old in o["content"]), None
            )
            entry["EXPECTED_OLD_PRESENT_IN_PRIOR_GOVERNED_READ"] = bool(match)
            entry["derived_from_observation_action_id"] = (
                match["action_id"] if match else None
            )
            entry["PATCH_ARGUMENT_SUPPORTED_BY_PRIOR_GOVERNED_OBSERVATION"] = bool(match)
    return entry


def _arg_hashes(parameters: Mapping[str, Any]) -> dict[str, Any]:
    """Deterministic hashes of a mutating action's arguments.

    The durable journal keeps only a request fingerprint, which was insufficient
    to show that a patch's ``expected_old`` came from an earlier governed read.
    These are computed by the harness from the proposal it actually received --
    never from model self-report -- and the raw source fragment is not stored.
    """

    import hashlib

    def digest(value: Any) -> str:
        blob = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    out: dict[str, Any] = {"arguments_fingerprint": digest(dict(parameters))}
    if "expected_old" in parameters:
        value = parameters["expected_old"]
        text = value if isinstance(value, str) else json.dumps(value, sort_keys=True, default=str)
        out["expected_old_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        out["expected_old_length"] = len(text)
    if "replacement" in parameters:
        value = parameters["replacement"]
        text = value if isinstance(value, str) else json.dumps(value, sort_keys=True, default=str)
        out["replacement_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        out["replacement_length"] = len(text)
    return out


def _pair_proposals(proposed: Any, executed: list) -> list[tuple[Any, Mapping[str, Any]]]:
    """Pair each executed record with the proposal that produced it, in order."""

    if not isinstance(proposed, (list, tuple)):
        return [(record, {}) for record in executed]
    remaining = [item for item in proposed if isinstance(item, Mapping)]
    pairs: list[tuple[Any, Mapping[str, Any]]] = []
    cursor = 0
    for record in executed:
        found: Mapping[str, Any] = {}
        for index in range(cursor, len(remaining)):
            if str(remaining[index].get("operation", "")) == record.operation:
                found = remaining[index]
                cursor = index + 1
                break
        pairs.append(
            (record, found.get("parameters") or found.get("arguments") or {})
        )
    return pairs


class TeamScheduler:
    """Run one fixed sequential, authority-backed Team flow."""

    parallel: bool = False

    def __init__(
        self,
        authority: RoleAuthority,
        baseline_digest: str | None = None,
        provider: MockLLMProvider | None = None,
        task_context: object | None = None,
        max_executor_rounds: int = 1,
        max_actions_per_round: int = MAX_ACTIONS_PER_ROUND,
        max_total_actions: int = MAX_TOTAL_ACTIONS,
        max_total_tokens: int | None = None,
    ) -> None:
        self._authority = authority
        self._baseline_digest = baseline_digest
        self.provider = provider or MockLLMProvider()
        # R2 H1: the canonical task context handed to every role prompt.
        self._task_context = task_context
        # R2 H2: bounded continuation.  The default of one round reproduces the
        # R1 behaviour exactly, so nothing changes unless R2 opts in.
        self._max_executor_rounds = max(int(max_executor_rounds), 1)
        self._max_actions_per_round = max(int(max_actions_per_round), 1)
        self._max_total_actions = max(int(max_total_actions), 1)
        self._max_total_tokens = max_total_tokens
        self.supervisor = SupervisorRole(self.provider)
        self.executor = ExecutorRole(self.provider)
        self.auditor = AuditorRole(self.provider)

    # -- helpers ------------------------------------------------------------

    def _token_usage(self) -> int | None:
        """Cumulative billable tokens, when the provider can report them."""

        snapshot = getattr(self.provider, "usage_snapshot", None)
        if not callable(snapshot):
            return None
        usage = snapshot() or {}
        if not isinstance(usage, Mapping):
            return None
        total = 0
        for key in ("prompt_tokens", "completion_tokens"):
            value = usage.get(key)
            if isinstance(value, int):
                total += value
        return total

    def _continuation_payload(
        self, round_index: int, feedback: list, previous_status: object
    ) -> dict[str, Any]:
        """What the next Executor round may see: context, its results, the budget.

        The canonical task context is unchanged across rounds.  The payload never
        carries grading material: there is no gold, no expected source and no
        hidden digest in it.
        """

        context = self._task_context
        block = ""
        if context is not None and hasattr(context, "team_task_block"):
            block = context.team_task_block()
        remaining_rounds = max(self._max_executor_rounds - round_index + 1, 0)
        return {
            "objective": getattr(context, "instruction", "") or "",
            "task_context": block,
            "round": round_index,
            "previous_status": previous_status,
            "governed_results": list(feedback),
            "budget": {
                "remaining_executor_rounds": remaining_rounds,
                "max_actions_per_round": self._max_actions_per_round,
                "remaining_total_actions": max(self._max_total_actions, 0),
                "max_total_tokens": self._max_total_tokens,
            },
            "instruction": (
                "These are the real results of your own governed actions. "
                "Propose the next actions, or propose none to finish."
            ),
        }

    def _ensure_task_registered(self, task_id: str) -> None:
        store = self._authority.state_store
        if store.checkpoint(task_id) is None:
            store.register_task(task_id)

    # -- the run ------------------------------------------------------------

    def run(
        self,
        task_id: str,
        run_id: str,
        payload: Mapping[str, Any] | None = None,
        *,
        allow_fault_injection: bool = False,
        completion: CompletionAuthority | None = None,
    ) -> TeamRunResult:
        state = TeamState(task_id, run_id)
        mailbox = Mailbox(task_id, run_id)
        context = _RunContext(
            self._authority, task_id, run_id, self._baseline_digest, completion
        )

        def result(status: str, verification: Mapping[str, Any]) -> TeamRunResult:
            return TeamRunResult(
                task_id=task_id,
                run_id=run_id,
                status=status,
                state=state,
                messages=mailbox.history,
                verification=dict(verification),
                actions=tuple(context.actions),
                refused_actions=tuple(context.refused),
                lifecycle_events=context.journal.events,
                task_completed=context.completion.task_completed(task_id),
            )

        try:
            self._ensure_task_registered(task_id)

            # HARNESS -> SUPERVISOR
            task = TeamMessage(
                task_id=task_id,
                run_id=run_id,
                sender=TeamRole.HARNESS,
                receiver=TeamRole.SUPERVISOR,
                message_type=MessageType.TASK,
                state_version=0,
                payload=dict(payload or {}),
            )
            mailbox.send(task)
            state.append_event("TASK_RECEIVED", role=TeamRole.HARNESS, message_id=task.message_id)

            # SUPERVISOR: planning only.  Any action it proposes is refused and
            # recorded; the Supervisor holds no tool authority at all.
            plan = self.supervisor.handle(mailbox.receive(TeamRole.SUPERVISOR))
            mailbox.send(plan)
            state.append_event(
                "SUPERVISOR_COMPLETED",
                role=TeamRole.SUPERVISOR,
                message_id=plan.message_id,
                task_state=TeamPhase.SUPERVISOR,
            )
            if plan.payload.get("actions"):
                for _ in plan.payload["actions"]:
                    context.refused.append(
                        RefusedAction(TeamRole.SUPERVISOR, "<plan>", "SUPERVISOR_HAS_NO_TOOL_AUTHORITY")
                    )
                state.append_event(
                    "SUPERVISOR_ACTION_REFUSED",
                    role=TeamRole.SUPERVISOR,
                    message_id=plan.message_id,
                    data={"proposed": len(plan.payload["actions"])},
                )

            # EXECUTOR: bounded continuation.  Round 1 proposes with no
            # observation, exactly as in R1.  Each later round receives the
            # governed tool results of the previous round, so an observation can
            # inform the next proposal.  Every round goes through the same
            # authority, lifecycle, durable runtime and journal: H2 adds
            # opportunities to propose governed actions, it does not loosen
            # governance.
            first = mailbox.receive(TeamRole.EXECUTOR)
            rounds: list[dict[str, Any]] = []
            executed_all: list[LifecycleRecord] = []
            feedback: list[dict[str, Any]] = []
            total_actions = 0
            # Governed reads from EARLIER rounds only: a read in the same batch
            # cannot have informed the proposal that carried the patch.
            prior_observations: list[dict[str, Any]] = []
            stop_reason = "ROUND_LIMIT_REACHED"
            previous_status: object = first.payload.get("status")

            for round_index in range(1, self._max_executor_rounds + 1):
                if round_index == 1:
                    message = first
                else:
                    if total_actions >= self._max_total_actions:
                        stop_reason = "ACTION_LIMIT_REACHED"
                        break
                    if self._max_total_tokens is not None:
                        used = self._token_usage()
                        if used is not None and used >= self._max_total_tokens:
                            stop_reason = "TOKEN_LIMIT_REACHED"
                            break
                    continuation = TeamMessage(
                        task_id=task_id,
                        run_id=run_id,
                        sender=TeamRole.HARNESS,
                        receiver=TeamRole.EXECUTOR,
                        message_type=MessageType.CONTINUATION,
                        state_version=mailbox.next_state_version,
                        parent_message_id=first.parent_message_id,
                        payload=self._continuation_payload(
                            round_index, feedback, previous_status
                        ),
                    )
                    mailbox.send(continuation)
                    state.append_event(
                        "EXECUTOR_CONTINUATION",
                        role=TeamRole.HARNESS,
                        message_id=continuation.message_id,
                        data={"round": round_index, "feedback_items": len(feedback)},
                    )
                    message = mailbox.receive(TeamRole.EXECUTOR)

                proposal = self.executor.propose(message)
                previous_status = proposal.get("status")
                proposed = proposal.get("actions")
                if isinstance(proposed, (list, tuple)) and len(proposed) > self._max_actions_per_round:
                    proposed = list(proposed)[: self._max_actions_per_round]

                refused_before = len(context.refused)
                observations_before_round = list(prior_observations)
                executed = context.run_proposals(
                    proposed,
                    role=TeamRole.EXECUTOR,
                    state=state,
                    allow_fault_injection=allow_fault_injection,
                )
                executed_all.extend(executed)
                total_actions += len(executed)
                for record in executed:
                    if record.operation == "workspace.read_text" and record.executor_invoked:
                        content = (record.outcome or {}).get("content")
                        if isinstance(content, str):
                            prior_observations.append(
                                {"action_id": record.action_id, "content": content}
                            )
                feedback = build_feedback(
                    executed, refused=context.refused[refused_before:]
                )
                rounds.append(
                    {
                        "round": round_index,
                        "status": proposal.get("status"),
                        "proposed": len(proposed) if isinstance(proposed, (list, tuple)) else 0,
                        "executed": len(executed),
                        "refused": len(context.refused) - refused_before,
                        # Per-round operations and durable outcomes: I3 needs to
                        # show what each continuation round actually did.
                        "operations": [record.operation for record in executed],
                        "results": [
                            _round_result(record, parameters, observations_before_round)
                            for record, parameters in _pair_proposals(proposed, executed)
                        ],
                    }
                )

                # -- deterministic stop conditions, in priority order --------
                if UNRESOLVED_UNCERTAIN_STOPS_EXECUTOR and any(
                    record.needs_reconciliation for record in executed
                ):
                    stop_reason = "UNRESOLVED_UNCERTAIN"
                    break
                if not executed:
                    stop_reason = "NO_ACTIONS_PROPOSED"
                    break
                if total_actions >= self._max_total_actions:
                    stop_reason = "ACTION_LIMIT_REACHED"
                    break
                if self._max_total_tokens is not None:
                    used = self._token_usage()
                    if used is not None and used >= self._max_total_tokens:
                        stop_reason = "TOKEN_LIMIT_REACHED"
                        break
                if str(proposal.get("status", "")).strip().upper() in _EXECUTOR_DONE_WORDS:
                    # Advisory only: a model saying "done" never completes a task.
                    stop_reason = "MODEL_DECLARED_DONE"
                    break

            execution = TeamMessage(
                task_id=task_id,
                run_id=run_id,
                sender=TeamRole.EXECUTOR,
                receiver=TeamRole.AUDITOR,
                message_type=MessageType.EXECUTION,
                state_version=mailbox.next_state_version,
                parent_message_id=first.parent_message_id,
                payload={
                    "status": previous_status,
                    "rounds": rounds,
                    "stop_reason": stop_reason,
                    "action_results": [
                        {
                            "action_id": record.action_id,
                            "operation": record.operation,
                            "authorization_decision": record.authorization_decision,
                            "durable_state": record.durable_state,
                            "executor_invoked": record.executor_invoked,
                        }
                        for record in executed_all
                    ],
                },
            )
            mailbox.send(execution)
            state.append_event(
                "EXECUTOR_COMPLETED",
                role=TeamRole.EXECUTOR,
                message_id=execution.message_id,
                task_state=TeamPhase.EXECUTOR,
                data={
                    "governed_actions": len(executed_all),
                    "executor_rounds": len(rounds),
                    "stop_reason": stop_reason,
                },
            )

            # AUDITOR: read-only observation, advisory only.  If the Executor
            # left an unresolved action, the audit observes but proposes no
            # action of its own.
            reconciliation_required = any(
                r.needs_reconciliation for r in executed_all
            )
            audit_proposal = self.auditor.handle(mailbox.receive(TeamRole.AUDITOR))
            if reconciliation_required:
                observations = []
                state.append_event(
                    "AUDIT_ACTIONS_SKIPPED_RECOVERY_REQUIRED",
                    role=TeamRole.AUDITOR,
                    data={"proposed": len(audit_proposal.payload.get("actions") or [])},
                )
            else:
                observations = context.run_proposals(
                    audit_proposal.payload.get("actions"),
                    role=TeamRole.AUDITOR,
                    state=state,
                )
            audit = TeamMessage(
                task_id=task_id,
                run_id=run_id,
                sender=TeamRole.AUDITOR,
                receiver=TeamRole.VERIFIER,
                message_type=MessageType.AUDIT,
                state_version=audit_proposal.state_version,
                parent_message_id=audit_proposal.parent_message_id,
                payload={
                    "status": audit_proposal.payload.get("status"),
                    "findings": list(audit_proposal.payload.get("findings") or []),
                    "observation_results": [
                        {
                            "action_id": record.action_id,
                            "operation": record.operation,
                            "durable_state": record.durable_state,
                        }
                        for record in observations
                    ],
                },
            )
            mailbox.send(audit)
            state.append_event(
                "AUDITOR_COMPLETED",
                role=TeamRole.AUDITOR,
                message_id=audit.message_id,
                task_state=TeamPhase.AUDITOR,
            )

            # VERIFIER: the audit message is advisory input only.  The single
            # completion decision comes from CompletionAuthority.
            mailbox.receive(TeamRole.VERIFIER)
            try:
                verification_result = context.completion.request_completion(
                    TeamRole.VERIFIER, task_id
                )
            except (StateTransitionError, CompletionAuthorityViolation) as exc:
                state.append_event(
                    "VERIFICATION_BLOCKED",
                    role=TeamRole.VERIFIER,
                    data={"reason": type(exc).__name__},
                )
                return result("BLOCKED", {"status": "BLOCKED", "accepted": False, "reason": str(exc)[:200]})

            accepted = verification_result.accepted
            verification = {
                "status": "ACCEPTED" if accepted else "REJECTED",
                "accepted": accepted,
                "reason_code": verification_result.reason_code,
                "verifier_version": verification_result.durable.verifier_version,
            }
            verify = TeamMessage(
                task_id=task_id,
                run_id=run_id,
                sender=TeamRole.VERIFIER,
                receiver=TeamRole.HARNESS,
                message_type=MessageType.VERIFY,
                state_version=audit.state_version + 1,
                parent_message_id=audit.message_id,
                payload=verification,
            )
            mailbox.send(verify)
            state.append_event(
                "VERIFIER_COMPLETED",
                role=TeamRole.VERIFIER,
                message_id=verify.message_id,
                task_state=TeamPhase.COMPLETED if accepted else TeamPhase.FAILED,
            )
            return result("VERIFIED_SUCCESS" if accepted else "VERIFIED_FAILURE", verification)
        except Exception as exc:  # fail closed
            # A canonical tool-contract violation is a protocol failure the caller
            # must classify, not an infrastructure failure to absorb here.  It is
            # detected by its stable protocol code, which keeps the scheduler free
            # of an import cycle with the benchmark package.
            if str(getattr(exc, "code", "")).startswith("PROTOCOL_"):
                raise
            state.fail(f"{type(exc).__name__}: {str(exc)[:448]}")
            return result("BLOCKED", {"status": "BLOCKED", "accepted": False, "reason": type(exc).__name__})
