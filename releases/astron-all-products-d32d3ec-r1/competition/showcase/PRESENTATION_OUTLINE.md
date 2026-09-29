# Presentation outline (10 slides)

> 版本与证据边界：本文介绍产品快照 `d32d3ec1bc49a78d0b14aabb6bf0daf79d3f4d88`；如提及 R2 评测数字，其测量运行来自 `13ee283ce8b6121af14b1bf0f1f9deefe1484cf2`。d32d3ec 本身没有正式模型实跑证据。


Content draft for the defence deck — the actual text, the actual number, and the
actual artifact to show on each page. No page needs a screenshot that does not
exist; where a page shows output, that output is produced by the command printed
on the page.

Rule for every page: one core message, and it must be true of snapshot `d32d3ec`.

---

**1. Title — Astron: 模型提议，运行时决定，验证器完成**

* Core: an execution-governance runtime for AI agents, Python 3.11+, Apache-2.0.
* Sub-line: source snapshot `d32d3ec`, package `astron 0.1.0rc2`, alpha.
* Visual: the one-line trust chain, typeset. Nothing else on the page.
* Say: identity and provenance in one sentence — Astron is the competition
  identity of the `paios_ce` codebase, import path kept for compatibility.

**2. The problem is not model intelligence**

* Core message: four recurring incidents are authority failures, not reasoning
  failures.
* Table (from `docs/PROJECT_OVERVIEW.md` §1): claims-of-completion / whitelist-as-prompt /
  killed-mid-side-effect / unanswerable audit question — each with why prompt-level
  mitigation fails.
* Asset: none needed; this is a text page. Say the four, then the position.

**3. What Astron changes**

* Core message: three authorities, all in code — permission engine, durable
  runtime, verifier.
* Visual: reuse the Mermaid flow in `docs/ARCHITECTURE.md` ("Shape of a run" in
  `README.md`). It is editable text, and every box names a real module.
* Say: "the model's output is data. It cannot pick its principal, grant itself a
  capability, or write TASK_COMPLETED."

**4. Live: one proposal, decided**

* Core message: deny-by-default is not a policy document.
* Command: `astron run-task examples/unknown_action_fixture.json; echo exit=$?`
* On-screen fields: `action_class: UNKNOWN_ACTION`, `error_code: E_UNKNOWN_ACTION`,
  `execution_attempted: false`, exit 5.
* Say: unregistered names are *explicitly* rejected and never coerced into a known
  class; that precedence is what stops a model inventing a tool that happens to
  contain the word "read".

**5. Live: a real task, with no model**

* Core message: the harness is demonstrable end to end without a provider.
* Command: `bash examples/demos/01_governed_task.sh`
* Show: `FAIL_AS_EXPECTED` baseline, then `status: PASS`, `verifier:
  VERIFIER_ACCEPTED`, the seven actions, then the two files on disk
  (`maintenance_config.py`, `.astron-artifacts/change_summary.json`).
* Say plainly: proposals here are Mock. This page measures the runtime, not a
  model. Then: the read-only batch of three was allowed; each mutating step stood
  alone in its turn.

**6. The page that answers "so what"**

* Core message: action success is not task completion, and a crash is not a retry
  signal.
* Command: `python examples/demos/03_crash_and_reconcile.py`
* Show the four lines: child exit 72 → `NEEDS_RECONCILIATION` / `UNCERTAIN` →
  `executor_invoked=False`, ledger still 1 → `CONFIRMED_SUCCEEDED` → `SUCCEEDED`.
* Asset: the `action_events` trail
  (`RECORDED → AUTHORIZED → ATTEMPT_STARTED → UNCERTAIN → SUCCEEDED`) as a strip.
* Say: rebuild state, re-execute an action, and confirm an external effect are
  three operations. Conflating them is how duplicate side effects ship.

**7. Verified completion, concretely**

* Core message: completion is a deterministic check with a reason code, persisted
  as a fact.
* Content: what `MaintenanceVerifier` refuses — any mutation outside the one
  permitted file, a config that is not exactly the repaired bytes, an artifact that
  fails the trusted schema, a bounded-test failure — and the accept path
  `VERIFIER_ACCEPTED` written to `task_verifications`.
* Contrast row: `RepoTaskRunner` maps model text like `done` to `AGENT_STOPPED`
  and returns **no** solved verdict.
* Say: the packaged verifier is fixed to one fixture. A general repository
  verifier is the biggest honest gap in the product.

**8. Where the code is, and how you extend it**

* Core message: this is a real, readable codebase a new contributor can enter.
* Content: three anchors from `docs/SOURCE_MAP.md` — entry `cli/main.py:601`,
  model call `agent/native.py:171`, ordering `runtime/durable_runtime.py:71`;
  then "adding a tool touches five places **on purpose**"
  (`docs/DEVELOPER_GUIDE.md` §3).
* Numbers: `src/paios_ce` product modules, `team/` experimental, 546 tests,
  zero runtime dependency on a provider SDK.
* Asset: the reading-order list; optional `git`-less note that the snapshot is a
  single committed revision, not a diff pile.

**9. Team mode — shown, and correctly labelled**

* Core message: role-scoped authority on the same engine, not a second runtime.
* Command (only if the schedule allows): `PYTHONPATH=src:. python examples/demos/04_team_offline_run.py`
  → `VERIFIED_SUCCESS`, five routed messages.
* Facts to state on the page, not in a footnote: not packaged (`pyproject.toml`
  packs `src/`), no CLI entry point, default `max_executor_rounds = 1`,
  `SUPERVISOR` capabilities are an empty set, the Auditor is advisory, only the
  VERIFIER role may request completion.
* Say: "not stronger — narrower. And in the measurement history, Team was the arm
  that produced zero capability passes."

**10. Boundaries, and what has actually been measured**

* Core message: the mechanism is real; the research conclusion does not exist yet.
* Left column (limits, from `docs/SECURITY_AND_LIMITATIONS.md`): not an OS
  sandbox; bounded test execution is a real subprocess; terminal is POSIX-only and
  pattern-gated; `rollback_supported` always false; audit sink is caller-supplied;
  Windows/Ubuntu runtime `NOT_RUN` for this revision.
* Right column (from `docs/EVALUATION_SUMMARY.md`): R2 = 120 formal runs
  (40 Direct / 40 Single / 40 Team), outcomes `PASS=6 TASK_FAIL=88
  PROVIDER_ERROR=23 HARNESS_ERROR=2 TEAM_BLOCKED=1`; capability subset `0/72`
  across all three arms — a floor effect, not an ordering; 23 provider errors
  censored the arms differently; R3 is development-set calibration, no
  final-holdout conclusion; Generic/Direct calibration scores are not Astron
  scores; the shipped snapshot `d32d3ec` is nine commits after the measured
  `13ee283` and carries no formal run evidence of its own.
* Close: replay slide 1's command output as the last image on the page —
  "the model proposes, the runtime decides, the verifier completes."

---

## Notes for whoever builds the deck

* Use `docs/ARCHITECTURE.md`'s Mermaid blocks as the only diagrams; they are
  editable text and every component name in them exists in the source. Do not
  redraw them into a prettier, vaguer picture.
* Every number on a slide needs its denominator and its censoring note. If a
  number cannot carry that, cut the number.
* No slide should imply certification, deployment, users, customers, revenue or
  an award. There is none to report.
* Do not include the R3 scaffold, the R2 task bank or holdout material in any
  slide or screenshot.
