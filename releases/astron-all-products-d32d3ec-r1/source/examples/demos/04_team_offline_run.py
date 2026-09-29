#!/usr/bin/env python3
"""Astron example - one offline Team run (EXPERIMENTAL, not a headline demo).

Status of this path, stated plainly:
  * ``team/`` is not installed by the wheel (setuptools packs ``src/`` only) and
    is not reachable from the ``astron`` CLI. Run it from the repository root.
  * Team adds roles, a mailbox and a role-scoped tool authority on top of the
    same Single permission engine, durable store and verifier. It does not add a
    second governance implementation.
  * The scheduler's default round budget is 1. It is a bounded supervisor ->
    executor -> auditor -> verifier pass, not a general multi-agent network.

Run:  PYTHONPATH=src:. python examples/demos/04_team_offline_run.py
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile

from paios_ce.agent.fixture import FixtureWorkspace
from paios_ce.state import SQLiteDurableStateStore
from team.authority import RoleAuthority
from team.mock_provider import MaintenanceTeamProvider
from team.scheduler import TeamScheduler

REPO_ROOT = Path(__file__).resolve().parents[2]
for entry in (str(REPO_ROOT / "src"), str(REPO_ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="astron-team-"))
    workdir.chmod(0o700)
    print(f"[team] artifacts directory: {workdir}")

    workspace = FixtureWorkspace.create(workdir / "fixture")
    with SQLiteDurableStateStore(workdir / "state.sqlite") as store:
        authority = RoleAuthority(workspace.root, store, python_executable=sys.executable)
        result = TeamScheduler(
            authority, workspace.baseline_digest, MaintenanceTeamProvider()
        ).run("team-demo-task", "team-demo-run", {"objective": "repair the fixture timeout"})

    print(f"[team] status          : {result.status}")
    print(f"[team] task_completed  : {result.task_completed}")
    print(f"[team] verification    : {dict(result.verification)}")
    print(f"[team] messages passed : {len(result.messages)}")
    print(f"[team] governed actions: {len(result.actions)}")
    print(f"[team] refused actions : {len(result.refused_actions)}")
    for refused in result.refused_actions:
        print(f"    refused: {refused}")
    print("[team] route of each message:")
    for message in result.messages:
        print(f"    {message.sender.value:>9} -> {message.receiver.value:<9} "
              f"v{message.state_version} {message.message_type.value}")
    print()
    print("[team] the proposals came from a deterministic offline provider; the")
    print("[team] source edit, the bounded pytest run and the completion decision were")
    print("[team] performed and judged by the same Single-core machinery as demo 1.")
    print("[team] note: the bounded test tool executes a real pytest subprocess, so")
    print("[team] this run is model-free and network-free, but not process-free.")
    return 0 if result.verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
