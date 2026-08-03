"""Provider contract (model provider contract).

A provider adapter MUST implement all required methods. Optional capabilities
are exposed via *_optional methods that return UnsupportedCapability rather
than raising or silently degrading. No silent fallback; unsupported
capability is a structured outcome.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional

from ..protocols import Capability


@dataclass
class ChatRequest:
    messages: List[Dict[str, str]] = field(default_factory=list)
    model_id: str = "mock"
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    capabilities: Optional[List[str]] = None
    trace_id: str = "trace_redacted_01"


@dataclass
class ChatResponse:
    content: str
    model_id: str
    finish_reason: str = "stop"
    usage: Dict[str, int] = field(default_factory=dict)
    trace_id: str = "trace_redacted_01"


@dataclass
class StreamChunk:
    delta: str
    index: int = 0
    finish_reason: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    trace_id: str = "trace_redacted_01"


@dataclass
class ToolCallResult:
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    content: str = ""
    model_id: str = "mock"
    trace_id: str = "trace_redacted_01"


@dataclass
class StructuredOutputResult:
    data: Dict[str, Any] = field(default_factory=dict)
    model_id: str = "mock"
    trace_id: str = "trace_redacted_01"


@dataclass
class ValidationResult:
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.valid


@dataclass
class ProviderHealth:
    component: str = "provider"
    status: str = "ok"  # ok | degraded | down
    reason: str = ""
    safe_details: Dict[str, Any] = field(default_factory=dict)


class UnsupportedCapability(Exception):
    """Structured outcome for an unsupported capability (not an error)."""

    def __init__(self, capability: str, message: str = "provider does not declare requested capability") -> None:
        self.capability = capability
        self.message = message
        super().__init__(f"{capability}: {message}")


class Provider(abc.ABC):
    """Unified provider interface."""

    provider_id: str = "abstract"

    @abc.abstractmethod
    def list_models(self) -> List[Dict[str, Any]]:
        """Descriptors of models this provider can actually serve."""

    @abc.abstractmethod
    def validate_configuration(self) -> ValidationResult:
        """Offline structural validation; MUST NOT consume API quota."""

    @abc.abstractmethod
    def get_capabilities(self) -> List[Capability]:
        """Declared capability subset; MUST match the manifest."""

    @abc.abstractmethod
    def chat(self, request: ChatRequest) -> ChatResponse:
        """Single/multi-turn chat."""

    @abc.abstractmethod
    def stream_chat(self, request: ChatRequest) -> Iterator[StreamChunk]:
        """Yields StreamChunk items; final chunk carries finish_reason/usage."""

    @abc.abstractmethod
    def tool_call(self, request: ChatRequest) -> ToolCallResult:
        """Emit structured tool calls; MUST NOT execute the tool."""

    @abc.abstractmethod
    def structured_output(self, request: ChatRequest, schema: Dict[str, Any]) -> StructuredOutputResult:
        """Produce JSON adhering to the provided schema."""

    @abc.abstractmethod
    def health_check(self) -> ProviderHealth:
        """Local-only self-check; MUST NOT consume real API quota."""

    def vision_optional(self, request: ChatRequest):
        return self._unsupported("VISION")

    def audio_input_optional(self, request: ChatRequest):
        return self._unsupported("AUDIO_INPUT")

    def embeddings_optional(self, request: ChatRequest):
        return self._unsupported("EMBEDDING")

    def _unsupported(self, capability: str):
        raise UnsupportedCapability(capability)
