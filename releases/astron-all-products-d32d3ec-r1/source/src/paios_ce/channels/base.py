"""Channel contract (channel adapter contract).

A channel adapter validates inbound messages, resolves identity, quarantines
attachments, and delivers outbound messages. Channels are subject to the
frozen security defaults: DM-only, owner allowlist, loopback only, high-risk
confirmation.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..protocols import ActionOrigin


@dataclass
class InboundMessage:
    text: str
    origin: ActionOrigin = ActionOrigin.CLI
    channel_id: str = "cli"
    principal_id: str = "principal:example.invalid/user-1"
    message_id: str = "msg_placeholder_01"
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    owner_only: bool = False


@dataclass
class OutboundMessage:
    text: str
    channel_id: str = "cli"
    trace_id: str = "trace_redacted_01"


class Channel(abc.ABC):
    """Channel adapter interface."""

    channel_id: str = "abstract"

    @abc.abstractmethod
    def validate_message(self, message: InboundMessage) -> Optional[str]:
        """Return an error reason if the message is invalid, else None."""

    @abc.abstractmethod
    def deliver(self, message: OutboundMessage) -> None:
        """Deliver an outbound message (redacted) to the channel."""
