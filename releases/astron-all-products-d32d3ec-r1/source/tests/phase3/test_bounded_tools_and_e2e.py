"""Phase 3 bounded-tool, recovery, verifier, and deterministic offline E2E tests."""

from __future__ import annotations

from pathlib import Path
import json
import sqlite3

import pytest

from paios_ce.agent import MaintenanceVerifier, NativeAgent, offline_maintenance_provider
from paios_ce.agent.fixture import FixtureError, FixtureWorkspace, maintenance_fixture_source, tree_digest
from paios_ce.providers import LiveProviderError, LiveProviderErrorCode, MockProvider, ToolCallResult
from paios_ce.state import SQLiteDurableStateStore, VerificationStatus
from paios_ce.tools import BoundedToolRuntime, ToolInputError


def _fixture(tmp_path: Path) -> FixtureWorkspace:
    return FixtureWorkspace.create(tmp_path / "fresh-fixture")


def _tool_call(name: str, arguments: dict[str, object], index: int) -> dict[str, object]:
    return {
        "id": f"cardinality-{index}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments, sort_keys=True)},
    }


def test_public_example_mirrors_the_packaged_fixture_source() -> None:
    example = Path(__file__).resolve().parents[2] / "examples" / "aic2026_repo_maintenance"
    assert tree_digest(example) == tree_digest(maintenance_fixture_source())


def test_offline_mock_e2e_uses_durable_actions_and_verifier_only_completion(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    with SQLiteDurableStateStore(tmp_path / "state.sqlite") as store:
        tools = BoundedToolRuntime(fixture.root, store)
        task_id = "phase3-offline-e2e"
        result = NativeAgent(
            offline_maintenance_provider(task_id),
            tools,
            MaintenanceVerifier(tools, fixture.baseline_digest),
        ).run(task_id)
        durable = store.task_verification(task_id)
        checkpoint = store.checkpoint(task_id)
    with SQLiteDurableStateStore(tmp_path / "state.sqlite") as restarted:
        recovered = restarted.recover_task(task_id)
        persisted = restarted.task_verification(task_id)
        final_checkpoint = restarted.checkpoint(task_id)
        assert recovered.journal is not None
        events_before = restarted.journal_events(recovered.journal.journal_id)
        again = restarted.recover_task(task_id)
        events_after = restarted.journal_events(recovered.journal.journal_id)
    assert result.accepted is True
    assert result.verifier.reason_code == "VERIFIER_ACCEPTED"
    assert [action["operation"] for action in result.actions] == [
        "workspace.read_text", "workspace.read_text", "workspace.read_text",
        "workspace.patch_text", "test.run_pytest_bounded", "workspace.write_artifact",
        "validate.json",
    ]
    assert result.actions[-1]["semantic_validation"] == "PASSED"
    assert durable is not None and durable.status is VerificationStatus.ACCEPTED
    assert checkpoint is not None and checkpoint.runtime_state == "TASK_COMPLETED"
    assert recovered.classification.value == "TERMINAL_SUCCESS"
    assert persisted is not None and persisted.status is VerificationStatus.ACCEPTED
    assert final_checkpoint is not None and final_checkpoint.runtime_state == "TASK_COMPLETED"
    assert again.classification.value == "TERMINAL_SUCCESS"
    assert events_after == events_before


def test_model_claiming_done_without_repair_is_not_task_completion(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    with SQLiteDurableStateStore(tmp_path / "state.sqlite") as store:
        tools = BoundedToolRuntime(fixture.root, store)
        result = NativeAgent(
            MockProvider(tool_call_batches=[[]]),
            tools,
            MaintenanceVerifier(tools, fixture.baseline_digest),
        ).run("phase3-false-completion")
        durable = store.task_verification("phase3-false-completion")
    assert result.accepted is False
    assert result.verifier.reason_code == "VERIFIER_CONFIG_NOT_REPAIRED"
    assert durable is not None and durable.status is VerificationStatus.REJECTED


def test_native_agent_retains_only_safe_provider_failure_diagnostics(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    provider = MockProvider()
    safe_diagnostics = {
        "http_status": 422,
        "provider_error_type": "invalid_request_error",
        "provider_error_code": "bad_tool_schema",
        "provider_error_message_sanitized": "schema rejected",
        "provider_request_id_safe": "req-safe-123",
        "request_contract_snapshot": {"tool_count": 7, "tool_names": ["workspace_read_text"]},
    }

    def fail(_request):
        raise LiveProviderError(
            LiveProviderErrorCode.PROVIDER_ERROR,
            "provider returned HTTP 422",
            safe_diagnostics=safe_diagnostics,
        )

    provider.tool_call = fail  # type: ignore[method-assign]
    with SQLiteDurableStateStore(tmp_path / "state.sqlite") as store:
        tools = BoundedToolRuntime(fixture.root, store)
        result = NativeAgent(provider, tools, MaintenanceVerifier(tools, fixture.baseline_digest)).run("phase3-safe-error")
    assert result.provider_error == "PROVIDER_ERROR"
    assert result.provider_diagnostics == safe_diagnostics
    assert result.request_contract_snapshot is None
    assert result.actions == ()


def test_native_agent_sends_v4_verified_artifact_contract_to_the_provider(
    tmp_path: Path,
) -> None:
    """The first provider request carries V3 safety plus the V4 artifact contract."""

    fixture = _fixture(tmp_path)
    provider = MockProvider(tool_call_batches=[[]])
    requests = []
    original = provider.tool_call

    def capture(request):
        requests.append([dict(message) for message in request.messages])
        return original(request)

    provider.tool_call = capture  # type: ignore[method-assign]
    with SQLiteDurableStateStore(tmp_path / "state.sqlite") as store:
        tools = BoundedToolRuntime(fixture.root, store)
        NativeAgent(provider, tools, MaintenanceVerifier(tools, fixture.baseline_digest)).run("phase3-v4-prompt")
    system_instruction = requests[0][0]["content"].lower()
    assert "aic2026_read_batch_verified_artifact_v4" in system_instruction
    assert "at most four read-only inspection calls" in system_instruction
    assert "workspace.list_files" in system_instruction
    assert "workspace.read_text" in system_instruction
    assert "issue exactly one tool call" in system_instruction
    assert "wait for all real tool results" in system_instruction
    assert "maintenance_completion.v1" in system_instruction
    assert ".astron-artifacts/change_summary.json" in system_instruction
    assert "task_id" in system_instruction
    assert "changed_files" in system_instruction
    assert "summary" in system_instruction


def test_native_agent_rejects_over_limit_batch_without_any_side_effect(
    tmp_path: Path,
) -> None:
    call_count = 5
    fixture = _fixture(tmp_path)
    state_path = tmp_path / "state.sqlite"
    provider = MockProvider()
    first = [_tool_call("workspace.read_text", {"path": "maintenance_config.py"}, index) for index in range(call_count)]
    batches = [first]
    observed_request_counts: list[int] = []

    def scripted(_request):
        calls = batches.pop(0) if batches else []
        observed_request_counts.append(len(calls))
        return ToolCallResult(
            tool_calls=calls,
            content="",
            model_id="mock-1",
            response_tool_call_metadata={
                "response_tool_call_count": len(calls),
                "response_provider_function_names": ["workspace_read_text"] * len(calls),
                "response_internal_operation_names": ["workspace.read_text"] * len(calls),
            },
        )

    provider.tool_call = scripted  # type: ignore[method-assign]
    with SQLiteDurableStateStore(state_path) as store:
        tools = BoundedToolRuntime(fixture.root, store)
        result = NativeAgent(provider, tools, MaintenanceVerifier(tools, fixture.baseline_digest)).run(
            f"phase3-cardinality-{call_count}"
        )
    with sqlite3.connect(state_path) as connection:
        authorization_count = connection.execute("SELECT COUNT(*) FROM authorization_replays").fetchone()[0]
        journal_count = connection.execute("SELECT COUNT(*) FROM action_journal").fetchone()[0]
        attempt_started_count = connection.execute(
            "SELECT COUNT(*) FROM action_events WHERE state = 'ATTEMPT_STARTED'"
        ).fetchone()[0]
    assert observed_request_counts[0] == call_count
    assert result.provider_error == "INVALID_MODEL_OUTPUT"
    assert result.actions == ()
    assert result.response_tool_call_metadata == {
        "response_tool_call_count": call_count,
        "response_provider_function_names": ["workspace_read_text"] * call_count,
        "response_internal_operation_names": ["workspace.read_text"] * call_count,
        "response_tool_call_names_truncated": False,
        "response_batch_classification": "REJECTED_TOO_MANY_CALLS",
    }
    assert "maintenance_config.py" not in repr(result.response_tool_call_metadata)
    assert authorization_count == journal_count == attempt_started_count == 0


def test_sequential_multistep_agent_observes_each_real_tool_result_before_next_turn(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    task_id = "phase3-sequential-single-action"
    provider = offline_maintenance_provider(task_id)
    captured_requests = []
    observed_call_counts: list[int] = []
    original = provider.tool_call

    def capture(request):
        captured_requests.append([dict(message) for message in request.messages])
        proposal = original(request)
        observed_call_counts.append(len(proposal.tool_calls))
        return proposal

    provider.tool_call = capture  # type: ignore[method-assign]
    with SQLiteDurableStateStore(tmp_path / "state.sqlite") as store:
        tools = BoundedToolRuntime(fixture.root, store)
        result = NativeAgent(
            provider, tools, MaintenanceVerifier(tools, fixture.baseline_digest)
        ).run(task_id)
    assert result.accepted is True
    assert observed_call_counts == [3, 1, 1, 1, 1, 0]
    for turn in captured_requests[1:]:
        assistant_indexes = [
            index for index, message in enumerate(turn)
            if message["role"] == "assistant" and "tool_calls" in message
        ]
        assert assistant_indexes
        latest_assistant = assistant_indexes[-1]
        expected_ids = [call["id"] for call in turn[latest_assistant]["tool_calls"]]
        tool_results = turn[latest_assistant + 1:]
        assert [message["role"] for message in tool_results] == ["tool"] * len(expected_ids)
        assert [message["tool_call_id"] for message in tool_results] == expected_ids


def test_verifier_rejects_malformed_artifact_even_after_source_repair(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    with SQLiteDurableStateStore(tmp_path / "state.sqlite") as store:
        tools = BoundedToolRuntime(fixture.root, store)
        task_id = "phase3-malformed-artifact"
        store.register_task(task_id)
        tools.execute(
            task_id, 1, "workspace.patch_text",
            {"path": "maintenance_config.py", "expected_old": "DEFAULT_TIMEOUT_SECONDS = 0", "replacement": "DEFAULT_TIMEOUT_SECONDS = 30"},
        )
        tools.execute(
            task_id, 2, "workspace.write_artifact",
            {"path": ".astron-artifacts/change_summary.json", "content": "{}"},
        )
        result = MaintenanceVerifier(tools, fixture.baseline_digest).verify(task_id)
    assert result.accepted is False
    assert result.reason_code == "VERIFIER_ARTIFACT_INVALID"


def test_verifier_rejects_forbidden_fixture_modification(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    with SQLiteDurableStateStore(tmp_path / "state.sqlite") as store:
        tools = BoundedToolRuntime(fixture.root, store)
        task_id = "phase3-forbidden-modification"
        store.register_task(task_id)
        tools.execute(
            task_id, 1, "workspace.patch_text",
            {"path": "maintenance_config.py", "expected_old": "DEFAULT_TIMEOUT_SECONDS = 0", "replacement": "DEFAULT_TIMEOUT_SECONDS = 30"},
        )
        tools.execute(
            task_id, 2, "workspace.write_artifact",
            {"path": ".astron-artifacts/change_summary.json", "content": json.dumps({"task_id": task_id, "changed_files": ["maintenance_config.py"], "summary": "fixed"})},
        )
        (fixture.root / "README.md").write_text("forbidden modification\n", encoding="utf-8")
        result = MaintenanceVerifier(tools, fixture.baseline_digest).verify(task_id)
    assert result.accepted is False
    assert result.reason_code == "VERIFIER_SCOPE_VIOLATION"


def test_outside_workspace_and_symlink_proposals_are_denied_before_execution(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    with SQLiteDurableStateStore(tmp_path / "state.sqlite") as store:
        tools = BoundedToolRuntime(fixture.root, store)
        with pytest.raises(ToolInputError):
            tools.execute("phase3-outside", 1, "workspace.read_text", {"path": "../outside.txt"})
        original = (fixture.root / "maintenance_config.py").read_text(encoding="utf-8")
        with pytest.raises(ToolInputError):
            tools.execute("phase3-outside-write", 1, "workspace.write_artifact", {"path": "maintenance_config.py", "content": "outside artifact scope"})
        outside = tmp_path / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        (fixture.root / "link.txt").symlink_to(outside)
        with pytest.raises(ToolInputError):
            tools.execute("phase3-symlink", 1, "workspace.read_text", {"path": "link.txt"})
    assert not (fixture.root / ".astron-artifacts").exists()
    assert (fixture.root / "maintenance_config.py").read_text(encoding="utf-8") == original


def test_fresh_fixture_baseline_fails_and_reset_is_deterministic(tmp_path: Path) -> None:
    first = FixtureWorkspace.create(tmp_path / "first")
    second = FixtureWorkspace.create(tmp_path / "second")
    with SQLiteDurableStateStore(tmp_path / "state.sqlite") as store:
        tools = BoundedToolRuntime(first.root, store)
        store.register_task("phase3-baseline")
        baseline = tools.execute("phase3-baseline", 1, "test.run_pytest_bounded", {})
        with pytest.raises(ToolInputError):
            tools.execute("phase3-baseline", 2, "test.run_pytest_bounded", {"target": "../outside"})
    assert baseline.result is not None and baseline.result.status.value == "failure"
    assert baseline.result.outcome["status"] == "FAILED"
    assert first.baseline_digest == second.baseline_digest
    assert (second.root / "maintenance_config.py").read_text(encoding="utf-8").endswith("= 0\n")


def test_existing_fixture_reopen_rejects_any_source_change_after_baseline(tmp_path: Path) -> None:
    fixture = FixtureWorkspace.create(tmp_path / "fresh")
    (fixture.root / "maintenance_config.py").write_text(
        "DEFAULT_TIMEOUT_SECONDS = 30\n", encoding="utf-8"
    )
    with pytest.raises(FixtureError):
        FixtureWorkspace.open_existing(fixture.root)


def test_bounded_tool_matrix_reads_validates_and_times_out_only_its_owned_child(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    with SQLiteDurableStateStore(tmp_path / "state.sqlite") as store:
        tools = BoundedToolRuntime(fixture.root, store, pytest_timeout_seconds=1)
        store.register_task("phase3-tool-matrix")
        listed = tools.execute("phase3-tool-matrix", 1, "workspace.list_files", {"path": "."})
        read = tools.execute("phase3-tool-matrix", 2, "workspace.read_text", {"path": "maintenance_config.py"})
        artifact = tools.execute(
            "phase3-tool-matrix", 3, "workspace.write_artifact",
            {"path": ".astron-artifacts/valid.json", "content": "{\"ok\": true}"},
        )
        valid_json = tools.execute("phase3-tool-matrix", 4, "validate.json", {"path": ".astron-artifacts/valid.json"})
        valid_file = tools.execute("phase3-tool-matrix", 5, "validate.file", {"path": "maintenance_config.py"})
        (fixture.root / "tests" / "test_timeout.py").write_text(
            "import time\n\ndef test_slow_fixture_case():\n    time.sleep(5)\n", encoding="utf-8"
        )
        timed_out = tools.execute("phase3-tool-matrix", 6, "test.run_pytest_bounded", {})
    assert listed.result is not None and listed.result.outcome["count"] >= 3
    assert read.result is not None and "DEFAULT_TIMEOUT_SECONDS" in read.result.outcome["content"]
    assert artifact.result is not None and artifact.result.status.value == "success"
    assert valid_json.result is not None and valid_json.result.outcome["json_type"] == "dict"
    assert valid_file.result is not None and valid_file.result.outcome["regular_file"] is True
    assert timed_out.result is not None and timed_out.result.status.value == "failure"
    assert timed_out.result.outcome["status"] == "TIMEOUT"


def test_mutating_tool_crash_after_durable_attempt_requires_restart_reconciliation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path)
    state_path = tmp_path / "state.sqlite"
    with SQLiteDurableStateStore(state_path) as store:
        tools = BoundedToolRuntime(fixture.root, store)

        def crash_after_attempt(parameters: dict[str, object]) -> dict[str, object]:
            raise RuntimeError("test-only crash after durable attempt boundary")

        monkeypatch.setattr(tools, "_patch_text", crash_after_attempt)
        first = tools.execute(
            "phase3-crash",
            1,
            "workspace.patch_text",
            {"path": "maintenance_config.py", "expected_old": "DEFAULT_TIMEOUT_SECONDS = 0", "replacement": "DEFAULT_TIMEOUT_SECONDS = 30"},
        )
    assert first.executor_invoked is True
    assert first.needs_reconciliation is True
    with SQLiteDurableStateStore(state_path) as restarted:
        recovered = restarted.recover_task("phase3-crash")
    assert recovered.classification.value == "NEEDS_RECONCILIATION"


def test_cli_mock_demo_is_explicitly_offline_and_live_without_named_config_is_blocked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from paios_ce.cli.main import main

    code = main([
        "maintenance-demo", "--mode", "mock", "--workspace", str(tmp_path / "workspace"),
        "--state-db", str(tmp_path / "state.sqlite"), "--task-id", "phase3-cli-mock",
    ])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["mode"] == "mock"
    assert payload["status"] == "PASS"
    assert payload["response_tool_call_metadata"] == {
        "response_tool_call_count": 0,
        "response_provider_function_names": [],
        "response_internal_operation_names": [],
        "response_tool_call_names_truncated": False,
        "response_batch_classification": "NO_CALL",
    }
    assert payload["completion_artifact_contract"] == {
        "visible": True,
        "schema_id": "maintenance_completion.v1",
        "artifact_path": ".astron-artifacts/change_summary.json",
        "required_keys": ["task_id", "changed_files", "summary"],
        "allow_extra_keys": True,
    }
    assert payload["artifact_semantic_validation"] == "PASSED"
    blocked = main([
        "maintenance-demo", "--mode", "live", "--workspace", str(tmp_path / "live-workspace"),
        "--state-db", str(tmp_path / "live-state.sqlite"),
    ])
    payload = json.loads(capsys.readouterr().out)
    assert blocked != 0
    assert payload["status"] == "BLOCKED_EXTERNAL_CREDENTIAL"


def test_cli_baseline_certification_reuses_only_the_exact_fresh_fixture(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from paios_ce.cli.main import main

    workspace = tmp_path / "fresh-fixture"
    baseline = main([
        "maintenance-baseline", "--workspace", str(workspace),
        "--state-db", str(tmp_path / "baseline.sqlite"), "--task-id", "phase3-run2-baseline",
    ])
    baseline_payload = json.loads(capsys.readouterr().out)
    assert baseline == 0
    assert baseline_payload["baseline_status"] == "FAIL_AS_EXPECTED"
    resumed = main([
        "maintenance-demo", "--mode", "mock", "--reuse-fixture", "--workspace", str(workspace),
        "--state-db", str(tmp_path / "live.sqlite"), "--task-id", "phase3-run2-mock",
    ])
    resumed_payload = json.loads(capsys.readouterr().out)
    assert resumed == 0
    assert resumed_payload["status"] == "PASS"
