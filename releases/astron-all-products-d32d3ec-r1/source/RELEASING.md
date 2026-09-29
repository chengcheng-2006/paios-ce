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

Version mapping for the current candidate:

- Git tag / human version: `0.1.0-rc.2`
- Python package version (PEP 440): `0.1.0rc2`

## Release Steps (publication gate)

1. Update version in `pyproject.toml`
2. Update `CHANGELOG.md`
3. Create annotated tag: `git tag -a vX.Y.Z -m "Release vX.Y.Z"`
4. Push tag to remote (requires maintainer authorization)
5. Create GitHub Release (requires maintainer authorization)
6. Upload to PyPI (requires maintainer authorization)

## Current Status

The current release-candidate line is `v0.1.0-rc.2` (package `0.1.0rc2`);
the tag has not been created yet — it will be created at the maintainer-authorized
remote step. The previous candidate tag `v0.1.0-rc.1` exists in the repository.

GitHub Release has not been created. PyPI and Zenodo are not authorized.

Publication actions (public transition, GitHub Release, PyPI, Zenodo) require
explicit maintainer authorization.

## Security Requirements

- Never include real secrets in releases
- Validate all third-party dependencies
- Ensure license compliance
- Run full security scan before any release