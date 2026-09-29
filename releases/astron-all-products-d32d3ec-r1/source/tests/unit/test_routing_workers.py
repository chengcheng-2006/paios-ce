"""Router and worker unit tests.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import pytest

from paios_ce.channels import CliChannel, InboundMessage, LocalWebChatSkeleton, OutboundMessage
from paios_ce.providers import MockProvider
from paios_ce.routing import MinimalRouter
from paios_ce.workers import MockWorker
from paios_ce.protocols import ActionRequest


def test_router_routes_mock():
    router = MinimalRouter(MockProvider())
    d = router.route("mock", "TEXT_CHAT")
    assert d.resolved is True
    assert d.provider_id == "mock"


def test_router_rejects_skeleton_providers():
    router = MinimalRouter(MockProvider())
    for pid in ("openai_compatible", "local_http", "ollama"):
        d = router.route(pid, "TEXT_CHAT")
        assert d.resolved is False


def test_router_rejects_unknown():
    router = MinimalRouter(MockProvider())
    d = router.route("wechat", "TEXT_CHAT")
    assert d.resolved is False


def test_router_default_is_mock():
    router = MinimalRouter(MockProvider())
    assert router.default_provider_id() == "mock"


def test_mock_worker_executes():
    w = MockWorker()
    ar = ActionRequest(action_id="act_1", operation="read_file_in_scope",
                       parameters={"trace_id": "trace_redacted_01"},
                       idempotency_key="idem_1")
    result = w.execute(ar)
    assert result.status.value == "success"
    assert ar.action_id in w.executed_action_ids


def test_mock_worker_denied_without_approval():
    w = MockWorker()
    ar = ActionRequest(action_id="act_2", operation="delete_file",
                       parameters={"trace_id": "trace_redacted_01"},
                       idempotency_key="idem_2", approval_required=True)
    result = w.execute(ar)
    assert result.status.value == "denied"


def test_cli_channel_validate():
    ch = CliChannel()
    assert ch.validate_message(InboundMessage(text="hello")) is None
    assert ch.validate_message(InboundMessage(text="")) is not None


def test_cli_channel_delivers():
    import io
    buf = io.StringIO()
    ch = CliChannel(out_stream=buf)
    ch.deliver(OutboundMessage(text="hello"))
    assert "hello" in buf.getvalue()


def test_local_web_skeleton_blocks_public_bind():
    from paios_ce.protocols import ActionOrigin

    ch = LocalWebChatSkeleton(public_bind=True)
    msg = InboundMessage(text="x", channel_id="local_web", origin=ActionOrigin.WEB)
    assert ch.validate_message(msg) is not None
