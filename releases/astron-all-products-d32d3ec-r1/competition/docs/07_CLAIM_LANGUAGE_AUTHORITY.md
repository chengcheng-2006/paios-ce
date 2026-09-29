# Claim Language Authority

> 版本边界：本材料依据历史证据基线 `11c6114f6ec0504628f912ebde9ba53821badb03`；只支持该基线对应的陈述，不构成 ZIP 中 `d32d3ec1bc49a78d0b14aabb6bf0daf79d3f4d88` 快照的运行或测试证据。详见同目录 README。


This file governs public wording for Astron Competition Evidence Baseline V1. Keep claims within the named evidence scenarios and levels.

The primary comparison target is a generic tool-calling agent. No fair comparative experiment is available, so this file does not authorize superiority claims about generic agents or named frameworks.

## SAFE TO CLAIM

- “Astron completed one real-model-driven end-to-end governed task.” This refers to the controlled task in `ASTRON_REAL_MODEL_END_TO_END_PROOF_V1`.
- “All five executed actions in the canonical proof were authorized and journaled.” The proof records five authorized actions and five journaled executions.
- “The required artifact was produced, and its recorded SHA-256 matched an independently recomputed SHA-256.”
- “Successful completion followed verifier acceptance.” The two declared criteria passed, durable verification was recorded as `ACCEPTED`, and the task reached `SUCCEEDED` afterward.
- “Astron separates model proposals from runtime authorization.” In the described path, proposals do not provide principal authority; the runtime checks authority and scope.
- “Astron is an execution-governance runtime for tool-using AI agents.” Its focus is authorization, durable action facts, and verifier-controlled acceptance. Recovery semantics for tested windows remain a qualified claim below.
- “AI 说完成，不等于任务真的完成。” In the canonical proof, `PROPOSE_COMPLETE` preceded verifier acceptance and task success.

## QUALIFIED CLAIM

- Recovery: “Action-aware recovery is supported by retained fault-matrix summaries and runtime tests for tested failure windows.” Keep this separate from the successful Live Proof; recovery was not demonstrated in that run. The retained 15/15 summary exists, but its original per-process output directory is unavailable for line-by-line reinspection in this review. Do not describe the outputs as independently reverified here.
- Model identity: “The run requested model ID `deepseek-flash`.” The provider-returned model identity was not durably recorded; only the requested model ID is supported.
- Write scope: “No out-of-scope workspace writes were observed in the canonical run's application records and before/after workspace snapshot comparison.” This is an application/workspace observation boundary, not an OS-wide or all-process filesystem audit.
- Test status: “Retained project test records support the documented test status.” The consolidation did not rerun the full suite; the retained regression log is not bound to the current source commit hash and is not a fresh exact-commit receipt.
- “Astron completed a real-model task with five decisions and five governed actions.” It is one controlled task, not a statistical reliability sample or evidence for every model or tool.
- “The run observed zero harness bypass and zero unjournaled executed actions.” Attribute this to the saved intents, journals, receipts, application events, and captured scope; do not expand it to unobservable systems or all future adapters.

## PROHIBITED CLAIM

- “Production reliability proven,” “production ready,” or equivalent reliability guarantees.
- “Exactly-once guaranteed” for arbitrary tools, services, or external systems.
- “Absolutely safe,” “cannot fail,” or “zero risk.”
- “Industry first,” “globally unique,” or equivalent novelty claims.
- “Superior to LangGraph,” “superior to AutoGen,” “better than generic agents,” or any measured success-rate advantage. No fair comparison was performed.
- “All models supported” or a claim that every model/provider behaves correctly.
- “Zero possible secret leakage” or an absolute claim about data exposure.
- “The provider confirmed it served `deepseek-flash`.” Only the requested model identifier is evidenced.
- “The successful Live Proof demonstrated crash recovery.” Recovery evidence comes from separate runtime and deterministic fault-injection runs.
- “Statistically improved success rate” or any statistical reliability improvement claim.
