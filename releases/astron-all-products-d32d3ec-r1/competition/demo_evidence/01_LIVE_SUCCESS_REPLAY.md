# Scene 1 — Live Success Replay

> 版本边界：本材料依据历史证据基线 `11c6114f6ec0504628f912ebde9ba53821badb03`；只支持该基线对应的陈述，不构成 ZIP 中 `d32d3ec1bc49a78d0b14aabb6bf0daf79d3f4d88` 快照的运行或测试证据。详见同目录 README。


**Purpose:** Show one canonical, real-model-driven, end-to-end governed task. This is a visual replay of the retained `ASTRON_REAL_MODEL_END_TO_END_PROOF_V1` evidence, not a new run.

**Recommended duration:** 35–45 seconds.

## On-screen sequence

1. **Task contract** — Show the bounded request: change only `MAX_RPS` from `10` to `20`, preserve the other two constants, and deliver the report.
2. **Model proposals and runtime authority** — Show the aggregate record: `5` provider calls → `5` model decisions → `5` proposed actions. Pair each proposal with its runtime authorization and journaled execution. Summary: `5/5` authorized, `5/5` executed and journaled, `0` denied.
3. **Result** — Show `MAX_RPS: 10 → 20`, then the delivered `.astron-artifacts/limiter-report.json` and its digest:

   ```text
   SHA-256 3c0a0c51248b9f9431bc869d8e6776b8ce882d0479ae9dba33eb4e258652c173
   ```

   Label the digest comparison `independently recomputed = durable record`.
4. **Completion** — End on the two passing criteria, durable `ACCEPTED` verification, and final `TASK_SUCCEEDED` state. For the exact event order, use Scene 2.

## Voiceover

> “In one controlled repository task, the requested model made five decisions. Astron authorized and journaled all five actions. The task changed `MAX_RPS` from 10 to 20 and delivered an artifact whose independently recomputed SHA-256 matched the durable record. Both declared acceptance criteria passed before the task succeeded.”

## Persistent qualification

Display in a readable lower-third or end card:

> “One controlled real-model task; not a statistical reliability sample. Requested model ID: `deepseek-flash`; provider-returned model identity was not durably recorded. Zero bypass and zero unjournaled execution were observed within captured application evidence.”

If showing write-scope observations, add:

> “No out-of-scope workspace writes were observed in application records and before/after workspace snapshots; this is not an OS-wide write audit.”

## Evidence anchors

- `ASTRON_COMPETITION_EVIDENCE_BASELINE_V1.md` §7: task scope, counts, artifact SHA-256, acceptance results and completion state.
- `ASTRON_COMPETITION_EVIDENCE_BASELINE_V1.md` §0: canonical proof identity and evidence-level definitions.
- `ASTRON_COMPETITION_EVIDENCE_BASELINE_V1.md` §11–12: approved wording and limitations.
- `01_POSITIONING.md` (“Three contributions” and “Primary hook and slogan”); `03_TECH_REPORT_CORE.md` §6; `04_DEMO_STORYBOARD.md` Scene 1; `06_JUDGE_QA.md` questions 11, 12, 18 and 19; `07_CLAIM_LANGUAGE_AUTHORITY.md` “SAFE TO CLAIM” and “QUALIFIED CLAIM”.

**Claim level:** A — live-proven for this one controlled task only.
