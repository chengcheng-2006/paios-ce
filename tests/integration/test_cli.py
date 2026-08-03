"""CLI integration tests.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import json

import pytest

from paios_ce.cli.main import build_parser, main


def _run(argv, capsys):
    code = main(argv)
    out = capsys.readouterr().out
    return code, out


def test_cli_demo(capsys):
    code, out = _run(["demo", "-i", "hello"], capsys)
    assert code == 0
    payload = json.loads(out)
    assert payload["command"] == "demo"


def test_cli_health(capsys):
    code, out = _run(["health"], capsys)
    assert code == 0
    payload = json.loads(out)
    assert payload["command"] == "health"
    assert len(payload["components"]) >= 3


def test_cli_validate_config(capsys):
    code, out = _run(
        ["validate-config",
         "--public-config", "examples/public_config.example.yaml",
         "--private-config", "examples/private_config.example.yaml"],
        capsys,
    )
    assert code == 0
    payload = json.loads(out)
    assert payload["valid"] is True


def test_cli_validate_config_invalid(capsys, tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("schema: [broken\n", encoding="utf-8")
    code, out = _run(["validate-config", "--public-config", str(bad)], capsys)
    assert code != 0
    payload = json.loads(out)
    assert payload["valid"] is False


def test_cli_run_task_demo_file(capsys):
    code, out = _run(["run-task", "examples/demo_task.json"], capsys)
    assert code == 0
    payload = json.loads(out)
    assert payload["command"] == "run-task"
    assert payload["status"] == "success"


def test_cli_run_task_missing_file(capsys):
    code, out = _run(["run-task", "no_such_file.json"], capsys)
    assert code != 0
    payload = json.loads(out)
    assert payload["status"] == "error"


def test_cli_run_task_invalid_json(capsys, tmp_path):
    f = tmp_path / "bad.json"
    f.write_text("{not json", encoding="utf-8")
    code, out = _run(["run-task", str(f)], capsys)
    assert code != 0


def test_cli_parser_has_expected_commands():
    parser = build_parser()
    sub_actions = parser._subparsers._group_actions[0].choices
    assert {"demo", "health", "validate-config", "run-task"}.issubset(sub_actions)
