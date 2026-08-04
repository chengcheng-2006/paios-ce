# Support Matrix

This document records the supported Python versions and the support status of
each PAIOS CE component. It is the authoritative source for support claims;
no other documentation may overclaim support beyond what is listed here.

## Python version support

| Python version | Status | Notes |
| --- | --- | --- |
| 3.11 | **Validated** (Windows + Ubuntu) | Reference runtime for the public tree. All 203 tests pass and coverage gates are met on Windows and Ubuntu (remote CI matrix). |
| 3.12 | **Validated** (Windows + Ubuntu) | Validated on Windows and Ubuntu in remote CI: 203 tests pass, coverage gates met, CLI and package build PASS. |
| 3.13 | Supplementary only | Validated opportunistically; not a release gate. |

The `requires-python` field in `pyproject.toml` is `>=3.11`.

## CI validation

Remote CI runs on GitHub Actions for every push to `main`:

- 4 matrix jobs (Windows + Ubuntu × Python 3.11 + 3.12) × 203 tests,
  0 failures / 0 errors / 0 skipped.
- line coverage 86.39%, branch coverage 73.50% (gates: 86.2% / 66.7%).

## Capability support status

| Capability | Support status | Notes |
| --- | --- | --- |
| Mock Provider | EXPERIMENTAL | Fully local, deterministic, no network, no API key. |
| CLI | EXPERIMENTAL | `paios-ce demo|health|validate-config|run-task`. |
| Live Provider | PLANNED | Not implemented; contract skeletons only. |
| Live Channel | PLANNED | Not implemented; channel skeletons only. |
| Speech | PLANNED | Not implemented. |
| Hermes/OpenClaw | planned adapter/dependency boundary | No integration shipped; no dependency on either runtime. |

## Component support status

| Component | Support status | Notes |
| --- | --- | --- |
| `paios_ce.audit` | EXPERIMENTAL | Redaction invariant enforced at every entry point. |
| `paios_ce.permissions` | EXPERIMENTAL | Permission engine and policy module. |
| `paios_ce.secrets` | EXPERIMENTAL | SecretRef abstraction; never exposes raw values. |
| `paios_ce.protocols` | EXPERIMENTAL | Public protocol models (extra="forbid"). |
| `paios_ce.config` | EXPERIMENTAL | Public/private config loader with safe defaults. |
| `paios_ce.providers` | Scaffold | Mock provider and provider skeletons only. |
| `paios_ce.workers` | Scaffold | Mock worker only. |
| `paios_ce.channels` | Scaffold | CLI and local-web channel skeletons. |
| `paios_ce.orchestrator` | Scaffold | Orchestrator skeleton. |
| `paios_ce.routing` | Scaffold | Router skeleton. |
| `paios_ce.health` | EXPERIMENTAL | Health check and diagnostics with redaction. |
| `paios_ce.demo` | EXPERIMENTAL | Demo task fixture. |
| `paios_ce.cli` | EXPERIMENTAL | `paios-ce` entry point. |
| `paios_ce.tools` | EXPERIMENTAL | Schema generation and validation helpers. |

## Out-of-scope items

- No production provider integration is shipped or supported.
- No network egress is performed by the scaffold; the `mock` provider is the
  default and only bundled provider.
- No raw audio storage, no remote execution, no group execution by default.
- This is a release candidate; the repository is currently private and publication
  is Owner-gated. No capability is labeled `production ready`, `stable`, or `fully
  supported`, and no live WeChat, live Feishu, production Hermes, or production
  OpenClaw support is claimed.

## Overclaim prevention

Documentation, README, and CHANGELOG entries must not assert support for
Python versions or components beyond what this matrix records. Any change to
support status must update this file first.
