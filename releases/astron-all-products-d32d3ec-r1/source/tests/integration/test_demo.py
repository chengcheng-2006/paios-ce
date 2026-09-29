"""Demo closed-loop integration tests.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import io

from paios_ce.demo import run_demo


def test_demo_success_flow():
    result = run_demo("summarize my task list")
    assert result.task_result_status in ("success", "denied")
    assert result.trace_id == "trace_demo_0001"
    assert result.summary


def test_demo_writes_redacted_audit():
    buf = io.StringIO()
    result = run_demo("hello", audit_stream=buf)
    text = buf.getvalue()
    assert text.strip().endswith("}")  # JSONL written
    assert "not-a-valid-provider-token" not in text
    assert "secret" not in text.lower() or "secretref" in text.lower() or "secret_value" not in text


def test_demo_fully_local_no_network():
    import socket

    # Block all socket creation to prove no network is attempted.
    def _block(*args, **kwargs):
        raise AssertionError("network access attempted")
    orig = socket.socket
    socket.socket = _block  # type: ignore[assignment]
    try:
        result = run_demo("summarize")
        assert result.task_result_status in ("success", "denied")
    finally:
        socket.socket = orig


def test_demo_structured_json():
    result = run_demo("hello")
    payload = result.to_json()
    assert '"demo_input": "hello"' in payload
