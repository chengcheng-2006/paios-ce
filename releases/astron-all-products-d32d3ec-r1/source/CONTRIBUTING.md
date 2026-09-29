# Contributing to Astron

Thank you for your interest in contributing to Astron. Astron is an
execution-control runtime for AI agent builders, evolved from the public PAIOS
CE baseline for the AIC 2026 competition.
It is currently a public-core release candidate (clean-room scaffold);
publication and release actions remain maintainer-controlled.

## Ways to contribute

- **Bug reports** — open an issue using the Bug report form.
- **Documentation improvements** — corrections and clarifications are welcome
  (Documentation improvement form, or a direct PR for small fixes).
- **Tests** — more coverage for existing behavior, especially negative and
  fail-closed paths.
- **Small implementation improvements** — narrowly scoped fixes and polish.
- **Adapter / provider ideas** — describe the design first; live adapters
  require prior design and security discussion.
- **Security issues** — do **not** open a public issue. Follow
  [SECURITY.md](SECURITY.md).

## Before you start

- Search existing issues and PRs first; the problem may already be known.
- Large features or design changes: discuss the design before implementing.
- Small fixes and documentation corrections can go straight to a PR.
- Never put real secrets, tokens, credentials, private configuration, or
  personal data into an issue, PR, example, or log output. Use placeholders
  only.

## Code of Conduct

Be respectful and constructive. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Development setup

Requires Python >= 3.11.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# POSIX:
source .venv/bin/activate
pip install -e ".[dev]"
```

## Testing

Run the authoritative test command (same as CI):

```bash
python -m pytest --cov=paios_ce --cov-branch --cov-report=term-missing -ra -q
```

Expectation: 0 failures and 0 errors. A small number of environment-specific
skips is acceptable (for example, symlink-dependent tests on filesystems
without symlink support).

Where behavior changes, add or update tests for the change, including the
fail-closed / deny paths where applicable.

## Code style

Keep the style consistent with the surrounding code. Ruff is available in the
dev environment but is not a CI gate; please avoid introducing new lint
regressions in the files you touch.

## Pull requests

Keep PRs focused:

- one logical change per PR;
- tests included where behavior changes;
- documentation updated where public behavior changes;
- no unrelated refactors;
- no secrets, personal data, or private paths;
- explain behavioral and security impact in the PR description.

## Generated files

Some artifacts are generated from source models:

- JSON Schemas under `schemas/` are generated from the pydantic models.
  If your change affects a model, regenerate through the official generator:

```bash
python -m paios_ce.tools.generate_schemas --out schemas
```

Do not hand-patch generated schema files unless the repository explicitly
requires manual maintenance.

## Security

- Respect the project's security defaults (see [SECURITY.md](SECURITY.md)).
- Secret values must never appear in code, config, logs, or test fixtures.
- New capabilities must go through risk review before being added to the
  permission engine.

## License

By contributing, you agree that your contributions will be licensed under the
Apache-2.0 License. See LICENSE and NOTICE for details.
