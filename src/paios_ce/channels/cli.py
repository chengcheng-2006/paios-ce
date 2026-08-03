"""CliChannel — local terminal channel (the release candidate P0).

Default DM-only, owner allowlist enforced by the orchestrator, loopback only,
structured redacted output. Does not require any secret or network.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import sys
from typing import Optional

from .base import Channel, InboundMessage, OutboundMessage


class CliChannel(Channel):
    """Writes outbound messages to stdout (redacted, structured)."""

    channel_id = "cli"

    def __init__(self, out_stream=None) -> None:
        self._out = out_stream if out_stream is not None else sys.stdout

    def validate_message(self, message: InboundMessage) -> Optional[str]:
        if not message.text or not message.text.strip():
            return "empty message"
        if message.channel_id != "cli":
            return "unsupported channel"
        return None

    def deliver(self, message: OutboundMessage) -> None:
        line = f"[{message.channel_id}] {message.text}"
        self._out.write(line + "\n")
        self._out.flush()
