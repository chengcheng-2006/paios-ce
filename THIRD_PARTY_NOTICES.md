# PAIOS CE — Third-Party Notices

This file lists the third-party dependencies actually introduced by PAIOS CE in the current release candidate.
Only components actually linked/imported at runtime or used by the development/test toolchain
are listed. Unused components are NOT listed.

## Runtime dependencies

| Component | Version constraint | Purpose | License |
|---|---|---|---|
| pydantic | >=2.7,<3 | Data models and validation for the Task/Action protocol and configuration | MIT |
| PyYAML | >=6.0,<7 | Load public/private config YAML files | MIT |
| jsonschema | >=4.20,<5 | Validate config files and protocol payloads against generated JSON Schemas | MIT |

## Development / test dependencies

| Component | Version constraint | Purpose | License |
|---|---|---|---|
| pytest | >=8,<9 | Unit/integration/security test runner | MIT |
| coverage | >=7,<8 | Coverage measurement | Apache-2.0 |
| pytest-cov | >=5,<8 | pytest plugin: `--cov`, `--cov-branch`, `--cov-report` options | MIT |

## Build-time only (R1 closure `_build_tools`, not runtime)

| Component | Version | Purpose | License |
|---|---|---|---|
| build | 1.5.0 | PEP-517 build frontend (`python -m build`, offline) | MIT |
| pyproject_hooks | 1.2.0 | Low-level build backend hook wrappers | MIT |
| colorama | 0.4.6 | Cross-platform colored terminal text (build dependency) | BSD-3-Clause |

These three packages are borrowed read-only for the **offline build only**
(network OFF). They are NOT runtime dependencies, are NOT included in the wheel
(0 members), and are NOT included in the the release candidate Handoff package (0 members).
They appear in the Delivery ZIP only as build-environment evidence, with their
license files intact. See `BUILD_TOOLS_FINAL_BOUNDARY.csv`.

## Not introduced in the current release candidate

The following components are intentionally NOT listed as runtime dependencies of the release candidate.
Their future introduction is governed by the PAIOS CE license and distribution policy:

- Hermes (planned: version-pinned dependency + adapter boundary; not vendored)
- OpenClaw / @openclaw/* (planned: dependency-only, pinned)
- GSAP (excluded from v0.1 by default; separate non-OSI license)
- faster-whisper (weights are install-time download only; not vendored)
- Ollama models (weights are install-time download only; not vendored)

the release candidate introduces NO live Provider, Channel, or Speech integrations, so no provider SDK,
channel SDK, or speech SDK is a runtime dependency.
