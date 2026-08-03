"""Provider contract and Mock Provider (Phase 2 MODEL_PROVIDER_CONTRACT).

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
from .skeletons import LocalHttpSkeleton, OpenAiCompatibleSkeleton

__all__ = [
    "ChatRequest",
    "ChatResponse",
    "LocalHttpSkeleton",
    "MockProvider",
    "OpenAiCompatibleSkeleton",
    "Provider",
    "ProviderHealth",
    "StreamChunk",
    "StructuredOutputResult",
    "ToolCallResult",
    "UnsupportedCapability",
    "ValidationResult",
]
