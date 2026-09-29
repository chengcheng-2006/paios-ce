"""Shared contract for the fixed Phase 3 maintenance completion artifact."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any


@dataclass(frozen=True)
class ArtifactContractValidation:
    """Semantic validation result with a stable, content-free reason code."""

    valid: bool
    reason_code: str


@dataclass(frozen=True)
class MaintenanceCompletionArtifactContract:
    """One authoritative contract shared by the Agent, tool, and verifier."""

    schema_id: str = "maintenance_completion.v1"
    artifact_path: str = ".astron-artifacts/change_summary.json"
    required_keys: tuple[str, ...] = ("task_id", "changed_files", "summary")
    required_changed_files: tuple[str, ...] = ("maintenance_config.py",)
    max_summary_characters: int = 256
    max_artifact_bytes: int = 16_384
    allow_extra_keys: bool = True

    def validate(
        self,
        payload: Any,
        task_id: str,
        *,
        artifact_bytes: int | None = None,
    ) -> ArtifactContractValidation:
        """Apply the existing deterministic verifier's artifact semantics."""

        if artifact_bytes is not None and artifact_bytes > self.max_artifact_bytes:
            return ArtifactContractValidation(False, "ARTIFACT_TOO_LARGE")
        if not isinstance(payload, dict):
            return ArtifactContractValidation(False, "ARTIFACT_NOT_OBJECT")
        for required_key in self.required_keys:
            if required_key not in payload:
                return ArtifactContractValidation(
                    False,
                    required_key.upper() + "_MISSING",
                )
        if not isinstance(payload["task_id"], str):
            return ArtifactContractValidation(False, "TASK_ID_WRONG_TYPE")
        if payload["task_id"] != task_id:
            return ArtifactContractValidation(False, "TASK_ID_MISMATCH")
        if not isinstance(payload["changed_files"], list):
            return ArtifactContractValidation(False, "CHANGED_FILES_WRONG_TYPE")
        if payload["changed_files"] != list(self.required_changed_files):
            return ArtifactContractValidation(False, "CHANGED_FILES_MISMATCH")
        if not isinstance(payload["summary"], str):
            return ArtifactContractValidation(False, "SUMMARY_WRONG_TYPE")
        if not payload["summary"].strip():
            return ArtifactContractValidation(False, "SUMMARY_EMPTY")
        if len(payload["summary"]) > self.max_summary_characters:
            return ArtifactContractValidation(False, "SUMMARY_TOO_LONG")
        return ArtifactContractValidation(True, "ARTIFACT_CONTRACT_VALID")

    def json_schema(self, task_id: str) -> dict[str, Any]:
        """Return an Agent-visible schema derived from the same typed values."""

        return {
            "$id": self.schema_id,
            "type": "object",
            "required": list(self.required_keys),
            "properties": {
                "task_id": {"type": "string", "const": task_id},
                "changed_files": {
                    "type": "array",
                    "const": list(self.required_changed_files),
                    "items": {"type": "string"},
                },
                "summary": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": self.max_summary_characters,
                    "pattern": r"\S",
                },
            },
            "additionalProperties": self.allow_extra_keys,
        }

    def agent_instructions(self, task_id: str) -> str:
        """Render the complete schema contract without exposing the solution."""

        required = ", ".join(self.required_keys)
        changed_files = json.dumps(list(self.required_changed_files), separators=(",", ":"))
        trusted_task_id = json.dumps(task_id)
        extras = "allowed" if self.allow_extra_keys else "forbidden"
        return (
            f"Completion artifact contract (schema_id={self.schema_id}): write UTF-8 JSON "
            f"only to {self.artifact_path}. The top level must be an object no larger than "
            f"{self.max_artifact_bytes} bytes. Required keys are: {required}. "
            f"task_id must equal the trusted current task ID {trusted_task_id}. "
            f"changed_files must be the workspace-relative source-file array {changed_files}; "
            "do not include artifacts, SQLite state, bytecode, pytest cache, or other temporary files. "
            f"summary must be a non-empty string of at most {self.max_summary_characters} characters. "
            f"Additional keys are {extras}. Before claiming completion, call validate.json once with "
            f"path={self.artifact_path} and schema_id={self.schema_id}. A syntax-only validate.json "
            "PASS does not establish this semantic contract, and even semantic validation does not "
            "complete the task; the deterministic verifier remains the sole completion authority."
        )

    def safe_metadata(self) -> dict[str, Any]:
        """Return content-free contract evidence suitable for the CLI receipt."""

        return {
            "visible": True,
            "schema_id": self.schema_id,
            "artifact_path": self.artifact_path,
            "required_keys": list(self.required_keys),
            "allow_extra_keys": self.allow_extra_keys,
        }


MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT = MaintenanceCompletionArtifactContract()


__all__ = [
    "ArtifactContractValidation",
    "MaintenanceCompletionArtifactContract",
    "MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT",
]
