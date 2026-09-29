"""One deliberately small OpenAI-compatible provider for Astron Phase 3.

The adapter proposes structured actions only.  It has no handle to a tool
executor, a durable state store, or task-completion state.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import os
import re
import socket
from typing import Any, Dict, Iterator, List, Mapping
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import urlparse

from ..audit import redact_text
from ..protocols import Capability
from .base import (
    ChatRequest,
    ChatResponse,
    Provider,
    ProviderHealth,
    StreamChunk,
    StructuredOutputResult,
    ToolCallResult,
    ValidationResult,
)


class LiveProviderErrorCode(str, Enum):
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
    INVALID_MODEL_OUTPUT = "INVALID_MODEL_OUTPUT"


class LiveProviderError(RuntimeError):
    """Redacted live-provider failure with a stable diagnostic class."""

    def __init__(
        self,
        code: LiveProviderErrorCode,
        message: str,
        *,
        safe_diagnostics: Mapping[str, object] | None = None,
    ) -> None:
        self.code = code
        self.safe_diagnostics = dict(safe_diagnostics or _empty_diagnostics())
        super().__init__(message)


_MAX_SAFE_ERROR_BODY_BYTES = 1024
_MAX_SAFE_PROVIDER_MESSAGE = 512
_MAX_SAFE_PROVIDER_TOKEN = 96
_MAX_SAFE_REQUEST_ID = 128
_PROVIDER_TOKEN_RE = re.compile(r"[A-Za-z0-9._:-]{1,96}")
_PROVIDER_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9._:-]{1,128}")
_SAFE_PROVIDER_FUNCTION_NAME_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
_SAFE_INTERNAL_OPERATION_NAME_RE = re.compile(r"[A-Za-z0-9_.-]{1,128}")
_MAX_SAFE_USAGE_COUNTER = 1_000_000_000
_SAFE_USAGE_FIELDS = frozenset({
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cached_tokens",
    "prompt_cache_hit_tokens",
    "prompt_cache_miss_tokens",
})

# Phase 3 internal operations are intentionally expressive. DeepSeek Chat
# Completions allows only letters, digits, underscores, and dashes for a
# function name, so the transport mapping is explicit and reversible.
_INTERNAL_TO_PROVIDER_TOOL_NAME = {
    "workspace.list_files": "workspace_list_files",
    "workspace.read_text": "workspace_read_text",
    "workspace.patch_text": "workspace_patch_text",
    "workspace.write_artifact": "workspace_write_artifact",
    "validate.json": "validate_json",
    "validate.file": "validate_file",
    "test.run_pytest_bounded": "test_run_pytest_bounded",
}
_PROVIDER_TO_INTERNAL_TOOL_NAME = {value: key for key, value in _INTERNAL_TO_PROVIDER_TOOL_NAME.items()}


def _empty_diagnostics(snapshot: Mapping[str, object] | None = None) -> dict[str, object]:
    """Return the only diagnostics shape that may cross the live boundary."""

    return {
        "http_status": None,
        "provider_error_type": "NOT_REPORTED",
        "provider_error_code": "NOT_REPORTED",
        "provider_error_message_sanitized": "NOT_REPORTED",
        "provider_request_id_safe": "NOT_REPORTED",
        "request_contract_snapshot": dict(snapshot or {}),
    }


def _safe_usage(payload: Mapping[str, object]) -> dict[str, int]:
    """Retain only bounded, non-negative Provider usage counters."""

    usage_raw = payload.get("usage")
    if not isinstance(usage_raw, Mapping):
        return {}
    return {
        key: value
        for key, value in usage_raw.items()
        if key in _SAFE_USAGE_FIELDS
        and isinstance(value, int)
        and not isinstance(value, bool)
        and 0 <= value <= _MAX_SAFE_USAGE_COUNTER
    }


@dataclass(frozen=True)
class OpenAICompatibleProviderConfig:
    """Non-secret configuration; ``api_key_env`` is a name, never a value."""

    base_url: str
    api_key_env: str
    model: str
    timeout_seconds: int = 20
    max_output_tokens: int = 512
    thinking_mode: str = "disabled"

    def validate(self) -> ValidationResult:
        errors: list[str] = []
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            errors.append("base_url must be an absolute HTTP(S) URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            errors.append("base_url must not contain credentials, query, or fragment")
        if not re.fullmatch(r"[A-Z_][A-Z0-9_]{0,127}", self.api_key_env or ""):
            errors.append("api_key_env must be an environment-variable name")
        if not isinstance(self.model, str) or not self.model.strip() or len(self.model) > 256:
            errors.append("model must be a non-empty bounded identifier")
        if not isinstance(self.timeout_seconds, int) or not 1 <= self.timeout_seconds <= 120:
            errors.append("timeout_seconds must be an integer between 1 and 120")
        if not isinstance(self.max_output_tokens, int) or not 1 <= self.max_output_tokens <= 4096:
            errors.append("max_output_tokens must be an integer between 1 and 4096")
        if self.thinking_mode != "disabled":
            errors.append("thinking_mode must be disabled in the bounded Phase 3 transport")
        return ValidationResult(valid=not errors, errors=errors)


class OpenAICompatibleProvider(Provider):
    """OpenAI-compatible HTTP adapter with no retries or execution authority."""

    provider_id = "openai_compatible"

    def __init__(self, config: OpenAICompatibleProviderConfig) -> None:
        self.config = config
        validation = config.validate()
        if not validation.valid:
            raise ValueError("invalid live provider configuration: " + "; ".join(validation.errors))
        # Read exactly the explicit reference.  Do not enumerate environment
        # variables and never include this value in an exception or response.
        self._api_key = os.environ.get(config.api_key_env)

    def list_models(self) -> List[Dict[str, Any]]:
        return [{"id": self.config.model, "provider": self.provider_id, "local": False}]

    def validate_configuration(self) -> ValidationResult:
        return self.config.validate()

    def get_capabilities(self) -> List[Capability]:
        return [Capability.TEXT_CHAT, Capability.TOOL_CALLING, Capability.STRUCTURED_OUTPUT]

    def chat(self, request: ChatRequest) -> ChatResponse:
        body, snapshot = self._request_payload(request)
        payload = self._post(body, snapshot)
        try:
            choice = payload["choices"][0]
            message = choice["message"]
            content = message.get("content") or ""
            if not isinstance(content, str):
                raise TypeError("content is not text")
            return ChatResponse(
                content=content,
                model_id=str(payload.get("model") or request.model_id or self.config.model),
                finish_reason=str(choice.get("finish_reason") or "stop"),
                usage=_safe_usage(payload),
                trace_id=request.trace_id,
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LiveProviderError(
                LiveProviderErrorCode.MALFORMED_RESPONSE,
                "provider response shape is invalid",
                safe_diagnostics=_empty_diagnostics(snapshot),
            ) from exc

    def stream_chat(self, request: ChatRequest) -> Iterator[StreamChunk]:
        raise LiveProviderError(LiveProviderErrorCode.INVALID_MODEL_OUTPUT, "streaming is not admitted in Phase 3")
        yield StreamChunk(delta="")  # pragma: no cover - keeps Iterator typing explicit

    def tool_call(self, request: ChatRequest) -> ToolCallResult:
        body, snapshot = self._request_payload(request)
        payload = self._post(body, snapshot)
        try:
            choice = payload["choices"][0]
            message = choice["message"]
            raw_calls = message.get("tool_calls") or []
            content = message.get("content") or ""
            if not isinstance(raw_calls, list) or not isinstance(content, str):
                raise TypeError("tool calls or content invalid")
            calls: list[dict[str, Any]] = []
            provider_function_names: list[str] = []
            internal_operation_names: list[str] = []
            for raw in raw_calls:
                function = raw.get("function") if isinstance(raw, dict) else None
                if not isinstance(function, dict) or not isinstance(function.get("name"), str):
                    raise TypeError("tool call function invalid")
                arguments = function.get("arguments")
                if not isinstance(arguments, str) or len(arguments.encode("utf-8")) > 16_384:
                    raise TypeError("tool arguments invalid")
                provider_name = function["name"]
                internal_name = _PROVIDER_TO_INTERNAL_TOOL_NAME.get(provider_name, provider_name)
                provider_function_names.append(self._safe_provider_function_name(provider_name))
                internal_operation_names.append(self._safe_internal_operation_name(internal_name))
                calls.append({
                    "id": str(raw.get("id") or ""),
                    "type": "function",
                    "function": {
                        "name": internal_name,
                        "arguments": arguments,
                    },
                })
            return ToolCallResult(
                tool_calls=calls,
                content=content,
                model_id=str(payload.get("model") or request.model_id or self.config.model),
                usage=_safe_usage(payload),
                request_contract_snapshot=snapshot,
                response_tool_call_metadata={
                    "response_tool_call_count": len(calls),
                    "response_provider_function_names": provider_function_names,
                    "response_internal_operation_names": internal_operation_names,
                },
                trace_id=request.trace_id,
            )
        except LiveProviderError:
            raise
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LiveProviderError(
                LiveProviderErrorCode.INVALID_MODEL_OUTPUT,
                "provider tool proposal is invalid",
                safe_diagnostics=_empty_diagnostics(snapshot),
            ) from exc

    def structured_output(self, request: ChatRequest, schema: Dict[str, Any]) -> StructuredOutputResult:
        response = self.chat(request)
        try:
            data = json.loads(response.content)
        except json.JSONDecodeError as exc:
            raise LiveProviderError(LiveProviderErrorCode.MALFORMED_RESPONSE, "provider did not return JSON") from exc
        if not isinstance(data, dict):
            raise LiveProviderError(LiveProviderErrorCode.INVALID_MODEL_OUTPUT, "provider JSON output must be an object")
        return StructuredOutputResult(data=data, model_id=response.model_id, trace_id=request.trace_id)

    def health_check(self) -> ProviderHealth:
        status = "ok" if self._api_key else "down"
        reason = "" if self._api_key else LiveProviderErrorCode.AUTHENTICATION_ERROR.value
        return ProviderHealth(
            component=self.provider_id,
            status=status,
            reason=reason,
            safe_details={"provider_id": self.provider_id, "model": self.config.model},
        )

    def _request_body(self, request: ChatRequest) -> bytes:
        """Return the bounded wire payload without exposing its contents."""

        return self._request_payload(request)[0]

    def _request_payload(self, request: ChatRequest) -> tuple[bytes, dict[str, object]]:
        safe_messages = self._serialize_messages(request.messages or [])
        body: dict[str, Any] = {
            "model": request.model_id or self.config.model,
            "messages": safe_messages,
            "max_tokens": min(request.max_tokens or self.config.max_output_tokens, self.config.max_output_tokens),
            "thinking": {"type": self.config.thinking_mode},
        }
        if request.temperature is not None:
            body["temperature"] = request.temperature
        serialized_tools, schema_fingerprints = self._serialize_tools(request.tools)
        if serialized_tools:
            body["tools"] = serialized_tools
        snapshot = self._safe_request_contract_snapshot(
            body, schema_fingerprints, [item["function"]["name"] for item in serialized_tools]
        )
        return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8"), snapshot

    def _serialize_messages(self, messages: object) -> list[dict[str, Any]]:
        if not isinstance(messages, list) or len(messages) > 32:
            raise LiveProviderError(LiveProviderErrorCode.INVALID_MODEL_OUTPUT, "message count exceeds bound")
        serialized: list[dict[str, Any]] = []
        pending_tool_call_ids: list[str] = []
        for item in messages:
            if not isinstance(item, dict):
                raise LiveProviderError(LiveProviderErrorCode.INVALID_MODEL_OUTPUT, "message is invalid")
            role, content = item.get("role"), item.get("content")
            if role not in {"system", "user", "assistant", "tool"} or not isinstance(content, str):
                raise LiveProviderError(LiveProviderErrorCode.INVALID_MODEL_OUTPUT, "message is invalid")
            if len(content.encode("utf-8")) > 16_384:
                raise LiveProviderError(LiveProviderErrorCode.INVALID_MODEL_OUTPUT, "message exceeds bound")
            if pending_tool_call_ids and role != "tool":
                raise LiveProviderError(
                    LiveProviderErrorCode.INVALID_MODEL_OUTPUT,
                    "assistant tool calls must all receive results before the next turn",
                )
            if role == "tool":
                call_id = item.get("tool_call_id")
                if (
                    not pending_tool_call_ids
                    or not isinstance(call_id, str)
                    or call_id != pending_tool_call_ids[0]
                ):
                    raise LiveProviderError(
                        LiveProviderErrorCode.INVALID_MODEL_OUTPUT,
                        "tool result identifier or order is invalid",
                    )
                serialized.append({"role": "tool", "tool_call_id": call_id, "content": content})
                pending_tool_call_ids.pop(0)
                continue
            if "tool_call_id" in item or (role != "assistant" and "tool_calls" in item):
                raise LiveProviderError(LiveProviderErrorCode.INVALID_MODEL_OUTPUT, "message fields are invalid")
            raw_tool_calls = item.get("tool_calls") if role == "assistant" else None
            if raw_tool_calls is not None:
                tool_calls = self._serialize_assistant_tool_calls(raw_tool_calls)
                pending_tool_call_ids = [call["id"] for call in tool_calls]
                serialized.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
            else:
                serialized.append({"role": role, "content": content})
        if pending_tool_call_ids:
            raise LiveProviderError(
                LiveProviderErrorCode.INVALID_MODEL_OUTPUT,
                "assistant tool calls are missing tool results",
            )
        return serialized

    def _serialize_assistant_tool_calls(self, raw_calls: object) -> list[dict[str, Any]]:
        if not isinstance(raw_calls, list) or not 1 <= len(raw_calls) <= 4:
            raise LiveProviderError(
                LiveProviderErrorCode.INVALID_MODEL_OUTPUT,
                "assistant tool-call history count is invalid",
            )
        serialized: list[dict[str, Any]] = []
        call_ids: set[str] = set()
        for raw in raw_calls:
            function = raw.get("function") if isinstance(raw, dict) else None
            call_id = raw.get("id") if isinstance(raw, dict) else None
            if (
                not isinstance(function, dict)
                or raw.get("type") != "function"
                or not isinstance(call_id, str)
                or not call_id
                or len(call_id.encode("utf-8")) > 128
                or call_id in call_ids
            ):
                raise LiveProviderError(LiveProviderErrorCode.INVALID_MODEL_OUTPUT, "assistant tool call is invalid")
            internal_name = function.get("name")
            arguments = function.get("arguments")
            if (
                not isinstance(internal_name, str)
                or internal_name not in _INTERNAL_TO_PROVIDER_TOOL_NAME
                or not isinstance(arguments, str)
                or len(arguments.encode("utf-8")) > 16_384
            ):
                raise LiveProviderError(LiveProviderErrorCode.INVALID_MODEL_OUTPUT, "assistant tool call is invalid")
            call_ids.add(call_id)
            serialized.append({
                "id": call_id,
                "type": "function",
                "function": {
                    "name": _INTERNAL_TO_PROVIDER_TOOL_NAME[internal_name],
                    "arguments": arguments,
                },
            })
        return serialized

    def _post(self, body: bytes, snapshot: Mapping[str, object]) -> Dict[str, Any]:
        if not self._api_key:
            raise LiveProviderError(
                LiveProviderErrorCode.AUTHENTICATION_ERROR,
                "named provider credential is unavailable",
                safe_diagnostics=_empty_diagnostics(snapshot),
            )
        endpoint = self.config.base_url.rstrip("/") + "/chat/completions"
        request = urlrequest.Request(
            endpoint,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self._api_key}"},
        )
        try:
            with urlrequest.urlopen(request, timeout=self.config.timeout_seconds) as response:
                raw = response.read(1_048_577)
                if len(raw) > 1_048_576:
                    raise LiveProviderError(
                        LiveProviderErrorCode.MALFORMED_RESPONSE,
                        "provider response exceeds bound",
                        safe_diagnostics=_empty_diagnostics(snapshot),
                    )
        except LiveProviderError:
            raise
        except urlerror.HTTPError as exc:
            if exc.code in {401, 403}:
                code = LiveProviderErrorCode.AUTHENTICATION_ERROR
            elif exc.code == 429:
                code = LiveProviderErrorCode.RATE_LIMITED
            else:
                code = LiveProviderErrorCode.PROVIDER_ERROR
            raise LiveProviderError(
                code,
                f"provider returned HTTP {exc.code}",
                safe_diagnostics=self._http_error_diagnostics(exc, snapshot),
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise LiveProviderError(
                LiveProviderErrorCode.TIMEOUT,
                "provider request timed out",
                safe_diagnostics=_empty_diagnostics(snapshot),
            ) from exc
        except (urlerror.URLError, OSError) as exc:
            raise LiveProviderError(
                LiveProviderErrorCode.TRANSPORT_ERROR,
                "provider transport failed",
                safe_diagnostics=_empty_diagnostics(snapshot),
            ) from exc
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LiveProviderError(
                LiveProviderErrorCode.MALFORMED_RESPONSE,
                "provider response is not JSON",
                safe_diagnostics=_empty_diagnostics(snapshot),
            ) from exc
        if not isinstance(payload, dict):
            raise LiveProviderError(
                LiveProviderErrorCode.MALFORMED_RESPONSE,
                "provider response must be an object",
                safe_diagnostics=_empty_diagnostics(snapshot),
            )
        return payload

    def _serialize_tools(self, tools: List[Dict[str, Any]] | None) -> tuple[list[dict[str, Any]], dict[str, str]]:
        if tools is None:
            return [], {}
        if not isinstance(tools, list) or len(tools) > 32:
            raise LiveProviderError(LiveProviderErrorCode.INVALID_MODEL_OUTPUT, "tool schema count is invalid")
        serialized: list[dict[str, Any]] = []
        fingerprints: dict[str, str] = {}
        for tool in tools:
            function = tool.get("function") if isinstance(tool, dict) else None
            if not isinstance(function, dict) or tool.get("type") != "function":
                raise LiveProviderError(LiveProviderErrorCode.INVALID_MODEL_OUTPUT, "tool schema is invalid")
            internal_name = function.get("name")
            description = function.get("description")
            parameters = function.get("parameters")
            if (
                not isinstance(internal_name, str)
                or internal_name not in _INTERNAL_TO_PROVIDER_TOOL_NAME
                or not isinstance(description, str)
                or not description.strip()
                or not isinstance(parameters, dict)
            ):
                raise LiveProviderError(LiveProviderErrorCode.INVALID_MODEL_OUTPUT, "tool schema is invalid")
            provider_name = _INTERNAL_TO_PROVIDER_TOOL_NAME[internal_name]
            serialized_function = dict(function)
            serialized_function["name"] = provider_name
            serialized.append({"type": "function", "function": serialized_function})
            canonical_schema = json.dumps(parameters, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            fingerprints[provider_name] = hashlib.sha256(canonical_schema.encode("utf-8")).hexdigest()
        return serialized, fingerprints

    def _safe_request_contract_snapshot(
        self,
        body: Mapping[str, Any],
        schema_fingerprints: Mapping[str, str],
        tool_names: list[str],
    ) -> dict[str, object]:
        base_path = urlparse(self.config.base_url).path.rstrip("/")
        endpoint_path = f"{base_path}/chat/completions" if base_path else "/chat/completions"
        strict_flags = [bool(tool["function"].get("strict", False)) for tool in body.get("tools", [])]
        return {
            "endpoint_path": endpoint_path,
            "model": str(body["model"]),
            "stream": False,
            "tool_count": len(tool_names),
            "tool_names": list(tool_names),
            "tool_choice": "NOT_SENT_PROVIDER_DEFAULT_AUTO" if tool_names else "NOT_SENT_PROVIDER_DEFAULT_NONE",
            "strict_mode": any(strict_flags),
            "strict_flags": strict_flags,
            "thinking_mode": self.config.thinking_mode,
            "reasoning_effort": "NOT_SENT",
            "max_output_tokens": int(body["max_tokens"]),
            "message_roles": [str(message["role"]) for message in body["messages"]],
            "json_schema_fingerprints": dict(schema_fingerprints),
        }

    def _http_error_diagnostics(
        self,
        exc: urlerror.HTTPError,
        snapshot: Mapping[str, object],
    ) -> dict[str, object]:
        diagnostics = _empty_diagnostics(snapshot)
        diagnostics["http_status"] = int(exc.code)
        diagnostics["provider_request_id_safe"] = self._safe_request_id(getattr(exc, "headers", None))
        try:
            raw = exc.read(_MAX_SAFE_ERROR_BODY_BYTES + 1)
        except OSError:
            diagnostics["provider_error_message_sanitized"] = "PROVIDER_ERROR_BODY_UNAVAILABLE"
            return diagnostics
        if len(raw) > _MAX_SAFE_ERROR_BODY_BYTES:
            diagnostics["provider_error_message_sanitized"] = "PROVIDER_ERROR_BODY_TOO_LARGE"
            return diagnostics
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            diagnostics["provider_error_message_sanitized"] = "PROVIDER_ERROR_BODY_NOT_JSON"
            return diagnostics
        error = payload.get("error") if isinstance(payload, dict) else None
        if not isinstance(error, dict):
            diagnostics["provider_error_message_sanitized"] = "PROVIDER_ERROR_BODY_UNRECOGNIZED"
            return diagnostics
        diagnostics["provider_error_type"] = self._safe_provider_token(error.get("type"))
        diagnostics["provider_error_code"] = self._safe_provider_token(error.get("code"))
        diagnostics["provider_error_message_sanitized"] = self._safe_provider_message(error.get("message"))
        return diagnostics

    def _safe_provider_message(self, value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            return "NOT_REPORTED"
        mapping = {self._api_key: "***"} if self._api_key else None
        redacted = redact_text(value, mapping)
        if re.search(r"(?i)\b(?:authorization|api[ _-]?key)\b", redacted):
            return "PROVIDER_ERROR_MESSAGE_REDACTED"
        normalized = " ".join(redacted.split())
        if len(normalized) > _MAX_SAFE_PROVIDER_MESSAGE:
            return normalized[:_MAX_SAFE_PROVIDER_MESSAGE]
        return normalized

    @staticmethod
    def _safe_provider_token(value: object) -> str:
        if not isinstance(value, str) or not _PROVIDER_TOKEN_RE.fullmatch(value):
            return "NOT_REPORTED"
        return value

    @staticmethod
    def _safe_request_id(headers: object) -> str:
        raw = headers.get("x-request-id") if hasattr(headers, "get") else None
        if not isinstance(raw, str) or not _PROVIDER_REQUEST_ID_RE.fullmatch(raw):
            return "NOT_REPORTED"
        return raw

    @staticmethod
    def _safe_provider_function_name(value: str) -> str:
        return value if _SAFE_PROVIDER_FUNCTION_NAME_RE.fullmatch(value) else "UNSAFE_NAME_REDACTED"

    @staticmethod
    def _safe_internal_operation_name(value: str) -> str:
        return value if _SAFE_INTERNAL_OPERATION_NAME_RE.fullmatch(value) else "UNSAFE_NAME_REDACTED"
