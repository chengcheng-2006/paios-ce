# Astron Documentation

Astron is the AIC 2026 competition identity evolved from the public PAIOS CE
baseline. Historical release links below intentionally retain their source
names.

## Start here

- [Project overview / 中文总览](../README.md)
- [English overview](../README.en.md)
- [Quick start](QUICKSTART.md)
- [Source code map](SOURCE_MAP.md)
- [Configuration reference](CONFIGURATION.md)
- [Developer guide](DEVELOPER_GUIDE.md)
- [Operations runbook](OPERATIONS.md)
- [Security and limitations](SECURITY_AND_LIMITATIONS.md)
- [Evaluation summary](EVALUATION_SUMMARY.md)
- [Demo guide](DEMO.md)
- [Frequently asked questions](FAQ.md)
- [AIC 2026 scope and baseline](aic2026/COMPETITION_SCOPE.md)

## Competition presentation layer

- [One-page project brief (judge-facing)](competition/ONE_PAGE_PROJECT_BRIEF.md)
- [90-second live demo script](competition/DEMO_SCRIPT_90S.md)
- [3-minute pitch script](competition/PITCH_3MIN.md)
- [Defence Q&A](competition/DEFENSE_QA.md)
- [Submission abstract (CN) / 报名摘要](competition/SUBMISSION_ABSTRACT_CN.md)
- [Innovation points](competition/INNOVATION_POINTS.md)
- [Technical route](competition/TECHNICAL_ROUTE.md)
- [Judge cheat sheet (60 s)](competition/JUDGE_CHEATSHEET.md)
- [Final demo runbook (operator)](competition/FINAL_DEMO_RUNBOOK.md)

## Architecture and security

- [Architecture](ARCHITECTURE.md)
- [Security model](SECURITY_MODEL.md)
- [Security policy](../SECURITY.md)
- [Support matrix](../SUPPORT_MATRIX.md)
- [Public release boundary](../PUBLIC_RELEASE_BOUNDARY.md)

## Capabilities

- [Local ASR](LOCAL_ASR.md)
- [Capability admission](CAPABILITY_ADMISSION.md)

## Project governance

- [Roadmap](ROADMAP.md)
- [Contributing](../CONTRIBUTING.md)
- [Code of Conduct](../CODE_OF_CONDUCT.md)
- [Changelog](../CHANGELOG.md)
- [Citation metadata](../CITATION.cff)
- [License](../LICENSE)
- [Notices](../NOTICE)

## Release candidate

Historical public pre-release of the source baseline:
[`v0.1.0-rc.1`](https://github.com/chengcheng-2006/paios-ce/releases/tag/v0.1.0-rc.1).

The release candidate includes a Mock Provider and CLI, plus an optional
Local ASR capability on the current development line. It does not ship live
providers, live channels, production speech, shell execution, remote
execution, or production Hermes/OpenClaw integration.
