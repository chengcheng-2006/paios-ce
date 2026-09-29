"""Offline unit tests for the Phase 3 OpenAI-compatible adapter."""

from __future__ import annotations

import io
import json
from urllib.error import HTTPError
from urllib.error import URLError

import pytest

from paios_ce.providers import (
    ChatRequest,
    LiveProviderError,
    LiveProviderErrorCode,
    OpenAICompatibleProvider,
    OpenAICompatibleProviderConfig,
)


def _config() -> OpenAICompatibleProviderConfig:
    return OpenAICompatibleProviderConfig(
        base_url="https://provider.example/v1",
        api_key_env="ASTRON_PHASE3_TEST_KEY",
        model="maintenance-model",
        timeout_seconds=5,
        max_output_tokens=128,
    )


def test_configuration_is_non_secret_and_missing_named_credential_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ASTRON_PHASE3_TEST_KEY", raising=False)
    provider = OpenAICompatibleProvider(_config())
    assert provider.validate_configuration().valid is True
    assert provider.health_check().reason == "AUTHENTICATION_ERROR"
    with pytest.raises(LiveProviderError) as exc:
        provider.chat(ChatRequest(messages=[{"role": "user", "content": "hello"}]))
    assert exc.value.code is LiveProviderErrorCode.AUTHENTICATION_ERROR


def test_configuration_rejects_credential_bearing_url_and_invalid_env_name() -> None:
    config = OpenAICompatibleProviderConfig(
        base_url="https://secret@provider.example/v1?token=forbidden",
        api_key_env="not-valid",
        model="model",
    )
    validation = config.validate()
    assert validation.valid is False
    assert len(validation.errors) >= 2


def test_tool_call_parses_one_openai_compatible_response_without_executing_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ASTRON_PHASE3_TEST_KEY", "never-echo-this")

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, limit: int) -> bytes:
            return json.dumps({
                "model": "maintenance-model",
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 7,
                    "total_tokens": 18,
                    "prompt_cache_hit_tokens": 3,
                    "cached_tokens": True,
                    "prompt_cache_miss_tokens": -1,
                    "untrusted_field": "must-not-be-retained",
                },
                "choices": [{"message": {"content": "", "tool_calls": [{
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "workspace.read_text", "arguments": "{\"path\": \"maintenance_config.py\"}"},
                }]}}],
            }).encode("utf-8")

    monkeypatch.setattr("paios_ce.providers.openai_compatible.urlrequest.urlopen", lambda request, timeout: _Response())
    result = OpenAICompatibleProvider(_config()).tool_call(
        ChatRequest(messages=[{"role": "user", "content": "propose one action"}], tools=[])
    )
    assert result.tool_calls[0]["function"]["name"] == "workspace.read_text"
    assert result.usage == {
        "prompt_tokens": 11,
        "completion_tokens": 7,
        "total_tokens": 18,
        "prompt_cache_hit_tokens": 3,
    }
    assert "never-echo-this" not in repr(result)
    assert "untrusted_field" not in repr(result)


@pytest.mark.parametrize(
    ("http_status", "expected"),
    [
        (401, LiveProviderErrorCode.AUTHENTICATION_ERROR),
        (403, LiveProviderErrorCode.AUTHENTICATION_ERROR),
        (429, LiveProviderErrorCode.RATE_LIMITED),
        (500, LiveProviderErrorCode.PROVIDER_ERROR),
    ],
)
def test_http_failure_taxonomy_is_stable_and_redacted(
    monkeypatch: pytest.MonkeyPatch, http_status: int, expected: LiveProviderErrorCode
) -> None:
    monkeypatch.setenv("ASTRON_PHASE3_TEST_KEY", "never-echo-this")

    def fail(request, timeout):
        raise HTTPError("https://provider.example/v1/chat/completions", http_status, "ignored", {}, None)

    monkeypatch.setattr("paios_ce.providers.openai_compatible.urlrequest.urlopen", fail)
    with pytest.raises(LiveProviderError) as exc:
        OpenAICompatibleProvider(_config()).chat(ChatRequest(messages=[{"role": "user", "content": "hello"}]))
    assert exc.value.code is expected
    assert "never-echo-this" not in str(exc.value)


def test_malformed_provider_response_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASTRON_PHASE3_TEST_KEY", "never-echo-this")

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, limit: int) -> bytes:
            return b"not-json"

    monkeypatch.setattr("paios_ce.providers.openai_compatible.urlrequest.urlopen", lambda request, timeout: _Response())
    with pytest.raises(LiveProviderError) as exc:
        OpenAICompatibleProvider(_config()).chat(ChatRequest(messages=[{"role": "user", "content": "hello"}]))
    assert exc.value.code is LiveProviderErrorCode.MALFORMED_RESPONSE


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (TimeoutError("timeout"), LiveProviderErrorCode.TIMEOUT),
        (URLError("offline"), LiveProviderErrorCode.TRANSPORT_ERROR),
    ],
)
def test_timeout_and_transport_taxonomy(
    monkeypatch: pytest.MonkeyPatch, failure: Exception, expected: LiveProviderErrorCode
) -> None:
    monkeypatch.setenv("ASTRON_PHASE3_TEST_KEY", "never-echo-this")

    def fail(request, timeout):
        raise failure

    monkeypatch.setattr("paios_ce.providers.openai_compatible.urlrequest.urlopen", fail)
    with pytest.raises(LiveProviderError) as exc:
        OpenAICompatibleProvider(_config()).chat(ChatRequest(messages=[{"role": "user", "content": "hello"}]))
    assert exc.value.code is expected


def test_invalid_tool_output_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASTRON_PHASE3_TEST_KEY", "never-echo-this")

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, limit: int) -> bytes:
            return b'{"choices":[{"message":{"tool_calls":[{"function":{"name":42,"arguments":"{}"}}]}}]}'

    monkeypatch.setattr("paios_ce.providers.openai_compatible.urlrequest.urlopen", lambda request, timeout: _Response())
    with pytest.raises(LiveProviderError) as exc:
        OpenAICompatibleProvider(_config()).tool_call(ChatRequest(messages=[{"role": "user", "content": "hello"}]))
    assert exc.value.code is LiveProviderErrorCode.INVALID_MODEL_OUTPUT


def test_tool_request_serializes_provider_safe_names_and_restores_internal_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ASTRON_PHASE3_TEST_KEY", "never-echo-this")
    captured: dict[str, object] = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, limit: int) -> bytes:
            return json.dumps({
                "model": "maintenance-model",
                "choices": [{"message": {"content": "", "tool_calls": [{
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "workspace_read_text", "arguments": "{\"path\": \"maintenance_config.py\"}"},
                }]}}],
            }).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _Response()

    monkeypatch.setattr("paios_ce.providers.openai_compatible.urlrequest.urlopen", fake_urlopen)
    result = OpenAICompatibleProvider(_config()).tool_call(ChatRequest(
        messages=[{"role": "system", "content": "bounded task"}],
        tools=[{
            "type": "function",
            "function": {
                "name": "workspace.read_text",
                "description": "Read a trusted workspace text file.",
                "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
            },
        }],
    ))
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["tools"][0]["function"]["name"] == "workspace_read_text"
    assert body["thinking"] == {"type": "disabled"}
    assert result.tool_calls[0]["function"]["name"] == "workspace.read_text"
    assert result.request_contract_snapshot["tool_names"] == ["workspace_read_text"]
    assert result.request_contract_snapshot["strict_mode"] is False
    assert result.request_contract_snapshot["tool_choice"] == "NOT_SENT_PROVIDER_DEFAULT_AUTO"
    assert result.request_contract_snapshot["thinking_mode"] == "disabled"


def test_tool_call_records_only_safe_cardinality_and_name_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ASTRON_PHASE3_TEST_KEY", "never-echo-this")

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, limit: int) -> bytes:
            return json.dumps({
                "model": "maintenance-model",
                "choices": [{"message": {"content": "", "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "workspace_read_text",
                            "arguments": "{\"path\": \"maintenance_config.py\"}",
                        },
                    },
                    {
                        "id": "call-2",
                        "type": "function",
                        "function": {
                            "name": "validate_file",
                            "arguments": "{\"path\": \"maintenance_config.py\"}",
                        },
                    },
                ]}}],
            }).encode("utf-8")

    monkeypatch.setattr(
        "paios_ce.providers.openai_compatible.urlrequest.urlopen",
        lambda request, timeout: _Response(),
    )
    result = OpenAICompatibleProvider(_config()).tool_call(
        ChatRequest(messages=[{"role": "user", "content": "propose one action"}], tools=[])
    )

    assert result.response_tool_call_metadata == {
        "response_tool_call_count": 2,
        "response_provider_function_names": ["workspace_read_text", "validate_file"],
        "response_internal_operation_names": ["workspace.read_text", "validate.file"],
    }
    assert "maintenance_config.py" not in repr(result.response_tool_call_metadata)


def test_tool_result_roundtrip_serializes_provider_safe_names_and_call_id_pairing() -> None:
    provider = OpenAICompatibleProvider(_config())
    calls = [
        {
            "id": "roundtrip-a",
            "type": "function",
            "function": {"name": "workspace.read_text", "arguments": "{\"path\":\"README.md\"}"},
        },
        {
            "id": "roundtrip-b",
            "type": "function",
            "function": {"name": "workspace.list_files", "arguments": "{\"path\":\".\"}"},
        },
    ]
    body, snapshot = provider._request_payload(ChatRequest(messages=[
        {"role": "system", "content": "bounded"},
        {"role": "assistant", "content": "", "tool_calls": calls},
        {"role": "tool", "tool_call_id": "roundtrip-a", "content": "{\"status\":\"success\"}"},
        {"role": "tool", "tool_call_id": "roundtrip-b", "content": "{\"status\":\"success\"}"},
    ]))
    payload = json.loads(body.decode("utf-8"))
    assistant = payload["messages"][1]
    assert [call["function"]["name"] for call in assistant["tool_calls"]] == [
        "workspace_read_text", "workspace_list_files",
    ]
    assert [message["tool_call_id"] for message in payload["messages"][2:]] == [
        "roundtrip-a", "roundtrip-b",
    ]
    assert snapshot["message_roles"] == ["system", "assistant", "tool", "tool"]


def test_tool_result_roundtrip_rejects_unresolved_assistant_tool_calls() -> None:
    provider = OpenAICompatibleProvider(_config())
    with pytest.raises(LiveProviderError) as exc:
        provider._request_payload(ChatRequest(messages=[
            {"role": "assistant", "content": "", "tool_calls": [
                {
                    "id": "roundtrip-a",
                    "type": "function",
                    "function": {"name": "workspace.read_text", "arguments": "{}"},
                },
                {
                    "id": "roundtrip-b",
                    "type": "function",
                    "function": {"name": "workspace.read_text", "arguments": "{}"},
                },
            ]},
            {"role": "tool", "tool_call_id": "roundtrip-a", "content": "{}"},
        ]))
    assert exc.value.code is LiveProviderErrorCode.INVALID_MODEL_OUTPUT


@pytest.mark.parametrize(
    "messages",
    [
        "not-a-list",
        [42],
        [{"role": "invalid", "content": ""}],
        [{"role": "user", "content": "x" * 16_385}],
        [{"role": "tool", "tool_call_id": "orphan", "content": "{}"}],
        [{"role": "user", "content": "", "tool_calls": []}],
        [{"role": "assistant", "content": "", "tool_calls": []}],
        [{"role": "assistant", "content": "", "tool_calls": [{}]}],
        [{"role": "assistant", "content": "", "tool_calls": [{
            "id": "unknown",
            "type": "function",
            "function": {"name": "unknown_tool", "arguments": "{}"},
        }]}],
        [
            {"role": "assistant", "content": "", "tool_calls": [{
                "id": "pending",
                "type": "function",
                "function": {"name": "workspace.read_text", "arguments": "{}"},
            }]},
            {"role": "user", "content": "too early"},
        ],
        [
            {"role": "assistant", "content": "", "tool_calls": [
                {
                    "id": "first",
                    "type": "function",
                    "function": {"name": "workspace.read_text", "arguments": "{}"},
                },
                {
                    "id": "second",
                    "type": "function",
                    "function": {"name": "workspace.read_text", "arguments": "{}"},
                },
            ]},
            {"role": "tool", "tool_call_id": "second", "content": "{}"},
        ],
    ],
)
def test_tool_result_roundtrip_rejects_invalid_or_ambiguous_message_protocol(messages) -> None:
    provider = OpenAICompatibleProvider(_config())
    with pytest.raises(LiveProviderError) as exc:
        provider._request_payload(ChatRequest(messages=messages))  # type: ignore[arg-type]
    assert exc.value.code is LiveProviderErrorCode.INVALID_MODEL_OUTPUT


@pytest.mark.parametrize("http_status", [400, 402, 418, 422, 500, 503, 599])
def test_http_error_metadata_is_safe_bounded_and_preserves_status(
    monkeypatch: pytest.MonkeyPatch, http_status: int
) -> None:
    monkeypatch.setenv("ASTRON_PHASE3_TEST_KEY", "never-echo-this")
    body = json.dumps({"error": {
        "type": "invalid_request_error",
        "code": "bad_tool_schema",
        "message": "provider rejected never-echo-this",
    }}).encode("utf-8")

    def fail(request, timeout):
        raise HTTPError(
            "https://provider.example/v1/chat/completions", http_status, "ignored",
            {"x-request-id": "req-safe-123"}, io.BytesIO(body),
        )

    monkeypatch.setattr("paios_ce.providers.openai_compatible.urlrequest.urlopen", fail)
    with pytest.raises(LiveProviderError) as exc:
        OpenAICompatibleProvider(_config()).tool_call(ChatRequest(
            messages=[{"role": "user", "content": "hello"}], tools=[]
        ))
    assert exc.value.code is LiveProviderErrorCode.PROVIDER_ERROR
    diagnostics = exc.value.safe_diagnostics
    assert diagnostics["http_status"] == http_status
    assert diagnostics["provider_error_type"] == "invalid_request_error"
    assert diagnostics["provider_error_code"] == "bad_tool_schema"
    assert diagnostics["provider_request_id_safe"] == "req-safe-123"
    assert len(diagnostics["provider_error_message_sanitized"]) <= 512
    assert "never-echo-this" not in diagnostics["provider_error_message_sanitized"]
    assert "Authorization" not in diagnostics
    assert diagnostics["request_contract_snapshot"]["endpoint_path"] == "/v1/chat/completions"


def test_final_http_tool_serializer_audit_is_structural_and_content_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the exact final serializer without issuing a network request."""

    from paios_ce.agent.native import _TOOL_SCHEMAS

    monkeypatch.setenv("ASTRON_PHASE3_TEST_KEY", "never-echo-this")
    provider = OpenAICompatibleProvider(_config())
    body, snapshot = provider._request_payload(ChatRequest(
        messages=[
            {"role": "system", "content": "prompt content must never enter the snapshot"},
            {"role": "user", "content": "fixture detail must never enter the snapshot"},
        ],
        tools=_TOOL_SCHEMAS,
    ))
    payload = json.loads(body.decode("utf-8"))
    functions = [item["function"] for item in payload["tools"]]
    assert payload["thinking"] == {"type": "disabled"}
    assert [function["name"] for function in functions] == [
        "workspace_list_files", "workspace_read_text", "workspace_patch_text",
        "workspace_write_artifact", "validate_json", "validate_file",
        "test_run_pytest_bounded",
    ]
    for function in functions:
        assert function["name"].replace("_", "").isalnum()
        assert isinstance(function["description"], str) and function["description"]
        assert isinstance(function["parameters"], dict)
        assert function.get("strict", False) is False
    assert snapshot["tool_count"] == 7
    assert snapshot["tool_choice"] == "NOT_SENT_PROVIDER_DEFAULT_AUTO"
    assert snapshot["strict_mode"] is False
    assert snapshot["thinking_mode"] == "disabled"
    assert len(snapshot["json_schema_fingerprints"]) == 7
    assert "prompt content" not in repr(snapshot)
    assert "fixture detail" not in repr(snapshot)
    assert "never-echo-this" not in repr(snapshot)


@pytest.mark.parametrize(
    ("body", "expected_message"),
    [
        (b"not-json", "PROVIDER_ERROR_BODY_NOT_JSON"),
        (b"x" * 2048, "PROVIDER_ERROR_BODY_TOO_LARGE"),
    ],
)
def test_http_error_non_json_and_oversized_bodies_are_not_persisted(
    monkeypatch: pytest.MonkeyPatch, body: bytes, expected_message: str
) -> None:
    monkeypatch.setenv("ASTRON_PHASE3_TEST_KEY", "never-echo-this")

    def fail(request, timeout):
        raise HTTPError(
            "https://provider.example/v1/chat/completions", 400, "ignored", {}, io.BytesIO(body)
        )

    monkeypatch.setattr("paios_ce.providers.openai_compatible.urlrequest.urlopen", fail)
    with pytest.raises(LiveProviderError) as exc:
        OpenAICompatibleProvider(_config()).chat(ChatRequest(messages=[{"role": "user", "content": "hello"}]))
    diagnostics = exc.value.safe_diagnostics
    assert diagnostics["http_status"] == 400
    assert diagnostics["provider_error_message_sanitized"] == expected_message


def test_http_error_message_is_truncated_to_the_fixed_safe_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ASTRON_PHASE3_TEST_KEY", "never-echo-this")
    body = json.dumps({"error": {
        "type": "invalid_request_error",
        "code": "bad_tool_schema",
        "message": "x" * 700,
    }}).encode("utf-8")

    def fail(request, timeout):
        raise HTTPError(
            "https://provider.example/v1/chat/completions", 422, "ignored", {}, io.BytesIO(body)
        )

    monkeypatch.setattr("paios_ce.providers.openai_compatible.urlrequest.urlopen", fail)
    with pytest.raises(LiveProviderError) as exc:
        OpenAICompatibleProvider(_config()).chat(ChatRequest(messages=[{"role": "user", "content": "hello"}]))
    assert len(exc.value.safe_diagnostics["provider_error_message_sanitized"]) == 512
