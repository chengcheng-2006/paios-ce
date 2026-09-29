# Judge Evidence Board

> 版本边界：本材料依据历史证据基线 `11c6114f6ec0504628f912ebde9ba53821badb03`；只支持该基线对应的陈述，不构成 ZIP 中 `d32d3ec1bc49a78d0b14aabb6bf0daf79d3f4d88` 快照的运行或测试证据。详见同目录 README。


## Canonical Live Proof — one controlled task

The eight cards below summarize `ASTRON_REAL_MODEL_END_TO_END_PROOF_V1`. Values are from the canonical baseline; the last card combines verification and terminal task state to keep the board within the eight-metric limit.

| # | Metric | Evidence-backed value | Claim level / boundary |
|---:|---|---|---|
| 1 | Real-model end-to-end tasks | **1** | A — one controlled task; not a statistical sample |
| 2 | Provider calls | **5** | A — Provider-returned model identity was not recorded |
| 3 | Model decisions | **5** | A — this run only |
| 4 | Governed actions executed | **5** | A — all five authorized |
| 5 | Executed actions journaled | **5/5** | A — durable action-journal evidence |
| 6 | Harness bypass observed | **0** | A — saved intents, journals, receipts, application events, and captured scope only |
| 7 | Delivered artifact SHA-256 | **Matches durable record** | A — independently recomputed digest: `3c0a0c51248b9f9431bc869d8e6776b8ce882d0479ae9dba33eb4e258652c173` |
| 8 | Acceptance and final state | **2/2 criteria PASS → ACCEPTED → TASK_SUCCEEDED** | A — verification acceptance precedes terminal success |

## Three responsibility boundaries

| Generic tool-calling agent | Astron execution-governance runtime |
|---|---|
| Model or application proposes tool actions | Runtime evaluates authorization and scope before governed execution |
| Application-specific records may track action attempts and outcomes | Action journal records authorization, attempt boundary, and outcome as durable action facts |
| Application-specific completion logic may accept a task | Verifier checks declared criteria and durable acceptance gates task success |

**Exact caption:** “Astron changes execution responsibility, not model intelligence.”

This is a neutral responsibility comparison, not a measured head-to-head result. Generic agents may implement these mechanisms; the baseline reports no fair comparative experiment and authorizes no superiority claim.

## Qualified recovery callout — separate evidence lane

**QUALIFIED RUNTIME / TESTED FAULT WINDOWS (B):** retained deterministic fault-matrix summary **15/15**. The raw per-process output directory is unavailable for line-by-line independent reinspection in this review. Recovery is separate from the positive Live Proof; its successful task did not include a crash or restart. The claim is limited to tested windows and does not promise arbitrary exactly-once behavior.

## Footer

`MAX_RPS: 10 → 20` · requested model ID: `deepseek-flash` (Provider-returned identity not durably recorded) · no production-scale reliability or statistical reliability claim.

**Evidence basis:** `ASTRON_COMPETITION_EVIDENCE_BASELINE_V1` §§7–8, 11–13; `01_POSITIONING.md` §§1, 3, 8; `03_TECH_REPORT_CORE.md` §§6–7; `04_DEMO_STORYBOARD.md` Scenes 1–3; `06_JUDGE_QA.md` §§1–3, 11–13, 17–18; `07_CLAIM_LANGUAGE_AUTHORITY.md` Safe and Qualified Claims.
