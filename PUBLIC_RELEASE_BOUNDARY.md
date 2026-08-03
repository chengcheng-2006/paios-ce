# Public Release Boundary

This document defines the boundary of the PAIOS CE public release candidate.
It states what is in scope, what is out of scope, and what guarantees apply.

## Scope of the public tree

The public tree contains only the clean-room implementation of the PAIOS CE
core scaffold:

- `src/paios_ce/` — the installable Python package.
- `tests/` — the test suite that proves the contract.
- `examples/` — example configuration and task fixtures (non-secret).
- `schemas/` — JSON Schemas for every public protocol model.
- Governance files: `LICENSE`, `NOTICE`, `THIRD_PARTY_NOTICES.md`,
  `README.md`, `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`,
  `CHANGELOG.md`, `SUPPORT_MATRIX.md`, `PUBLIC_RELEASE_BOUNDARY.md`,
  `.gitignore`, `.gitattributes`, `pyproject.toml`.

## Out of scope

The public tree does **not** contain, and the public release does **not**
ship:

- Audit evidence, test-run logs, coverage databases, or validator packages.
- Owner personal data (email, phone, local filesystem paths).
- Production configuration, production secrets, or real provider credentials.
- Legacy source code from any prior implementation.
- Model weights, audio, video, or database files.
- Git metadata: candidate archives exclude `.git`. The published
  GitHub repository (Phase 6) will instead use a new clean-room Git
  history built from this same tree.
- `policy.py.orig` or any other merge/policy conflict artifact.

## Boundary guarantees

A static byte scan of the public tree satisfies:

| Check | Required value |
| --- | --- |
| Real secret | 0 |
| Complete key-shaped literal (sk-/ghp_/github_pat_/AIza/AKIA/xoxb-) | 0 |
| Owner PII (except copyright notices) | 0 |
| Production path | 0 |
| Legacy source | 0 |
| `policy.py.orig` | 0 |
| Git metadata (`.git/`) | 0 |
| Database / audio / video / model weight | 0 |

## Release candidate identification

- Release candidate: **RC2** (publication hygiene remediation of RC1).
- Historical candidates (RC1 and the original Handoff) are preserved
  unmodified as audit evidence and are **not** part of this public release.
- The public tree is sealed as `PAIOS_CE_PUBLIC_TREE_RC2.zip` before
  independent Validator execution and is not rebuilt afterwards.

## No production claims

PAIOS CE is a clean-room scaffold. The public release makes no claim of
production readiness, SLA, or fitness for any particular deployment. See
`SUPPORT_MATRIX.md` for the supported Python versions and the support
status of each component.
