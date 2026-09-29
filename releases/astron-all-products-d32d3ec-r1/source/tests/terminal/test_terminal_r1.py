"""Deterministic certification tests for the governed Terminal R1 capability."""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import threading
import time

import pytest

from paios_ce.agent import MaintenanceVerifier, NativeAgent
from paios_ce.agent.fixture import FixtureWorkspace
from paios_ce.providers import MockProvider, ToolCallResult
from paios_ce.state import SQLiteDurableStateStore
from paios_ce.tools import (
    BoundedToolRuntime,
    TerminalEnabledToolRuntime,
    TerminalService,
    TerminalToolRuntime,
    ToolInputError,
)


def _service(tmp_path: Path) -> TerminalService:
    root = tmp_path / "workspace"
    root.mkdir()
    return TerminalService(root)


def _open(service: TerminalService, owner: str = "agent-a", **kwargs: object) -> str:
    return str(service.open(owner, **kwargs)["terminal_id"])


def _call(name: str, arguments: dict[str, object], index: int) -> dict[str, object]:
    return {
        "id": f"terminal-loop-{index}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments, sort_keys=True)},
    }


def test_t01_open_session(tmp_path: Path) -> None:
    service = _service(tmp_path)
    terminal_id = _open(service)
    listed = service.list("agent-a")
    assert listed["count"] == 1
    assert listed["sessions"][0]["terminal_id"] == terminal_id
    service.shutdown()


def test_t02_send_echo(tmp_path: Path) -> None:
    service = _service(tmp_path)
    terminal_id = _open(service)
    result = service.send("agent-a", terminal_id, "printf terminal-r1")
    assert result["output"] == "terminal-r1"
    assert result["exit_code"] == 0
    service.shutdown()


def test_t03_persistent_cwd(tmp_path: Path) -> None:
    service = _service(tmp_path)
    (service.workspace_root / "child").mkdir()
    terminal_id = _open(service)
    assert service.send("agent-a", terminal_id, "cd child")["exit_code"] == 0
    result = service.send("agent-a", terminal_id, "pwd")
    assert result["output"].strip() == str(service.workspace_root / "child")
    service.shutdown()


def test_t04_persistent_environment(tmp_path: Path) -> None:
    service = _service(tmp_path)
    terminal_id = _open(service)
    service.send("agent-a", terminal_id, "export TERMINAL_R1_VALUE=persistent")
    result = service.send("agent-a", terminal_id, 'printf "$TERMINAL_R1_VALUE"')
    assert result["output"] == "persistent"
    service.shutdown()


def test_t05_multiple_sequential_commands(tmp_path: Path) -> None:
    service = _service(tmp_path)
    terminal_id = _open(service)
    assert service.send("agent-a", terminal_id, "VALUE=first")["exit_code"] == 0
    assert service.send("agent-a", terminal_id, "VALUE=${VALUE}-second")["exit_code"] == 0
    assert service.send("agent-a", terminal_id, 'printf "$VALUE"')["output"] == "first-second"
    service.shutdown()


def test_t06_read_incremental_output(tmp_path: Path) -> None:
    service = _service(tmp_path)
    terminal_id = _open(service)
    result = service.send("agent-a", terminal_id, "sleep 0.1; printf later", run_in_background=True)
    assert result["background"] is True
    time.sleep(0.2)
    read = service.read("agent-a", terminal_id)
    assert "later" in read["output"]
    assert service.read("agent-a", terminal_id)["output"] == ""
    service.shutdown()


def test_t07_exit_code_success(tmp_path: Path) -> None:
    service = _service(tmp_path)
    result = service.send("agent-a", _open(service), "true")
    assert result["exit_code"] == 0
    service.shutdown()


def test_t08_exit_code_failure(tmp_path: Path) -> None:
    service = _service(tmp_path)
    result = service.send("agent-a", _open(service), "false")
    assert result["exit_code"] == 1
    service.shutdown()


def test_t09_foreground_timeout_interrupts_command(tmp_path: Path) -> None:
    service = _service(tmp_path)
    result = service.send("agent-a", _open(service), "sleep 10", timeout_seconds=1)
    assert result["timed_out"] is True
    service.shutdown()


def test_t10_background_process(tmp_path: Path) -> None:
    service = _service(tmp_path)
    terminal_id = _open(service)
    result = service.send("agent-a", terminal_id, "sleep 10", run_in_background=True)
    assert result["background"] is True
    assert isinstance(result["process_id"], int)
    assert service.list("agent-a")["sessions"][0]["status"] == "running"
    service.shutdown()


def test_t11_sigint_interrupts_foreground_process(tmp_path: Path) -> None:
    service = _service(tmp_path)
    terminal_id = _open(service)
    holder: dict[str, object] = {}

    def run() -> None:
        holder["result"] = service.send("agent-a", terminal_id, "sleep 10", timeout_seconds=10)

    worker = threading.Thread(target=run)
    worker.start()
    time.sleep(0.2)
    signal_result = service.signal("agent-a", terminal_id, "SIGINT")
    worker.join(timeout=3)
    assert signal_result["signal"] == "SIGINT"
    assert not worker.is_alive()
    assert "result" in holder
    service.shutdown()


def test_t12_close_session(tmp_path: Path) -> None:
    service = _service(tmp_path)
    terminal_id = _open(service)
    result = service.close("agent-a", terminal_id)
    assert result["status"] == "closed"
    service.shutdown()


def test_t13_list_only_own_sessions(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _open(service, "agent-a")
    _open(service, "agent-b")
    assert service.list("agent-a")["count"] == 1
    assert service.list("agent-b")["count"] == 1
    service.shutdown()


def test_t14_owner_isolation(tmp_path: Path) -> None:
    service = _service(tmp_path)
    terminal_id = _open(service, "agent-a")
    with pytest.raises(ToolInputError, match="owner isolation"):
        service.send("agent-b", terminal_id, "printf forbidden")
    with pytest.raises(ToolInputError, match="owner isolation"):
        service.read("agent-b", terminal_id)
    with pytest.raises(ToolInputError, match="owner isolation"):
        service.signal("agent-b", terminal_id, "SIGINT")
    with pytest.raises(ToolInputError, match="owner isolation"):
        service.close("agent-b", terminal_id)
    service.shutdown()


def test_t15_invalid_terminal_id(tmp_path: Path) -> None:
    service = _service(tmp_path)
    with pytest.raises(ToolInputError, match="terminal id"):
        service.read("agent-a", "not-a-terminal-id")
    service.shutdown()


def test_t16_workspace_cwd_validation(tmp_path: Path) -> None:
    service = _service(tmp_path)
    with pytest.raises(ToolInputError, match="escapes"):
        service.open("agent-a", cwd="../")
    service.shutdown()


def test_t17_output_truncation_is_explicit(tmp_path: Path) -> None:
    service = _service(tmp_path)
    result = service.send("agent-a", _open(service), "yes x | head -c 9000")
    assert result["truncated"] is True
    assert "OUTPUT_TRUNCATED" in result["output"]
    service.shutdown()


def test_t18_action_journal_record_is_redacted(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    state_path = tmp_path / "state.sqlite"
    with SQLiteDurableStateStore(state_path) as store:
        store.register_task("terminal-journal")
        terminal = TerminalToolRuntime(root, store)
        opened = terminal.execute("terminal-journal", "open", "agent-a", "terminal_open", {"env": {"FAKE_API_KEY": "journal-secret"}})
        terminal_id = opened.result.outcome["terminal_id"]  # type: ignore[union-attr]
        terminal.execute("terminal-journal", "send", "agent-a", "terminal_send", {"terminal_id": terminal_id, "input": 'printf "$FAKE_API_KEY"'})
        terminal.shutdown()
    journal = (terminal.service.log_root / "action-journal.jsonl").read_text(encoding="utf-8")
    assert "terminal_send" in journal and "request_fingerprint" in journal
    assert "journal-secret" not in journal


def test_t19_duplicate_logical_dispatch_is_not_reexecuted(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    with SQLiteDurableStateStore(tmp_path / "state.sqlite") as store:
        store.register_task("terminal-replay")
        terminal = TerminalToolRuntime(root, store)
        first = terminal.execute("terminal-replay", "open", "agent-a", "terminal_open", {})
        replay = terminal.execute("terminal-replay", "open", "agent-a", "terminal_open", {})
        assert first.executor_invoked is True
        assert replay.executor_invoked is False
        assert replay.result is None
        assert terminal.service.list("agent-a")["count"] == 1
        terminal.shutdown()


def test_t20_shutdown_cleans_child_process_group(tmp_path: Path) -> None:
    service = _service(tmp_path)
    terminal_id = _open(service)
    started = service.send("agent-a", terminal_id, "sleep 30", run_in_background=True)
    child_pid = int(started["process_id"])
    service.shutdown()
    time.sleep(0.1)
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)


def test_t21_secret_redaction(tmp_path: Path) -> None:
    service = _service(tmp_path)
    terminal_id = _open(service, env={"FAKE_API_KEY": "not-a-real-secret"})
    result = service.send("agent-a", terminal_id, 'printf "$FAKE_API_KEY"')
    assert "not-a-real-secret" not in result["output"]
    assert result["output"] == "***REDACTED***"
    service.shutdown()


def test_t22_tool_result_feedback_reaches_next_agent_turn(tmp_path: Path) -> None:
    fixture = FixtureWorkspace.create(tmp_path / "fixture")
    requests: list[list[dict[str, object]]] = []
    advertised_tool_names: list[list[str]] = []
    provider = MockProvider()

    def scripted(request):
        requests.append([dict(message) for message in request.messages])
        advertised_tool_names.append([item["function"]["name"] for item in request.tools or []])
        turn = len(requests)
        if turn == 1:
            return ToolCallResult(tool_calls=[_call("terminal_open", {}, 1)], model_id="mock-1")
        tool_messages = [message for message in request.messages if message.get("role") == "tool"]
        latest = json.loads(str(tool_messages[-1]["content"]))
        if turn == 2:
            terminal_id = latest["outcome"]["terminal_id"]
            return ToolCallResult(tool_calls=[_call("terminal_send", {"terminal_id": terminal_id, "input": "printf loop-feedback"}, 2)], model_id="mock-1")
        if turn == 3:
            terminal_id = json.loads(str(tool_messages[-2]["content"]))["outcome"]["terminal_id"]
            return ToolCallResult(tool_calls=[_call("terminal_read", {"terminal_id": terminal_id}, 3)], model_id="mock-1")
        return ToolCallResult(tool_calls=[], model_id="mock-1")

    provider.tool_call = scripted  # type: ignore[method-assign]
    with SQLiteDurableStateStore(tmp_path / "state.sqlite") as store:
        bounded = BoundedToolRuntime(fixture.root, store)
        terminal = TerminalToolRuntime(fixture.root, store)
        tools = TerminalEnabledToolRuntime(bounded, terminal, agent_owner=BoundedToolRuntime.PRINCIPAL_ID)
        try:
            result = NativeAgent(provider, tools, MaintenanceVerifier(bounded, fixture.baseline_digest), max_steps=5).run("terminal-loop")
        finally:
            tools.shutdown()
    assert [action["operation"] for action in result.actions] == ["terminal_open", "terminal_send", "terminal_read"]
    assert any(message.get("role") == "tool" and "terminal_id" in str(message.get("content")) for message in requests[1])
    assert {"terminal_open", "terminal_send", "terminal_read"}.issubset(advertised_tool_names[0])


def _governed(tmp_path: Path, task_id: str, *, service: TerminalService | None = None):
    root = tmp_path / "workspace"
    root.mkdir(exist_ok=True)
    store = SQLiteDurableStateStore(tmp_path / f"{task_id}.sqlite")
    store.register_task(task_id)
    return store, TerminalToolRuntime(root, store, service=service)


def test_t23_uncertain_terminal_action_is_not_redriven(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Requirement 12: an unprovable outcome must reconcile, never auto-retry."""

    store, terminal = _governed(tmp_path, "terminal-uncertain")
    with store:
        sent = "term_" + "0" * 20
        parameters = {"terminal_id": sent, "input": "printf never-dispatched"}

        def crash(*_args: object, **_kwargs: object) -> dict[str, object]:
            raise RuntimeError("simulated crash after the durable attempt boundary")

        monkeypatch.setattr(terminal.service, "send", crash)
        first = terminal.execute("terminal-uncertain", "send", "agent-a", "terminal_send", parameters)
        assert first.executor_invoked is True
        assert first.needs_reconciliation is True
        assert first.result is None

        # The same logical call is re-submitted by the runtime.  The durable
        # layer must refuse to dispatch it again rather than re-run a shell
        # command whose first outcome is unknown.
        dispatched: list[object] = []
        monkeypatch.setattr(terminal.service, "send", lambda *a, **k: dispatched.append(a))
        replay = terminal.execute("terminal-uncertain", "send", "agent-a", "terminal_send", parameters)
        assert replay.executor_invoked is False
        assert replay.needs_reconciliation is True
        assert dispatched == []
        terminal.shutdown()


def test_t24_governed_owner_isolation_between_agents(tmp_path: Path) -> None:
    """Requirement 7: isolation must hold on the governed tool path, not only in-process."""

    root = tmp_path / "workspace"
    root.mkdir()
    service = TerminalService(root)
    with SQLiteDurableStateStore(tmp_path / "shared.sqlite") as store:
        store.register_task("terminal-a")
        store.register_task("terminal-b")
        agent_a = TerminalToolRuntime(root, store, service=service)
        agent_b = TerminalToolRuntime(root, store, service=service)
        opened = agent_a.execute("terminal-a", "open", "agent-a", "terminal_open", {})
        terminal_id = str(opened.result.outcome["terminal_id"])  # type: ignore[union-attr]
        for operation, parameters in (
            ("terminal_send", {"terminal_id": terminal_id, "input": "printf forbidden"}),
            ("terminal_read", {"terminal_id": terminal_id}),
            ("terminal_signal", {"terminal_id": terminal_id, "signal": "SIGINT"}),
            ("terminal_close", {"terminal_id": terminal_id}),
        ):
            denied = agent_b.execute("terminal-b", f"b-{operation}", "agent-b", operation, parameters)
            assert denied.result is not None
            assert denied.result.outcome["code"] == "TERMINAL_POLICY_OR_INPUT_DENIED"
            assert "owner isolation" in str(denied.result.outcome["detail"])
        assert agent_b.execute("terminal-b", "b-list", "agent-b", "terminal_list", {}).result.outcome["count"] == 0  # type: ignore[union-attr]
        assert agent_a.execute("terminal-a", "a-list", "agent-a", "terminal_list", {}).result.outcome["count"] == 1  # type: ignore[union-attr]
        service.shutdown()


def test_t25_terminal_policy_blocks_admin_destructive_and_network_commands(tmp_path: Path) -> None:
    """Requirement 9: terminal policy hooks deny explicitly dangerous syntax."""

    service = _service(tmp_path)
    terminal_id = _open(service)
    for command in ("sudo rm -rf /", "rm -rf ./build", "curl https://example.invalid", "wget http://x", "shutdown -h now"):
        with pytest.raises(ToolInputError):
            service.send("agent-a", terminal_id, command)
    assert service.send("agent-a", terminal_id, "printf still-alive")["output"] == "still-alive"
    service.shutdown()


def test_t26_terminal_input_bounds_and_unknown_fields(tmp_path: Path) -> None:
    """Requirement 8/14: schema-bounded input is enforced below the model."""

    store, terminal = _governed(tmp_path, "terminal-bounds")
    with store:
        with pytest.raises(ToolInputError):
            terminal.execute("terminal-bounds", "x", "agent-a", "terminal_open", {"cwd": ".", "shell": "/bin/sh"})
        with pytest.raises(ToolInputError):
            terminal.execute("terminal-bounds", "y", "agent-a", "terminal_open", {"env": {"BAD NAME": "v"}})
        with pytest.raises(ToolInputError):
            terminal.execute("terminal-bounds", "z", "agent-a", "terminal_send", {"terminal_id": "term_" + "0" * 20, "input": ""})
        with pytest.raises(ToolInputError):
            terminal.execute("terminal-bounds", "w", "agent-a", "os.system", {})
        terminal.shutdown()


def test_t27_terminal_log_root_cannot_live_inside_the_workspace(tmp_path: Path) -> None:
    """Requirement 10: terminal bookkeeping never mutates the graded workspace."""

    root = tmp_path / "workspace"
    root.mkdir()
    with pytest.raises(ToolInputError, match="outside the agent workspace"):
        TerminalService(root, log_root=root / "inside")
    assert not (root / "inside").exists()


def test_t28_shared_service_workspace_must_match_governed_runtime(tmp_path: Path) -> None:
    """A shared service may not smuggle a different workspace into the registry."""

    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    service = TerminalService(first)
    with SQLiteDurableStateStore(tmp_path / "terminal-service-mismatch.sqlite") as store:
        with pytest.raises(ToolInputError, match="workspace does not match"):
            TerminalToolRuntime(second, store, service=service)
    service.shutdown()
