# Public Release Boundary

This document defines the boundary of the historical PAIOS CE public release
candidate. It states what was in scope, what was out of scope, and what
guarantees apply. The Astron AIC competition branch additionally retains
internal evidence under `docs/aic2026/evidence/`; that evidence is not
automatically part of a public or anonymous runtime distribution, and it is
not present in this source snapshot — the retained directories there are the
durable contract documents under `docs/aic2026/`.

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
  GitHub repository will instead use a new clean-room Git
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

- Release candidate: `v0.1.0-rc.1`.
- Candidate generation: `git archive` of the final main commit.
- Internal RC1/RC2 audit history is preserved as internal audit evidence and
  must not be presented as user-facing release versions.

## No production claims

PAIOS CE is a clean-room scaffold. The public release makes no claim of
production readiness, SLA, or fitness for any particular deployment. See
`SUPPORT_MATRIX.md` for the supported Python versions and the support
status of each component.
