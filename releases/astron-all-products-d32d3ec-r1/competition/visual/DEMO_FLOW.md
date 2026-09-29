# Judge Demo Flow

> 版本边界：本材料依据历史证据基线 `11c6114f6ec0504628f912ebde9ba53821badb03`；只支持该基线对应的陈述，不构成 ZIP 中 `d32d3ec1bc49a78d0b14aabb6bf0daf79d3f4d88` 快照的运行或测试证据。详见同目录 README。


## First 20 seconds

1. Open on the label **RECORDED VERIFIED RUN** and the one-task proof identity.
2. State Astron's role: an execution-governance runtime for tool-using agents.
3. Show the three responsibilities: model proposes, runtime decides, verifier accepts.
4. Deliver the hook: **AI 说完成，不等于任务真的完成。**

Do not begin with storage internals, schemas, or code symbols.

## Scene 1 — Real successful execution (40 seconds)

Use `SCREEN_01_EXECUTION_PROOF.html`.

- 0–8 s: show the bounded task and final task state.
- 8–20 s: reveal the untimed task/plan phases, then the five model decisions, five proposals, five authorizations, and five successful journaled executions.
- 20–29 s: show the single-line source change and the scoped “0 observed” note.
- 29–36 s: show the report artifact and digest match.
- 36–40 s: hold the eight-card evidence board.

Voiceover: “This recorded proof covers one controlled real-model-driven task. Five decisions led to five governed actions. All five were authorized and journaled. The requested change was made, and the artifact digest matched its independent recomputation.”

## Scene 2 — Verifier-controlled completion (35 seconds)

Use `SCREEN_02_VERIFIER_CONTROL.html`.

- 0–8 s: select `PROPOSE_COMPLETE` and hold the “NOT SUCCESS YET” divider.
- 8–18 s: show both acceptance criteria passing and the durable `ACCEPTED` result.
- 18–24 s: reveal `TASK_SUCCEEDED` after acceptance; show the exact recorded event numbers 43–47.
- 24–30 s: reveal the corrupt-artifact refusal in a separately labeled retained deterministic example.
- 30–35 s: hold the memory hook.

Voiceover: “The model proposed completion first. The verifier checked the two declared criteria, recorded acceptance, and only then did the task succeed. A separate retained deterministic example shows a corrupt artifact being refused.”

## Scene 3 — Action-aware recovery (45 seconds)

Use `SCREEN_03_ACTION_AWARE_RECOVERY.html`.

- 0–6 s: show the qualification banner and separation from the successful proof.
- 6–16 s: follow `ACTION_PROPOSED → AUTHORIZED → ATTEMPT_STARTED → OUTCOME UNKNOWN → UNCERTAIN → RECONCILIATION`.
- 16–29 s: reveal reconciliation and the three outcomes.
- 29–36 s: show the retained `15/15` summary with its tested-window qualifier.
- 36–42 s: show the raw-output review limitation.
- 42–45 s: close on **Timeout ≠ no side effect**.

Voiceover: “This is separate runtime and tested-failure-window evidence. An uncertain outcome requires reconciliation. Missing evidence does not authorize retry; trusted confirmation that an action was not applied can make it retry-eligible, followed by an explicit call.”

## Comparison insert

`SCREEN_04_GENERIC_AGENT_VS_ASTRON.html` is a short optional inset during the opening or Scene 1. Use equal visual weight and the caption **Astron changes execution responsibility, not model intelligence.** It is a responsibility diagram, not a comparative experiment.

## Delivery checks

- Keep **RECORDED VERIFIED RUN** visible on every positive-proof screen.
- Do not call the replay “live.” Do not show a current execution cursor, clock, or fabricated timestamps.
- Keep recovery visually separate from the positive proof.
- Keep the requested-model caveat and captured-scope caveat available wherever their facts appear.
- No Provider call, Astron run, test, or new evidence is required to present this flow.
