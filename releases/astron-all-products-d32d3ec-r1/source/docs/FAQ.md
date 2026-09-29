# Frequently Asked Questions

## Is Astron a production-ready personal assistant?

No. `v0.1.0-rc.1` is a release candidate for a clean-room public-core scaffold.
It does not claim production readiness, an SLA, or suitability for a particular
deployment.

## Does it call a real large language model?

No live provider is bundled. The current release includes a deterministic local
Mock Provider for contracts, tests, and demos.

## Does the demo require an API key?

No. The bundled demo is local and API-key-free.

## Does the repository contain real credentials?

It must not. Examples use placeholders, and the public tree is scanned for
common credential patterns and forbidden files.

## What is `SecretRef`?

`SecretRef` is an indirection mechanism. Components exchange a reference to a
secret source rather than serializing the secret value into configuration,
tasks, logs, errors, or audit events.

## Can it execute shell commands?

Arbitrary shell and administrator elevation are hard-blocked in the current
release candidate.

## Can it transcribe local audio?

On the current development line, `astron transcribe FILE` can transcribe a
local audio file through the optional faster-whisper adapter (install with
`pip install -e ".[dev,speech]"`). Speech is disabled by default
(`speech.enabled = false`) and defaults to local-files-only. See
[docs/LOCAL_ASR.md](LOCAL_ASR.md).

## Does it support WeChat, Feishu, Hermes, or OpenClaw?

No production integration is shipped. Those areas are planned adapter
boundaries only and must not be described as supported.

## Does it send data over the network?

The bundled Mock Provider performs no network access. A future live adapter
would require an explicit network, credential, permission, audit, and rollback
review.

## Which Python versions are validated?

The package contract admits Python 3.11 and later. The current competition
revision has exact local Python 3.12/macOS evidence. Windows and Ubuntu runtime
validation remain `NOT_RUN`; historical baseline CI is not current runtime
certification. See [`../SUPPORT_MATRIX.md`](../SUPPORT_MATRIX.md).

## How do I report a security issue?

Use GitHub private vulnerability reporting or Security Advisories. Do not open
a public Issue containing vulnerability details.

## Why is the project so conservative?

The purpose of the public core is to make dangerous assumptions visible before
real integrations and privileges are added. A smaller, auditable boundary is
more valuable here than a broad but implicit capability set.

## What contributions are useful now?

Useful contributions include:

- documentation corrections;
- protocol and schema tests;
- redaction tests;
- permission and replay tests;
- safe configuration examples;
- portability fixes for supported Python versions.

Live adapters should begin with a design/security discussion.
