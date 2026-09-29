"""Deterministic verifier for the one Phase 3 maintenance fixture."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from ..maintenance_artifact import MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT
from ..state import TaskVerification, VerificationStatus
from ..tools import BoundedToolRuntime
from .fixture import tree_digest


@dataclass(frozen=True)
class VerificationResult:
    accepted: bool
    reason_code: str
    evidence: dict[str, object]
    durable: TaskVerification


class MaintenanceVerifier:
    """Fixed oracle for a fresh trusted fixture, not a general repo verifier."""

    VERSION = "phase3-maintenance-verifier-v1"

    def __init__(self, tools: BoundedToolRuntime, baseline_digest: str) -> None:
        self._tools = tools
        self._root = tools.workspace_root
        self._baseline_digest = baseline_digest

    def verify(self, task_id: str, *, step: int = 90) -> VerificationResult:
        """Run deterministic structural checks, bounded tests, then persist a result."""

        failure = self._structural_failure(task_id)
        if failure is not None:
            code, evidence = failure
            return self._persist(task_id, False, code, evidence)
        test = self._tools.execute(task_id, step, "test.run_pytest_bounded", {})
        if (
            not test.executor_invoked
            or test.needs_reconciliation
            or test.result is None
            or test.result.status.value != "success"
            or test.result.outcome.get("status") != "PASSED"
        ):
            return self._persist(
                task_id,
                False,
                "VERIFIER_TEST_FAILED",
                {"baseline_digest": self._baseline_digest[:16], "test_action": test.action.action_id},
            )
        final_digest = tree_digest(self._root, exclude={".astron-artifacts", "__pycache__", ".pytest_cache"})
        return self._persist(
            task_id,
            True,
            "VERIFIER_ACCEPTED",
            {
                "baseline_digest": self._baseline_digest[:16],
                "final_digest": final_digest[:16],
                "test_status": "PASSED",
            },
        )

    def _structural_failure(self, task_id: str) -> tuple[str, dict[str, object]] | None:
        try:
            paths = self._changed_or_unexpected_paths()
        except OSError:
            return "VERIFIER_SCOPE_VIOLATION", {"baseline_digest": self._baseline_digest[:16]}
        if paths:
            return "VERIFIER_SCOPE_VIOLATION", {"unexpected_path_count": len(paths)}
        config = self._root / "maintenance_config.py"
        try:
            config_text = config.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return "VERIFIER_CONFIG_INVALID", {"baseline_digest": self._baseline_digest[:16]}
        if config_text != '"""Small configuration module maintained by the Phase 3 fixture."""\n\nDEFAULT_TIMEOUT_SECONDS = 30\n':
            return "VERIFIER_CONFIG_NOT_REPAIRED", {"baseline_digest": self._baseline_digest[:16]}
        contract = MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT
        artifact = self._root / contract.artifact_path
        try:
            raw = artifact.read_text(encoding="utf-8")
            payload = json.loads(raw)
        except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
            return "VERIFIER_ARTIFACT_INVALID", {"baseline_digest": self._baseline_digest[:16]}
        if not contract.validate(
            payload,
            task_id,
            artifact_bytes=len(raw.encode("utf-8")),
        ).valid:
            return "VERIFIER_ARTIFACT_INVALID", {"baseline_digest": self._baseline_digest[:16]}
        return None

    def _changed_or_unexpected_paths(self) -> list[str]:
        """Reject every source/test mutation except the declared source file."""

        unexpected: list[str] = []
        allowed_top = {".astron-artifacts", "__pycache__", ".pytest_cache"}
        expected_files = {
            "README.md": (
                "# AIC 2026 repository-maintenance fixture\n\n"
                "This is a deliberately small, trusted fixture for Astron Phase 3. Its\n"
                "`tests/` directory fails on an untouched fresh copy. A task must make one\n"
                "permitted source correction, produce `.astron-artifacts/change_summary.json`,\n"
                "and pass the trusted verifier. It is not an arbitrary-code sandbox and must\n"
                "not be pointed at an Owner repository.\n"
            ),
            "tests/test_maintenance_config.py": (
                "from maintenance_config import DEFAULT_TIMEOUT_SECONDS\n\n\n"
                "def test_default_timeout_is_safe_for_interactive_maintenance() -> None:\n"
                "    assert DEFAULT_TIMEOUT_SECONDS == 30\n"
            ),
        }
        for path in sorted(self._root.rglob("*")):
            relative = path.relative_to(self._root).as_posix()
            if relative.split("/", 1)[0] in allowed_top or "__pycache__" in relative.split("/"):
                continue
            if path.is_symlink() or (path.is_dir() and relative != "tests"):
                unexpected.append(relative)
            elif path.is_file() and relative not in {"maintenance_config.py", *expected_files}:
                unexpected.append(relative)
            elif path.is_file() and relative in expected_files:
                try:
                    if path.read_text(encoding="utf-8") != expected_files[relative]:
                        unexpected.append(relative)
                except (OSError, UnicodeDecodeError):
                    unexpected.append(relative)
        return unexpected

    def _persist(
        self,
        task_id: str,
        accepted: bool,
        reason_code: str,
        evidence: dict[str, object],
    ) -> VerificationResult:
        durable = self._tools.state_store.record_task_verification(
            task_id,
            VerificationStatus.ACCEPTED if accepted else VerificationStatus.REJECTED,
            reason_code,
            self.VERSION,
            evidence,
        )
        return VerificationResult(
            accepted=durable.status is VerificationStatus.ACCEPTED,
            reason_code=durable.reason_code,
            evidence=durable.evidence,
            durable=durable,
        )
