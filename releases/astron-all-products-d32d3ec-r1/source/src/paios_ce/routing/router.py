"""MinimalRouter — routes a TaskEnvelope to a Provider.

Current policy:
  - default provider: mock (no API key, no network)
  - "openai_compatible", "local_http", "ollama" are recognized provider IDs
    but are NOT connectable in the current release candidate (interface skeletons only).
  - unknown provider -> routing decision "unsupported".

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..providers import Provider
from ..providers.mock import MockProvider


@dataclass(frozen=True)
class RoutingDecision:
    provider_id: str
    capability: str
    resolved: bool
    reason: str


class MinimalRouter:
    """Routes only to the Mock Provider in the current release candidate."""

    def __init__(self, provider: Optional[Provider] = None) -> None:
        self._provider = provider or MockProvider()

    @property
    def provider(self) -> Provider:
        return self._provider

    def route(self, provider_id: str, capability: str) -> RoutingDecision:
        pid = (provider_id or "mock").strip().lower()
        if pid == "mock":
            return RoutingDecision(pid, capability, True, "mock provider selected (default)")
        if pid in {"openai_compatible", "local_http", "ollama"}:
            return RoutingDecision(
                pid, capability, False,
                f"{pid} is a release candidate interface skeleton only; not connectable in the current release candidate",
            )
        return RoutingDecision(pid, capability, False, "unknown provider id")

    def default_provider_id(self) -> str:
        return "mock"
