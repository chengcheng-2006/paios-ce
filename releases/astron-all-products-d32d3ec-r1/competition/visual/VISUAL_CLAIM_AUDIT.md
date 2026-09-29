# Astron Competition Visual Claim Audit V1

> 版本边界：本材料依据历史证据基线 `11c6114f6ec0504628f912ebde9ba53821badb03`；只支持该基线对应的陈述，不构成 ZIP 中 `d32d3ec1bc49a78d0b14aabb6bf0daf79d3f4d88` 快照的运行或测试证据。详见同目录 README。


**Result: PASS** — the rendered claims stay within the retained evidence and the approved claim language. This is a presentation audit, not a new run, test, or verification of Astron.

## Audit scope and method

Reviewed all four screen renderers and the index in `visual.js`, the normalized replay dataset, the page-level labels and captions, and the expandable provenance controls. Compared factual wording against `outputs/07_CLAIM_LANGUAGE_AUTHORITY.md` and the named entries in `outputs/ASTRON_COMPETITION_DEMO_EVIDENCE_V1/06_EVIDENCE_TO_SCREEN_MAP.json`.

Every value-bearing record under `facts` includes a `source_reference` and an exact `claim_map_ref`. Validation found 67 such records; all 67 map references resolve to entries in the prior evidence map. The map link and source details are expandable from each displayed fact. Presentation metadata is separately identified and is not used to strengthen evidence claims.

## Screen-by-screen review

| Surface | Visible claims checked | Evidence and map authority | Result and boundary |
| --- | --- | --- | --- |
| Index | Local, static evidence presentation; four linked screens; no runtime or Provider connection. | Visual Production V1 §§12, 15–16; the index makes no new proof claim. | **PASS.** Uses an evidence-replay label and does not display current-run metrics. |
| 01 — Execution proof | One bounded task; `MAX_RPS` 10 → 20; requested model ID `deepseek-flash` with returned identity `NOT_RECORDED`; five calls/decisions/proposals/authorizations/executions; 5/5 journal coverage; action request/authorization/execution distinction; source change; artifact digest; scoped zero observations; exactly eight evidence-board metrics. | Map entries: “Scene 1 title and proof identity”; “Scene 1 task scope card: MAX_RPS 10 → 20; other two constants retained”; “Scene 1 count cards”; “Evidence board metric: harness bypass observed = 0”; “Scene 1 artifact card”; “Scene 1 optional model-ID footnote.” Baseline §§5, 7, 11–13; Claim Language Authority safe and qualified claims. | **PASS.** Describes one controlled run only. Model identity is explicitly requested, not Provider-confirmed. The zero-bypass metric is scoped to saved intents, journals, receipts, application events, and captured scope. The forbidden-mutation note is limited to saved intents, application records, and checked workspace evidence, not an OS-wide audit. The completion events 43–47 are separated from earlier untimed presentation phase labels; no timestamps or fabricated event positions are shown. `USER_DELIVERABLE` is labeled as the requested presentation class, not canonical artifact metadata. No unsupported per-action tool name, receipt ID, checkpoint, or risk score is shown. |
| 02 — Verifier control | `PROPOSE_COMPLETE` is not success; both declared criteria pass; durable verification is `ACCEPTED`; `TASK_SUCCEEDED` follows; recorded event positions 43–47; corrupt-artifact refusal is a separate retained deterministic example. | Map entries: “Scene 2 positive completion timeline”; “Scene 2 acceptance criteria and durable status”; “Scene 2 separate retained negative example”; “Scene 2 memory hook.” Baseline §§7–9, 13; Claim Language Authority safe claims. | **PASS.** The positive run and retained negative example are visibly separated. The screen does not suggest the proposal itself grants success or that all possible criteria are verified. The exact completion order is shown without timestamps. |
| 03 — Action-aware recovery | Qualified runtime/tested failure-window evidence; `ACTION_PROPOSED → AUTHORIZED → ATTEMPT_STARTED → OUTCOME UNKNOWN → UNCERTAIN → RECONCILIATION`; three reconciliation outcomes; `15/15` retained summary; line-by-line review limitation; “Timeout ≠ no side effect.” | Map entries: “Scene 3 persistent qualification banner”; “Scene 3 recovery state diagram”; “Scene 3 retained fault-matrix summary card: 15/15”; “Scene 3 raw-output limitation footer.” Baseline §§8, 11–13; Claim Language Authority qualified recovery claim. | **PASS.** The page is labeled `QUALIFIED EVIDENCE REPLAY` and explicitly says it is not part of the positive Live Proof. `CONFIRMED_NOT_APPLIED` only becomes retry-eligible after trusted confirmation and still requires an explicit call; `NO_EVIDENCE` remains uncertain and gives no retry eligibility. The retained 15/15 result is not described as freshly rerun or independently rechecked. No arbitrary exactly-once or production-scale claim appears. |
| 04 — Responsibility comparison | Generic tool-calling flow alongside Astron’s explicit responsibility stages; “Astron changes execution responsibility, not model intelligence”; explicit disclaimer that the diagram does not claim generic agents lack authorization, durable records, or verification; no measured outcome. | Map entry: “Scene 1 neutral responsibility comparison inset: generic tool-calling flow beside Astron's explicit authorization, action record, and verifier stages.” Claim level E, illustrative only; baseline §§2, 4, 9; Claim Language Authority comparison boundary. | **PASS.** The diagram is labeled explanatory and not a comparative experiment. Both lanes have neutral styling. It does not claim that generic agents lack authorization, journaling, verification, or any other capability, and it makes no superiority claim. |

## Cross-screen language and data checks

- Positive proof screens show **RECORDED VERIFIED RUN**. The index, recovery, and explanatory comparison use distinct replay labels so neither qualified evidence nor an illustrative diagram is presented as the positive run.
- The only numbered recorded sequence is events 43–47. Earlier execution-path labels are explicitly untimed evidence-phase labels, not raw numbered journal events.
- The board contains exactly eight data-backed metrics: real-model tasks proven, model decisions, executed actions, journal coverage, harness bypass observed, artifact digest, acceptance criteria, and final state.
- `deepseek-flash` appears only as the requested model ID; Provider-returned identity remains `NOT_RECORDED`.
- The generic-agent comparison is illustrative, not empirical. Recovery evidence remains a separate B-level tested-window claim. The positive run remains a one-task A-level claim.
- No unsupported timestamps, token counts, costs, latency, hidden verifier checks, arbitrary risk values, Provider-confirmed model identity, universal guarantees, or winner/superiority language is rendered.

## Verification record

- JavaScript syntax check: **PASS**.
- Replay JSON parse and provenance/map-reference check: **PASS** — 67 sourced values, all map references valid; exactly eight evidence-board metrics; recorded completion events exactly 43–47; recovery path contains all six specified states.
- HTML parsing: **PASS** — index plus four screen pages.
- Responsive visual review: **PASS** at 1440, 1280, 800, and 390 px representative widths. Recovery and comparison diagrams switch to vertical sequences on narrow screens; the verifier proposal, `NOT SUCCESS YET`, acceptance, and final success remain distinct.
- Local preview loaded both the replay dataset and the prior evidence map. The presentation uses local static files only; it did not start Astron or contact a Provider.
- Demo timing follows `outputs/ASTRON_COMPETITION_DEMO_EVIDENCE_V1/05_DEMO_CAPTURE_PLAN.md`: 40 s + 35 s + 45 s = 120 s.
- Product source, harness, Provider, verifier, tests, and evidence archives were not modified for this visual production.
