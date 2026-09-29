# Judge Q&A

> 版本边界：本材料依据历史证据基线 `11c6114f6ec0504628f912ebde9ba53821badb03`；只支持该基线对应的陈述，不构成 ZIP 中 `d32d3ec1bc49a78d0b14aabb6bf0daf79d3f4d88` 快照的运行或测试证据。详见同目录 README。


Answers follow the evidence and limits in `ASTRON_COMPETITION_EVIDENCE_BASELINE_V1`.

## 1. Why isn’t Astron just another Agent framework?

Astron’s focus is execution governance after a model proposes an action in a generic tool-calling agent: independent authorization, durable action facts, conservative recovery, and verifier-controlled completion. Planner, memory, RAG, skills, and tool calling are supporting capabilities, not the primary contributions. The claim is about Astron’s explicit runtime authority, not that other frameworks lack these mechanisms.

## 2. Why not use LangGraph?

LangGraph makes workflow and graph persistence a first-class abstraction through checkpoints and stores, as described in its [official Persistence documentation](https://docs.langchain.com/oss/python/langgraph/persistence). Astron focuses on execution authority, durable action lifecycle, and verification-controlled completion. The baseline contains no fair comparison, so it makes no superiority claim.

## 3. Isn’t this just permission control?

Permission answers whether an action may be attempted. Astron also records whether it was attempted and its result, handles uncertain outcomes through reconciliation, verifies the artifact and declared criteria, and gates durable task completion on acceptance.

## 4. Isn’t the Verifier just pytest?

No. A test runner can be one kind of check, but the Live Proof did not run pytest. Its verifier checked the declared acceptance criteria and artifact evidence, then controlled the durable completion transition. The proof records both criteria passing and accepted completion.

## 5. Why can’t the model decide completion?

The model’s statement is not evidence that the artifact exists, its digest matches, or each acceptance condition passes. In the Live Proof, `PROPOSE_COMPLETE` preceded verification; `TASK_SUCCEEDED` followed verifier acceptance.

## 6. What is different from checkpointing?

A checkpoint preserves task or application state. Astron’s action journal records the attempt boundary and outcome for each governed action. After interruption, a checkpoint alone may not tell whether a side effect occurred; action facts and reconciliation inform the recovery decision. For tested failure windows, retained runtime evidence and tests support these recovery semantics; the original per-process output directory is unavailable for line-by-line review in this audit.

## 7. What happens if timeout occurs after a side effect?

For tested failure windows, retained runtime evidence and tests support classifying an attempt with no trustworthy terminal result as `UNCERTAIN`. Astron reconciles against trusted external facts. Lack of evidence does not authorize blind retry; only trusted confirmation that the action was not applied can make it retry-eligible, followed by an explicit call. The original per-process output directory is unavailable for line-by-line review in this audit.

## 8. Does Astron guarantee exactly-once?

No. It does not guarantee arbitrary external systems execute exactly once. Retained runtime evidence and tests support semantics for specified actions and tested fault windows; original per-process outputs are unavailable for line-by-line review in this audit. External systems still need observable outcomes and safe idempotency or reconciliation strategies.

## 9. Does governance reduce Agent autonomy?

Governance constrains which proposed side effects may execute and who can accept completion. The model can still reason and propose actions. The baseline does not measure autonomy, so it makes no quantitative claim that governance increases or reduces it.

## 10. Why add another runtime layer?

To make authorization, action attempts and outcomes, uncertainty handling, and completion acceptance explicit runtime responsibilities. In the Live Proof, those records support review of a real task’s path from proposal through accepted completion.

## 11. What does the real Live Proof prove?

In one controlled repository task, the canonical `ASTRON_REAL_MODEL_END_TO_END_PROOF_V1` recorded five real provider calls and model decisions, five proposed and executed actions, all five authorized and journaled, the requested `MAX_RPS` change from 10 to 20, a produced artifact whose recorded SHA-256 matched an independent recomputation, two passing acceptance criteria, durable `ACCEPTED` verification, and final `SUCCEEDED` status. It also recorded no harness bypass or out-of-scope writes within the captured application and workspace evidence.

## 12. What does it NOT prove?

It does not confirm the provider-reported model identity: `deepseek-flash` is the requested model ID, while the returned model field was not durably recorded. It does not show recovery during that successful run, support for every model or external system, arbitrary exactly-once behavior, a fair advantage over generic agents or named frameworks, production reliability, or statistical reliability. The no-write observation is limited to application records and captured workspace snapshots.

## 13. Is Astron production ready?

The baseline does not establish production readiness. It contains one controlled real-model success and retained deterministic runtime/fault-window summaries for tested cases, but no production-scale reliability estimate, broad external-user replication, or current-commit full-suite test receipt. The original per-process fault outputs are unavailable for line-by-line review in this audit.

## 14. Why is Astron useful to open-source developers?

It makes execution responsibility inspectable: developers can review authorization records, action attempts and outcomes, reconciliation decisions, artifact evidence, and verifier acceptance. The baseline demonstrates this in a controlled repository-maintenance task. It does not claim broad ecosystem adoption or measured developer productivity gains.

## 15. Why does this fit AI+OpenSource?

It applies AI to a practical open-source development task and makes the resulting tool actions and acceptance evidence reviewable. The proof changed a repository source value and delivered a report under a governed workflow. This is a fit based on the demonstrated task, not a claim of comparative impact.

## 16. What should a judge remember after seeing Astron?

**AI 说完成，不等于任务真的完成。** The model proposes, the runtime decides, and the verifier accepts.

## 17. Did you prove recovery live?

No. The successful Live Proof demonstrated governed execution through verifier-accepted completion. Recovery evidence comes from separate runtime and fault-window tests and retained summaries for tested failure windows. The retained 15/15 fault-matrix summary is available, but its original per-process output directory is not currently present, so those outputs cannot be independently reinspected line by line in this review. Recovery is not statistically proven, and the successful Live Proof did not demonstrate recovery.

## 18. Did DeepSeek confirm the exact served model?

No. The run requested model ID `deepseek-flash`; the provider-returned model identity was not durably recorded. We can state the requested ID only.

## 19. Did you prove zero filesystem escape?

No OS-wide or all-process filesystem claim is made. No out-of-scope workspace writes were observed within the canonical run's application records and before/after workspace snapshot comparison. That observation does not establish that no write occurred elsewhere on the system.

## 20. Did this exact commit just pass the full suite?

No fresh full-suite run is established by this baseline consolidation. Retained project test records support the documented historical test status, but they are not a newly run, exact-commit full-suite receipt. The retained regression log lacks a binding to this source commit hash.
