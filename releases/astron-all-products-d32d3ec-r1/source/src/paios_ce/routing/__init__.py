"""Minimal router (provider routing and fallback policy).

Routing in the release candidate only to the Mock Provider. OpenAI-Compatible, Local HTTP, and
Ollama provider IDs are reserved interface slots (never connected live).

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from .router import MinimalRouter, RoutingDecision

__all__ = ["MinimalRouter", "RoutingDecision"]
