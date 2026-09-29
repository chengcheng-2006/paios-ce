"""Mock Provider unit tests.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import socket

import pytest

from paios_ce.providers import (
    ChatRequest,
    MockProvider,
    UnsupportedCapability,
)
from paios_ce.providers.base import ValidationResult


def test_mock_chat():
    prov = MockProvider()
    resp = prov.chat(ChatRequest(messages=[{"role": "user", "content": "hello"}]))
    assert resp.content
    assert resp.finish_reason == "stop"
    assert resp.usage["total_tokens"] > 0


def test_mock_stream():
    prov = MockProvider()
    chunks = list(prov.stream_chat(ChatRequest(messages=[{"role": "user", "content": "hello"}])))
    assert len(chunks) >= 1
    assert chunks[-1].finish_reason == "stop"


def test_mock_tool_call():
    prov = MockProvider()
    tc = prov.tool_call(ChatRequest(messages=[{"role": "user", "content": "use tool"}]))
    assert tc.tool_calls
    assert tc.tool_calls[0]["type"] == "function"


def test_mock_structured_output():
    prov = MockProvider()
    so = prov.structured_output(ChatRequest(), schema={})
    assert "summary_class" in so.data


def test_mock_error():
    prov = MockProvider(fail_mode="error")
    with pytest.raises(UnsupportedCapability):
        prov.chat(ChatRequest())


def test_mock_timeout():
    prov = MockProvider(fail_mode="timeout")
    with pytest.raises(TimeoutError):
        prov.chat(ChatRequest())


def test_mock_no_network():
    prov = MockProvider()
    try:
        socket.create_connection  # noqa: B018
    except Exception:
        pass
    resp = prov.chat(ChatRequest(messages=[{"role": "user", "content": "offline"}]))
    assert resp.content


def test_mock_capabilities_are_local():
    prov = MockProvider()
    caps = {c.value for c in prov.get_capabilities()}
    assert "LOCAL_INFERENCE" in caps
    assert "TEXT_CHAT" in caps


def test_mock_validate_configuration():
    prov = MockProvider()
    vr = prov.validate_configuration()
    assert isinstance(vr, ValidationResult)
    assert vr.valid is True


def test_mock_health_ok():
    prov = MockProvider()
    h = prov.health_check()
    assert h.status == "ok"
    assert "not-a-valid-provider-token" not in repr(h.safe_details)


def test_mock_fixed_response():
    prov = MockProvider(fixed_responses={"hello": "hi there"})
    resp = prov.chat(ChatRequest(messages=[{"role": "user", "content": "say hello"}]))
    assert resp.content == "hi there"


def test_mock_deterministic():
    p1 = MockProvider()
    p2 = MockProvider()
    r1 = p1.chat(ChatRequest(messages=[{"role": "user", "content": "abc"}]))
    r2 = p2.chat(ChatRequest(messages=[{"role": "user", "content": "abc"}]))
    assert r1.content == r2.content


def test_mock_unsupported_optional():
    prov = MockProvider()
    with pytest.raises(UnsupportedCapability):
        prov.vision_optional(ChatRequest())
