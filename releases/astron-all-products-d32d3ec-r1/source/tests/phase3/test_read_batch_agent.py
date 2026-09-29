"""V3 bounded sequential read-batch admission and roundtrip regressions."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any

import pytest

from paios_ce.agent import MaintenanceVerifier, NativeAgent, offline_maintenance_provider
from paios_ce.agent.fixture import FixtureWorkspace
from paios_ce.providers import MockProvider, ToolCallResult
from paios_ce.state import SQLiteDurableStateStore
from paios_ce.tools import BoundedToolRuntime


def _call(name: str, arguments: dict[str, object], call_id: str) -> dict[str, object]:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments, sort_keys=True)},
    }


def _read(path: str, call_id: str) -> dict[str, object]:
    return _call("workspace.read_text", {"path": path}, call_id)


def _patch(call_id: str) -> dict[str, object]:
    return _call(
        "workspace.patch_text",
        {
            "path": "maintenance_config.py",
            "expected_old": "DEFAULT_TIMEOUT_SECONDS = 0",
            "replacement": "DEFAULT_TIMEOUT_SECONDS = 30",
        },
        call_id,
    )


def _provider_names(calls: list[dict[str, object]]) -> list[str]:
    return [str(call["function"]["name"]).replace(".", "_") for call in calls]  # type: ignore[index]


def _run_first_response(
    tmp_path: Path,
    calls: list[dict[str, object]],
    *,
    task_id: str,
    configure_tools=None,
):
    fixture = FixtureWorkspace.create(tmp_path / "fresh-fixture")
    state_path = tmp_path / "state.sqlite"
    provider = MockProvider()
    captured: list[list[dict[str, Any]]] = []
    provider_turn = 0

    def scripted(request):
        nonlocal provider_turn
        captured.append(json.loads(json.dumps(request.messages)))
        provider_turn += 1
        if provider_turn == 1:
            return ToolCallResult(
                tool_calls=calls,
                content="",
                model_id="mock-1",
                response_tool_call_metadata={
                    "response_tool_call_count": len(calls),
                    "response_provider_function_names": _provider_names(calls),
                    "response_internal_operation_names": [
                        str(call["function"]["name"]) for call in calls  # type: ignore[index]
                    ],
                },
            )
        raise RuntimeError("test stop after roundtrip capture")

    provider.tool_call = scripted  # type: ignore[method-assign]
    with SQLiteDurableStateStore(state_path) as store:
        tools = BoundedToolRuntime(fixture.root, store)
        if configure_tools is not None:
            configure_tools(tools)
        result = NativeAgent(
            provider,
            tools,
            MaintenanceVerifier(tools, fixture.baseline_digest),
        ).run(task_id)
    return result, captured, state_path, fixture


@pytest.mark.parametrize(
    ("calls", "classification", "operations", "next_turn"),
    [
        ([], "NO_CALL", [], False),
        ([_read("maintenance_config.py", "one-read")], "SINGLE_ACTION", ["workspace.read_text"], True),
        ([_patch("one-patch")], "SINGLE_ACTION", ["workspace.patch_text"], True),
        (
            [_read("maintenance_config.py", "two-a"), _read("README.md", "two-b")],
            "READ_ONLY_BATCH",
            ["workspace.read_text", "workspace.read_text"],
            True,
        ),
        (
            [_read("maintenance_config.py", "three-a"), _read("README.md", "three-b"), _read("maintenance_config.py", "three-c")],
            "READ_ONLY_BATCH",
            ["workspace.read_text"] * 3,
            True,
        ),
        (
            [_read("maintenance_config.py", "four-a"), _read("README.md", "four-b"), _read("maintenance_config.py", "four-c"), _read("README.md", "four-d")],
            "READ_ONLY_BATCH",
            ["workspace.read_text"] * 4,
            True,
        ),
        (
            [_call("workspace.list_files", {"path": "."}, "list-a"), _read("maintenance_config.py", "read-b")],
            "READ_ONLY_BATCH",
            ["workspace.list_files", "workspace.read_text"],
            True,
        ),
    ],
)
def test_v3_admits_only_zero_single_or_bounded_read_batch(
    tmp_path: Path,
    calls: list[dict[str, object]],
    classification: str,
    operations: list[str],
    next_turn: bool,
) -> None:
    result, captured, _, _ = _run_first_response(
        tmp_path, calls, task_id=f"v3-admission-{classification}-{len(calls)}"
    )
    assert [action["operation"] for action in result.actions] == operations
    assert result.response_tool_call_metadata["response_batch_classification"] == classification
    assert len(captured) == (2 if next_turn else 1)


@pytest.mark.parametrize(
    ("calls", "classification"),
    [
        ([_read("maintenance_config.py", f"over-{index}") for index in range(5)], "REJECTED_TOO_MANY_CALLS"),
        ([_read("maintenance_config.py", "mixed-read"), _patch("mixed-patch")], "REJECTED_MIXED_BATCH"),
        (
            [_read("maintenance_config.py", "mixed-read-test"), _call("test.run_pytest_bounded", {}, "mixed-test")],
            "REJECTED_MIXED_BATCH",
        ),
        (
            [
                _patch("mixed-patch-artifact"),
                _call(
                    "workspace.write_artifact",
                    {"path": ".astron-artifacts/change_summary.json", "content": "{}"},
                    "mixed-artifact",
                ),
            ],
            "REJECTED_MIXED_BATCH",
        ),
        ([_patch("patch-a"), _patch("patch-b")], "REJECTED_MIXED_BATCH"),
        (
            [_read("maintenance_config.py", "known-read"), _call("unknown_tool", {}, "unknown")],
            "REJECTED_MIXED_BATCH",
        ),
    ],
)
def test_v3_rejects_entire_over_limit_or_mixed_batch_before_any_execution(
    tmp_path: Path,
    calls: list[dict[str, object]],
    classification: str,
) -> None:
    result, captured, state_path, fixture = _run_first_response(
        tmp_path, calls, task_id=f"v3-reject-{classification}-{len(calls)}"
    )
    with sqlite3.connect(state_path) as connection:
        authorization_count = connection.execute("SELECT COUNT(*) FROM authorization_replays").fetchone()[0]
        journal_count = connection.execute("SELECT COUNT(*) FROM action_journal").fetchone()[0]
        attempt_count = connection.execute(
            "SELECT COUNT(*) FROM action_events WHERE state = 'ATTEMPT_STARTED'"
        ).fetchone()[0]
    assert result.provider_error == "INVALID_MODEL_OUTPUT"
    assert result.actions == ()
    assert result.response_tool_call_metadata["response_batch_classification"] == classification
    assert authorization_count == journal_count == attempt_count == 0
    assert len(captured) == 1
    assert (fixture.root / "maintenance_config.py").read_text(encoding="utf-8").endswith("= 0\n")


def test_three_read_batch_has_independent_durable_actions_and_strict_execution_order(
    tmp_path: Path,
) -> None:
    calls = [
        _read("maintenance_config.py", "read-a"),
        _read("README.md", "read-b"),
        _read("maintenance_config.py", "read-c"),
    ]
    events: list[str] = []

    def instrument(tools: BoundedToolRuntime) -> None:
        original = tools._read_text

        def observed(parameters):
            events.append("START " + parameters["path"])
            outcome = original(parameters)
            events.append("END " + parameters["path"])
            return outcome

        tools._read_text = observed  # type: ignore[method-assign]

    result, captured, state_path, _ = _run_first_response(
        tmp_path,
        calls,
        task_id="v3-three-read-durable",
        configure_tools=instrument,
    )
    with sqlite3.connect(state_path) as connection:
        authorization_count = connection.execute("SELECT COUNT(*) FROM authorization_replays").fetchone()[0]
        journal_count, identity_count = connection.execute(
            "SELECT COUNT(*), COUNT(DISTINCT action_identity) FROM action_journal"
        ).fetchone()
        attempt_count = connection.execute(
            "SELECT COUNT(*) FROM action_events WHERE state = 'ATTEMPT_STARTED'"
        ).fetchone()[0]
        success_count = connection.execute(
            "SELECT COUNT(*) FROM action_events WHERE state = 'SUCCEEDED'"
        ).fetchone()[0]
    assert [action["operation"] for action in result.actions] == ["workspace.read_text"] * 3
    assert authorization_count == journal_count == identity_count == attempt_count == success_count == 3
    assert events == [
        "START maintenance_config.py", "END maintenance_config.py",
        "START README.md", "END README.md",
        "START maintenance_config.py", "END maintenance_config.py",
    ]
    roundtrip = captured[1]
    assistant = roundtrip[-4]
    tool_results = roundtrip[-3:]
    assert assistant["role"] == "assistant"
    assert [call["id"] for call in assistant["tool_calls"]] == ["read-a", "read-b", "read-c"]
    assert [message["role"] for message in tool_results] == ["tool", "tool", "tool"]
    assert [message["tool_call_id"] for message in tool_results] == ["read-a", "read-b", "read-c"]


def test_read_batch_scope_failure_is_paired_and_does_not_block_other_safe_reads(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("OUTSIDE_CONTENT_MUST_NOT_BE_READ", encoding="utf-8")
    calls = [
        _read("maintenance_config.py", "safe-a"),
        _read("../outside.txt", "outside"),
        _read("README.md", "safe-b"),
    ]
    result, captured, state_path, _ = _run_first_response(
        tmp_path, calls, task_id="v3-read-scope-failure"
    )
    with sqlite3.connect(state_path) as connection:
        journal_count = connection.execute("SELECT COUNT(*) FROM action_journal").fetchone()[0]
    assert [action["operation"] for action in result.actions] == ["workspace.read_text"] * 2
    assert journal_count == 2
    tool_results = captured[1][-3:]
    assert [message["tool_call_id"] for message in tool_results] == ["safe-a", "outside", "safe-b"]
    outside_result = json.loads(tool_results[1]["content"])
    assert outside_result == {"code": "SCOPE_OR_INPUT_VIOLATION", "status": "failure"}
    assert "OUTSIDE_CONTENT_MUST_NOT_BE_READ" not in json.dumps(tool_results)


@pytest.mark.parametrize(
    "calls",
    [
        [
            _read("maintenance_config.py", "valid-before-malformed"),
            {
                "id": "malformed-json",
                "type": "function",
                "function": {"name": "workspace.read_text", "arguments": "not-json"},
            },
        ],
        [
            _read("maintenance_config.py", "duplicate-id"),
            _read("README.md", "duplicate-id"),
        ],
    ],
)
def test_read_batch_validates_all_call_structure_before_first_execution(
    tmp_path: Path,
    calls: list[dict[str, object]],
) -> None:
    result, _, state_path, _ = _run_first_response(
        tmp_path, calls, task_id="v3-invalid-read-batch-structure"
    )
    with sqlite3.connect(state_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM authorization_replays").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM action_journal").fetchone()[0] == 0
    assert result.provider_error == "INVALID_MODEL_OUTPUT"
    assert result.actions == ()


def test_v4_prompt_and_full_offline_agent_preserve_v3_single_side_effect_turns(
    tmp_path: Path,
) -> None:
    fixture = FixtureWorkspace.create(tmp_path / "fresh-fixture")
    task_id = "v3-full-offline"
    provider = offline_maintenance_provider(task_id)
    captured: list[list[dict[str, Any]]] = []
    call_counts: list[int] = []
    original = provider.tool_call

    def capture(request):
        captured.append(json.loads(json.dumps(request.messages)))
        result = original(request)
        call_counts.append(len(result.tool_calls))
        return result

    provider.tool_call = capture  # type: ignore[method-assign]
    with SQLiteDurableStateStore(tmp_path / "state.sqlite") as store:
        tools = BoundedToolRuntime(fixture.root, store)
        result = NativeAgent(
            provider,
            tools,
            MaintenanceVerifier(tools, fixture.baseline_digest),
        ).run(task_id)
        checkpoint = store.checkpoint(task_id)
    instruction = captured[0][0]["content"]
    assert "AIC2026_READ_BATCH_VERIFIED_ARTIFACT_V4" in instruction
    assert "workspace.list_files" in instruction
    assert "workspace.read_text" in instruction
    assert "maintenance_completion.v1" in instruction
    assert call_counts == [3, 1, 1, 1, 1, 0]
    assert [action["operation"] for action in result.actions] == [
        "workspace.read_text", "workspace.read_text", "workspace.read_text",
        "workspace.patch_text", "test.run_pytest_bounded", "workspace.write_artifact",
        "validate.json",
    ]
    assert result.actions[-1]["semantic_validation"] == "PASSED"
    assert result.accepted is True
    assert checkpoint is not None and checkpoint.runtime_state == "TASK_COMPLETED"
