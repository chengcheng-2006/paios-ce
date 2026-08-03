# PAIOS CE

PAIOS CE is a clean-room public core scaffold for a privacy-preserving personal AI
orchestrator. It implements the public skeleton, interface contracts, and a minimal
local demo closed loop from scratch, in full compliance with the frozen architecture.

> **Status:** This is a **local pre-release candidate** (not yet published).
> No Provider, Channel, or Speech capability is labeled SUPPORTED. The Mock Provider and
> CLI are `EXPERIMENTAL`. Linux remote CI remains pending.

## Highlights

- **Config Loader** — PublicConfig / PrivateConfig / RuntimeConfig with strict precedence:
  CLI flags → process environment → private local config → public project config →
  built-in safe defaults.
- **SecretRef** — reference-only secret indirection. `EnvSecretRef` (portable default) and
  `InMemorySecretRef` (tests/demo). Values are never stored in config, never logged, never
  serialized, never placed in TaskEnvelope or AuditEvent.
- **Permission / Risk Engine** — deny-by-default, capability allowlist, filesystem/network
  scope, HIGH-risk confirmation, CRITICAL/ADMIN/shell hard blocks, idempotency + replay
  detection.
- **Task / Action Protocol** — pydantic models for TaskEnvelope, ActionRequest,
  ApprovalRequest, ActionResult, TaskResult, ErrorEnvelope, AuditEvent, validated against
  generated JSON Schemas.
- **Mock Provider** — fully local, deterministic, no network, no API key. Supports chat,
  streaming, tool calls, structured output, failure and latency simulation.
- **CLI Channel** — `paios-ce demo|health|validate-config|run-task`.
- **Minimal Router + Orchestrator** — routes only to Mock Provider in the current candidate.
- **Redacted Audit Logger** — JSONL structured audit with mandatory redaction.
- **Health / Diagnostics** — safe component status with no secrets, no full env, no private
  paths.

## Install (local development)

Requires Python >= 3.11.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# POSIX:
# source .venv/bin/activate
pip install -e ".[dev]"
```

## Quick demo

```bash
paios-ce demo
paios-ce health
paios-ce validate-config
paios-ce run-task examples/demo_task.json
```

`paios-ce demo` runs the full closed loop: user input → TaskEnvelope → Risk evaluation →
Mock Provider → Mock Worker (optional) → TaskResult → redacted audit event. It requires no
network, no API key, and no real secret.

## Layout

```
paios_ce/
  config/        PublicConfig / PrivateConfig / RuntimeConfig + loader
  secrets/       SecretRef interface, EnvSecretRef, InMemorySecretRef
  protocols/     TaskEnvelope / ActionRequest / ... / AuditEvent models + schemas
  permissions/   Permission / Risk engine
  providers/     Provider contract + MockProvider
  channels/      Channel contract + CLI channel
  routing/       Minimal router
  workers/       Worker contract + MockWorker
  audit/         Redacted audit logger + redaction helpers
  health/        health_check / diagnostics
  cli/           paios-ce command line
  demo/          Demo workflow
```

## License

Apache-2.0. Copyright 2026 Cheng Cheng. See LICENSE, NOTICE, THIRD_PARTY_NOTICES.md.
