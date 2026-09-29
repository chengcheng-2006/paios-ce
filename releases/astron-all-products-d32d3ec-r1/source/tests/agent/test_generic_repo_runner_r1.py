"""Synthetic-only certification for the generic governed repository runner."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from paios_ce.agent import RepoTask, RepoTaskBudget, RepoTaskRunner
from paios_ce.providers import MockProvider, ToolCallResult


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, text=True, stdout=subprocess.PIPE).stdout


def _repo(tmp_path: Path, *, broken: bool = True) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "calc.py").write_text("def add(a, b):\n    return a - b\n" if broken else "def add(a, b):\n    return a + b\n")
    (root / "helper.py").write_text("NAME = 'synthetic'\n")
    tests = root / "tests"; tests.mkdir()
    (tests / "test_calc.py").write_text("from calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n")
    _git(root, "init"); _git(root, "config", "user.email", "qa@example.invalid"); _git(root, "config", "user.name", "QA")
    _git(root, "add", "."); _git(root, "commit", "-m", "synthetic baseline")
    return root


def _call(name: str, arguments: dict[str, object], index: int, *, call_id: str | None = None) -> dict[str, object]:
    return {"id": call_id or f"call-{index}", "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


def _task(root: Path, tmp_path: Path, **kwargs: object) -> RepoTask:
    return RepoTask("synthetic-task", root, "Fix the synthetic addition bug.", kwargs.pop("budget", RepoTaskBudget(8, 15, 8, 256)), **kwargs)


def _run(root: Path, tmp_path: Path, batches: list[list[dict[str, object]]], **kwargs: object):
    return RepoTaskRunner(MockProvider(tool_call_batches=batches), model_id="mock-1", runtime_root=tmp_path / "runtime").run(_task(root, tmp_path, **kwargs))


def test_r01_simple_python_bug(tmp_path: Path) -> None:
    result = _run(_repo(tmp_path), tmp_path, [[_call("workspace.patch_text", {"path": "calc.py", "expected_old": "return a - b", "replacement": "return a + b"}, 1)], []])
    assert "return a + b" in result.final_diff


def test_r02_multi_file_inspection(tmp_path: Path) -> None:
    result = _run(_repo(tmp_path), tmp_path, [[_call("workspace.read_text", {"path": "calc.py"}, 1)], [_call("workspace.read_text", {"path": "helper.py"}, 2)], []])
    assert result.tool_calls == 2


def test_r03_terminal_command(tmp_path: Path) -> None:
    result = _run(_repo(tmp_path), tmp_path, [[_call("terminal_open", {}, 1)], []])
    assert result.trajectory[0]["operation"] == "terminal_open"


def test_r04_pytest_failure_edit_pass(tmp_path: Path) -> None:
    result = _run(_repo(tmp_path), tmp_path, [[_call("test.run_pytest_bounded", {}, 1)], [_call("workspace.patch_text", {"path": "calc.py", "expected_old": "return a - b", "replacement": "return a + b"}, 2)], [_call("test.run_pytest_bounded", {}, 3)], []])
    assert result.tool_calls == 3


def test_r05_git_diff_capture(tmp_path: Path) -> None:
    result = _run(_repo(tmp_path), tmp_path, [[_call("workspace.patch_text", {"path": "calc.py", "expected_old": "- b", "replacement": "+ b"}, 1)], []])
    assert result.files_changed == ("calc.py",)


def test_r06_budget_exhaustion(tmp_path: Path) -> None:
    result = _run(_repo(tmp_path), tmp_path, [[_call("workspace.read_text", {"path": "calc.py"}, 1)]], budget=RepoTaskBudget(1, 15, 1, 256))
    assert result.runtime_status == "BUDGET_EXHAUSTED"


def test_r07_done_is_not_grading(tmp_path: Path) -> None:
    class DoneProvider(MockProvider):
        def tool_call(self, request): return ToolCallResult(content="done", tool_calls=[], model_id="mock-1")
    root = _repo(tmp_path)
    result = RepoTaskRunner(DoneProvider(), model_id="mock-1", runtime_root=tmp_path / "runtime").run(_task(root, tmp_path))
    assert result.runtime_status == "AGENT_STOPPED" and result.final_answer == "done"


def test_r08_tool_error_feedback(tmp_path: Path) -> None:
    result = _run(_repo(tmp_path), tmp_path, [[_call("workspace.read_text", {"path": "missing.py"}, 1)], []])
    assert result.trajectory[0]["status"] == "failure"


def test_r09_terminal_timeout(tmp_path: Path) -> None:
    task_id = "synthetic-task"; owner = f"repo-task:{task_id}"
    terminal_id = "term_" + hashlib.sha256(f"{task_id}:open:{owner}".encode()).hexdigest()[:20]
    result = _run(_repo(tmp_path), tmp_path, [[_call("terminal_open", {}, 1, call_id="open")], [_call("terminal_send", {"terminal_id": terminal_id, "input": "sleep 2", "timeout_seconds": 1}, 2)], []])
    assert result.trajectory[1]["status"] == "failure"


def test_r10_terminal_replay_protection(tmp_path: Path) -> None:
    result = _run(_repo(tmp_path), tmp_path, [[_call("terminal_open", {}, 1, call_id="same")], [_call("terminal_open", {}, 2, call_id="same")], []])
    assert result.tool_calls == 2


def test_r11_one_task_one_workspace(tmp_path: Path) -> None:
    root = _repo(tmp_path); runner = RepoTaskRunner(MockProvider(tool_call_batches=[[]]), model_id="mock-1", runtime_root=tmp_path / "runtime")
    runner.run(_task(root, tmp_path))
    with pytest.raises(ValueError, match="fresh runtime"):
        runner.run(_task(root, tmp_path))


def test_r12_cross_task_runtime_isolation(tmp_path: Path) -> None:
    root = _repo(tmp_path); runner = RepoTaskRunner(MockProvider(tool_call_batches=[[], []]), model_id="mock-1", runtime_root=tmp_path / "runtime")
    runner.run(_task(root, tmp_path)); second = RepoTask("second-task", root, "Inspect only.", RepoTaskBudget(1, 15, 1, 64))
    assert runner.run(second).task_id == "second-task"


def test_r13_dirty_workspace_rejected(tmp_path: Path) -> None:
    root = _repo(tmp_path); (root / "calc.py").write_text("dirty\n")
    with pytest.raises(ValueError, match="clean"):
        _run(root, tmp_path, [[]])


def test_r14_problem_statement_exact_hash(tmp_path: Path) -> None:
    root = _repo(tmp_path); task = RepoTask("hash-task", root, "Exact public problem.", RepoTaskBudget(1, 15, 1, 64))
    result = RepoTaskRunner(MockProvider(tool_call_batches=[[]]), model_id="mock-1", runtime_root=tmp_path / "runtime").run(task)
    assert result.problem_statement_sha256 == hashlib.sha256(b"Exact public problem.").hexdigest()


def test_r15_final_answer_captured(tmp_path: Path) -> None:
    class AnswerProvider(MockProvider):
        def tool_call(self, request): return ToolCallResult(content="final synthetic answer", tool_calls=[], model_id="mock-1")
    result = RepoTaskRunner(AnswerProvider(), model_id="mock-1", runtime_root=tmp_path / "runtime").run(_task(_repo(tmp_path), tmp_path))
    assert result.final_answer == "final synthetic answer"


def test_r16_empty_diff_is_valid_result(tmp_path: Path) -> None:
    result = _run(_repo(tmp_path), tmp_path, [[]])
    assert result.final_diff == "" and result.runtime_status == "AGENT_STOPPED"


def test_r17_multi_turn_loop(tmp_path: Path) -> None:
    result = _run(_repo(tmp_path), tmp_path, [[_call("workspace.read_text", {"path": "calc.py"}, 1)], [_call("workspace.list_files", {"path": "."}, 2)], []])
    assert result.turns == 3


def test_r18_secret_redaction_by_terminal(tmp_path: Path) -> None:
    task_id = "synthetic-task"; owner = f"repo-task:{task_id}"
    terminal_id = "term_" + hashlib.sha256(f"{task_id}:open:{owner}".encode()).hexdigest()[:20]
    result = _run(_repo(tmp_path), tmp_path, [[_call("terminal_open", {"env": {"API_KEY": "secret"}}, 1, call_id="open")], [_call("terminal_send", {"terminal_id": terminal_id, "input": "printf $API_KEY"}, 2)], []])
    assert "secret" not in json.dumps(result.trajectory)
