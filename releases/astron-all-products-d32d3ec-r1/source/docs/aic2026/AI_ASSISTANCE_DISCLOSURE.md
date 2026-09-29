# Generative AI and automation assistance disclosure

This disclosure is prepared for the AIC 2026 “AI + Open Source” competition.
It describes why generative AI or automated tools were used, where they
participated, and how a human Owner reviewed, modified, and verified the work.

## Tools and purposes

### Codex development assistance

Codex was used as an AI-assisted software-development tool for:

- repository discovery and implementation drafting;
- test and regression-case drafting;
- debugging support and evidence reconciliation;
- command execution under explicit Owner-defined authority boundaries;
- documentation, report, checklist, and demo-script drafting; and
- consistency checks across source, tests, retained evidence, and claims.

Codex did not own the product requirements, acceptance threshold, security
policy, benchmark protocol, release decision, or competition submission.

### DeepSeek live Provider evaluation

The explicitly selected DeepSeek OpenAI-compatible model was used as the
proposal source in bounded live acceptance runs and the frozen Phase 4
benchmark. It proposed tool calls for repository-maintenance tasks. Astron,
not the model, supplied the trusted principal, decided authorization, executed
bounded tools, persisted state, and decided verified completion.

DeepSeek was not required to produce the deterministic Mock demo, crash tests,
package validation, security checks, or core offline reproduction. The model
and service are not bundled with the project.

### Deterministic automation

Project scripts, pytest, schema validators, package validators, hash tools,
and security scanners were used to build and verify evidence. These are
automation tools, not substitutes for the Owner's acceptance decision.

## Participation by development stage

| Stage | AI/automation participation | Human Owner control and review |
| --- | --- | --- |
| Problem definition | Codex helped organize requirements already supplied by the Owner | Owner selected the problem, scope, competition positioning, and three contributions |
| Architecture and security | Codex drafted implementations and tests against explicit contracts | Owner decided trust boundaries, fail-closed behavior, credential rules, and acceptance gates |
| Implementation | Codex proposed and applied bounded source/test changes in authorized phases | Owner authorized each phase and reviewed terminal receipts and evidence |
| Testing and debugging | Codex ran deterministic tests and diagnosed failures; scripts collected machine evidence | Owner decided whether evidence justified a fix, rerun, deferral, or gate transition |
| Live evaluation | DeepSeek proposed actions inside the frozen bounded protocol | Owner supplied credentials interactively, launched authorized runs, and froze the protocol and result interpretation |
| Benchmark | Automation materialized, hashed, and replayed the fixed result matrix | Owner approved the protocol, accepted all retained failures, and prohibited result shopping |
| Documentation | Codex drafted competition-facing prose and checklists from repository evidence | Owner must review, edit, approve, export, and submit the final materials |
| Release/submission | No AI tool has authority to publish or submit | Owner alone decides push, merge, tag, release, and competition submission |

## Human review, modification, and verification

The human Owner:

- set the requirements and prohibited-action boundaries for each phase;
- made architecture, security, evidence, benchmark, and remediation decisions;
- inspected or supplied real run receipts and authorized narrowly scoped
  external operations;
- required regression-first changes and immutable failure retention;
- rejected unsupported upgrades from `NOT_RUN`, `PARTIAL`, or sender-side
  success to `PASS`;
- selected the final result language, including the 34/40 versus 32/40
  interpretation and explicit Phase 5 deferrals; and
- remains responsible for reviewing every competition artifact before
  publication or submission.

AI-drafted source and prose were not accepted solely because an AI generated
them. Acceptance required repository review, tests, package/CLI smoke,
security checks, evidence reconciliation, and an Owner decision appropriate
to the phase.

## Boundaries and attribution

- The project does not claim that all source or documentation was written
  without generative-AI assistance.
- It also does not claim that AI generated and accepted the work without human
  governance.
- No AI output is assumed to transfer third-party copyright or license rights.
  Dependencies, inherited baseline work, and external services are attributed
  separately.
- Credentials, private environment data, and raw rejected Provider payloads
  are not intended to appear in public evidence.
- AI assistance does not change the Apache-2.0 licensing of Astron-owned
  contributions or the licenses of third-party components.

## Submission declaration

```text
AI_ASSISTED_DEVELOPMENT=YES
CODEX_ASSISTED_IMPLEMENTATION_TESTING_DOCUMENTATION=YES
LIVE_MODEL_USED_AS_BOUNDED_PROPOSAL_SOURCE=YES
OWNER_CONTROLLED_REQUIREMENTS_ARCHITECTURE_ACCEPTANCE=YES
HUMAN_REVIEW_MODIFICATION_VERIFICATION_REQUIRED=YES
AI_AUTHORIZED_RELEASE_OR_SUBMISSION=NO
```
