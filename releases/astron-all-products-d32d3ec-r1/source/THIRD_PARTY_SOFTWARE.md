# Open-source and third-party resources usage list

This manifest is the competition-facing inventory of software, services, and
inherited open-source material used by Astron. It separates Astron-owned work
from dependencies and external resources. Version constraints are taken from
`pyproject.toml` unless explicitly described as validation-environment
evidence.

## Core platform and build system

| Resource | Version or range | License / terms | Role | Source | Usage and distribution boundary |
| --- | --- | --- | --- | --- | --- |
| Python | >=3.11 | Python Software Foundation License | Runtime and standard-library SQLite/process/file primitives | [python.org](https://www.python.org/) | Required interpreter; not bundled by the Astron wheel |
| setuptools | >=83,<84 | MIT | PEP 517 build backend | [github.com/pypa/setuptools](https://github.com/pypa/setuptools) | Isolated build dependency; not an Astron runtime capability |
| build | validator environment | MIT | Preferred PEP 517 build frontend | [github.com/pypa/build](https://github.com/pypa/build) | Development/package validation only; `pip wheel` is the validator fallback |
| pyproject-hooks | resolved with build | MIT | PEP 517 hook wrapper used by build | [github.com/pypa/pyproject-hooks](https://github.com/pypa/pyproject-hooks) | Transitive package-validation tool; not bundled in the Astron wheel |

## Direct runtime dependencies

| Resource | Declared range | Locally resolved evidence version | License | Role | Source |
| --- | --- | ---: | --- | --- | --- |
| Pydantic | >=2.7,<3 | 2.13.5 | MIT | Typed protocol, config, and artifact validation | [github.com/pydantic/pydantic](https://github.com/pydantic/pydantic) |
| PyYAML | >=6.0,<7 | 6.0.3 | MIT | YAML configuration loading | [github.com/yaml/pyyaml](https://github.com/yaml/pyyaml) |
| jsonschema | >=4.20,<5 | 4.26.0 | MIT | JSON Schema validation | [github.com/python-jsonschema/jsonschema](https://github.com/python-jsonschema/jsonschema) |
| pytest | >=9.0.3,<10 | 9.1.1 | MIT | Fixed trusted maintenance-test tool and regression runner | [github.com/pytest-dev/pytest](https://github.com/pytest-dev/pytest) |

The resolved versions above document one local validation environment; the
declared compatible ranges remain the package contract.

## Development and validation dependencies

| Resource | Declared range | Locally resolved evidence version | License | Role | Source |
| --- | --- | ---: | --- | --- | --- |
| coverage.py | >=7,<8 | 7.16.0 | Apache-2.0 | Line and branch coverage measurement | [github.com/nedbat/coveragepy](https://github.com/nedbat/coveragepy) |
| pytest-cov | >=5,<8 | 7.1.0 | MIT | pytest coverage integration | [github.com/pytest-dev/pytest-cov](https://github.com/pytest-dev/pytest-cov) |

These tools are used to validate Astron. They are not bundled as Astron source
and, except for pytest's separately declared runtime role, are not base runtime
dependencies.

## Optional local speech extra

| Resource | Version or relationship | License | Role | Source | Boundary |
| --- | --- | --- | --- | --- | --- |
| faster-whisper | >=1.1.0,<1.3 | MIT | Optional local-file speech-to-text adapter | [github.com/SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Optional `speech` extra; not used by the competition maintenance demo |
| CTranslate2 | resolved transitively by faster-whisper | MIT | Optional inference engine | [github.com/OpenNMT/CTranslate2](https://github.com/OpenNMT/CTranslate2) | Not in the base install |
| PyAV | resolved transitively by faster-whisper | BSD-3-Clause | Optional audio decoding and FFmpeg binding | [github.com/PyAV-Org/PyAV](https://github.com/PyAV-Org/PyAV) | Not in the base install |

No speech model weights or audio datasets are bundled. A user selecting a
model must separately review its license and terms.

## Inherited open-source baseline

| Resource | Frozen identity | License | Use | Boundary |
| --- | --- | --- | --- | --- |
| PAIOS CE public baseline | commit `c0a60b2cecabd43634992d1b0871881087619d82`; tree `0e82a6d026ea029e28c570d05f7754d484f6c17e`; historical tag `v0.1.0-rc.2` | Apache-2.0 | Starting repository, typed protocols, baseline permission/config/audit/Mock capabilities, and historical provenance | Not presented as an Astron competition invention; see `docs/aic2026/CONTRIBUTION_BOUNDARY.md` |

Astron retains the historical repository URL, `paios_ce` internal namespace,
and deprecated `paios-ce` compatibility CLI instead of rewriting provenance.

## External AI service used for evaluation

| Resource | Identity used | Terms | Role | Source | Distribution boundary |
| --- | --- | --- | --- | --- | --- |
| DeepSeek OpenAI-compatible API | `deepseek-v4.1-flash-expires-on-0910` in the frozen live evidence | Provider service terms; not an open-source dependency | Bounded proposal source for live acceptance and the Phase 4 benchmark | [platform.deepseek.com](https://platform.deepseek.com/) | No SDK, model weights, credential, or service code is bundled; not required for deterministic reproduction |

The Provider is proposal-only. Its successful HTTP response is not action
authorization, execution evidence, or verified completion.

## Explicit exclusions

Astron does not vendor model weights, benchmark Provider credentials, private
repositories, private datasets, Hermes, OpenClaw, GSAP, browser automation
stacks, channel SDKs, or arbitrary-shell frameworks. Git, shell utilities,
operating-system libraries, pip, and virtual environments are environment
tools rather than distributed Astron components.

## License compatibility statement

The directly declared open-source dependencies use permissive MIT,
Apache-2.0, BSD-3-Clause, or PSF terms that are compatible with Astron's
Apache-2.0 distribution when their required notices and license terms are
preserved. This manifest is an engineering inventory, not legal advice.

`LICENSE` and `NOTICE` remain authoritative for Astron-owned distribution.
Upstream projects remain governed by their own licenses and terms.
