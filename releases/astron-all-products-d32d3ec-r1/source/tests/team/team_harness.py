"""Shared Team test harness.

Deliberately **not** named ``conftest.py``.  A ``conftest.py`` in a directory
without ``__init__.py`` is imported by pytest under the bare module name
``conftest``, which shadows the repository's shared ``tests/conftest.py`` and
breaks collection for the whole suite.  This module is imported explicitly by the
Team test files instead.

Every governed test needs the same three things: a fresh packaged fixture, one
durable state store, and a ``RoleAuthority`` bound to both.  Keeping that in one
place makes it obvious that no test constructs an ungoverned Team path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

from paios_ce.agent.fixture import FixtureWorkspace
from paios_ce.state import SQLiteDurableStateStore

from team.authority import RoleAuthority
from team.mock_provider import MaintenanceTeamProvider, MockLLMProvider
from team.scheduler import TeamRunResult, TeamScheduler


@dataclass
class GovernedTeam:
    """A scheduler wired to one fixture and one durable authority."""

    workspace: FixtureWorkspace
    store: SQLiteDurableStateStore
    authority: RoleAuthority

    def scheduler(self, provider: MockLLMProvider | None = None) -> TeamScheduler:
        return TeamScheduler(
            self.authority,
            self.workspace.baseline_digest,
            provider or MaintenanceTeamProvider(),
        )

    def run(
        self,
        task_id: str = "team-task",
        run_id: str = "team-run",
        payload: dict | None = None,
        *,
        provider: MockLLMProvider | None = None,
        allow_fault_injection: bool = False,
    ) -> TeamRunResult:
        return self.scheduler(provider).run(
            task_id,
            run_id,
            payload or {"objective": "offline"},
            allow_fault_injection=allow_fault_injection,
        )

    def read(self, relative: str) -> str:
        return (self.workspace.root / relative).read_text(encoding="utf-8")

    def close(self) -> None:
        self.store.close()


def build_governed_team(tmp_path: Path) -> GovernedTeam:
    """Create a fresh fixture, state store and role authority."""

    workspace = FixtureWorkspace.create(tmp_path / "fixture")
    store = SQLiteDurableStateStore(tmp_path / "state.sqlite")
    store.__enter__()
    authority = RoleAuthority(workspace.root, store, python_executable=sys.executable)
    return GovernedTeam(workspace=workspace, store=store, authority=authority)
