"""Provider contract and Mock Provider (model provider contract).

The release candidate implements the Mock Provider (P0) only. OpenAI-Compatible, Local HTTP,
and Ollama remain interface skeletons / PLANNED, never live connections.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

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
from .mock import MockProvider
from .openai_compatible import (
    LiveProviderError,
    LiveProviderErrorCode,
    OpenAICompatibleProvider,
    OpenAICompatibleProviderConfig,
)
from .skeletons import LocalHttpSkeleton, OpenAiCompatibleSkeleton

__all__ = [
    "ChatRequest",
    "ChatResponse",
    "LocalHttpSkeleton",
    "MockProvider",
    "LiveProviderError",
    "LiveProviderErrorCode",
    "OpenAICompatibleProvider",
    "OpenAICompatibleProviderConfig",
    "OpenAiCompatibleSkeleton",
    "Provider",
    "ProviderHealth",
    "StreamChunk",
    "StructuredOutputResult",
    "ToolCallResult",
    "UnsupportedCapability",
    "ValidationResult",
]
