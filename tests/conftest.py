"""Shared pytest fixtures for the PAIOS CE test suite.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

EXAMPLES = REPO_ROOT / "examples"
SCHEMAS = REPO_ROOT / "schemas"


@pytest.fixture
def public_example() -> Path:
    return EXAMPLES / "public_config.example.yaml"


@pytest.fixture
def private_example() -> Path:
    return EXAMPLES / "private_config.example.yaml"


@pytest.fixture
def demo_task_file() -> Path:
    return EXAMPLES / "demo_task.json"


@pytest.fixture
def schemas_dir() -> Path:
    return SCHEMAS


@pytest.fixture
def load_public_example(public_example):
    def _load():
        with open(public_example, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    return _load


@pytest.fixture
def load_private_example(private_example):
    def _load():
        with open(private_example, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    return _load


@pytest.fixture
def read_schema(schemas_dir):
    def _read(name: str) -> dict:
        with open(schemas_dir / name, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return _read
