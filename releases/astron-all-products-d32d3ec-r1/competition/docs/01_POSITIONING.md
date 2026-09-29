# Astron positioning

> 版本边界：本材料依据历史证据基线 `11c6114f6ec0504628f912ebde9ba53821badb03`；只支持该基线对应的陈述，不构成 ZIP 中 `d32d3ec1bc49a78d0b14aabb6bf0daf79d3f4d88` 快照的运行或测试证据。详见同目录 README。


## 中文定位

Astron 是面向通用 Tool-Calling Agent 的执行治理运行时。它不负责让模型变得更聪明，而是把模型提出的动作变成可授权、可追踪、可恢复、可验证的执行事实。模型提出动作；受信任的运行时依据独立身份、权限和范围决定动作能否执行。只有 Verifier 按预先声明的验收条件核验并持久记录后，任务才算完成。对已测故障窗口，留存运行时证据支持依据动作事实恢复的语义；原始逐进程输出当前不可逐条复查。

## English positioning

Astron is an execution-governance runtime for tool-using AI agents, turning model proposals into authorized, durable and independently verified execution. The model proposes actions; a trusted runtime uses independent identity, permissions, and scope to decide whether they may execute, and durably records authorization, attempts, outcomes, and verification. For tested failure windows, retained runtime evidence supports recovery based on action facts; the original per-process outputs are unavailable for line-by-line review in this audit. A task is complete only after a Verifier checks its declared acceptance conditions and records the result durably.

## One-line problem

模型的“完成”回答不能单独证明动作是否获准、是否发生、交付物是否有效，或任务是否应被接受。

## Target users

- 构建会通过工具产生真实副作用的 Agent 的工程团队。
- 需要复核动作授权、执行结果、中断恢复和任务验收记录的团队。
- 希望把模型建议与执行权限、动作事实及完成判定分开的产品和平台团队。

## What Astron is

- 面向通用 Tool-Calling Agent 的执行治理运行时。
- 让模型提出动作，由运行时依据可信身份、授权和有限范围决定是否执行。
- 记录动作尝试和结果，并在结果不确定时依据可信外部事实核对。
- 由 Verifier 按声明的验收条件检查交付物，并控制耐久的任务完成状态。
- 当前比赛路径是受控仓库维护任务。

## What Astron is not

- 不是让模型更聪明的产品定位，也不是任意系统操作平台。
- 不声称独占授权、动作日志或验收机制，也不声称通用 Agent 缺少这些机制。
- 不保证任意外部系统的 exactly-once，不证明绝对安全或生产可靠性。
- 不证明优于通用 Agent 或特定框架，也不能确认 Provider 实际返回的模型名称。

## Three contributions

1. **Trusted Execution Separation（可信执行分离）** — 模型输出仍是提议；运行时根据可信 principal、权限和有限操作范围决定执行。在一次受控真实模型任务中，五个动作均获授权、执行并记入日志。
2. **Verifier-Controlled Completion（Verifier 控制完成）** — Verifier 复核交付物摘要和声明的验收结果，再将接受结论写入耐久状态。该次实跑先记录模型的完成提议，随后两项条件通过，最后才记录任务成功。
3. **Action-Aware Recovery（面向动作事实的恢复）** — 执行前记录尝试；中断后若没有可信终态则标记为不确定，要求核对外部事实，避免把缺少回复当作安全重试依据。此主张由已测窗口的留存运行时与确定性故障证据支持，与成功实跑分开；不表示本次重新播放或复查了原始故障输出。

## Primary hook and slogan

**AI 说完成，不等于任务真的完成。**

**An AI saying it is done does not mean the task is actually complete.**

## Pitches

### 20 seconds

AI Agent 能提出动作，但一句“完成”不能证明动作获准、结果落地或任务达标。Astron 是面向通用 Tool-Calling Agent 的执行治理运行时：它记录并约束真实动作，由 Verifier 按条件确认完成。

### 60 seconds

AI Agent 调用工具时，团队需要知道的不只是模型想做什么，还包括动作是否获准、是否真的发生、中断后能否安全继续，以及交付物是否符合要求。Astron 是面向通用 Tool-Calling Agent 的执行治理运行时：模型提出动作，可信运行时决定是否执行并留下动作事实；若结果不确定，运行时要求依据外部事实核对；最后由 Verifier 检查预先声明的验收条件并耐久记录完成状态。一次受控真实模型任务完成了五次受治理动作，修改了 `MAX_RPS`，独立复算交付物 SHA-256 并匹配耐久记录值，两项条件通过后由 Verifier 接受并记录任务成功。恢复能力来自与该实跑分开的、针对已测窗口的留存运行时和确定性故障证据。

### 180 seconds

AI Agent 的回答、工具的返回值和用户任务的完成，是不同的事实。模型能提出动作，却不能凭自己的输出授予权限，也不能单独证明副作用是否发生、交付物是否有效或任务是否应该结束。Astron 是面向通用 Tool-Calling Agent 的执行治理运行时，核心是把这些执行责任交给受信任的运行时和独立验收流程。

模型提出动作后，运行时根据可信身份、权限和当前范围决定是否允许执行，并耐久记录授权、尝试和结果。如果任务在动作执行附近中断，缺少结果不被当成可以安全重试的证据；未得到可信终态的动作被视为不确定，需要根据外部事实核对。任务结束时，Verifier 会复核声明的验收条件和交付物摘要，并将接受结果耐久记录。这样，模型提出完成与任务真正成功之间有可复核的判定过程。

在 `ASTRON_REAL_MODEL_END_TO_END_PROOF_V1` 中，一项受控仓库任务使用五次真实 Provider 调用和五次模型决策，完成五次受治理动作；`MAX_RPS` 从 `10` 改为 `20`，交付物 SHA-256 独立复算后与耐久记录一致，两项验收条件通过后由 Verifier 接受，任务进入成功状态。这是一个受控任务的完整正向执行链，不是统计可靠性样本。保存的启动命令证明请求了 `deepseek-flash`，但结果没有记录 Provider 返回的模型字段，因此无法确认服务端实际报告的模型名称。保守恢复则由与该成功实跑分开的、针对已测窗口的留存运行时及确定性故障证据支持；成功实跑本身没有崩溃或重启。当前没有公平通用 Agent 对照，亦无生产规模可靠性证据，所以 Astron 不据此主张性能优势、普遍 exactly-once 或生产可靠性。
