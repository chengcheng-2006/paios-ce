"""Role-scoped tool authority expressed entirely through existing src/ classes.

The problem this adapter solves
-------------------------------
``BoundedToolRuntime.__init__`` grants *every* caller the same authority:

    capabilities = set(self._CAPABILITIES.values())   # all five capabilities
    principal_id = "principal:astron/phase3-native-agent"

so a Supervisor, an Executor and an Auditor holding that runtime are
indistinguishable and fully privileged.  There is no public constructor that
expresses "this role may read but not mutate".

What this adapter does
----------------------
``RoleScopedToolRuntime`` subclasses the certified runtime and re-parameterizes
**only** the authority profile, using the same public ``PermissionEngine``,
``ScopeGuard`` and ``DurableActionRuntime`` that the base constructor already
uses.  All request building, parameter normalization, path/scope checks, dispatch
and execution stay inherited and unmodified.

It copies no permission, journal, runtime or verifier logic, and it does not
weaken the base class: a role profile is always a subset of the base grant.

SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from paios_ce.permissions import PermissionEngine, PrincipalContext, ScopeGuard
from paios_ce.protocols import ActionRequest, ActionResult
from paios_ce.runtime.durable_runtime import DurableActionRuntime, DurableExecutionResult
from paios_ce.state import SQLiteDurableStateStore
from paios_ce.tools import BoundedToolRuntime

from ..mailbox import TeamRole


class UnknownRoleError(ValueError):
    """Raised when a Team role has no declared authority profile."""


#: Capability strings are the ones already used by ``BoundedToolRuntime._CAPABILITIES``.
CAPABILITY_READ = "WORKSPACE_READ"
CAPABILITY_WRITE = "WORKSPACE_WRITE"
CAPABILITY_ARTIFACT = "ARTIFACT_WRITE"
CAPABILITY_TEST = "TEST_RUN_PYTEST"

_READ_SCOPE = BoundedToolRuntime.WORKSPACE_SCOPE
_ARTIFACT_SCOPE = BoundedToolRuntime.ARTIFACT_SCOPE


@dataclass(frozen=True, slots=True)
class RoleToolProfile:
    """The complete authority a Team role is allowed to hold."""

    role: TeamRole
    principal_id: str
    capabilities: frozenset[str]
    fs_read_classes: frozenset[str]
    fs_write_classes: frozenset[str]

    @property
    def can_execute_tools(self) -> bool:
        return bool(self.capabilities)

    @property
    def can_mutate_workspace(self) -> bool:
        return CAPABILITY_WRITE in self.capabilities or CAPABILITY_ARTIFACT in self.capabilities


#: Deny-by-default role matrix.  A role is expressed by narrowing, never extending.
ROLE_TOOL_PROFILES: Mapping[TeamRole, RoleToolProfile] = {
    # The Supervisor plans.  It holds no tool capability at all, so an attempted
    # tool action is denied by the real Permission Engine rather than by prose.
    TeamRole.SUPERVISOR: RoleToolProfile(
        role=TeamRole.SUPERVISOR,
        principal_id="principal:astron/team-supervisor",
        capabilities=frozenset(),
        fs_read_classes=frozenset(),
        fs_write_classes=frozenset(),
    ),
    # The Executor is the only role that may mutate the workspace or artifacts.
    TeamRole.EXECUTOR: RoleToolProfile(
        role=TeamRole.EXECUTOR,
        principal_id="principal:astron/team-executor",
        capabilities=frozenset({
            CAPABILITY_READ,
            CAPABILITY_WRITE,
            CAPABILITY_ARTIFACT,
            CAPABILITY_TEST,
        }),
        fs_read_classes=frozenset({_READ_SCOPE}),
        fs_write_classes=frozenset({_READ_SCOPE, _ARTIFACT_SCOPE}),
    ),
    # The Auditor observes.  It may read and run the trusted bounded test, but it
    # holds no write capability and no write scope, so it cannot mutate anything.
    TeamRole.AUDITOR: RoleToolProfile(
        role=TeamRole.AUDITOR,
        principal_id="principal:astron/team-auditor",
        capabilities=frozenset({CAPABILITY_READ, CAPABILITY_TEST}),
        fs_read_classes=frozenset({_READ_SCOPE}),
        fs_write_classes=frozenset(),
    ),
    # The Verifier runs the deterministic bounded test as part of verification.
    # It is not granted write or artifact capability; completion authority comes
    # from MaintenanceVerifier, not from a tool.
    TeamRole.VERIFIER: RoleToolProfile(
        role=TeamRole.VERIFIER,
        principal_id="principal:astron/team-verifier",
        capabilities=frozenset({CAPABILITY_READ, CAPABILITY_TEST}),
        fs_read_classes=frozenset({_READ_SCOPE}),
        fs_write_classes=frozenset(),
    ),
}

ROLE_PRINCIPALS: Mapping[TeamRole, str] = {
    role: profile.principal_id for role, profile in ROLE_TOOL_PROFILES.items()
}


def profile_for(role: TeamRole) -> RoleToolProfile:
    try:
        return ROLE_TOOL_PROFILES[role]
    except KeyError as exc:  # pragma: no cover - defensive
        raise UnknownRoleError(f"no authority profile for role {role!r}") from exc


class RoleScopedToolRuntime(BoundedToolRuntime):
    """The certified bounded runtime, re-scoped to one Team role.

    Inherited unchanged: request construction, parameter normalization, path and
    scope enforcement, operation dispatch, artifact/test execution, and the
    governed ``execute`` entry point that drives authorization -> journal ->
    attempt boundary -> executor -> terminal fact.
    """

    def __init__(
        self,
        role: TeamRole,
        workspace_root: str | Path,
        state_store: SQLiteDurableStateStore,
        *,
        python_executable: str | Path | None = None,
        pytest_timeout_seconds: int = 15,
    ) -> None:
        super().__init__(
            workspace_root,
            state_store,
            python_executable=python_executable,
            pytest_timeout_seconds=pytest_timeout_seconds,
        )
        profile = profile_for(role)
        self.role = role
        self.profile = profile
        # Re-scope authority with the same public classes the base constructor
        # used.  The base grant is only ever narrowed here.
        shared_store = self._runtime.state_store
        self._engine = PermissionEngine(
            capabilities=set(profile.capabilities),
            owner_allowlist=set(),
            principal_id=profile.principal_id,
            scope_guard=ScopeGuard(
                fs_read_classes=set(profile.fs_read_classes),
                fs_write_classes=set(profile.fs_write_classes),
            ),
            durable_state_store=shared_store,
        )
        self._runtime = DurableActionRuntime(self._engine, shared_store)

    # -- read-only introspection -------------------------------------------

    @property
    def principal_id(self) -> str:
        return self.profile.principal_id

    @property
    def capabilities(self) -> frozenset[str]:
        return self.profile.capabilities

    @property
    def can_execute_tools(self) -> bool:
        return self.profile.can_execute_tools

    # -- reuse-only extensions ---------------------------------------------

    def build_request(
        self,
        task_id: str,
        step: int,
        operation: str,
        parameters: Mapping[str, Any],
    ) -> ActionRequest:
        """Public accessor over the inherited request builder.

        Exposed so the authority layer can inspect or reason about the exact
        request the certified builder would produce, without duplicating it.
        """

        return self._build_request(task_id, step, operation, parameters)

    def principal_context(self) -> PrincipalContext:
        return PrincipalContext(principal_id=self.profile.principal_id)

    def execute_governed(
        self,
        task_id: str,
        step: int,
        operation: str,
        parameters: Mapping[str, Any],
    ) -> DurableExecutionResult:
        """Run the inherited governed path, retaining the durable journal entry.

        Identical to the inherited ``execute()`` — same request builder, same
        ``DurableActionRuntime``, same terminal executor — except that the
        returned ``DurableExecutionResult`` still carries its ``JournalEntry``.

        The Team layer needs that journal identifier to *prove* its lifecycle
        claims against the one authority.  No authorization, journal or
        execution logic is duplicated: both entry points call the same
        ``DurableActionRuntime.execute`` with the runtime's own terminal
        executor.
        """

        return self._governed(task_id, step, operation, parameters, self._execute_request)

    def execute_with_executor(
        self,
        task_id: str,
        step: int,
        operation: str,
        parameters: Mapping[str, Any],
        executor: Callable[[ActionRequest], ActionResult],
    ) -> DurableExecutionResult:
        """Run the governed path with a caller-supplied terminal executor.

        Used for deterministic fault injection.  Authorization and the durable
        attempt boundary are unchanged; only the innermost side effect is
        replaced.  A crash after the attempt boundary therefore produces
        ``UNCERTAIN`` exactly as it would in production.
        """

        return self._governed(task_id, step, operation, parameters, executor)

    def _governed(
        self,
        task_id: str,
        step: int,
        operation: str,
        parameters: Mapping[str, Any],
        executor: Callable[[ActionRequest], ActionResult],
    ) -> DurableExecutionResult:
        request = self._build_request(task_id, step, operation, parameters)
        return self._runtime.execute(
            task_id,
            request,
            executor,
            principal_context=self.principal_context(),
        )

    def durable_runtime(self) -> DurableActionRuntime:
        """The exact durable runtime this role is governed by."""

        return self._runtime

    def permission_engine(self) -> PermissionEngine:
        """The exact permission engine this role is governed by."""

        return self._engine
