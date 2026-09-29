"""Deterministic, no-network provider used only by Team unit tests."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping

from .mailbox import TeamRole


@dataclass(frozen=True, slots=True)
class ProviderCall:
    role: TeamRole
    operation: str
    task_id: str
    run_id: str


#: One synthetic provider call.  Every mock role call reports exactly this, so the
#: per-call cost basis is identical for every arm and every role.
SYNTHETIC_CALL_USAGE: Mapping[str, int] = {
    "prompt_tokens": 100,
    "completion_tokens": 25,
    "prompt_cache_hit_tokens": 0,
    "prompt_cache_miss_tokens": 100,
    "reasoning_tokens": 10,
}


class MockLLMProvider:
    """A deterministic stand-in; it never reads credentials or performs I/O.

    Implements the same role-provider contract as a live provider: ``plan``,
    ``execute`` and ``audit`` return a role payload, ``calls`` records the role
    calls made, and ``drain_usage`` yields the token usage attributable to them.
    A live provider differs only in where those values come from.
    """

    def __init__(self) -> None:
        self.calls: list[ProviderCall] = []
        self._pending_usage: list[dict[str, int]] = []

    def _record(self, role: TeamRole, operation: str, task_id: str, run_id: str) -> None:
        self.calls.append(ProviderCall(role, operation, task_id, run_id))
        self._pending_usage.append(dict(SYNTHETIC_CALL_USAGE))

    def drain_usage(self) -> list[dict[str, int]]:
        """Return and clear the usage attributable to calls made so far."""

        drained = list(self._pending_usage)
        self._pending_usage.clear()
        return drained

    def plan(self, task_id: str, run_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        self._record(TeamRole.SUPERVISOR, "plan", task_id, run_id)
        return {
            "objective": payload.get("objective", "mock task"),
            "steps": ["mock_execution"],
        }

    def execute(self, task_id: str, run_id: str, plan: Mapping[str, Any]) -> dict[str, Any]:
        self._record(TeamRole.EXECUTOR, "execute", task_id, run_id)
        return {
            "status": "MOCK_EXECUTED",
            "plan_steps": list(plan.get("steps", [])),
            "artifact_ref": f"mock://{task_id}",
        }

    def audit(self, task_id: str, run_id: str, execution: Mapping[str, Any]) -> dict[str, Any]:
        self._record(TeamRole.AUDITOR, "audit", task_id, run_id)
        return {
            "status": "PASS",
            "checked_artifact": execution.get("artifact_ref"),
            "findings": [],
        }


class MaintenanceTeamProvider(MockLLMProvider):
    """Deterministic offline provider that drives the packaged maintenance fixture.

    It only *proposes*: the Supervisor proposes no actions, the Executor proposes
    the source repair and the completion artifact, and the Auditor proposes a
    read-only validation.  Whether any of that happens is decided by the
    authority path, not here.
    """

    SOURCE_PATH = "maintenance_config.py"
    ARTIFACT_PATH = ".astron-artifacts/change_summary.json"
    REPAIR_OLD = "DEFAULT_TIMEOUT_SECONDS = 0"
    REPAIR_NEW = "DEFAULT_TIMEOUT_SECONDS = 30"
    SUMMARY = "Repaired the default maintenance timeout and verified the trusted suite."

    def plan(self, task_id: str, run_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        self.calls.append(ProviderCall(TeamRole.SUPERVISOR, "plan", task_id, run_id))
        return {
            "objective": payload.get("objective", "offline maintenance repair"),
            "steps": [self.SOURCE_PATH, self.ARTIFACT_PATH],
        }

    def execute(self, task_id: str, run_id: str, plan: Mapping[str, Any]) -> dict[str, Any]:
        self.calls.append(ProviderCall(TeamRole.EXECUTOR, "execute", task_id, run_id))
        artifact = json.dumps(
            {
                "task_id": task_id,
                "changed_files": [self.SOURCE_PATH],
                "summary": self.SUMMARY,
            },
            sort_keys=True,
        )
        return {
            "status": "PROPOSED",
            "actions": [
                {
                    "operation": "workspace.patch_text",
                    "parameters": {
                        "path": self.SOURCE_PATH,
                        "expected_old": self.REPAIR_OLD,
                        "replacement": self.REPAIR_NEW,
                    },
                },
                {
                    "operation": "workspace.write_artifact",
                    "parameters": {"path": self.ARTIFACT_PATH, "content": artifact},
                },
            ],
        }

    def audit(self, task_id: str, run_id: str, execution: Mapping[str, Any]) -> dict[str, Any]:
        self.calls.append(ProviderCall(TeamRole.AUDITOR, "audit", task_id, run_id))
        return {
            "status": "PASS",
            "findings": [],
            "actions": [
                {"operation": "validate.file", "parameters": {"path": self.SOURCE_PATH}},
            ],
        }
