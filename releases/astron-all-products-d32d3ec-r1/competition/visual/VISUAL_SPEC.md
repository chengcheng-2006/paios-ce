# Astron Competition Visual Production V1

> 版本边界：本材料依据历史证据基线 `11c6114f6ec0504628f912ebde9ba53821badb03`；只支持该基线对应的陈述，不构成 ZIP 中 `d32d3ec1bc49a78d0b14aabb6bf0daf79d3f4d88` 快照的运行或测试证据。详见同目录 README。


## Purpose

This package is an offline, evidence-backed presentation layer for the canonical `ASTRON_REAL_MODEL_END_TO_END_PROOF_V1` and the separately qualified recovery evidence. It is a recorded replay, not an Astron runtime, benchmark, or new execution.

The positive proof screens carry **RECORDED VERIFIED RUN**. The index, recovery, and comparison pages use **EVIDENCE REPLAY**, **QUALIFIED EVIDENCE REPLAY**, and **EXPLANATORY EVIDENCE REPLAY** respectively, so they are not mistaken for the positive run. The recovery screen also carries **QUALIFIED RUNTIME / TESTED FAILURE-WINDOW EVIDENCE — NOT PART OF THE POSITIVE LIVE PROOF**. The only numbered event sequence shown is the recorded completion chain, events 43–47. Earlier items are untimed phase labels. No wall-clock timestamps are shown.

## Design direction

- Dense, professional developer-console layout with a warm near-white canvas, dark ink, restrained blue navigation, green accepted/succeeded states, and muted amber for evidence limitations.
- Prioritize task state, authorization, durable action facts, artifact identity, and verifier acceptance. Model prose remains secondary.
- Use compact typography, aligned data tables, visible source/claim affordances, and short labels. Avoid chat bubbles, fake terminal output, animations that imply a new run, winner imagery, and decorative gradients.
- Use the exact memory hook **AI 说完成，不等于任务真的完成。**
- Keep comparison copy neutral: **Astron changes execution responsibility, not model intelligence.**

## Screen set

### `SCREEN_01_EXECUTION_PROOF.html`

Primary proof screen. Left rail shows the bounded task, `SUCCEEDED`, `VERIFIED`, and the requested model ID with the “provider-returned identity not recorded” note. The center timeline shows the evidence sequence without invented timestamps. Counts appear as summaries: five model decisions, five proposed and authorized actions, five executed and journaled actions. The right detail card shows one action kind only at the level supported by the public evidence; it omits a fabricated per-action ID, tool name, risk score, or checkpoint ID. The bottom evidence board has exactly eight metrics.

### `SCREEN_02_VERIFIER_CONTROL.html`

Completion authority screen. It shows only the two-line `MAX_RPS` diff, the artifact path/size/digest comparison, both declared criteria, durable `ACCEPTED`, and `TASK_SUCCEEDED`. A visual gap separates `PROPOSE_COMPLETE` from verifier acceptance. The requested hook and supporting line explain that the model can propose completion but cannot grant itself success.

### `SCREEN_03_ACTION_AWARE_RECOVERY.html`

Qualified recovery screen. It shows `ACTION_PROPOSED → AUTHORIZED → ATTEMPT_STARTED → OUTCOME UNKNOWN → UNCERTAIN → RECONCILIATION`, then the three evidence-based branches. It displays `Timeout ≠ no side effect`, the retained `15/15` summary, and the original per-process-output review limitation. No element suggests this occurred in the positive task or promises arbitrary exactly-once behavior.

### `SCREEN_04_GENERIC_AGENT_VS_ASTRON.html`

Neutral responsibility comparison. The generic tool-calling flow and Astron flow receive equal visual weight. No winner icons, ranking, measured outcomes, or claims that other agents lack authorization, durable records, or verification.

## Evidence and interaction policy

- All displayed factual values are hydrated from `DEMO_REPLAY_DATA_V1.json`.
- Each fact record has a `source_reference` and exact `claim_map_ref` into the prior `06_EVIDENCE_TO_SCREEN_MAP.json`. Screen links/details expose those references.
- Timeline labels before event 43 are phase labels requested for presentation. They have no event number or timestamp. Events 43–47 preserve the baseline's recorded order and numbers.
- `deepseek-flash` is always labeled **requested model ID**. The provider-returned identity is shown as **not recorded**.
- The artifact digest is shown as matching the durable record and independent recomputation. It is not described as proof that the whole system is correct.
- `USER_DELIVERABLE` is labeled as a presentation class requested by the visual brief; it is not presented as canonical artifact metadata.
- “0 observed” always retains its scope note. It is not an OS-wide audit.
- No token counts, costs, latency, numeric risk ratings, hidden verifier checks, fabricated per-action tool identities, or unsourced timestamps appear.
- Recovery remains a B-level/tested-window claim separate from A-level positive execution evidence.
- The UI works offline, makes no network requests, calls no Provider, and starts no Astron process.

## Responsive behavior

- **1440 px:** three-column execution-proof layout with a persistent task rail, timeline, and event detail panel; evidence board spans the page bottom.
- **1280 px:** reduce rail and detail widths while retaining all three proof areas and the bottom board.
- **800 px:** stack task summary above timeline and place action details after the timeline as a secondary section; keep task and verification states readable without horizontal scrolling.
- **390 px:** single-column layout; preserve `PROPOSE_COMPLETE`, the verification state, and `TASK_SUCCEEDED` as distinct, readable rows. Keep the task status and two criteria visible without horizontal scrolling. Collapse secondary source details, but retain a tap-to-open source/claim reference.
- Status is conveyed through text and shape as well as color. Interactive controls have keyboard focus states and accessible names; reduced-motion preferences disable transitions.

## Local preview

From the `outputs` directory, serve the static files with `python3 -m http.server 8000` and open `http://localhost:8000/ASTRON_COMPETITION_VISUAL_PRODUCTION_V1/`. Serving from `outputs` makes both the local replay JSON and the prior evidence map available at their referenced relative paths. The preview uses only local files.
