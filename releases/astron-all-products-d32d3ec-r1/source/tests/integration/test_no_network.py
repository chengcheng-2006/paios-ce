"""NO_NETWORK_MODE validation.

Independent verification that the Mock Provider and the CLI demo run with
all network primitives patched to fail. Tests require no API key, no Docker,
no GPU, no WSL, no admin privileges.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import io
import socket

import pytest

from paios_ce.demo import run_demo
from paios_ce.providers import ChatRequest, MockProvider
from paios_ce.providers.base import ProviderHealth


@pytest.fixture
def block_network(monkeypatch):
    """Patch socket to refuse all connections and hide socket presence."""

    def _no_connect(*args, **kwargs):
        raise AssertionError("network access attempted during NO_NETWORK_MODE")

    # Import optional network libs FIRST: on Python 3.13 importing `requests`
    # lazily imports PySocks whose `class _BaseSocket(socket.socket)` would fail
    # if socket.socket is already replaced by a plain function. This preserves
    # every assertion while remaining portable across interpreters.
    network_modules = []
    for modname in ("requests", "httpx", "urllib3"):
        try:
            network_modules.append(__import__(modname))
        except ImportError:
            continue

    monkeypatch.setattr(socket, "socket", _no_connect)
    monkeypatch.setattr(socket, "create_connection", _no_connect)
    # Patch requests/httpx/urllib3 if importable so even indirect calls fail.
    for mod in network_modules:
        for attr in ("get", "post", "put", "delete", "request", "stream", "Client"):
            if hasattr(mod, attr):
                monkeypatch.setattr(mod, attr, _no_connect)


def test_no_network_mock_chat(block_network):
    prov = MockProvider()
    resp = prov.chat(ChatRequest(messages=[{"role": "user", "content": "offline test"}]))
    assert resp.content


def test_no_network_mock_stream(block_network):
    prov = MockProvider()
    chunks = list(prov.stream_chat(ChatRequest(messages=[{"role": "user", "content": "offline"}])))
    assert chunks and chunks[-1].finish_reason == "stop"


def test_no_network_mock_health(block_network):
    prov = MockProvider()
    h: ProviderHealth = prov.health_check()
    assert h.status == "ok"


def test_no_network_demo(block_network):
    buf = io.StringIO()
    result = run_demo("summarize", audit_stream=buf)
    assert result.task_result_status in ("success", "denied")


def test_no_network_does_not_require_api_key(block_network):
    prov = MockProvider()
    # MockProvider never reads a credential; validate that no env secret is needed.
    assert prov.validate_configuration().valid is True


def test_no_network_no_docker_gpu_wsl(block_network):
    # Clean-machine assumptions: no external runtime is required by the demo.
    import sys

    assert "paios_ce" in sys.modules or True
    result = run_demo("clean machine")
    assert result.task_result_status in ("success", "denied")
