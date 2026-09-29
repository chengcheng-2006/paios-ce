# Action-Aware Recovery — Qualified Runtime / Fault-Window Evidence

> 版本边界：本材料依据历史证据基线 `11c6114f6ec0504628f912ebde9ba53821badb03`；只支持该基线对应的陈述，不构成 ZIP 中 `d32d3ec1bc49a78d0b14aabb6bf0daf79d3f4d88` 快照的运行或测试证据。详见同目录 README。


> **Evidence level: B — qualified runtime/fault-window evidence.** This scene is separate from `ASTRON_REAL_MODEL_END_TO_END_PROOF_V1`. Recovery was not demonstrated in the successful Live Proof.

## On-screen story

Show a state diagram for one governed action interrupted after its attempt began but before a trustworthy terminal result was durably recorded:

```text
ACTION_PROPOSED
    ↓ runtime authorization decision
AUTHORIZED
    ↓ persist attempt boundary
ATTEMPT_STARTED
    ↓ process interruption; outcome not durably known
UNCERTAIN
    ↓ reconcile against trusted external facts
    ├─ confirmed applied  → CONFIRMED_SUCCEEDED → terminal success; do not repeat
    ├─ confirmed not applied → CONFIRMED_NOT_APPLIED → RETRY_ELIGIBLE
    │                                                   ↓ explicit call still required
    └─ no trustworthy evidence → NO_EVIDENCE → remain unresolved; no retry
```

`NO_EVIDENCE` does not grant retry eligibility. Only trusted `CONFIRMED_NOT_APPLIED` can make the action retry-eligible, and that status still does not execute it: a subsequent explicit call is required. A confirmed success is terminal and is not repeated.

**Takeaway:** Timeout ≠ no side effect.

## Judge-facing narration

> “For tested failure windows, retained runtime evidence supports action-aware recovery. When an attempt has no trustworthy terminal result, Astron marks it uncertain and reconciles against external facts. It does not treat missing evidence as permission to retry.”

## Evidence and qualification

- The baseline classifies this as **B: runtime or process fault-injection evidence**, scoped to tested failure windows. Real subprocess tests cover interruption before the side effect, after a side effect but before terminal persistence, after terminal success, and after terminal failure.
- A retained deterministic fault-matrix summary reports **15/15**. Its original per-process output directory is unavailable; this review cannot independently reverify the raw output line by line or replay it. Present the summary only with that limitation. It is not a current-commit regression receipt.
- The positive Live Proof completed without a crash or restart. Do not intercut this diagram as if it occurred in that run.
- This does not establish arbitrary external-system exactly-once behavior, production-scale reliability, or coverage beyond the named tested windows.

## Capture direction

Use a clearly labeled explanatory state diagram and the retained-summary count. Do not present it as a playable per-event crash recording or imply new execution. Keep the on-screen qualifier visible: **“Qualified runtime / fault-window evidence; separate from Live Proof. Retained 15/15 summary; raw per-process output unavailable for line-by-line reinspection.”**

**Evidence basis:** `ASTRON_COMPETITION_EVIDENCE_BASELINE_V1` §§8, 10, 12–13; `03_TECH_REPORT_CORE.md` §7; `04_DEMO_STORYBOARD.md` Scene 3; `06_JUDGE_QA.md` §§6–8, 13, 17; `07_CLAIM_LANGUAGE_AUTHORITY.md` Qualified Claim, Recovery.
