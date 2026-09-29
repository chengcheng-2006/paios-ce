"""Regression for restart processes that import the durable state authority first."""

from __future__ import annotations

import subprocess
import sys


def test_state_authority_imports_in_a_fresh_process() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from paios_ce.state import SQLiteDurableStateStore; "
                "print(SQLiteDurableStateStore.__name__)"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "SQLiteDurableStateStore"
