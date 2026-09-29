"""C2 Authority Integration acceptance tests.

Covers the five C2 acceptance criteria:

1. Permission boundary   - Supervisor cannot execute, Auditor cannot mutate,
                           Executor requires real authorization.
2. Action lifecycle      - REQUESTED / AUTHORIZED / STARTED / COMPLETED are
                           produced and provably backed by the durable journal.
3. Verifier authority    - only the Verifier may reach TASK_COMPLETED.
4. Crash recovery        - a crash after the attempt boundary is UNCERTAIN,
                           never SUCCESS.
5. Duplicate protection  - one action identity cannot produce two side effects.

All tests are offline: they use the packaged maintenance fixture and no provider.
"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from pathlib import Path
import sys

import pytest

from paios_ce.agent.fixture import FixtureWorkspace
from paios_ce.state import (
    ActionState,
    RecoveryClassification,
    SQLiteDurableStateStore,
)
from paios_ce.tools import ToolInputError

from team.adapters.tool_authority import RoleScopedToolRuntime
from team.authority import AuthorityViolation, RoleAuthority
from team.journal import (
    ACTION_ALREADY_TERMINAL,
    ACTION_AUTHORIZED,
    ACTION_COMPLETED,
    ACTION_REQUESTED,
    ACTION_STARTED,
    ACTION_UNCERTAIN,
    AUTHORIZATION_CHECKED,
    AUTHORIZATION_DENIED,
    JournalProjectionError,
    TeamActionJournal,
)
from team.lifecycle import ActionLifecycle
from team.mailbox import TeamRole
from team.verifier import CompletionAuthority, CompletionAuthorityViolation

TASK_ID = "c2-acceptance"
RUN_ID = "c2-run-1"

PATCH_OLD = "DEFAULT_TIMEOUT_SECONDS = 0"
PATCH_NEW = "DEFAULT_TIMEOUT_SECONDS = 30"
REPAIR_PARAMS = {
    "path": "maintenance_config.py",
    "expected_old": PATCH_OLD,
    "replacement": PATCH_NEW,
}
ARTIFACT_PATH = ".astron-artifacts/change_summary.json"


@dataclass
class Harness:
    workspace: FixtureWorkspace
    store: SQLiteDurableStateStore
    authority: RoleAuthority
    journal: TeamActionJournal
    lifecycle: ActionLifecycle
    completion: CompletionAuthority

    def read(self, relative: str) -> str:
        return (self.workspace.root / relative).read_text(encoding="utf-8")

    def repair(self, artifact_step: int = 21, patch_step: int = 20) -> None:
        """Make one permitted source correction and write the required artifact."""

        patch = self.lifecycle.submit(TeamRole.EXECUTOR, patch_step, "workspace.patch_text", REPAIR_PARAMS)
        assert patch.durable_state == ActionState.SUCCEEDED.value
        artifact = json.dumps(
            {
                "task_id": TASK_ID,
                "changed_files": ["maintenance_config.py"],
                "summary": "Repaired the default maintenance timeout and verified the suite.",
            },
            sort_keys=True,
        )
        written = self.lifecycle.submit(
            TeamRole.EXECUTOR,
            artifact_step,
            "workspace.write_artifact",
            {"path": ARTIFACT_PATH, "content": artifact},
        )
        assert written.durable_state == ActionState.SUCCEEDED.value


@pytest.fixture
def harness(tmp_path: Path):
    workspace = FixtureWorkspace.create(tmp_path / "fixture")
    store = SQLiteDurableStateStore(tmp_path / "state.sqlite")
    store.__enter__()
    store.register_task(TASK_ID)
    authority = RoleAuthority(workspace.root, store, python_executable=sys.executable)
    journal = TeamActionJournal(TASK_ID, RUN_ID, store)
    lifecycle = ActionLifecycle(authority, journal, TASK_ID)
    completion = CompletionAuthority(authority, workspace.baseline_digest)
    try:
        yield Harness(workspace, store, authority, journal, lifecycle, completion)
    finally:
        store.close()


# ===========================================================================
# 1. Permission boundary
# ===========================================================================


def test_executor_action_is_authorized_and_durably_recorded(harness: Harness) -> None:
    record = harness.lifecycle.submit(TeamRole.EXECUTOR, 1, "workspace.list_files", {})

    assert record.authorization_decision == "allow"
    assert record.executor_invoked is True
    assert record.durable_state == ActionState.SUCCEEDED.value
    assert record.succeeded is True

    entry = harness.journal.durable_entry(record.action_id)
    assert entry is not None
    assert entry.principal_id == harness.authority.profile(TeamRole.EXECUTOR).principal_id
    assert entry.idempotency_key == record.idempotency_key


def test_supervisor_cannot_execute(harness: Harness) -> None:
    with pytest.raises(AuthorityViolation):
        harness.lifecycle.submit(TeamRole.SUPERVISOR, 1, "workspace.list_files", {})

    # The refusal is recorded and no durable action fact was created.
    events = harness.journal.events
    assert any(event.event_type == ACTION_REQUESTED for event in events)
    assert any(event.event_type == AUTHORIZATION_DENIED for event in events)
    assert not any(event.event_type == ACTION_COMPLETED for event in events)
    assert harness.store.recover_task(TASK_ID).classification is RecoveryClassification.NO_ATTEMPT


def test_supervisor_holds_no_capability_and_its_engine_would_also_deny(
    harness: Harness,
) -> None:
    assert harness.authority.can_execute(TeamRole.SUPERVISOR) is False
    assert harness.authority.capabilities(TeamRole.SUPERVISOR) == frozenset()
    assert harness.authority.allows_operation(TeamRole.SUPERVISOR, "workspace.read_text") is False

    # Second, independent layer: bypass the harness gate and go straight to the
    # governed runtime.  The role's own PermissionEngine still denies.
    runtime = harness.authority.runtime_for(TeamRole.SUPERVISOR)
    assert runtime.can_execute_tools is False
    execution = runtime.execute(TASK_ID, 2, "workspace.read_text", {"path": "maintenance_config.py"})
    assert execution.authorization_decision == "deny"
    assert execution.executor_invoked is False


def test_auditor_cannot_mutate_workspace_or_artifacts(harness: Harness) -> None:
    before = harness.read("maintenance_config.py")

    for step, operation, parameters in (
        (10, "workspace.patch_text", REPAIR_PARAMS),
        (11, "workspace.write_artifact", {"path": ARTIFACT_PATH, "content": "{}"}),
    ):
        record = harness.lifecycle.submit(TeamRole.AUDITOR, step, operation, parameters)
        assert record.authorization_decision != "allow"
        assert record.executor_invoked is False
        assert record.denied is True
        assert record.succeeded is False

    assert harness.read("maintenance_config.py") == before
    assert not (harness.workspace.root / ARTIFACT_PATH).exists()
    assert harness.authority.profile(TeamRole.AUDITOR).can_mutate_workspace is False


def test_auditor_may_still_observe_read_only(harness: Harness) -> None:
    record = harness.lifecycle.submit(
        TeamRole.AUDITOR, 12, "workspace.read_text", {"path": "maintenance_config.py"}
    )
    assert record.authorization_decision == "allow"
    assert record.executor_invoked is True
    assert record.durable_state == ActionState.SUCCEEDED.value


def test_executor_cannot_execute_without_the_governed_path() -> None:
    """The Team layer cannot fall back to an ungoverned execution path."""

    signature = inspect.signature(RoleScopedToolRuntime.__init__)
    state_store = signature.parameters["state_store"]
    assert state_store.default is inspect.Parameter.empty, (
        "a role runtime must always be bound to the durable authority"
    )


def test_every_role_shares_exactly_one_durable_authority(harness: Harness) -> None:
    """The whole point of C2: one authority source, not a second execution core."""

    for role in (TeamRole.SUPERVISOR, TeamRole.EXECUTOR, TeamRole.AUDITOR, TeamRole.VERIFIER):
        runtime = harness.authority.runtime_for(role)
        assert runtime.durable_runtime().state_store is harness.store
        assert runtime.permission_engine().durable_state_store is harness.store


def test_role_profiles_are_only_ever_narrowings_of_the_single_grant(
    harness: Harness,
) -> None:
    from paios_ce.tools import BoundedToolRuntime
    from team.adapters.tool_authority import ROLE_TOOL_PROFILES

    full_grant = set(BoundedToolRuntime._CAPABILITIES.values())
    assert set(ROLE_TOOL_PROFILES) == {
        TeamRole.SUPERVISOR,
        TeamRole.EXECUTOR,
        TeamRole.AUDITOR,
        TeamRole.VERIFIER,
    }
    for role, profile in ROLE_TOOL_PROFILES.items():
        assert set(profile.capabilities) <= full_grant
        assert harness.authority.capabilities(role) == profile.capabilities


# ===========================================================================
# 2. Action lifecycle
# ===========================================================================


def test_lifecycle_emits_requested_authorized_started_completed(harness: Harness) -> None:
    record = harness.lifecycle.submit(TeamRole.EXECUTOR, 1, "workspace.list_files", {})

    assert record.event_types == (
        ACTION_REQUESTED,
        AUTHORIZATION_CHECKED,
        ACTION_AUTHORIZED,
        ACTION_STARTED,
        ACTION_COMPLETED,
    )


def test_denied_lifecycle_reports_denial_and_never_a_start(harness: Harness) -> None:
    record = harness.lifecycle.submit(TeamRole.AUDITOR, 13, "workspace.patch_text", REPAIR_PARAMS)

    assert ACTION_AUTHORIZED not in record.event_types
    assert ACTION_STARTED not in record.event_types
    assert ACTION_COMPLETED not in record.event_types
    assert AUTHORIZATION_DENIED in record.event_types


def test_lifecycle_events_correspond_to_durable_journal_states(harness: Harness) -> None:
    record = harness.lifecycle.submit(TeamRole.EXECUTOR, 1, "workspace.list_files", {})

    durable_states = [event.state for event in harness.journal.durable_events(record.action_id)]
    assert durable_states == [
        ActionState.RECORDED,
        ActionState.AUTHORIZED,
        ActionState.ATTEMPT_STARTED,
        ActionState.SUCCEEDED,
    ]
    # Every Team transition carries the durable sequence it was derived from.
    projected = [
        event
        for event in harness.journal.events_for(record.action_id)
        if "durable_sequence" in event.data
    ]
    assert [event.data["durable_sequence"] for event in projected] == [2, 3, 4]
    assert [event.event_type for event in projected] == [
        ACTION_AUTHORIZED,
        ACTION_STARTED,
        ACTION_COMPLETED,
    ]
    harness.journal.assert_projection_consistent(record.action_id)
    harness.journal.assert_no_unbacked_success()


def test_team_journal_cannot_claim_a_success_the_journal_does_not_record(
    harness: Harness,
) -> None:
    """The guard that keeps Astron at one authority source."""

    harness.journal.record(ACTION_COMPLETED, action_id="ghost-action", role=TeamRole.EXECUTOR)
    with pytest.raises(JournalProjectionError):
        harness.journal.assert_projection_consistent("ghost-action")
    with pytest.raises(JournalProjectionError):
        harness.journal.assert_no_unbacked_success()


# ===========================================================================
# 3. Verifier authority
# ===========================================================================


@pytest.mark.parametrize(
    "role", [TeamRole.SUPERVISOR, TeamRole.EXECUTOR, TeamRole.AUDITOR]
)
def test_non_verifier_roles_cannot_complete(harness: Harness, role: TeamRole) -> None:
    with pytest.raises(CompletionAuthorityViolation):
        harness.completion.request_completion(role, TASK_ID)

    # The refusal happened before verification, so no completion fact exists.
    assert harness.completion.task_completed(TASK_ID) is False
    assert harness.completion.completion_record(TASK_ID) is None
    assert [attempt.role for attempt in harness.completion.rejected_attempts] == [role]


def test_only_the_verifier_can_complete_a_repaired_task(harness: Harness) -> None:
    harness.repair()
    assert harness.completion.task_completed(TASK_ID) is False

    result = harness.completion.request_completion(TeamRole.VERIFIER, TASK_ID)

    assert result.accepted is True
    assert result.reason_code == "VERIFIER_ACCEPTED"
    assert harness.completion.task_completed(TASK_ID) is True
    evidence = harness.completion.completion_evidence(TASK_ID)
    assert evidence["task_completed"] is True
    assert evidence["status"] == "ACCEPTED"


def test_verifier_rejects_an_unrepaired_task(harness: Harness) -> None:
    result = harness.completion.request_completion(TeamRole.VERIFIER, TASK_ID)

    assert result.accepted is False
    assert harness.completion.task_completed(TASK_ID) is False


def test_completion_roles_are_exactly_the_verifier(harness: Harness) -> None:
    assert CompletionAuthority.COMPLETING_ROLE is TeamRole.VERIFIER
    assert harness.authority.profile(TeamRole.VERIFIER).can_mutate_workspace is False


# ===========================================================================
# 4. Crash recovery
# ===========================================================================


def test_crash_after_attempt_boundary_is_uncertain_never_success(
    harness: Harness,
) -> None:
    record = harness.lifecycle.simulate_crash_after_attempt_started(
        TeamRole.EXECUTOR, 30, "workspace.patch_text", REPAIR_PARAMS
    )

    assert record.needs_reconciliation is True
    assert record.durable_state == ActionState.UNCERTAIN.value
    assert record.succeeded is False
    assert ACTION_UNCERTAIN in record.event_types
    assert ACTION_COMPLETED not in record.event_types

    entry = harness.journal.durable_entry(record.action_id)
    assert entry is not None and entry.current_state is ActionState.UNCERTAIN

    recovered = harness.lifecycle.assert_recovery_never_reports_success()
    assert recovered.classification is RecoveryClassification.NEEDS_RECONCILIATION
    assert recovered.journal is not None
    assert recovered.journal.current_state is ActionState.UNCERTAIN
    assert recovered.classification is not RecoveryClassification.TERMINAL_SUCCESS


def test_recovery_never_executes_anything(harness: Harness) -> None:
    harness.lifecycle.simulate_crash_after_attempt_started(
        TeamRole.EXECUTOR, 31, "workspace.patch_text", REPAIR_PARAMS
    )
    before = harness.read("maintenance_config.py")

    harness.lifecycle.recover()
    harness.lifecycle.recover()

    assert harness.read("maintenance_config.py") == before


def test_recovery_reports_success_only_for_a_durable_success(harness: Harness) -> None:
    harness.lifecycle.submit(TeamRole.EXECUTOR, 1, "workspace.list_files", {})

    recovered = harness.lifecycle.recover()

    assert recovered.classification is RecoveryClassification.TERMINAL_SUCCESS
    assert recovered.journal is not None
    assert recovered.journal.current_state is ActionState.SUCCEEDED


def test_uncertain_action_is_not_a_completion(harness: Harness) -> None:
    harness.lifecycle.simulate_crash_after_attempt_started(
        TeamRole.EXECUTOR, 32, "workspace.patch_text", REPAIR_PARAMS
    )

    assert harness.completion.task_completed(TASK_ID) is False


# ===========================================================================
# 5. Duplicate protection
# ===========================================================================


def test_duplicate_action_does_not_replay_the_side_effect(harness: Harness) -> None:
    first = harness.lifecycle.submit(TeamRole.EXECUTOR, 40, "workspace.patch_text", REPAIR_PARAMS)
    assert first.executor_invoked is True
    assert first.succeeded is True
    after_first = harness.read("maintenance_config.py")
    durable_events_after_first = len(harness.journal.durable_events(first.action_id))

    second = harness.lifecycle.submit(TeamRole.EXECUTOR, 40, "workspace.patch_text", REPAIR_PARAMS)

    assert second.action_id == first.action_id
    assert second.idempotency_key == first.idempotency_key
    assert second.executor_invoked is False
    assert second.durable_state == ActionState.SUCCEEDED.value
    assert ACTION_ALREADY_TERMINAL in second.event_types

    # Exactly one side effect: the file was patched once and the executor never
    # ran a second time (a second run would have failed its precondition).
    assert harness.read("maintenance_config.py") == after_first
    assert harness.read("maintenance_config.py").count(PATCH_NEW) == 1
    assert len(harness.journal.durable_events(first.action_id)) == durable_events_after_first


def test_one_action_identity_cannot_describe_two_different_requests(
    harness: Harness,
) -> None:
    first = harness.lifecycle.submit(TeamRole.EXECUTOR, 41, "workspace.patch_text", REPAIR_PARAMS)
    assert first.succeeded is True
    after_first = harness.read("maintenance_config.py")

    # Same step and operation => same action_id, but different parameters.
    conflicting = harness.lifecycle.submit(
        TeamRole.EXECUTOR,
        41,
        "workspace.patch_text",
        {
            "path": "maintenance_config.py",
            "expected_old": PATCH_NEW,
            "replacement": "DEFAULT_TIMEOUT_SECONDS = 45",
        },
    )

    assert conflicting.action_id == first.action_id
    assert conflicting.authorization_decision != "allow"
    assert conflicting.executor_invoked is False
    assert conflicting.denied is True
    assert harness.read("maintenance_config.py") == after_first


def test_distinct_steps_produce_distinct_actions(harness: Harness) -> None:
    one = harness.lifecycle.submit(TeamRole.EXECUTOR, 50, "workspace.list_files", {})
    two = harness.lifecycle.submit(TeamRole.EXECUTOR, 51, "workspace.list_files", {})

    assert one.action_id != two.action_id
    assert one.idempotency_key != two.idempotency_key
    assert one.executor_invoked is True and two.executor_invoked is True


# ===========================================================================
# Boundary: no live provider, no benchmark
# ===========================================================================


def test_authority_layer_cannot_reach_a_provider_or_the_network() -> None:
    """C2 must not be able to reach a model, a benchmark, or the network.

    Checked over the actual import graph rather than by substring search.
    """

    import ast

    import team.authority as authority_module
    import team.journal as journal_module
    import team.lifecycle as lifecycle_module
    import team.verifier as verifier_module

    network_roots = {"requests", "urllib", "urllib3", "http", "socket", "httpx", "ssl"}
    for module in (authority_module, lifecycle_module, verifier_module, journal_module):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        roots = {name.split(".")[0] for name in imported}
        assert not (roots & network_roots), f"{module.__name__} imports {roots & network_roots}"
        assert not any("providers" in name for name in imported), (
            f"{module.__name__} imports a provider module"
        )
