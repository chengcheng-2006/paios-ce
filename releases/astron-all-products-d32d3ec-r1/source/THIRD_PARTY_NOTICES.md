# Astron — Third-Party Notices

This file summarizes dependencies used by the current Astron package and
validation toolchain. The competition-facing inventory, upstream sources,
resolved evidence versions, inherited PAIOS CE baseline, and external
evaluation service are listed in [`THIRD_PARTY_SOFTWARE.md`](THIRD_PARTY_SOFTWARE.md).

## Runtime dependencies

| Component | Version constraint | Purpose | License |
|---|---|---|---|
| pydantic | >=2.7,<3 | Data models and validation for the Task/Action protocol and configuration | MIT |
| PyYAML | >=6.0,<7 | Load public/private config YAML files | MIT |
| jsonschema | >=4.20,<5 | Validate config files and protocol payloads against generated JSON Schemas | MIT |

## Development / test dependencies

| Component | Version constraint | Purpose | License |
|---|---|---|---|
| pytest | >=9.0.3,<10 | Fixed maintenance-test tool and unit/integration/security test runner | MIT |
| coverage | >=7,<8 | Coverage measurement | Apache-2.0 |
| pytest-cov | >=5,<8 | pytest plugin: `--cov`, `--cov-branch`, `--cov-report` options | MIT |

## Build-time and package-validation tools

| Component | Version / constraint | Purpose | License |
|---|---|---|---|
| setuptools | >=83,<84 | Declared PEP 517 build backend | MIT |
| build | validation environment | Preferred PEP 517 build frontend | MIT |
| pyproject-hooks | resolved with build | Low-level PEP 517 hook wrapper | MIT |

These tools are not Astron runtime capabilities and are not bundled as Astron
source. Isolated build dependency resolution may access the configured Python
package index; that setup traffic is not a live model request.

## Optional runtime dependencies (Local ASR `speech` extra)

| Component | Version constraint | Purpose | License |
|---|---|---|---|
| faster-whisper | >=1.1.0,<1.3 | Optional local speech-to-text adapter (CPU int8 reference mode) | MIT |
| ctranslate2 | pulled by faster-whisper | CTranslate2 inference engine for faster-whisper | MIT |
| av (PyAV) | pulled by faster-whisper | Audio decoding (bundles FFmpeg libraries) | BSD-3-Clause |

These are **optional** (`pip install astron[speech]`); the base install does
not include them. No model weights are bundled; the user is responsible for
reviewing the license and terms of the model they select.

## External AI service

The frozen live acceptance and Phase 4 benchmark used an explicitly selected
DeepSeek OpenAI-compatible API model as a bounded proposal source. No Provider
SDK, model weights, service code, or credential is bundled, and the service is
not required for deterministic core reproduction. See
[`THIRD_PARTY_SOFTWARE.md`](THIRD_PARTY_SOFTWARE.md) and
[`AI_ASSISTANCE_DISCLOSURE.md`](docs/aic2026/AI_ASSISTANCE_DISCLOSURE.md).

## Not bundled

- model weights, datasets, and user audio;
- Provider or channel SDKs;
- API credentials or private configuration;
- Hermes, OpenClaw, GSAP, or Ollama models.
