"""MockProvider — deterministic, fully-local provider for demo/tests.

Facts (Phase 3 execution prompt section 13):
  - CURRENT_EVIDENCE_STATUS = ABSENT -> IMPLEMENTED after tests pass
  - CURRENT_PUBLIC_SUPPORT_LABEL = PLANNED -> EXPERIMENTAL
  - PHASE_3_PRIORITY = P0
  - fully local; no network; no API key; deterministic; configurable fixed
    responses; can simulate failure, latency, tool calls, and structured
    output; usable for the demo.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Dict, Iterator, List, Optional

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

_MOCK_CAPABILITIES = [
    Capability.TEXT_CHAT,
    Capability.TOOL_CALLING,
    Capability.STRUCTURED_OUTPUT,
    Capability.STREAMING,
    Capability.LOCAL_INFERENCE,
]


class MockProvider(Provider):
    """Deterministic local mock provider.

    ``fail_mode`` may be one of {None, "error", "timeout"} to simulate provider
    failure. ``latency_seconds`` simulates delay. ``fixed_responses`` maps a
    prompt substring to a canned reply. ``tool_calls`` is a list of canned tool
    call dicts returned by tool_call(). ``structured_payload`` is the payload
    returned by structured_output(). Defaults are deterministic and schema-safe.
    """

    provider_id = "mock"

    def __init__(
        self,
        fixed_responses: Optional[Dict[str, str]] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        structured_payload: Optional[Dict[str, Any]] = None,
        fail_mode: Optional[str] = None,
        latency_seconds: float = 0.0,
    ) -> None:
        self._fixed = dict(fixed_responses or {})
        self._tool_calls = list(tool_calls or [
            {
                "id": "call_mock_01",
                "type": "function",
                "function": {
                    "name": "mock.read_file_in_scope",
                    "arguments": json.dumps({"path_class": "quarantine_temp"}),
                },
            }
        ])
        self._structured = dict(structured_payload or {"summary_class": "summary_produced"})
        self._fail_mode = fail_mode
        self._latency = max(0.0, float(latency_seconds))
        if self._fail_mode not in (None, "error", "timeout"):
            raise ValueError("fail_mode must be one of {None,'error','timeout'}")

    # -- contract -----------------------------------------------------------

    def list_models(self) -> List[Dict[str, Any]]:
        return [
            {"id": "mock-1", "provider": "mock", "local": True, "supported_capabilities": [c.value for c in _MOCK_CAPABILITIES]}
        ]

    def validate_configuration(self) -> ValidationResult:
        errors = []
        if self._fail_mode == "error":
            errors.append("mock provider configured to simulate configuration failure")
        return ValidationResult(valid=not errors, errors=errors)

    def get_capabilities(self) -> List[Capability]:
        return list(_MOCK_CAPABILITIES)

    def _maybe_delay(self) -> None:
        if self._latency:
            time.sleep(self._latency)

    def _simulate_failure(self) -> None:
        if self._fail_mode == "error":
            raise UnsupportedCapability("TEXT_CHAT", "mock provider simulated failure")
        if self._fail_mode == "timeout":
            raise TimeoutError("mock provider simulated timeout")

    def _render(self, request: ChatRequest) -> str:
        last = (request.messages or [{}])[-1].get("content", "") if request.messages else ""
        for key, reply in self._fixed.items():
            if key and key.lower() in str(last).lower():
                return reply
        digest = hashlib.sha256(str(last).encode("utf-8")).hexdigest()[:8]
        return f"mock deterministic reply [{digest}] for: {str(last)[:40]}"

    def chat(self, request: ChatRequest) -> ChatResponse:
        self._maybe_delay()
        self._simulate_failure()
        content = self._render(request)
        return ChatResponse(
            content=content,
            model_id=request.model_id or "mock-1",
            finish_reason="stop",
            usage={"prompt_tokens": 8, "completion_tokens": 8, "total_tokens": 16},
            trace_id=request.trace_id,
        )

    def stream_chat(self, request: ChatRequest) -> Iterator[StreamChunk]:
        self._maybe_delay()
        self._simulate_failure()
        content = self._render(request)
        words = content.split(" ") or ["."]
        for idx, word in enumerate(words):
            yield StreamChunk(delta=word + (" " if idx < len(words) - 1 else ""), index=idx, trace_id=request.trace_id)
        yield StreamChunk(delta="", index=len(words), finish_reason="stop",
                          usage={"prompt_tokens": 8, "completion_tokens": 8, "total_tokens": 16},
                          trace_id=request.trace_id)

    def tool_call(self, request: ChatRequest) -> ToolCallResult:
        self._maybe_delay()
        self._simulate_failure()
        return ToolCallResult(tool_calls=list(self._tool_calls), content="", model_id=request.model_id or "mock-1", trace_id=request.trace_id)

    def structured_output(self, request: ChatRequest, schema: Dict[str, Any]) -> StructuredOutputResult:
        self._maybe_delay()
        self._simulate_failure()
        # Deterministic: always return the configured payload (schema-safe by default).
        return StructuredOutputResult(data=dict(self._structured), model_id=request.model_id or "mock-1", trace_id=request.trace_id)

    def health_check(self) -> ProviderHealth:
        if self._fail_mode == "error":
            return ProviderHealth(component="mock", status="degraded", reason="mock provider simulated failure",
                                  safe_details={"provider_id": "mock", "capabilities": [c.value for c in _MOCK_CAPABILITIES]})
        return ProviderHealth(component="mock", status="ok", reason="",
                              safe_details={"provider_id": "mock", "capabilities": [c.value for c in _MOCK_CAPABILITIES]})

    # -- optional capability skeletons --------------------------------------

    def vision_optional(self, request: ChatRequest):
        raise UnsupportedCapability("VISION")

    def audio_input_optional(self, request: ChatRequest):
        raise UnsupportedCapability("AUDIO_INPUT")

    def embeddings_optional(self, request: ChatRequest):
        raise UnsupportedCapability("EMBEDDING")
