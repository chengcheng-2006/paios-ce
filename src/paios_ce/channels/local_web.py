"""Local Web Chat skeleton (OPTIONAL — interface only).

Declares the local web chat adapter shape. NOT implemented in the current release candidate: no
server, no port, no public bind, no frontend persistence. Loopback only by
default; public_bind is explicit opt-in (and still not implemented here).

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

from typing import Optional

from .base import Channel, InboundMessage, OutboundMessage


class LocalWebChatSkeleton(Channel):
    """Interface skeleton for a local web chat/dashboard adapter."""

    channel_id = "local_web"

    def __init__(self, listen: str = "127.0.0.1", port: int = 8080, public_bind: bool = False) -> None:
        self._listen = listen
        self._port = port
        self._public_bind = public_bind

    @property
    def bind_public(self) -> bool:
        return self._public_bind

    def validate_message(self, message: InboundMessage) -> Optional[str]:
        if self._public_bind:
            return "local_web skeleton does not support public bind in the current release candidate"
        if message.origin.value != "web":
            return "unsupported origin for local_web"
        return None

    def deliver(self, message: OutboundMessage) -> None:
        raise NotImplementedError("local_web skeleton is not implemented in the current release candidate")
