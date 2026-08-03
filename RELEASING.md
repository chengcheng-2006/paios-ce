# Releasing PAIOS CE

This document describes the release process for PAIOS CE.

## Prerequisites

Before creating a release:

1. Ensure all tests pass: `pytest`
2. Ensure coverage meets gates: `pytest --cov=paios_ce`
3. Run security scan: `python tools/security_local_scan.py`
4. Validate package build: `python tools/package_local_validate.py`

## Version Scheme

PAIOS CE follows [Semantic Versioning](https://semver.org/):

- `MAJOR.MINOR.PATCH` for stable releases
- `MAJOR.MINOR.PATCH-rc.N` for release candidates
- `MAJOR.MINOR.PATCH.devN` for development versions

## Release Steps (Phase 6)

1. Update version in `pyproject.toml`
2. Update `CHANGELOG.md`
3. Create annotated tag: `git tag -a vX.Y.Z -m "Release vX.Y.Z"`
4. Push tag to remote (Phase 6 only, requires Owner authorization)
5. Create GitHub Release (Phase 6 only)
6. Upload to PyPI (Phase 6 only, requires Owner authorization)

## Current Phase

PAIOS CE is currently in Phase 5: Local Public Repository Candidate.

No remote operations, GitHub releases, or PyPI uploads are authorized yet.

The current candidate tag is `v0.1.0-rc.1` (local only).

## Security Requirements

- Never include real secrets in releases
- Validate all third-party dependencies
- Ensure license compliance
- Run full security scan before any release