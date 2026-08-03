# Contributing to PAIOS CE

Thank you for your interest in contributing to PAIOS CE. This project is currently in
Phase 3/4 clean-room scaffold development and is not yet a public release.

## Current Status

PAIOS CE is a clean-room public core scaffold for a privacy-preserving personal AI
orchestrator. At this stage, contributions are not yet being solicited publicly.

## Code of Conduct

- Be respectful and constructive.
- Follow the project's security-first, privacy-first philosophy.
- Do not submit real secrets, tokens, or production data.
- All examples must use placeholders only.

## Development Setup

Requires Python >= 3.11.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# POSIX:
# source .venv/bin/activate
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest
pytest --cov=paios_ce
```

All tests must pass (0 failures, 0 errors, 0 skipped). New functionality must include
corresponding tests.

## Security

- All contributions must respect the project's security defaults (see SECURITY.md).
- Secret values must never appear in code, config, logs, or test fixtures.
- New capabilities must go through risk review before being added to the permission engine.

## License

By contributing, you agree that your contributions will be licensed under the Apache-2.0
License. See LICENSE and NOTICE for details.
