# ASTRON COMPETITION EVIDENCE BASELINE V1

> 发布副本说明：本报告对应旧源码提交 `11c6114f6ec0504628f912ebde9ba53821badb03`，不是交付快照 `d32d3ec1bc49a78d0b14aabb6bf0daf79d3f4d88` 的验证报告。公开副本仅将本机绝对路径改为根目录占位符、并将两个本地文件链接改写为相对路径说明；报告中的证据摘要和结论未改。原始运行证据包未随本目录公开。

## 0. Baseline Identity

| 项目 | 本基线的可核验值 |
| --- | --- |
| 产品 | Astron |
| 基线 | `ASTRON_COMPETITION_EVIDENCE_BASELINE_V1`，首份正式比赛证据基线 |
| 产品源码根目录 | `PRODUCT_ROOT`（本机绝对路径已脱敏） |
| 源码提交 | `11c6114f6ec0504628f912ebde9ba53821badb03` |
| 源码树 | `2d0e6477c7d4e083bbd23e44a7228b7eedb47e24` |
| 工作树 | 核验时 `git status --porcelain=v1` 为空 |
| 实跑证据根目录 | `EVIDENCE_ROOT`（本机绝对路径已脱敏） |
| 比赛用实跑名称 | `ASTRON_REAL_MODEL_END_TO_END_PROOF_V1` |
| 本次整理 | 只读；新增 Provider 调用、产品运行和测试运行均为 `0` |

**证据定位约定。** `PROOF_DIR` 指 `EVIDENCE_ROOT` 下包含唯一一份 SHA-256 为 `c64a134b8a63d3cb98242753e8d84d613c498be113f1d3ce08b80f2011b67445` 的 `run-dir/smoke-result.json` 的归档目录。`MANIFEST_CURRENT` 指 `EVIDENCE_ROOT` 根目录下 SHA-256 为 `05fe3795fa13ac8c625b1a9078b3a0b6183e8b35b4a3af548b6ec4f70457ab8a` 的 22 行 `.sha256` 清单。下文的 `PROOF_DIR/run-dir/...` 是可由结果摘要唯一解析的路径。归档原有工程记录继续保留；比赛叙事只使用上述实跑名称。源码路径均相对 `PRODUCT_ROOT`，测试和证据路径按本节根目录解析。

**证据等级。** `A`＝真实模型单次实跑直接证明；`B`＝运行时或进程故障注入证明；`C`＝自动化测试证明；`D`＝有源码实现、尚无对应运行证明；`E`＝仅设计。等级只覆盖列明的场景，不自动外推到其他模型、工具、外部系统或生产环境。

## 1. Executive Summary

Astron 是面向通用 Tool-Calling Agent 的执行治理运行时。它不以让模型更聪明为主要目标，而是改变模型建议与真实动作之间的权力边界：模型提出动作，受信任的运行时依据独立的身份、权限和范围决定能否执行，并把授权、尝试、结果与验收分别写成耐久事实。任务中断后，运行时读取动作日志判断哪些效果可能已经发生；结果不确定时要求基于外部事实核对，而不把缺少回复当成安全重试的理由。模型说“完成”、工具返回成功和用户任务被接受是三种不同状态；只有预先声明的验收条件经 Verifier 检查并写入耐久记录，任务才能成功。在本基线的一次真实模型任务中，Astron 完成五次受治理动作，将任务工作区中的 `MAX_RPS` 从 `10` 改为 `20`，生成并校验交付物摘要，两项验收条件均通过，最终留下 `TASK_SUCCEEDED`。这证明了当前受控任务的完整执行链；恢复能力由另外的确定性故障证据支持。它强调可被团队复核的执行事实，而非模型对自身表现的评价。

## 2. What Astron Is

**定位：** Astron 是面向通用 Tool-Calling Agent 的执行治理运行时。模型可以形成计划和动作提议；运行时负责可信身份、授权、有限工具执行、耐久动作事实、保守恢复和任务验收。当前比赛路径是受控仓库维护任务，并非任意系统操作平台。架构说明（基线源码相对路径 `docs/ARCHITECTURE.md`）与安全边界（基线源码相对路径 `docs/SECURITY_MODEL.md`）给出源码侧定义。

| 能力 | 本基线中的角色 |
| --- | --- |
| Planner、Skills、Context Manager | 帮助形成和约束提议的支持能力；不自行授予权限 |
| Project Memory、RAG Lite | 为提议提供上下文的支持能力；检索文本不是授权主体 |
| Tool Calling | 模型与工具运行时之间的接口；调用意图仍须过治理边界 |
| SQLite | 保存授权、动作、核对和验收事实的实现设施；数据库选型本身不是创新主张 |
| Checkpoint | 恢复所需的一种记录；必须结合动作日志及核对结果解释 |

## 3. Problem Definition

核心问题是**执行责任**：某个动作是否有资格发生、是否实际发生、中断后留下什么可依赖的事实、交付物是否有效，以及谁有权宣布任务结束。模型回答可以说明意图，不能单独证明这些事实。

| 待回答的问题 | Astron 指定的权威事实 |
| --- | --- |
| “允许执行吗？” | 独立于模型请求的可信 principal、权限决策和当前安全上下文 |
| “执行了吗？” | 授权记录、动作日志、执行回执及其状态 |
| “超时或崩溃后能重试吗？” | `ATTEMPT_STARTED`、`UNCERTAIN` 与可信核对结果 |
| “交付物有效吗？” | 重新读取文件的摘要与声明的验收条件 |
| “谁能说完成？” | Verifier 接受并写入耐久任务验收记录 |

这是一组关于权限、耐久性和核验的工程问题；其论证范围不等于“所有 AI 都不安全”。

## 4. Generic Tool-Calling Agent vs Astron

**公平比较对象：通用 Tool-Calling Agent。** 此类 Agent 可以已有 Planner、Memory、RAG、Skills、重试、工具调用与上下文管理；这里不把它们描绘成缺失能力。下面比较的是责任由谁承担，不是宣称所有现有框架缺少治理机制。

```text
通用形态：用户 → LLM → 可选 Planner / Memory / RAG / Skills
                 → Agent Loop → Tool Call → Tool → 模型最终回答

Astron 形态：用户 → Agent Intelligence → Action Proposal
             → Execution-Governance Runtime → Authorization
             → Governed Tool Execution → 耐久动作事实 / 交付物
             → Verifier → Accepted Completion
```

| 责任 | 通用形态中可由应用自行安排 | Astron 当前明确的运行时权威 |
| --- | --- | --- |
| 选择下一步 | 模型、Planner 或应用 | Agent Intelligence；不是三项核心差异之一 |
| 允许副作用 | 应用自定的工具和政策 | 可信 principal、Permission Engine、受限工具表及授权回放身份 |
| 解释中断后的动作 | 应用自定的持久化与核对逻辑 | 动作日志先记尝试，再按 `UNCERTAIN` 和核对事实决定后续 |
| 宣布完成 | 应用自定的结束条件 | 声明式验收条件、Verifier、耐久 `TASK_COMPLETED` 转移 |

Astron 把这些执行责任设为一等运行时权威。它不声称自己独占这些机制，也没有完成与某个当代通用 Agent 的公平对照实验。

## 5. Three Core Contributions

本基线只将以下**三项**列为核心贡献。每一项同时列出源码、测试和运行证据；某个场景的证据不替另一场景背书。

1. **Trusted Execution Separation（可信执行分离）— A，限于当前实跑。** 模型输出进入 `ToolRouter` 后仍只是数据。`BoundedToolRuntime` 以运行时给定的 principal 和有限操作表构造请求，经 `PermissionEngine` 与 `DurableActionRuntime` 决定是否执行。源码：`src/paios_ce/agent/router.py:326-367`、`src/paios_ce/tools/bounded.py:45-147`。测试：`tests/agent_v0/test_governance_invariants.py` 的未治理执行/耐久日志约束，以及 `tests/security/test_idempotency_replay_security.py`。实跑：五个动作各有提议、授权、日志和成功回执，五个授权决策在权威存储中为 `allow`；没有观察到绕过路径。参见 §7、§13。

2. **Verifier-Controlled Completion（Verifier 控制完成）— A，限于当前实跑。** `CompletionAuthority` 先复核交付物摘要和每项验收结果，再把 Verifier 的结论交给耐久存储；存储拒绝未解决动作或缺少动作日志的接受结果。源码：`src/paios_ce/agent/completion.py:86-207`、`src/paios_ce/state/durable.py:1016-1105`。测试：`tests/agent_v0/test_agent_loop.py` 中缺 Verifier、未耐久记录、接受和拒绝分支；`tests/agent_v0/test_verification.py` 中动作日志前置条件。实跑：先出现 `PROPOSE_COMPLETE`，随后两项条件均 `PASS`，`task_verifications=ACCEPTED`，最后才出现 `TASK_SUCCEEDED`。

3. **Action-Aware Recovery（面向动作事实的恢复）— B，限于已测故障窗口。** `DurableActionRuntime` 在调用执行器前持久化 `ATTEMPT_STARTED`；无终态的尝试被归入 `UNCERTAIN`，可信核对只观察外部事实，不能借恢复重新执行动作。源码：`src/paios_ce/runtime/durable_runtime.py:71-166`、`src/paios_ce/state/durable.py:764-932`、`src/paios_ce/agent/orchestrator.py:841-889`。测试与运行证据：`tests/recovery/test_process_crash_recovery.py` 的真实子进程退出窗口、`tests/agent_v0/test_recovery.py` 的任务恢复路径以及留存的确定性故障结果。**成功实跑没有发生崩溃或重启；它不是本项恢复主张的实跑证据。**

## 6. System Architecture

```text
可信任务约束 ─────────────────────────────────────────────┐
用户 → Agent / 模型 → 动作提议 → ToolRouter → 受限工具运行时 │
                                      ↓                     │
                         可信 principal + Permission Engine │
                                      ↓                     │
                         授权回放记录 + Action Journal       │
                                      ↓                     │
                         ATTEMPT_STARTED → 工具执行          │
                                      ↓                     │
                         结果 / UNCERTAIN → 核对与恢复       │
                                      ↓                     │
                         文件 / 交付物 → Verifier ←───────────┘
                                      ↓
                         ACCEPTED → 耐久 TASK_COMPLETED
```

`ActionRequest` 不提供 principal 权威；运行时另行传入 `PrincipalContext`。授权回放绑定幂等键、可信 principal、规范化请求指纹及当前安全上下文指纹。授权记录不能代替执行记录；Checkpoint 不能代替动作日志；Agent Store 中的计划、记忆和检索结果不能提升权限。源码总览（基线源码相对路径 `docs/ARCHITECTURE.md`）与§13给出入口、符号和测试。

## 7. Real-Model End-to-End Proof V1

**比赛可用表述：**“在 Astron Competition Evidence Baseline V1 下，当前 Astron V1 完成了一项由真实模型驱动、端到端受治理的任务。”本次 `PROVIDER_ID=openai_compatible` 和 `REQUESTED_MODEL=deepseek-flash` 由保存的启动命令证明；运行结果没有记录 Provider 返回的 model 字段，故 `PROVIDER_REPORTED_MODEL=NOT_RECORDED`，**无法确认服务端实际报告的模型名称**。

任务约束只允许把 `src/limiter.py` 中 `MAX_RPS = 10` 改成 `MAX_RPS = 20`，保留另两个常量，随后用受治理的交付工具写出 `.astron-artifacts/limiter-report.json`。声明的条件为 `AC-CeilingRaised` 和 `AC-ReportDelivered`；该任务没有授予终端能力，也未运行 pytest 工具。证据为 `PROOF_DIR/run-dir/smoke-result.json`、工作区文件、两个 SQLite 权威存储和归档摘要清单。

| 核验项 | 独立复核结果 |
| --- | --- |
| `REAL_PROVIDER_CALLS` / `MODEL_DECISIONS` | `5 / 5`；决策事件累计调用数为 `1…5` |
| `TOOL_ACTIONS_PROPOSED` / `TOOL_ACTIONS_EXECUTED` | `5 / 5`；三次读取、一次精确补丁、一次交付物写入 |
| `AUTHORIZED_ACTIONS` / `DENIED_ACTIONS` | `5 / 0`；五个权威授权记录均为 `allow` |
| `HARNESS_BYPASS` / `UNJOURNALED_EXECUTED_ACTIONS` | `0 / 0`，按保存的意图、日志、回执与应用事件核对 |
| `JOURNALED_EXECUTED_ACTIONS` | `5`；五条日志均为 `SUCCEEDED`，每条有授权、开始尝试和终态事件 |
| 源码结果 | `MAX_RPS: 10 → 20`；`BURST_WINDOW_SECONDS=5` 和 `METRIC_PREFIX="edge_"` 保持不变 |
| `FORBIDDEN_MUTATIONS` / `OUT_OF_SCOPE_WRITES` | 已观察到 `0 / 0`；初始两文件摘要、最终文件清单及五条意图一致，范围见§12 |
| 两项验收条件 | `AC-CeilingRaised=PASS`；`AC-ReportDelivered=PASS` |
| 耐久验收与任务 | `task_verifications.status=ACCEPTED`；`runtime_tasks.runtime_state=TASK_COMPLETED`；Agent 任务 `SUCCEEDED` |

交付物存在，大小 `128` 字节；记录与本次从磁盘重算的 SHA-256 均为 `3c0a0c51248b9f9431bc869d8e6776b8ce882d0479ae9dba33eb4e258652c173`。初始 `src/limiter.py` 的保存摘要为 `a524dccbaa0808b82044d33cd85cdd35b7b42c2b200d2daf4f445562102cd373`；改动后 SHA-256 为 `321fea911a576c4a7d8cd219cb28dea318527e75b265385c2a16613e5caf36f0`；未改动的 `docs/rate-limits.md` 为 `9b729c72b65d110669727c35c02ca35a1ae166c4789b5b7cbab8690846f3408f`。`MANIFEST_CURRENT` 的 22 个成员均已重算且一致。

**完成链的实际顺序：**事件 `43 PROPOSE_COMPLETE` → `44 VERIFICATION_STARTED` → `45 VERIFICATION_RESULT: ACCEPT` → `46 VERIFICATION_ACCEPTED` → `47 TASK_SUCCEEDED`。模型建议结束发生在 Verifier 接受之前。五个动作的 `action_journal.authorization_decision` 与 `authorization_replays.decision` 均保留真实 `allow` 值；事件投影的脱敏问题不改变这一权威事实。

## 8. Runtime / Recovery / Security Evidence

**运行时及故障注入证明（B，与§7分开）：** 动作状态按 `AUTHORIZED → ATTEMPT_STARTED → SUCCEEDED / FAILED / UNCERTAIN` 记录。进程在副作用后、终态持久化前退出时，恢复为 `UNCERTAIN`；`NO_EVIDENCE` 不产生重试资格。仅可信的 `CONFIRMED_NOT_APPLIED` 可写入 `RETRY_ELIGIBLE`，其后仍需显式调用；可信确认已成功时核对为终态成功，不重复副作用。真实子进程故障测试覆盖前置窗口、副作用后、终态成功后和终态失败后退出。留存的固定故障矩阵为 `15/15`，但属于另一次确定性运行，不能写成此次真实模型任务发生过故障恢复。对应的原始进程输出目录目前不在本机；本次只能复查留存汇总、源码和测试定义，不能逐条重查原始故障输出，也不能将其称为当前提交的回归收据。`tests/agent_v1/test_p11_resume_v1.py` 还检查未解决动作拒绝直接 resume，以及已核对动作不重放。

**授权回放（B）：** 旧授权可在 SQLite 重新打开后恢复完整决策；相同幂等键配不同动作、参数、principal 或安全上下文时拒绝替换原记录。进程重启测试与固定故障矩阵支持这些受控场景。

**有限工具和越界拒绝（B）：** 有限工具表与工作区路径约束在固定故障矩阵中拒绝目录穿越和符号链接逃逸；未导出工具的拒绝另有自动化测试（C）。当前实跑的五个允许动作给出正向 A 证据；它的 `DENIED_ACTIONS=0`，不能用来证明拒绝路径。保留的回归日志记录 `1608 passed, 2 skipped`，此次未重跑，且该日志没有绑定本节的当前提交哈希。

**治理权威与可观测性：** 实跑的 `action_journal.authorization_decision` 和 `authorization_replays.decision` 是耐久授权权威。`agent_events.safe_details_json` 对 `authorization_decision` 过度脱敏，单看该投影无法分辨 `allow` 与 `deny`；它是非阻塞可观测性限制，不能误写成授权权威丢失。有界工具与授权测试只能支持对应边界，不能推出未来所有适配器零泄漏或绝对安全。

## 9. Judge Memory Hooks

**主记忆点：AI 说完成，不等于任务真的完成。** 本次实跑的模型先提出完成；两项条件经 Verifier 检查并耐久接受后，任务才成功。支持句：“模型提出动作，Runtime 决定动作是否有资格发生。”以及“恢复 Agent，应恢复真实动作发生到了哪一步。”英文架构句 **“The model proposes. The runtime decides. The verifier accepts.”** 分别由动作授权记录、动作日志和验收链支持。

### Judge Q&A

| 问题 | 可守住证据边界的回答 |
| --- | --- |
| 为什么不是又一个 Agent framework？ | 当前贡献落在提议之后的执行权威：授权、动作事实、保守恢复和验收。Planner、Skills、Memory 等是支持能力。 |
| 为什么不用 LangGraph？ | [LangGraph 官方文档](https://docs.langchain.com/oss/python/langgraph/persistence)已有 checkpoint 和 store。Astron 在本项目中把动作级授权、尝试日志、核对和 Verifier 验收具体实现并验证；尚无公平对照，不能宣称优于 LangGraph。 |
| 不就是权限控制吗？ | 权限只回答能否尝试；日志回答是否尝试及结果，核对处理不确定性，Verifier 决定任务是否满足合同。 |
| Verifier 不就是 pytest 吗？ | pytest 可作为某类条件的受限检查；本次实跑没有运行 pytest。Verifier 还复核声明的条件、交付物摘要，并控制耐久完成转移。 |
| 为什么模型不能直接说 Done？ | 自述不证明文件存在、摘要一致或条件通过。本次事件顺序显示 `PROPOSE_COMPLETE` 之后才验收。 |
| 与 checkpoint 有何不同？ | Checkpoint 保存状态；动作日志记录尝试边界和终态。只恢复对话或计划，无法判定中断前副作用是否已经发生。 |
| 超时后怎么办？ | 若已越过持久化尝试边界而无可信终态，归入 `UNCERTAIN`；先核对外部事实，不盲目重试。 |
| 如何避免重复副作用？ | 幂等身份防止错配回放；已成功动作不重做；不确定动作需可信核对。结论只覆盖已测动作与故障窗口。 |
| 保证 exactly-once 吗？ | 不保证任意外部系统的严格 exactly-once；外部系统仍须提供可观察结果和安全幂等/核对策略。 |
| 证明生产可靠性了吗？ | 没有。单次正向实跑与受控故障试验不足以给出生产规模、跨平台或统计可靠性结论。 |
| 真实模型实跑证明什么？ | 当前受控任务中五次模型决策走完授权、执行、交付物摘要、两项验收和耐久成功链。 |
| 它没有证明什么？ | 没证明 Provider 返回的模型标识、其他模型适用性、故障恢复发生于该次实跑、通用 Agent 性能优势或生产可靠性。 |

## 10. Competition Demo Story

最多三幕，全部使用已有证据；不为演示再造一次 Provider 运行。

1. **真实成功任务。** 展示保存的任务合同、五个模型决策与五个治理动作、`MAX_RPS: 10 → 20`、交付物及重算摘要。解说“模型提议，运行时决定并记录实际动作”。
2. **Verifier 控制完成。** 对照同一任务的 `PROPOSE_COMPLETE` 与后续 `VERIFICATION_STARTED → RESULT → ACCEPTED → TASK_SUCCEEDED`，并展示两项 `PASS` 和耐久验收行。解说“说完成并不会改变任务终态”。
3. **面向动作事实的恢复。** 展示留存的确定性故障矩阵汇总和真实子进程测试断言，据此解释“副作用后丢失结果 → `UNCERTAIN` → 可信核对 → 不重复执行”的状态过程。现有归档不提供可直接播放的逐事件故障轨迹；字幕明确标成“确定性故障证据”，不标成真实模型实跑片段。

## 11. Claim Ledger

### SAFE TO CLAIM

| 等级 | 可公开使用的精确表述 |
| --- | --- |
| A | 当前 Astron V1 在一个受控仓库任务中完成真实模型驱动的端到端受治理执行。 |
| A | 该任务有五次 Provider 调用、五次模型决策、五次经授权和日志记录的工具执行；拒绝与未记日志执行均未观察到。 |
| A | `MAX_RPS` 从 `10` 变为 `20`，交付物存在且 SHA-256 与耐久记录相同；两项验收条件通过后，任务状态为 `SUCCEEDED`。 |
| B | 在已测进程故障窗口中，Astron 以动作日志识别不确定状态，要求核对，并避免测试账本中的盲目重复副作用。 |
| C | 当前源码包含可信 principal、有限工具、授权回放及 Verifier 完成约束的对应测试；留存日志显示测试曾通过，未在本次只读整理中重跑。 |

### QUALIFIED CLAIM

| 等级 | 必须随主张附上的限定 |
| --- | --- |
| A | “请求 `deepseek-flash`”可说；Provider 实际返回的 model 字段未持久化，不能说服务端确认提供了该模型。 |
| A | “禁止变更和工作区越界写入为零”指受治理意图与前后工作区快照所观察的范围；并非操作系统级完整写入审计。 |
| B | 恢复、重放保护与故障注入属于独立运行时证据；成功实跑中没有崩溃、超时后的重启或核对事件。 |
| C | 留存测试日志不等于此次当前提交上新运行的精确哈希绑定测试收据。 |

### DO NOT CLAIM

“行业首创”或“全球唯一”；绝对安全；生产级可靠性已证；任意系统 exactly-once；优于 LangGraph 或 AutoGen；相对通用 Agent 具有更高成功率；所有模型均受支持；任何情况下都不会泄露密钥；本次成功实跑证明了崩溃恢复；Provider 已确认提供 `deepseek-flash`。

## 12. Known Limitations

1. 当前 Astron V1 的完整正向真实模型证明只有本基线这一个受控任务；它不是统计可靠性样本。
2. 保存了请求模型名称，未保存 Provider 回应中的 model 字段；模型服务身份仍未知。
3. 尚无与当前通用 Tool-Calling Agent 的公平任务、权限、工具和验收口径对照，不能推导性能优势。
4. 恢复主张主要来自确定性、真实子进程故障与运行时测试；未在本次真实模型成功链中触发中断或重启，也未覆盖任意外部服务。保留的 `15/15` 故障矩阵摘要仍可查，但其原始进程输出目录当前不在本机，无法逐项复查原始输出。
5. 尚无生产规模性能与广泛外部用户复现的证据。留存回归日志缺少当前提交哈希绑定，本次未运行测试。
6. Agent 事件投影过度脱敏授权决策；审计需读取权威动作日志和授权回放表。该问题不影响现有权威字段的保存。
7. 零越界写入与零绕过的证据来自应用记录及工作区前后快照，不能排除不可观察的瞬时文件或工作区外写入；宣传时应保留该范围。
8. 第三幕没有可直接播放的逐事件故障轨迹；现有材料为确定性故障矩阵汇总和相应测试断言。

## 13. Evidence Index

**定位方法。** 在 `EVIDENCE_ROOT` 对 `smoke-result.json` 计算 SHA-256，命中 §0 的摘要后取其上两级为 `PROOF_DIR`。对根目录的 `.sha256` 文件计算摘要，以 §0 的值定位 `MANIFEST_CURRENT`。随后使用下列相对路径。`PROOF_DIR/run-dir/smoke-result.json` 的 SHA-256 是 `c64a134b8a63d3cb98242753e8d84d613c498be113f1d3ce08b80f2011b67445`。这样可精确定位成功证据而不把工程归档编号写进比赛文案。

| 公共主张 / 等级 | 源码路径与符号 | 测试路径 | 运行或故障证据 | 真实模型证据 |
| --- | --- | --- | --- | --- |
| 可信执行分离 / A | `src/paios_ce/cli/agent_commands.py::_cmd_agent_run`; `src/paios_ce/agent/api.py::AstronAgent`; `src/paios_ce/agent/router.py::ToolRouter.execute`; `src/paios_ce/tools/bounded.py:45-147`; `src/paios_ce/runtime/durable_runtime.py::execute` | `tests/agent_v0/test_governance_invariants.py`; `tests/security/test_idempotency_replay_security.py` | `docs/aic2026/evidence/phase4/DETERMINISTIC_FAULT_RESULTS.md`，仅作独立故障证据 | `PROOF_DIR/run-dir/ws/.astron/agent_state.sqlite` 的 `agent_action_intents`、`agent_action_receipts`、`agent_events`；`PROOF_DIR/run-dir/runtime/<task_id>/state.sqlite` 的 `action_journal`、`authorization_replays`，各五条 |
| Verifier 控制完成 / A | `src/paios_ce/agent/api.py:282-304`; `src/paios_ce/agent/completion.py::CompletionAuthority.evaluate`; `src/paios_ce/state/durable.py::record_task_verification` | `tests/agent_v0/test_agent_loop.py`; `tests/agent_v0/test_verification.py`; `tests/agent_v1/test_p8_verification_registry.py` | `docs/aic2026/VERIFIED_COMPLETION.md` 为合同说明；故障矩阵含损坏交付物拒绝 | `PROOF_DIR/run-dir/smoke-result.json` 的 `result.verification`；Agent 事件序号 `43-47`；权威 DB 的 `task_verifications`、`task_verification_events`、`runtime_tasks` |
| 动作级恢复 / B | `src/paios_ce/runtime/durable_runtime.py:71-166`; `src/paios_ce/state/durable.py:764-932`; `src/paios_ce/agent/orchestrator.py:841-889`; `src/paios_ce/agent/reconciliation.py::settle` | `tests/recovery/test_process_crash_recovery.py`; `tests/agent_v0/test_recovery.py`; `tests/agent_v1/test_p11_resume_v1.py` | `docs/aic2026/evidence/phase2/PROCESS_RESTART_EVIDENCE.md`; `docs/aic2026/evidence/phase4/DETERMINISTIC_FAULT_RESULTS.md` 保留 `15/15` 摘要；对应原始进程输出目录当前不可用；`EVIDENCE_ROOT/RELATED_LOGS/pytest_regr_final.txt` | 本次正常执行只有已成功的日志与 checkpoint；无故障恢复事件 |
| 授权回放 / B | `src/paios_ce/state/durable.py::authorize_replay` | `tests/state/test_durable_store.py`; `tests/security/test_idempotency_replay_security.py` | 前述进程重启证据及故障矩阵的重放场景 | 权威 `authorization_replays` 中五个 `allow`；本次没有错配回放 |
| 有限工具与越界拒绝 / B | `src/paios_ce/tools/bounded.py:60-77,170-180`; `src/paios_ce/agent/router.py::ToolRouter.execute` | `tests/phase3/test_bounded_tools_and_e2e.py`; `tests/agent_v0/test_governance_invariants.py` | 前述故障矩阵的路径穿越和符号链接场景 | 五个允许动作来自有限工具表；本次没有拒绝事件 |
| 实跑任务结果与交付物 / A | `src/paios_ce/agent/completion.py:124-184`、任务合同中的两项条件 | `tests/agent_v1/test_p13_e2e_scenarios.py` 包含本地受控场景 | `PROOF_DIR/_gates/preparer_stdout.txt` 记初始两文件摘要；`PROOF_DIR/_gates/offline_evidence_dump.txt` 记最终清单 | `PROOF_DIR/run-dir/ws/src/limiter.py` SHA-256 `321fea…36f0`；`.../.astron-artifacts/limiter-report.json` SHA-256 `3c0a…c173`；`PROOF_DIR/run-dir/smoke-result.json` |
| 授权权威与投影限制 / A | `src/paios_ce/state/durable.py` 的 `action_journal`、`authorization_replays` 表；`src/paios_ce/audit/redact.py::_is_secret_like` | `tests/state/test_durable_store.py`; `tests/security/test_redaction_invariant.py` | `EVIDENCE_ROOT/GOVERNANCE_FORENSICS.md`，只用作权威层定位和投影限制说明 | `PROOF_DIR/run-dir/runtime/<task_id>/state.sqlite` 的真实授权值；`PROOF_DIR/run-dir/ws/.astron/agent_state.sqlite` 的投影值 |
| Provider 请求配置 / A | `src/paios_ce/cli/agent_commands.py::_cmd_agent_run` | `tests/phase3/test_openai_compatible_provider.py` | 保存的启动命令，仅证明发出的配置 | `PROOF_DIR/_gates/launcher.sh:10,29` 记录请求 `deepseek-flash` 及 `openai_compatible`；结果未保存 Provider 回报的 model 字段 |
| 证据包摘要闭合 / A | 不适用，属归档完整性核验 | 不适用 | `MANIFEST_CURRENT`，按 §0 的摘要定位，22 行 | 22 个成员本次重算均与清单相符；主结果 SHA-256 见 §0 |

此处 `<task_id>` 为 `task_7f3e1aa2e2e64f89a49c`。已独立复核的关键摘要：交付物 `3c0a0c51248b9f9431bc869d8e6776b8ce882d0479ae9dba33eb4e258652c173`；修改后源码 `321fea911a576c4a7d8cd219cb28dea318527e75b265385c2a16613e5caf36f0`；未改文档 `9b729c72b65d110669727c35c02ca35a1ae166c4789b5b7cbab8690846f3408f`。本索引中的旧故障结果只支持对应故障场景；不自动升级为当前提交的全量测试收据。

## 14. Team Handoff Summary

| 交接项 | 唯一比赛口径 |
| --- | --- |
| WHAT ASTRON IS | 面向通用 Tool-Calling Agent 的执行治理运行时；模型提议，运行时授权并记录，Verifier 接受完成 |
| THREE CONTRIBUTIONS | 可信执行分离；Verifier 控制完成；面向动作事实的恢复 |
| PRIMARY LIVE PROOF | `ASTRON_REAL_MODEL_END_TO_END_PROOF_V1`：五次真实 Provider 调用与五次模型决策，五次受治理动作，`MAX_RPS: 10 → 20`，交付物摘要一致，两项条件通过，耐久 `SUCCEEDED` |
| WHAT WE CAN SAFELY CLAIM | 当前受控任务的完整正向执行链（A）；已测故障窗口的保守恢复（B） |
| WHAT WE CANNOT CLAIM | 服务端确认的模型身份、任意系统 exactly-once、生产可靠性、通用 Agent 优势或绝对安全 |
| PRIMARY DEMO | 三幕：保存的真实成功任务；同一任务的 Verifier 验收链；单独标注的确定性恢复证据 |
| PRIMARY MEMORY HOOK | **AI 说完成，不等于任务真的完成。** |
| SOURCE BASELINE | `11c6114f6ec0504628f912ebde9ba53821badb03` / `2d0e6477c7d4e083bbd23e44a7228b7eedb47e24` |
| EVIDENCE ROOT | `EVIDENCE_ROOT`（本机绝对路径已脱敏）；以 §0 的结果摘要定位当前成功集 |

报告、README、演示视频、前端文案与问答均应沿用本基线的三项贡献、证据等级及限定词；将来若有新证据，应形成明确的新基线，不静默改写这份证据或原始归档。
