# Support Matrix

This document records the supported Python versions and the support status of
each Astron competition-baseline component. It is the authoritative source for support claims;
no other documentation may overclaim support beyond what is listed here.

Astron is the current competition identity. The `paios_ce` import namespace and
`paios-ce` command remain explicit legacy compatibility surfaces; `astron` is
the primary CLI. Historical CI entries below retain their original PAIOS CE
source provenance and are not current macOS cross-platform validation.

## Python version support

| Python version | Status | Notes |
| --- | --- | --- |
| 3.11 | Declared supported; current competition runtime `NOT_RUN` | `requires-python` admits 3.11. Historical baseline remote CI exists, but the current AIC evidence revision has no reviewed local Windows or Ubuntu runtime receipt. |
| 3.12 | **Validated on macOS**; Windows/Ubuntu runtime `NOT_RUN` | Current local evidence: 452 passed + 1 filesystem-dependent skip, package/fresh-install/CLI PASS. Historical baseline remote CI is not current cross-platform certification. |
| 3.13 | Supplementary only | Validated opportunistically; not a release gate. |

The `requires-python` field in `pyproject.toml` is `>=3.11`.

## CI validation

The historical public baseline ran this GitHub Actions matrix on pushes to
`main`:

- 4 matrix jobs (Windows + Ubuntu × Python 3.11 + 3.12) × 299 tests,
  0 failures / 0 errors (1 symlink test is skipped on Windows
  where it requires elevation; it runs on Ubuntu).
- line coverage 87.83%, branch coverage 76.62% (gates: 86.2% / 66.7%).

The current competition evidence revision has not been pushed or merged to
`main`, so that historical matrix is provenance only:

```text
CURRENT_COMPETITION_REVISION_REMOTE_CI=NOT_RUN
CURRENT_COMPETITION_REVISION_WINDOWS_RUNTIME=NOT_RUN
CURRENT_COMPETITION_REVISION_UBUNTU_RUNTIME=NOT_RUN
```

## Capability support status

| Capability | Support status | Notes |
| --- | --- | --- |
| Mock Provider | EXPERIMENTAL | Fully local, deterministic, no network, no API key. |
| CLI | EXPERIMENTAL | Primary: `astron demo|maintenance-demo|health|validate-config|run-task|transcribe`; legacy alias: `paios-ce`. |
| Local file ASR | EXPERIMENTAL | `speech.transcribe_local`; disabled by default; optional faster-whisper adapter; real-model smoke passed (Windows, CPU int8, tiny model). See docs/LOCAL_ASR.md. |
| Speech (general) | EXPERIMENTAL | Only local file transcription is implemented; live speech/channel remains PLANNED. |
| OpenAI-compatible Live Provider | EXPERIMENTAL, credential-gated | Explicit base URL, named current-environment credential, bounded request/output, and no fallback. No real-provider acceptance is claimed without a supplied credential and verifier-PASS task. |
| Live Channel | PLANNED | Not implemented; channel skeletons only. |
| Hermes/OpenClaw | planned adapter/dependency boundary | No integration shipped; no dependency on either runtime. |

## Component support status

| Component | Support status | Notes |
| --- | --- | --- |
| `paios_ce.audit` | EXPERIMENTAL | Redaction invariant enforced at every entry point. |
| `paios_ce.permissions` | EXPERIMENTAL | Permission engine and policy module. |
| `paios_ce.secrets` | EXPERIMENTAL | SecretRef abstraction; never exposes raw values. |
| `paios_ce.protocols` | EXPERIMENTAL | Public protocol models (extra="forbid"). |
| `paios_ce.config` | EXPERIMENTAL | Public/private config loader with safe defaults. |
| `paios_ce.providers` | EXPERIMENTAL | Mock plus one explicit OpenAI-compatible proposal adapter; it cannot execute tools or mark task completion. |
| `paios_ce.workers` | Scaffold | Mock worker only. |
| `paios_ce.channels` | Scaffold | CLI and local-web channel skeletons. |
| `paios_ce.orchestrator` | Scaffold | Orchestrator skeleton. |
| `paios_ce.routing` | Scaffold | Router skeleton. |
| `paios_ce.health` | EXPERIMENTAL | Health check and diagnostics with redaction. |
| `paios_ce.demo` | EXPERIMENTAL | Demo task fixture. |
| `paios_ce.cli` | EXPERIMENTAL | `astron` primary entry point (including `transcribe`); `paios-ce` is a legacy alias. |
| `paios_ce.speech` | EXPERIMENTAL | Typed contracts, policy, adapter and service for local file ASR. |
| `paios_ce.tools` | EXPERIMENTAL | Schema helpers plus the finite Phase 3 workspace/validation/bounded-pytest tool surface. |
| `paios_ce.agent` | EXPERIMENTAL | Fixed-fixture native proposal loop and deterministic verifier only; not a general agent framework. |

## Out-of-scope items

- No provider other than the explicit OpenAI-compatible adapter is shipped.
  That adapter is default-off and its real acceptance remains
  credential-gated; `mock` is the default offline provider.
- No network egress occurs in the default mock/demo path. Live mode performs
  only the configured provider request and never falls back to another host.
- No raw audio storage, no remote execution, no group execution by default.
- This is a release candidate. Publication and release actions remain
  maintainer-controlled. No capability is labeled `production ready`, `stable`, or `fully
  supported`, and no live WeChat, live Feishu, production Hermes, or production
  OpenClaw support is claimed.

## Overclaim prevention

Documentation, README, and CHANGELOG entries must not assert support for
Python versions or components beyond what this matrix records. Any change to
support status must update this file first.
