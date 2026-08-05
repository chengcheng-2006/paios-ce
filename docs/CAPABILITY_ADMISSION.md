# Progressive Capability Admission

PAIOS CE grows by admitting one narrowly scoped capability at a time. A new
capability is not accepted merely because it works once; it must pass a
defined admission checklist and receive an honest support status.

## Levels

| Level | Name | Typical capability |
| --- | --- | --- |
| L0 | Local mock | deterministic task loop |
| L1 | Read-only input | local ASR, allowlisted file read |
| L2 | Low-risk output | owner reply, workspace document |
| L3 | Scoped tools | browser read, calendar draft |
| L4 | Reversible external writes | confirmed message, event or PR |
| L5 | High-risk structured workers | named system operation with second factor |

Arbitrary shell is not the goal of L5. High-risk work should remain a named,
typed operation with constrained parameters.

## Admission checklist

Every new capability must define:

1. public typed request and result models;
2. capability ID and operation name;
3. support status;
4. default enabled state;
5. caller and owner rule;
6. resource scope;
7. risk level;
8. confirmation rule;
9. secret handling;
10. network behavior;
11. retry and idempotency;
12. audit fields and redaction;
13. failure and rollback;
14. unit, integration and security tests;
15. clean-machine acceptance;
16. documentation and removal path.

## Status vocabulary

```text
PLANNED
SCAFFOLD
EXPERIMENTAL
VALIDATED
SUPPORTED
BLOCKED
```

`SUPPORTED` is reserved for a separately accepted release policy. The
authoritative status of every capability is recorded in
[`SUPPORT_MATRIX.md`](../SUPPORT_MATRIX.md); no other document may overclaim
beyond it.

## Local ASR (Phase 9A)

Local file ASR (`SPEECH_TRANSCRIBE_LOCAL` / `speech.transcribe_local`) is the
first real capability admitted after the Mock-only release.

- typed contracts: `TranscriptionRequest`, `TranscriptionResult`,
  `TranscriptionSegment`, `TranscriptionInfo`, `SpeechRuntimeConfig`,
  `AudioInputPolicy`;
- default enabled state: `false` (`speech.enabled = false`);
- resource scope: one existing local audio file, read-only;
- risk level: LOW (L1 read-only input);
- network behavior: `local_files_only = true` by default; no implicit model
  download; an explicit offline error
  (`E_SPEECH_MODEL_NOT_AVAILABLE_OFFLINE`) is returned when a model is not
  cached;
- secret handling: no credentials involved; model-cache paths never appear in
  audit or error output;
- audit: metadata-only (`safe_source_label`, counts, language, model label,
  device, compute type); transcript text and absolute source paths are
  structurally absent;
- tests: deterministic unit/integration/security tests with a fake model
  backend; real-model smoke is separate and is not required for the
  deterministic suite.

## Initial roadmap

| Order | Capability | Initial status | Risk |
| ---: | --- | --- | --- |
| 1 | Local file ASR | EXPERIMENTAL (Phase 9A) | Low |
| 2 | One real text Provider | Planned | Medium |
| 3 | Feishu owner-only DM | Planned | Medium |
| 4 | Local TTS | Planned | Low |
| 5 | Allowlisted read-only files | Planned | Medium |
| 6 | Browser read-only research | Planned | Medium |
| 7 | Reversible external writes | Planned | High |
| 8 | Structured Windows workers | Planned | High |
| Later | Personal WeChat | Research | High |
| Long-term blocked | Arbitrary shell/admin | Blocked | Critical |
