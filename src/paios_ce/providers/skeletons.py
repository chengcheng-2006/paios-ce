"""Provider skeleton stubs (OPTIONAL — interface only).

OpenAI-Compatible, Local HTTP, and Ollama provider adapters are declared as
interface skeletons. They are NEVER connected live in the current release candidate: no live
credential, no live network, no API call. Their methods raise
UnsupportedCapability or NotImplementedError to make that explicit.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List

from ..protocols import Capability
from .base import (
    ChatRequest,
    ChatResponse,
    Provider,
    ProviderHealth,
    StreamChunk,
    StructuredOutputResult,
    ToolCallResult,
    UnsupportedCapability,
    ValidationResult,
)


class OpenAiCompatibleSkeleton(Provider):
    """Interface skeleton for an OpenAI-compatible provider.

    NOT implemented in the current release candidate. Any call raises UnsupportedCapability.
    """

    provider_id = "openai_compatible"

    def list_models(self) -> List[Dict[str, Any]]:
        raise UnsupportedCapability("MODELS", "openai_compatible is a release candidate skeleton; not connectable")

    def validate_configuration(self) -> ValidationResult:
        return ValidationResult(valid=False, errors=["openai_compatible skeleton not implemented"])

    def get_capabilities(self) -> List[Capability]:
        return []

    def chat(self, request: ChatRequest) -> ChatResponse:
        raise UnsupportedCapability("TEXT_CHAT", "openai_compatible skeleton not implemented")

    def stream_chat(self, request: ChatRequest) -> Iterator[StreamChunk]:
        raise UnsupportedCapability("STREAMING", "openai_compatible skeleton not implemented")

    def tool_call(self, request: ChatRequest) -> ToolCallResult:
        raise UnsupportedCapability("TOOL_CALLING", "openai_compatible skeleton not implemented")

    def structured_output(self, request: ChatRequest, schema: Dict[str, Any]) -> StructuredOutputResult:
        raise UnsupportedCapability("STRUCTURED_OUTPUT", "openai_compatible skeleton not implemented")

    def health_check(self) -> ProviderHealth:
        return ProviderHealth(component="openai_compatible", status="down",
                              reason="the release candidate skeleton; no live connection")


class LocalHttpSkeleton(Provider):
    """Interface skeleton for a local HTTP provider (loopback only).

    NOT implemented in the current release candidate.
    """

    provider_id = "local_http"

    def list_models(self) -> List[Dict[str, Any]]:
        raise UnsupportedCapability("MODELS", "local_http is a release candidate skeleton; not connectable")

    def validate_configuration(self) -> ValidationResult:
        return ValidationResult(valid=False, errors=["local_http skeleton not implemented"])

    def get_capabilities(self) -> List[Capability]:
        return []

    def chat(self, request: ChatRequest) -> ChatResponse:
        raise UnsupportedCapability("TEXT_CHAT", "local_http skeleton not implemented")

    def stream_chat(self, request: ChatRequest) -> Iterator[StreamChunk]:
        raise UnsupportedCapability("STREAMING", "local_http skeleton not implemented")

    def tool_call(self, request: ChatRequest) -> ToolCallResult:
        raise UnsupportedCapability("TOOL_CALLING", "local_http skeleton not implemented")

    def structured_output(self, request: ChatRequest, schema: Dict[str, Any]) -> StructuredOutputResult:
        raise UnsupportedCapability("STRUCTURED_OUTPUT", "local_http skeleton not implemented")

    def health_check(self) -> ProviderHealth:
        return ProviderHealth(component="local_http", status="down",
                              reason="the release candidate skeleton; no live connection")
