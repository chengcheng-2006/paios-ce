# Scene 2 — Verifier-Controlled Completion

> 版本边界：本材料依据历史证据基线 `11c6114f6ec0504628f912ebde9ba53821badb03`；只支持该基线对应的陈述，不构成 ZIP 中 `d32d3ec1bc49a78d0b14aabb6bf0daf79d3f4d88` 快照的运行或测试证据。详见同目录 README。


**Purpose:** Make the completion authority visible: a model's completion proposal is followed by verification; only verifier acceptance and durable recording precede task success.

**Recommended duration:** 30–40 seconds.

## On-screen sequence: canonical positive proof

Replay the same `ASTRON_REAL_MODEL_END_TO_END_PROOF_V1` event sequence. Preserve the recorded order and labels:

```text
43 PROPOSE_COMPLETE
44 VERIFICATION_STARTED
45 VERIFICATION_RESULT: ACCEPT
46 VERIFICATION_ACCEPTED
47 TASK_SUCCEEDED
```

Alongside the event rail, show the actual declared criteria:

```text
AC-CeilingRaised   PASS
AC-ReportDelivered PASS
task_verifications.status = ACCEPTED
runtime task = TASK_COMPLETED
Agent task = SUCCEEDED
```

Use a visual pause between `PROPOSE_COMPLETE` and `VERIFICATION_ACCEPTED`; do not depict the proposal itself as changing task status. End with the memory hook:

> **AI 说完成，不等于任务真的完成。**

## Retained deterministic negative example

After the positive event rail, show a clearly separated card:

```text
DETERMINISTIC FAULT-MATRIX SUMMARY — NOT A LIVE-PROOF EVENT
Corrupt artifact → Verifier refusal
```

Caption it:

> “A retained deterministic fault-matrix summary records refusal for a corrupted artifact. This is a separate test example, not a replay or new run, and not part of the successful real-model task.”

Do not add an invented event number, timestamp, run transcript, or claim that this case was rerun or independently rechecked at raw-output level.

## Voiceover

> “The model proposed completion first. The Verifier then checked both declared criteria. Only after acceptance was durably recorded did the task succeed. In a separate retained deterministic test summary, a corrupted artifact is refused. These two records show why a completion claim and an accepted task are different states.”

## Evidence anchors and claim level

- Positive sequence and criterion results: `ASTRON_COMPETITION_EVIDENCE_BASELINE_V1.md` §5 item 2, §7 event order and verification table, and §13 Verifier evidence row.
- Negative example: `ASTRON_COMPETITION_EVIDENCE_BASELINE_V1.md` §8 (retained fault-matrix summary) and §13 (Verifier row: damaged-artifact refusal). Treat as a retained summary only; the original per-process output directory is unavailable for line-by-line review.
- Supporting wording: `01_POSITIONING.md` (“Verifier-Controlled Completion” and primary hook); `03_TECH_REPORT_CORE.md` §§2, 4 and 6; `04_DEMO_STORYBOARD.md` Scene 2; `06_JUDGE_QA.md` questions 4, 5 and 16; `07_CLAIM_LANGUAGE_AUTHORITY.md` “SAFE TO CLAIM”.

**Positive sequence claim level:** A — live-proven for this one controlled task.<br>
**Corrupt-artifact example claim level:** retained deterministic fault-matrix summary; separate from Live Proof, without raw per-process output reinspection.
