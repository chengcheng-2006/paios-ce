# Project overview

For reviewers, technical leads and new contributors who need the whole picture
before opening code.

## The problem

Agent frameworks are good at producing *proposals*. Production systems need
*accepted outcomes*, and the gap between them is where the failures live:

* a model reports "I updated the config" — the file is unchanged, or unchanged in
  the wrong place;
* a tool whitelist is enforced by prompt text, so a hallucinated function name or
  an `rm -rf` inside a "script" is only as blocked as the model decided to be;
* a long-running action dies halfway; on restart, nobody can say whether the
  external effect happened, so the retry duplicates it;
* state lives in the conversation, so a process restart loses the story, and an
  auditor cannot reconstruct what was authorized.

Model-side improvements (better prompting, better models, more reflection) do not
close this gap, because the gap is about **who holds authority**, not about how
smart the proposer is.

## The position Astron takes

> The model proposes. The runtime decides. The verifier completes.

Three separate authorities, all in code:

1. **Permission engine** — an `ActionRequest` is data. A separately supplied
   trusted principal, a capability allowlist, scope classes and a risk policy
   decide `allow / deny / blocked / confirmation_required`. Unknown names,
   arbitrary shell, elevation and critical classes are hard-blocked.
2. **Durable runtime** — before an effect happens, the attempt is persisted; after
   it, the terminal outcome is persisted. If the process cannot prove the outcome,
   the action is recorded `UNCERTAIN` and no automatic retry occurs.
3. **Verifier** — completion is a deterministic check of state (what changed, what
   must not have changed, whether the bounded tests pass, whether the completion
   artifact satisfies a trusted schema). A model's own claim maps to
   `AGENT_STOPPED`, never to "complete".

## Who this is for

* Developers shipping an agent that touches repositories, files or any system
  where a duplicated side effect is expensive.
* Teams that need a defensible answer to "what did this agent do, under whose
  authority, and who checked it".
* Researchers measuring agent behaviour who need the harness itself to stop
  contaminating the measurement — an arm that silently retries or self-reports
  success destroys comparability.
* Anyone building for regulated or shared environments where "the prompt said not
  to" is not a control.

Astron is **not** a chatbot framework, not a workflow engine, and not a model
library. It has no UI, no service, and no channel integrations.

## A task, start to finish

```text
owner: "repair the failing timeout default in this fixture"
  ↓  (trusted code) fresh fixture copy + baseline digest + SQLite store
  ↓  provider proposes: workspace.read_text ×3 in one read-only batch
  ↓  loop validates the batch (reads may batch; effects may not)
  ↓  BoundedToolRuntime normalizes → ActionRequest with fixed scopes
  ↓  PermissionEngine: capability? scope? risk? hard block? replay identity?
  ↓  journal: AUTHORIZED → ATTEMPT_STARTED → execute → SUCCEEDED
  ↓  provider proposes: workspace.patch_text (one mutating call this turn)
  ↓  provider proposes: test.run_pytest_bounded
  ↓  provider proposes: workspace.write_artifact → validate.json (schema-bound)
  ↓  provider returns no calls  →  loop stops
  ↓  MaintenanceVerifier: structural + forbidden-mutation + bounded tests + artifact contract
  ↓  record_task_verification → ACCEPTED  →  the task is complete
```

Failure branches are equally real: a mixed batch is rejected whole; an unknown
tool name is blocked with `E_UNKNOWN_ACTION` before any capability check; a
capability or scope miss yields `deny` with `execution_attempted=false`; a raised
executor after the attempt boundary yields `UNCERTAIN` and `needs_reconciliation`,
which then needs a trusted observer rather than a retry.

Try it in 60 seconds: `bash examples/demos/01_governed_task.sh`.

## Module responsibilities

| Module | Owns | Status |
| --- | --- | --- |
| `paios_ce.protocols` | wire models: `TaskEnvelope`, `ActionRequest`, `ActionResult`, `AuditEvent` | experimental, stable shapes |
| `paios_ce.permissions` | the decision, risk policy, principal identity, replay | experimental |
| `paios_ce.state` | the durable authority: journal, events, checkpoints, reconciliations, verifications; private-file security | experimental |
| `paios_ce.runtime` | ordering of authorize → attempt → effect → terminal, plus recovery and reconciliation | experimental |
| `paios_ce.tools` | the bounded workspace/test surface and the governed terminal sessions | experimental |
| `paios_ce.agent` | the proposal loop, the fixture, the verifier, the artifact contract, `RepoTaskRunner` | experimental; verifier is fixture-specific |
| `paios_ce.providers` | provider contract, Mock, one OpenAI-compatible proposal adapter | experimental |
| `paios_ce.config` | public/private/env/CLI precedence, safe defaults | experimental |
| `paios_ce.audit` | redaction invariant and event emission | experimental |
| `paios_ce.cli` | the `astron` entry point and stable exit codes | experimental |
| `paios_ce.speech` | optional local file ASR | experimental, off by default |
| `paios_ce.{orchestrator,routing,workers,channels}` | composition skeletons | **Scaffold** — not the governed path |
| `team/` | roles, mailbox, role-scoped authority, completion gate | **experimental**, not packaged, not on the CLI |

## What is already useful today

* A working, testable governance core with 546 offline tests, including real
  cross-process crash recovery — you can adopt the permission engine, the durable
  store, or the whole loop independently.
* A maintenance-style repository task that genuinely completes end to end under
  governance, with a completion artifact contract.
* A generic governed repository runner (`RepoTaskRunner`) that adds clean-checkout
  enforcement, budget accounting and diff capture while refusing to hand out a
  solved verdict — the shape most teams actually need for coding agents.
* A deterministic offline path that makes the guarantees demonstrable in a
  5-minute talk with no network.
* A research-usable arm: because the harness is explicit about authorization,
  attempts and completion, it can be instrumented without the measurement silently
  depending on hidden retries.

## Plausible applications, and where the line is

Already demonstrated in this repository: controlled edits to a small Python
repository, bounded test execution, structured change summaries as validated
artifacts, refusal of destructive or unknown actions, and recovery from a killed
mid-action process.

Reasonable directions that the design supports but this snapshot does **not**
demonstrate — and which should not be described as shipped:

* repository maintenance at scale (dependency bumps, lint/typing cleanups, CI
  repair) — needs a real general verifier, not the fixture oracle;
* controlled handling of files with policy (redaction, retention, private-state
  guarantees exist; a document workflow does not);
* resumable long-running jobs — the durable journal and reconciliation contract
  are the foundation, but there is no scheduler, no queue and no service;
* any external side effect (payments, messages, deployments) — the policy classes
  hard-block these today, and enabling one means writing an action-specific
  reconciler, not just granting a capability.

The distinction that matters in every case: the runtime is real, the *application
wrappers* around it are not.

## Usage boundaries

* One workspace per run; the workspace is a copy, not your repository. Pointing
  Astron at an owner repo is explicitly out of contract (`agent/fixtures/.../README.md`).
* One task family is verified: the maintenance fixture. Everything else is your
  verifier to write.
* `UNCERTAIN` requires a human or an action-specific observer to resolve. That is
  a design feature, and it means Astron will sometimes honestly stall.
* Team mode is a single bounded round by default, has no CLI, and is not packaged.
* Platform: macOS/Linux for the core; the terminal capability is POSIX-only; the
  state-privacy code has a Windows ACL backend, but the current revision's
  Windows/Ubuntu runtime is recorded as `NOT_RUN`.
* Nothing here claims production readiness — see `SUPPORT_MATRIX.md`,
  `PUBLIC_RELEASE_BOUNDARY.md`, and `docs/SECURITY_AND_LIMITATIONS.md`.

## Where the research stands

R2 ran 120 formal runs across Direct/Single/Team and produced a floor effect on
the capability subset; it established no success-rate or safety advantage for
Astron. R3 is still calibrating on a development set with no final-holdout result.
The full picture, including which numbers are censored and why, is in
[EVALUATION_SUMMARY.md](EVALUATION_SUMMARY.md). Research status is context for
interpreting the project honestly — it is not a list of product capabilities, and
the R3 scaffold is not Astron.

## History

`paios_ce` (PAIOS CE) is the original package and the upstream repository name;
Astron is the competition identity built on top of it, announced in
`docs/aic2026/COMPETITION_SCOPE.md` with the baseline recorded in
`docs/aic2026/BASELINE.md`. The import path and the `paios-ce` console alias were
kept deliberately for compatibility; renaming them would break every existing
import for no functional gain. The provenance boundary is also recorded in
`docs/aic2026/CONTRIBUTION_BOUNDARY.md`.
