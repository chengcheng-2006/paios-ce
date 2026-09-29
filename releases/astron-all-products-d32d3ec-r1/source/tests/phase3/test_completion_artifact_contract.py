"""V4 single-source completion-artifact contract regressions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from paios_ce.agent import MaintenanceVerifier, NativeAgent
from paios_ce.agent.fixture import FixtureWorkspace
from paios_ce.maintenance_artifact import MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT
from paios_ce.providers import MockProvider
from paios_ce.state import SQLiteDurableStateStore
from paios_ce.tools import BoundedToolRuntime, ToolInputError


def _call(name: str, arguments: dict[str, object], call_id: str) -> dict[str, object]:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments, sort_keys=True)},
    }


def _correct_payload(task_id: str) -> dict[str, object]:
    return {
        "task_id": task_id,
        "changed_files": ["maintenance_config.py"],
        "summary": "Corrected the bounded maintenance timeout and verified it.",
    }


@pytest.mark.parametrize(
    ("mutate", "reason_code"),
    [
        (lambda payload: payload.pop("task_id"), "TASK_ID_MISSING"),
        (lambda payload: payload.update(task_id=17), "TASK_ID_WRONG_TYPE"),
        (lambda payload: payload.update(task_id="wrong-task"), "TASK_ID_MISMATCH"),
        (lambda payload: payload.pop("changed_files"), "CHANGED_FILES_MISSING"),
        (lambda payload: payload.update(changed_files="maintenance_config.py"), "CHANGED_FILES_WRONG_TYPE"),
        (lambda payload: payload.update(changed_files=["/absolute/maintenance_config.py"]), "CHANGED_FILES_MISMATCH"),
        (lambda payload: payload.pop("summary"), "SUMMARY_MISSING"),
        (lambda payload: payload.update(summary=42), "SUMMARY_WRONG_TYPE"),
        (lambda payload: payload.update(summary="   "), "SUMMARY_EMPTY"),
        (lambda payload: payload.update(summary="x" * 257), "SUMMARY_TOO_LONG"),
    ],
)
def test_completion_artifact_contract_preserves_verifier_negative_semantics(
    tmp_path: Path,
    mutate,
    reason_code: str,
) -> None:
    task_id = "v4-contract-negative"
    payload = _correct_payload(task_id)
    mutate(payload)
    validation = MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT.validate(payload, task_id)
    assert validation.valid is False
    assert validation.reason_code == reason_code

    fixture = FixtureWorkspace.create(tmp_path / "fresh-fixture")
    (fixture.root / "maintenance_config.py").write_text(
        '"""Small configuration module maintained by the Phase 3 fixture."""\n\n'
        "DEFAULT_TIMEOUT_SECONDS = 30\n",
        encoding="utf-8",
    )
    artifact = fixture.root / MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT.artifact_path
    artifact.parent.mkdir(mode=0o700)
    artifact.write_text(json.dumps(payload), encoding="utf-8")
    with SQLiteDurableStateStore(tmp_path / "state.sqlite") as store:
        tools = BoundedToolRuntime(fixture.root, store)
        store.register_task(task_id)
        verification = MaintenanceVerifier(tools, fixture.baseline_digest).verify(task_id)
    assert verification.accepted is False
    assert verification.reason_code == "VERIFIER_ARTIFACT_INVALID"


def test_completion_artifact_contract_preserves_extra_key_semantics() -> None:
    task_id = "v4-contract-extra"
    payload = _correct_payload(task_id)
    payload["additional_context"] = {"safe": True}
    validation = MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT.validate(payload, task_id)
    assert validation.valid is True
    assert MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT.allow_extra_keys is True


def test_agent_visible_contract_and_verifier_share_one_required_field_source(
    tmp_path: Path,
) -> None:
    task_id = "v4-contract-parity"
    fixture = FixtureWorkspace.create(tmp_path / "fresh-fixture")
    provider = MockProvider(tool_call_batches=[[]])
    requests = []
    original = provider.tool_call

    def capture(request):
        requests.append(request)
        return original(request)

    provider.tool_call = capture  # type: ignore[method-assign]
    with SQLiteDurableStateStore(tmp_path / "state.sqlite") as store:
        tools = BoundedToolRuntime(fixture.root, store)
        NativeAgent(provider, tools, MaintenanceVerifier(tools, fixture.baseline_digest)).run(task_id)

    contract = MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT
    instruction = requests[0].messages[0]["content"]
    visible_schema = contract.json_schema(task_id)
    assert set(visible_schema["required"]) == set(contract.required_keys)
    assert set(visible_schema["properties"]) == set(contract.required_keys)
    for required_key in contract.required_keys:
        assert required_key in instruction
    assert contract.schema_id in instruction
    assert contract.artifact_path in instruction
    assert task_id in instruction

    tools_by_name = {
        item["function"]["name"]: item["function"] for item in requests[0].tools
    }
    assert contract.schema_id in tools_by_name["workspace.write_artifact"]["description"]
    validate_schema = tools_by_name["validate.json"]["parameters"]
    assert validate_schema["properties"]["schema_id"]["enum"] == [contract.schema_id]


def test_attempt5_wrong_keys_then_syntax_validation_still_fails_verifier(
    tmp_path: Path,
) -> None:
    fixture = FixtureWorkspace.create(tmp_path / "fresh-fixture")
    task_id = "attempt5-artifact-regression"
    wrong_artifact = json.dumps({
        "schema_version": "1",
        "task": task_id,
        "change": "timeout",
        "validation": "passed",
    })
    provider = MockProvider(tool_call_batches=[
        [_call("workspace.patch_text", {
            "path": "maintenance_config.py",
            "expected_old": "DEFAULT_TIMEOUT_SECONDS = 0",
            "replacement": "DEFAULT_TIMEOUT_SECONDS = 30",
        }, "attempt5-patch")],
        [_call("workspace.write_artifact", {
            "path": ".astron-artifacts/change_summary.json",
            "content": wrong_artifact,
        }, "attempt5-artifact")],
        [_call("validate.json", {
            "path": ".astron-artifacts/change_summary.json",
        }, "attempt5-syntax")],
        [],
    ])
    with SQLiteDurableStateStore(tmp_path / "state.sqlite") as store:
        tools = BoundedToolRuntime(fixture.root, store)
        result = NativeAgent(
            provider, tools, MaintenanceVerifier(tools, fixture.baseline_digest)
        ).run(task_id)
    assert [action["operation"] for action in result.actions] == [
        "workspace.patch_text", "workspace.write_artifact", "validate.json",
    ]
    assert result.actions[-1]["status"] == "success"
    assert result.accepted is False
    assert result.verifier.reason_code == "VERIFIER_ARTIFACT_INVALID"


def test_named_semantic_validation_uses_trusted_task_binding(
    tmp_path: Path,
) -> None:
    fixture = FixtureWorkspace.create(tmp_path / "fresh-fixture")
    task_id = "v4-named-schema"
    artifact = fixture.root / ".astron-artifacts" / "change_summary.json"
    artifact.parent.mkdir(mode=0o700)
    artifact.write_text(json.dumps(_correct_payload(task_id)), encoding="utf-8")
    with SQLiteDurableStateStore(tmp_path / "state.sqlite") as store:
        tools = BoundedToolRuntime(fixture.root, store)
        store.register_task(task_id)
        valid = tools.execute(task_id, 1, "validate.json", {
            "path": MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT.artifact_path,
            "schema_id": MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT.schema_id,
        })
        artifact.write_text(json.dumps(_correct_payload("wrong-task")), encoding="utf-8")
        invalid = tools.execute(task_id, 2, "validate.json", {
            "path": MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT.artifact_path,
            "schema_id": MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT.schema_id,
        })
        with pytest.raises(ToolInputError):
            tools.execute(task_id, 3, "validate.json", {
                "path": MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT.artifact_path,
                "schema_id": "../../untrusted-schema.json",
            })
        with pytest.raises(ToolInputError):
            tools.execute(task_id, 4, "validate.json", {
                "path": "maintenance_config.py",
                "schema_id": MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT.schema_id,
            })
    assert valid.result is not None and valid.result.status.value == "success"
    assert valid.result.outcome["semantic_validation"] == "PASSED"
    assert invalid.result is not None and invalid.result.status.value == "failure"
    assert invalid.result.outcome["semantic_validation"] == "FAILED"
    assert invalid.result.outcome["reason_code"] == "TASK_ID_MISMATCH"


def test_named_semantic_validation_enforces_shared_artifact_byte_bound(
    tmp_path: Path,
) -> None:
    fixture = FixtureWorkspace.create(tmp_path / "fresh-fixture")
    task_id = "v4-named-schema-byte-bound"
    artifact = fixture.root / MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT.artifact_path
    artifact.parent.mkdir(mode=0o700)
    oversized = _correct_payload(task_id)
    oversized["extra"] = "x" * MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT.max_artifact_bytes
    artifact.write_text(json.dumps(oversized), encoding="utf-8")
    with SQLiteDurableStateStore(tmp_path / "state.sqlite") as store:
        tools = BoundedToolRuntime(fixture.root, store)
        store.register_task(task_id)
        validation = tools.execute(task_id, 1, "validate.json", {
            "path": MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT.artifact_path,
            "schema_id": MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT.schema_id,
        })
    assert validation.result is not None
    assert validation.result.status.value == "failure"
    assert validation.result.outcome["semantic_validation"] == "FAILED"
    assert validation.result.outcome["reason_code"] == "ARTIFACT_TOO_LARGE"
