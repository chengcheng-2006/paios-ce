# Astron Phase 3: Live Provider Contract

## Scope

Phase 3 admits exactly one optional, OpenAI-compatible text provider. It is
an action-proposal component, not an executor, a verifier, an identity
authority, or a source of durable completion truth.

```text
LIVE_PROVIDER_DEFAULT=OFF
MODEL_MAY_EXECUTE_TOOL_DIRECTLY=NO
MODEL_MAY_MARK_TASK_COMPLETED=NO
```

The bundled deterministic mock remains the normal offline path. A successful
mock run is never evidence that a network provider was contacted.

## Configuration and secrets

The live configuration contains only these non-secret values:

| Field | Contract |
| --- | --- |
| `base_url` | absolute HTTP(S) provider endpoint, without a credential |
| `api_key_env` | exact environment-variable *name* holding the credential |
| `model` | non-empty provider model identifier |
| `timeout_seconds` | bounded HTTP request timeout |
| `max_output_tokens` | bounded requested/generated output size |
| `thinking_mode` | fixed `disabled` for this bounded multi-turn transport |

`api_key_env` is a reference, not a secret value. Astron reads only that
explicitly named variable when a live provider is constructed. It does not
enumerate the process environment, inspect shell history, inspect a keychain,
or load `.env` files. A literal key, authorization header, secret payload, or
`SecretValue` in this configuration is invalid.

The provider never writes a credential to SQLite, an evidence document, a
log, an exception message, an action request, an audit record, or a model
prompt. Stable error classes are supplemented only by bounded safe metadata:
an exact HTTP status when present, provider error type/code, a credential-
redacted message of at most 512 characters, and a syntactically safe request
ID. It never stores a raw response body or header.

## Request and response boundary

The implementation uses the OpenAI-compatible `/chat/completions` request
shape over an explicitly configured endpoint. Requests contain the selected
model, a bounded message list, a bounded `max_tokens`, explicit disabled
thinking, and the fixed function schemas used for Phase 3 action proposals.
The HTTP serializer converts Astron's internal dotted operation names to a
fixed reversible provider-safe form (for example, `workspace.read_text` to
`workspace_read_text`) and maps returned names back before the bounded runtime
sees them. It does not use automatic retry, streaming, background polling,
tool execution, browser automation, shell access, or fallback-provider
routing.

Every live request carries a content-free `safe_request_contract_snapshot` in
its success or failure result: endpoint path, model, stream mode, tool count
and names, tool choice mode, strict flags, thinking mode, output bound,
message-role sequence, and JSON Schema fingerprints. It deliberately excludes
message content, tool arguments, file content, raw request bytes, headers,
and credentials.

Only a syntactically valid function-call proposal is returned to the native
task loop. Natural-language content, provider metadata, and malformed
arguments have no execution authority. The loop independently validates the
operation and arguments, constructs its own `ActionRequest`, asks the
Permission Engine, writes the durable action journal, records
`ATTEMPT_STARTED`, and only then invokes its trusted bounded-tool executor.

## Agent read-batch / verified-artifact contract

```text
AGENT_CONTRACT_VERSION=AIC2026_READ_BATCH_VERIFIED_ARTIFACT_V4
TOOL_CHOICE=PROVIDER_DEFAULT_AUTO
STRICT_MODE=NO
THINKING_MODE=disabled
READ_ONLY_BATCH_ALLOWLIST=workspace.list_files,workspace.read_text
MAX_READ_ONLY_TOOL_CALLS_PER_TURN=4
PARALLEL_TOOL_EXECUTION=NO
SINGLE_MUTATING_ACTION_PER_TURN=YES
COMPLETION_ARTIFACT_CONTRACT_VISIBLE=YES
COMPLETION_ARTIFACT_SCHEMA_ID=maintenance_completion.v1
```

The production Agent instruction permits zero calls, one ordinary bounded
call, or two to four calls only when every operation is one of the two frozen
read-only operations above. Any multi-call response containing a write,
artifact, validation, test, unknown, or other operation is rejected in full
before any call executes. More than four calls is likewise rejected before
execution. A single mutating or testing call keeps the existing authorization,
journal, attempt, and execution path.

An admitted read batch is never a combined action and is never parallel. The
native Agent first validates the complete batch, then submits each read in the
provider's original order through the ordinary bounded runtime. Each actual
read receives its own `ActionRequest`, authorization decision, durable journal,
`ATTEMPT_STARTED`, and terminal result. The next provider turn is possible
only after one assistant tool-call message and an ordered, call-ID-bound tool
result for every admitted read have been formed.

This instruction is behavioral guidance, not a security boundary. Runtime
batch admission is the fail-closed enforcement point. It does not select a
safe-looking prefix, discard a mutating suffix, or implement parallel action
semantics. V4 retains every V3 admission rule and additionally exposes the
typed completion-artifact schema shared with the deterministic verifier. The
instruction contains no fixture solution, expected edit,
verifier oracle, raw argument, or workspace content.

The Agent receives the fixed artifact path, required key names, value types,
workspace-relative `changed_files` semantics, trusted current task ID, summary
bound, and extra-key policy. `validate.json` accepts only the trusted named
schema `maintenance_completion.v1`; no model-controlled schema path exists.
Syntax-only validation is explicitly distinguished from semantic validation,
and neither can mark the task complete without an independent verifier PASS.

For a successful provider response, the CLI may retain only bounded response
shape evidence: exact tool-call count, syntactically safe provider and internal
operation names, the V3 batch classification, and content-free artifact
contract/semantic-validation status. It never retains tool
arguments, message content, raw response payloads, headers, or credentials.
Names are capped in storage; a truncation flag distinguishes a complete
safe-name list from a bounded one.

## Stable failure taxonomy

| Error | Meaning | Retry by this phase |
| --- | --- | --- |
| `AUTHENTICATION_ERROR` | missing credential or provider rejected authentication | no automatic retry |
| `RATE_LIMITED` | provider returned a rate-limit response | no automatic retry |
| `TIMEOUT` | bounded request deadline elapsed | no automatic retry |
| `TRANSPORT_ERROR` | DNS/TLS/socket/connection failure | no automatic retry |
| `PROVIDER_ERROR` | other non-success provider response | no automatic retry |
| `MALFORMED_RESPONSE` | response was not valid expected JSON | no automatic retry |
| `INVALID_MODEL_OUTPUT` | response violates the bounded proposal or V3/V4 admission contract | no automatic retry |

The error class is a diagnostic fact, not proof that no provider-side work was
performed. In particular, a timeout is not silently retried with an assumed
idempotency property.

## Acceptance boundary

Live acceptance requires a deliberately named current-environment credential,
a minimal preflight request, and one fixed fresh-fixture maintenance task that
passes the deterministic verifier. The Owner-operated Attempt 6 launcher first
creates the fixture and proves its expected initial failure through the
existing `test.run_pytest_bounded` operation; it requests a credential only
after that baseline gate passes. If the named credential is absent or the
provider cannot be reached, implementation and offline tests may still pass,
but Phase 3 remains `BLOCKED_EXTERNAL_CREDENTIAL`; it is not a live-provider
PASS.
