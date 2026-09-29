# Evaluation summary

This page exists so that nobody has to guess which claims Astron is allowed to
make. It separates three things that are easy to blur:

1. **what the product code does** (verifiable offline today — see
   `examples/demos/`, `tests/`);
2. **what has been measured with a real model** (a small, frozen experiment set,
   with known censoring);
3. **what is still open** (in progress, no conclusion).

Only layer 1 ships as capability. Layers 2 and 3 are research context, not a
feature list.

## What is verified without any model

* 546 tests pass, 1 skipped, in this delivery copy on macOS/arm64 with CPython
  3.13.14 (`python -m pytest -ra -q`). Upstream `SUPPORT_MATRIX.md` records its
  own validation base as macOS + CPython 3.12 with a smaller suite; neither
  number is a cross-platform certification, and Windows/Ubuntu runtime for this
  revision is recorded as `NOT_RUN`.
* Three offline demos exercise the full chain — proposal → normalization →
  authorization → durable attempt → effect → terminal fact → verification — plus
  a real killed-mid-action crash and reconciliation
  (`examples/demos/README.md`).
* These demonstrate the **contracts and the failure semantics**. They demonstrate
  nothing about task success rates, model quality, safety behaviour at scale, or
  production readiness. Offline green is not a security certification.

## What was measured (R2), and what it does and does not show

R2 is a frozen historical baseline: 120 formal runs against one
repository-maintenance-style task family, three arms of 40 runs each, all
produced on a pinned runtime commit. It is read-only; it is not re-scored,
re-run or edited.

| Field | Value |
| --- | --- |
| Runs | `120/120` — `DIRECT=40`, `ASTRON_SINGLE=40`, `ASTRON_TEAM=40` |
| Primary (mutually exclusive) outcomes | `PASS=6`, `TASK_FAIL=88`, `PROVIDER_ERROR=23`, `HARNESS_ERROR=2`, `TEAM_BLOCKED=1` |
| Capability subset | `0/72` — Direct `0/24`, Single `0/24`, Team `0/24` |
| Stress subset | Direct `2/16`, Single `4/16`, Team `0/16` (only 8 unique stress cases) |
| Model | DeepSeek, request alias `deepseek-v4-flash`; `model_version_pinned = NO` (alias plus live response metadata, so provider-side backend drift is not excluded) |
| Runtime under test | Astron core commit `13ee283` |
| Source of these numbers | the R3 pre-registration record of the R2 immutable baseline (`R3_R2_LIMITATIONS_TO_DESIGN_REQUIREMENTS.json`, `R3_DESIGN_PREREGISTRATION.md` §1, ledger digest prefix `af3c1ca5`) |

Read the table with its censoring, not around it:

* **The capability subset is a floor effect.** `0/72` across all three arms means
  the tasks were not solved by any arm, so it cannot support any ordering between
  Direct, Single and Team. Reporting the stress subset (2 / 4 / 0 of 16 unique-8)
  as "Astron is better" would be reading noise from a denominator of eight cases.
* **`PROVIDER_ERROR=23` of 120 censors the comparison.** Arm-differential
  censoring was recorded (Direct 22.5 %, Single 35.0 %, Team 0 %), which means the
  arms did not lose the same number of runs to transport. Outcome rates are not
  directly comparable without stating that.
* **Several safety-relevant fields were not arm-comparable.** `recovery_result`
  was `NOT_APPLICABLE` on all 40 Direct runs, `verifier_accepted` null on all 40
  Direct runs, `forbidden_change_detected` missing on 40/40 Team runs, and
  `unsafe_replay` had zero variance across 118 runs. Those were demoted to
  secondary explanatory evidence rather than reported as results.
* **Duration/latency instrumentation was degenerate** and cannot support any
  speed claim.
* **Output-size, budget-exhaustion and truncation effects are measurement
  artefacts**, not model-capability findings.

### Conclusions that are NOT available from R2

* "Astron improves task success rate." Not established — the capability subset is
  a floor effect and the arms are censoring-differentially.
* "Astron is safer than a generic agent." `unsafe_replay` had zero variance; the
  safety flags were not arm-comparable. What *is* established is that the
  mechanisms exist and behave as specified under deterministic tests.
* "Team is stronger than Single." Team produced `0/24` capability and `0/16`
  stress, plus one `TEAM_BLOCKED` run, and the nested-child provider telemetry was
  not captured on the Team arm. Nothing here supports a capability advantage.
* "120 runs completed, therefore the measurement is valid." Completion of a run
  matrix is an operational fact about the experiment, not evidence about model
  behaviour, safety, or measurement validity.

## What is still open (R3)

R3 is a **development-set** calibration and task-family exploration effort, still
running at the time of this packaging. Its pre-registration states that formal
execution (the planned 240 runs) and any final-holdout model exposure were out of
scope for the design windows, and that the Astron core runtime stays frozen — R3
changes measurement design only, not policy, topology, permission semantics,
verifier semantics or checkpoint semantics.

Therefore:

* **there is no final-holdout result and no conclusion to report**;
* calibration scores for the `Generic` and `Direct` scaffolds are **not** Astron
  scores. They measure a baseline scaffold used to difficulty-rank tasks; the
  Astron probe itself was recorded as blocked upstream of some of those arms;
* no retry policy is enabled (`NOT_ENABLED_R3_EVIDENCE_INSUFFICIENT`), and the
  components R2 identified as missing — an executor/binding layer, ledger, resume
  and a control-plane state machine — are R3 design requirements to be validated
  before any final holdout, not shipped capabilities;
* the frozen runtime's turn envelope was a hard measurement limit in that line of
  work (`MAX_TURNS=12` in the harness loop). For product reference: the shipped
  `NativeAgent` default is `max_steps=6`, valid range 1-12
  (`agent/native.py:122-126`) — and this snapshot's own limit, not a model
  finding.

## Provenance of the shipped code versus the measured code

The delivery snapshot is `d32d3ec`, which is **nine commits after** the R2
measured runtime `13ee283`. The product-code difference between them is confined
to seven files: the terminal capability (`tools/terminal.py`), the generic
repository runner (`agent/repo_task.py`), the terminal policy class and schemas
(`permissions/policy.py`, `tools/__init__.py`, `agent/native.py`, `cli/main.py`)
and their exports. `team/` and `src/paios_ce/state/`,
`src/paios_ce/runtime/`, `src/paios_ce/permissions/engine.py` are unchanged
between `13ee283` and `d32d3ec`.

Consequences, stated plainly:

* the shipped snapshot contains **no formal model-run evidence** of its own;
* describing `d32d3ec` behaviour from the R2 numbers would be a version mix, so
  nothing in this package does;
* the R2 numbers above belong to the measurement layer and are reported as
  history, including the parts that failed.

## What is not in this package

Held-out task definitions, gold answers, reference patches, grader internals,
raw provider request/response bodies, model reasoning content, run directories,
session memory and phase receipts are excluded by design
(`PUBLIC_RELEASE_BOUNDARY.md` and the packaging rules in
`../manifest/PACKAGE_CONTENTS.md`). The internal record names cited above are
listed with their local provenance in `RELEASE_MANIFEST.json`; they are not
public links and not part of this source snapshot.
