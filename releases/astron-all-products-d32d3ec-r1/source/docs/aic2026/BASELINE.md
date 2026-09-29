# Astron AIC 2026 Baseline

## Frozen source

| Field | Recorded value |
| --- | --- |
| Source repository | `https://github.com/chengcheng-2006/paios-ce` |
| Source-project name | PAIOS CE |
| Competition-project name | Astron |
| Base commit | `c0a60b2cecabd43634992d1b0871881087619d82` |
| Base tree | `0e82a6d026ea029e28c570d05f7754d484f6c17e` |
| Historical tag at base | `v0.1.0-rc.2` |
| Baseline date (commit) | 2026-08-09T11:20:18+08:00 |
| Competition branch | `aic/2026-ai-opensource` |

The clone was independently created from the listed public remote, verified at
the exact commit before any competition file was changed, and then used to
create the competition branch. Historical Git provenance is not renamed.

## macOS environment

| Field | Recorded value |
| --- | --- |
| Primary execution platform | macOS |
| macOS | 15.7.7 (24G720) |
| Architecture | arm64 |
| System `python3` | 3.9.6 (unsupported by the project) |
| Test interpreter | isolated Python 3.12.14 venv |
| Project requirement | Python `>=3.11` |

The disposable test venv was created outside the clone using the supplied
Python 3.12 runtime. It was installed with the repository's documented
`pip install -e ".[dev]"` command. No private PAIOS/Harness checkout, model,
credential, or Windows machine was used.

## Unmodified-baseline evidence

All commands below ran while `HEAD` was the base commit and the clone was
clean. Full command records and sanitized output summaries were retained in the
internal `docs/aic2026/evidence/` tree, which is not part of this source snapshot.

| Gate | Result |
| --- | --- |
| Editable dev install | PASS |
| Test collection | 299 tests collected |
| `python -m pytest -ra -q` | PASS: 298 passed, 1 filesystem skip |
| Coverage command | PASS: 86% total coverage on macOS/Python 3.12.14 |
| CLI health, demo, config, task fixture | PASS |
| Import smoke | PASS: `paios_ce==0.1.0rc2` |
| Schema validation | PASS: 9 schemas; phase-2 external-contract check skipped by design |
| Wheel build and fresh-install smoke | PASS |
| Local secret/forbidden-content scan | PASS |
| Actual local ASR-model execution | NOT_RUN: optional dependency/model cache intentionally absent |

The only test skip was `tests/unit/test_speech_policy.py:117`, where junction
creation is unsupported on this macOS filesystem. It is an environment-specific
skip, not a passing Windows or Ubuntu claim.

## Capability inventory

The labels below use the competition rule: **SUPPORTED** requires a real
implementation plus executable evidence in this baseline; **SCAFFOLD** means
that an interface, mock, skeleton, or incomplete durability boundary exists;
**PLANNED** means no current implementation.

| Capability | Classification | Evidence and boundary |
| --- | --- | --- |
| Typed task/action contracts | SUPPORTED | Pydantic models, JSON Schema validation, unit/integration suite |
| Permission and risk engine | SUPPORTED | Deny-by-default, scope, risk, and hard-block tests plus CLI demo |
| Deny-by-default unknown-action handling | SUPPORTED | Security tests and explicit `E_UNKNOWN_ACTION` behavior |
| SecretRef | SUPPORTED | Public abstractions and redaction/security tests |
| Audit and redaction | SUPPORTED | Redaction invariants, CLI health/demo, and security suite |
| CLI and deterministic local text demo | SUPPORTED | `health`, `demo`, `validate-config`, and `run-task` smoke evidence |
| JSON Schema tooling | SUPPORTED | 9 generated-schema validation round trips |
| Deterministic Mock Provider path | SUPPORTED | Offline test coverage and demo evidence; never a live provider claim |
| SQLite state | SCAFFOLD | `SQLiteStateAdapterSkeleton` only; it never opens a database |
| Action Journal | PLANNED | No implementation exists |
| Checkpoint/recovery | PLANNED | No implementation exists |
| Idempotency/replay | SCAFFOLD | In-memory cache/replay code exists but has confirmed Phase-0 semantic defects |
| Provider abstraction | SCAFFOLD | Mock implementation and live-provider skeletons only |
| Live Provider | PLANNED | No live integration or credential evidence |
| Worker abstraction | SCAFFOLD | Mock worker only; no bounded real developer tools |
| Orchestrator and router | SCAFFOLD | Minimal mock-only path; not a general runtime |
| Verified completion | PLANNED | No artifact verifier or completion acceptance exists |
| Bounded developer tools | PLANNED | No real bounded developer-tool implementation exists |
| Local-file ASR | SCAFFOLD | Typed optional adapter and deterministic tests exist; no real model ran on this Mac |
| CI platform validation | SCAFFOLD | Workflows exist, but current Windows/Ubuntu execution is NOT_RUN |
| Packaging | SUPPORTED (wheel smoke) | Local wheel build plus fresh-install `health`/`--help`; no publication occurred |

## Known baseline conditions

- `ActionRequest` has no principal field or request-fingerprint field.
- The in-memory idempotency cache can convert a cached `BLOCKED` decision to
  `ALLOW` on retry and accepts a same-key request with changed parameters. The
  deterministic evidence was retained in the internal `docs/aic2026/evidence/`
  tree, which is not part of this source snapshot, and no Phase 0 fix was made there.
- The source tree's current package/import namespace is `paios_ce`. Astron
  uses it as a documented legacy internal compatibility namespace during this
  competition phase.
- No Windows or Ubuntu runtime was executed locally.
