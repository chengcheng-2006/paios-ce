"""Channel contract and CLI channel (Phase 2 CHANNEL_ADAPTER_CONTRACT).

The release candidate implements the CLI channel (local, DM-only, loopback). No real
external channels (WeChat/Feishu/Telegram/Slack/Discord) are implemented.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from .base import Channel, InboundMessage, OutboundMessage
from .cli import CliChannel
from .local_web import LocalWebChatSkeleton

__all__ = ["Channel", "CliChannel", "InboundMessage", "LocalWebChatSkeleton", "OutboundMessage"]
