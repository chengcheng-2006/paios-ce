"""Role authority: who may ask for what, expressed over the existing engine.

The Team layer decides *who proposes what*.  Whether a proposed action may
actually happen is answered by Astron's existing ``PermissionEngine``; this
module only selects the correct role-scoped profile and refuses roles that hold
no execution authority at all.

No permission rule, risk rule, capability string or scope rule is reimplemented
here.  ``authority`` is a *selection* layer over ``paios_ce.permissions``.

SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from paios_ce.state import SQLiteDurableStateStore
from paios_ce.tools import BoundedToolRuntime

from .adapters.tool_authority import (
    ROLE_TOOL_PROFILES,
    RoleScopedToolRuntime,
    RoleToolProfile,
    profile_for,
)
from .mailbox import TeamRole


class AuthorityViolation(PermissionError):
    """Raised when a role attempts something its authority forbids.

    Fail closed: the caller must not fall back to a privileged path.
    """


class RoleAuthority:
    """Owns one role-scoped governed runtime per Team role.

    All runtimes share exactly one durable state store, so authorization replay,
    the action journal and task verification remain a single authority.
    """

    #: Roles that may drive the governed tool path at all.
    EXECUTING_ROLES = (TeamRole.EXECUTOR, TeamRole.AUDITOR, TeamRole.VERIFIER)

    def __init__(
        self,
        workspace_root: str | Path,
        state_store: SQLiteDurableStateStore,
        *,
        python_executable: str | Path | None = None,
        pytest_timeout_seconds: int = 15,
    ) -> None:
        self._store = state_store
        self._runtimes: dict[TeamRole, RoleScopedToolRuntime] = {}
        for role in ROLE_TOOL_PROFILES:
            self._runtimes[role] = RoleScopedToolRuntime(
                role,
                workspace_root,
                state_store,
                python_executable=python_executable,
                pytest_timeout_seconds=pytest_timeout_seconds,
            )

    # -- introspection ------------------------------------------------------

    @property
    def state_store(self) -> SQLiteDurableStateStore:
        return self._store

    def profile(self, role: TeamRole) -> RoleToolProfile:
        return profile_for(role)

    def runtime_for(self, role: TeamRole) -> RoleScopedToolRuntime:
        try:
            return self._runtimes[role]
        except KeyError as exc:  # pragma: no cover - defensive
            raise AuthorityViolation(f"role {role!r} holds no governed runtime") from exc

    def can_execute(self, role: TeamRole) -> bool:
        return self.profile(role).can_execute_tools

    def capabilities(self, role: TeamRole) -> frozenset[str]:
        return self.profile(role).capabilities

    def describe(self) -> dict[str, dict[str, Any]]:
        """The frozen role authority matrix, for evidence and tests."""

        return {
            role.value: {
                "principal_id": profile.principal_id,
                "capabilities": sorted(profile.capabilities),
                "can_execute_tools": profile.can_execute_tools,
                "can_mutate_workspace": profile.can_mutate_workspace,
                "fs_write_classes": sorted(profile.fs_write_classes),
            }
            for role, profile in sorted(
                ROLE_TOOL_PROFILES.items(), key=lambda item: item[0].value
            )
        }

    # -- the harness-level gate --------------------------------------------

    def require_tool_authority(self, role: TeamRole) -> RoleScopedToolRuntime:
        """Return the role runtime, or fail closed before any authorization.

        A role with no tool capability (the Supervisor) never reaches the
        governed path.  This is the first of two independent layers: the second
        is the role's own ``PermissionEngine``, which would deny the request even
        if this gate were bypassed.
        """

        runtime = self.runtime_for(role)
        if not runtime.can_execute_tools:
            raise AuthorityViolation(
                f"{role.value} holds no task tool authority and cannot execute actions"
            )
        return runtime

    def require_mutation_authority(self, role: TeamRole) -> None:
        """Fail closed for any role that may not change workspace or artifacts."""

        profile = self.profile(role)
        if not profile.can_mutate_workspace:
            raise AuthorityViolation(f"{role.value} may not mutate the workspace or artifacts")

    # -- capability questions over the existing engine ----------------------

    def allows_operation(self, role: TeamRole, operation: str) -> bool:
        """Whether the role's own engine grants the capability this operation needs.

        Uses the role's real ``PermissionEngine.has_capability``; the
        operation-to-capability mapping is read from the certified bounded
        runtime rather than restated here.
        """

        required = BoundedToolRuntime._CAPABILITIES.get(operation)
        if required is None:
            return False
        return self.runtime_for(role).permission_engine().has_capability(required)

    def operation_capability(self, operation: str) -> str | None:
        return BoundedToolRuntime._CAPABILITIES.get(operation)

    # -- forwarding to the governed path ------------------------------------

    def execute(
        self,
        role: TeamRole,
        task_id: str,
        step: int,
        operation: str,
        parameters: Mapping[str, Any],
    ):
        """Authorize and execute one action through the certified governed path."""

        runtime = self.require_tool_authority(role)
        return runtime.execute(task_id, step, operation, parameters)
