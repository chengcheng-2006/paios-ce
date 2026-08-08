# Roadmap

This roadmap describes intended areas of work. It is not a support promise.

## Stage 1 — Public-core quality

- improve documentation and onboarding;
- strengthen protocol and schema examples;
- expand negative permission tests;
- improve redaction and diagnostics tests;
- keep Windows and Ubuntu validation green on Python 3.11 and 3.12.

## Stage 2 — Adapter acceptance framework

Before any live adapter, define reusable gates for:

- credential references and rotation;
- network destination allowlists;
- capability declarations;
- action risk classification;
- explicit confirmation;
- timeout, retry, and idempotency behavior;
- redaction;
- rollback;
- clean-machine validation;
- support-matrix updates.

## Stage 3 — Narrow experimental adapters

Only after the acceptance framework is frozen, consider one narrowly scoped
experimental adapter at a time.

An adapter remains experimental until its end-to-end evidence passes. Its
existence in a branch or skeleton does not mean it is supported.

### Local ASR

- typed speech contracts (`TranscriptionRequest` / `TranscriptionResult` / ...);
- audio input policy (extension / size / duration allowlists, read-only);
- optional faster-whisper adapter with lazy import and `local_files_only`;
- `paios-ce transcribe` CLI command;
- metadata-only audit events;
- status: EXPERIMENTAL (real-model smoke passed on Windows, CPU int8, tiny model).

Remaining work before EXPERIMENTAL: real-model smoke on a runtime where
faster-whisper/CTranslate2 can load, plus any fixes it reveals.

## Stage 4 — Operational hardening

Potential future work:

- durable state-adapter contracts;
- stronger provenance and artifact signing;
- reproducible release assets;
- expanded platform testing;
- structured migration and rollback tools;
- documented incident-response procedures.

## Explicit non-goals for the current candidate

- broad provider marketplaces;
- unrestricted tool execution;
- arbitrary shell;
- public-by-default listeners;
- hidden credential propagation;
- production multi-user hosting;
- claims of fully autonomous operation.

## Versioning

Published release candidates are available from
[GitHub Releases](https://github.com/chengcheng-2006/paios-ce/releases).
The `main` branch remains the development line for subsequent work.

Documentation improvements merged after a tag do not change the historical
source archive of that release. A future release may include those
improvements under a new tag after maintainer approval and validation.
