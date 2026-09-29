# Astron AIC 2026 Contribution Boundary

## Baseline before the competition branch

The public PAIOS CE source baseline is
`chengcheng-2006/paios-ce` at
`c0a60b2cecabd43634992d1b0871881087619d82`. The following are inherited,
pre-competition capabilities or materials, not Astron competition claims:

- typed protocols and JSON Schemas;
- deny-by-default permission/risk behavior;
- SecretRef, redacted audit, configuration, CLI, and deterministic mock demo;
- mock/skeleton provider, worker, router, orchestrator, and state interfaces;
- optional local-file ASR source; and
- historical PAIOS CE commits, tags, release metadata, URLs, and assets.

## Additions on the Astron competition branch

Phase 0 added only competition-governance and identity work:

- the Astron user-visible distribution and primary CLI identity;
- `docs/aic2026/` scope, baseline, boundary, and evidence records;
- a documented strict-xfail regression proving the confirmed idempotency/replay
  defect; and
- a current [`Astron social-preview SVG`](../assets/brand/astron-social-preview.svg)
  derived from the editable baseline layout.

Phase 1 adds only authorization-contract closure:

- a runtime-side trusted principal context, separate from `ActionRequest`;
- canonical SHA-256 request and current-security-context fingerprints;
- complete, process-local authorization replay records that preserve the
  original decision; and
- strict regression coverage for replay, principal spoofing, canonicalization,
  SecretRef safety, malformed records, and concurrent first authorization.

Phase 1 does not add durable SQLite state, an action journal, checkpoint or
restart recovery, live provider, bounded developer tool, artifact verifier,
benchmark, desktop application, or competition demo. In particular, its replay
records are in-memory authorization records, not durable execution evidence.

Phase 2 adds only durable local runtime/recovery closure:

- a versioned standard-library SQLite state authority with fail-closed schema,
  corruption, timeout, and permission behavior;
- durable authorization replay bound to the Phase 1 canonical identity;
- an append-oriented action journal, runtime-only checkpoint, strict state
  transitions, and deterministic reconciliation interface; and
- test-only real-subprocess crash fixtures with a safe append-once ledger.

Phase 2 does not add a Live Provider, bounded developer tool, artifact
verifier, verified task completion, real repository-maintenance Agent, formal
benchmark, or a claim of strict exactly-once execution.

Phase 3 adds only one bounded real-AI/task path:

- one default-off OpenAI-compatible action-proposal adapter configured solely
  by endpoint, named environment credential, model, and bounds;
- a finite local workspace tool surface, including a trusted fixed pytest
  invocation but no arbitrary shell or general process capability;
- a fresh deterministic repository-maintenance fixture and verifier-only
  `TASK_COMPLETED` transition persisted as schema-v2 state; and
- a deterministic Mock offline E2E path plus a separate credential-gated live
  preflight/task path.

Phase 3 does not add a fallback provider, browser, desktop/UI automation,
arbitrary shell, arbitrary repository access, remote execution, multi-agent
execution, a general benchmark, or a claim of live-provider acceptance without
the separately observed real E2E evidence.

## Legacy compatibility and provenance

| Surface | Phase-0 decision | Reason |
| --- | --- | --- |
| Public historical repository URL | Retained as `chengcheng-2006/paios-ce` | It is the verified source provenance; no remote rename is authorized |
| Git commits, tags, releases, CHANGELOG history | Retained | Historical facts must not be rewritten |
| Python import namespace `paios_ce` | Retained as `LEGACY_INTERNAL_NAMESPACE` | A full import-tree migration is deferred to avoid a Phase-0 semantic rewrite |
| `paios-ce` command | Retained as deprecated compatibility alias | Existing users retain an explicit transition path |
| `astron` command | Primary | Current competition CLI and documentation entry point |
| Schema IDs `https://paios.ce/...` and `PAIOS_*` example names | Retained | Existing public contract and environment compatibility surface |
| Existing `paios-ce-*` baseline assets | Retained | Baseline artifacts are preserved; current Astron assets use new names |

Astron therefore means the competition project identity; `paios_ce` does not
mean that PAIOS CE was historically called Astron.

## Third-party material

The project continues to use its declared open-source dependencies, including
Pydantic, PyYAML, JSON Schema tooling, pytest, and optional faster-whisper.
They are dependencies or tools, not Astron-created capabilities. No model
weights, external credentials, competition account, paid service, or private
project implementation was used in Phase 0.

## AI coding assistance and Owner responsibilities

Codex may assist with implementation, boilerplate, test generation, debugging,
and documentation drafting. The Owner remains responsible for problem
definition, scope, architecture decisions, security policy, acceptance
criteria, benchmark design, result acceptance, and release/submission
decisions.

## Phase-0 release and authority boundary

```text
REMOTE_MUTATION=FORBIDDEN
PUSH=NO
MERGE_TO_MAIN=FORBIDDEN
RELEASE=FORBIDDEN
```

No remote branch, repository setting, tag, GitHub Release, or PyPI release may
be changed under this boundary.
