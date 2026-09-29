# Project brief

> 版本与证据边界：本文介绍产品快照 `d32d3ec1bc49a78d0b14aabb6bf0daf79d3f4d88`；如提及 R2 评测数字，其测量运行来自 `13ee283ce8b6121af14b1bf0f1f9deefe1484cf2`。d32d3ec 本身没有正式模型实跑证据。


Two lengths, same facts. Nothing here is claimed beyond what the code in
`../../source/` does and what `../../source/docs/EVALUATION_SUMMARY.md` permits.

---

## A. Short version (报名简介 / README 摘要 / 对外沟通)

**Astron — 面向 AI Agent 的可恢复、可验证执行治理运行时**

模型可以提议动作，但动作是否执行、执行到哪一步、任务是否真的完成，不应该由模型自己说。
Astron 把这三件事从提示词搬进代码：默认拒绝的权限引擎决定动作能否执行；SQLite 持久动作日志
在执行前后各落一次事实，进程中途崩溃时动作处于 `UNCERTAIN`，不允许盲目重试，必须由可信观测器
核对；确定性验证器是唯一的完成权威——动作成功不等于任务完成，模型说“做完了”更不等于。

核心机制已实现并可离线演示：7 个受限工作区/测试工具 + 6 个受治理终端会话、幂等授权身份、
崩溃恢复与核对、脱敏审计、验证后完成。Python 3.11+，无框架依赖，无网络依赖，
Apache-2.0，546 项离线测试通过（含真实跨进程崩溃恢复）。

**English.** Astron is an execution-governance runtime that sits between a model's
tool proposal and an accepted external outcome. A deny-by-default permission engine
decides whether an action runs; a durable SQLite action journal records the attempt
*before* the effect and the outcome *after*, so a process killed mid-action leaves
an `UNCERTAIN` fact that must be reconciled by a trusted observer rather than
blindly retried; and a deterministic verifier—not the model—holds completion
authority. Offline-demonstrable, no API key, Apache-2.0, 546 passing tests.

---

## B. Detailed version

### 1. 要解决的实际问题

让 Agent 接触工具之后，反复出现的四类事故都不是“模型不够聪明”：

| 现象 | 根因 | 常见“缓解”为什么不够 |
| --- | --- | --- |
| 模型声称已改文件，实际没改或改错位置 | 完成判定交给了被考核的一方 | 提示词要求“请确认”，没有可验证判据 |
| 白名单内的工具被用来跑破坏性命令，或调出不存在的动作 | 权限写在提示里、约束靠模型自律 | 未知动作、shell 语法、提权需要代码级硬阻断 |
| 外部副作用写到一半进程死了，重启后重复执行 | 没有“尝试已开始”的持久事实 | 内存里的对话历史随进程消失 |
| 事后无法回答“谁授权、执行了什么、谁判定完成” | 状态、决策、结果混在日志和对话里 | 缺一个可重放的事实源 |

Astron 的立场是一句话：**模型提议，运行时决定，验证器完成。**

### 2. 解决方式与对应源码

| 机制 | 实现位置 | 关键行为 |
| --- | --- | --- |
| 默认拒绝 + 风险策略 | `src/paios_ce/permissions/{engine,policy}.py` | 能力按名授予；未知动作、任意 shell、提权、CRITICAL、金融、身份类硬阻断；稳定错误码 `E_UNKNOWN_ACTION` 等 |
| 可信主体与幂等身份 | `permissions/identity.py`，`state/durable.py:authorize_replay` | `key + principal + 请求指纹 + 安全上下文指纹`；主体不来自模型 JSON；换主体重用 key → 阻断 |
| 持久动作生命周期 | `runtime/durable_runtime.py`，`state/durable.py` | 授权→AUTHORIZED→ATTEMPT_STARTED→执行→SUCCEEDED/FAILED/UNCERTAIN，全部落库；WAL + `synchronous=FULL`；文件 owner-private |
| 不确定与核对 | `state/durable.py:recover_task/reconcile` | 重启后只做分类，绝不自动重放；只有可信 Reconciler 的观测能落终态 |
| 受限工具面 | `tools/bounded.py`（7 操作）、`tools/terminal.py`（6 操作） | 路径/符号链接/字节/输出/超时全有界；终端仅 SIGINT、命令语法策略、输出脱敏 |
| 验证后完成 | `agent/verifier.py`，`maintenance_artifact.py` | 结构检查 + 禁止改动 + 有界测试 + 产物契约；`record_task_verification` 落库；模型自述只映射 `AGENT_STOPPED` |
| 提议来源 | `providers/{mock,openai_compatible}.py` | Mock 离线；真实模型显式开启、只给端点/模型名/环境变量名，密钥值不进配置 |
| 通用仓库任务 | `agent/repo_task.py` | 要求干净 checkout、独立预算（轮数/调用/挂钟/输出 token）、捕获 diff 与轨迹，不产出“已解决”判定 |
| 脱敏审计 | `audit/{logger,redact}.py` | 禁止键、密钥形状值、路径提示；不可证明已脱敏则拒发事件 |
| 实验性 Team | `team/` | 角色化权限（SUPERVISOR 零能力）+ 邮箱路由 + 只允许 VERIFIER 请求完成；复用同一套引擎/状态库/验证器 |

### 3. 代表性使用场景

**已在本仓库演示（可复跑）**

1. `bash examples/demos/01_governed_task.sh` — 一次真实仓库维护任务：读→精确替换
   →跑有界测试→写结构化变更产物→按可信 schema 校验→验证器判 `VERIFIER_ACCEPTED`。
2. `bash examples/demos/02_permission_denial.sh` — 同一份 JSON 形状的五种结局：
   允许、未知动作阻断、云出口阻断、shell 语法阻断、越权读拒绝；所有拒绝都报告
   `execution_attempted=false`。
3. `python examples/demos/03_crash_and_reconcile.py` — 真实子进程在副作用之后、终态
   写入之前被杀；新进程恢复出 `NEEDS_RECONCILIATION`，同主体重投被拒，换主体重用 key
   被阻断，账本观测器确认后落 `SUCCEEDED`，账本始终只有 1 行。

**设计支持但本快照未演示（不得当作已交付）**：规模化仓库维护（需要通用验证器）、
受控文件处理流程、可恢复长任务（无调度器/服务）、任何外部副作用（当前是硬阻断，
开通需为该类动作写专用核对器）。

### 4. 当前限制（不回避）

* 验证器只对**一个固定 fixture** 成立；通用仓库验证器是最大的真实空白。
* 有界测试执行是**真实 pytest 子进程**，受限不等于只读，更不等于操作系统沙箱；
  终端能力是真实 shell（POSIX only），策略是模式匹配 + cwd 归一化。
* `rollback_supported` 恒为 `False`，没有补偿语义。
* Team 未打包、无 CLI 入口、默认执行轮次预算 1，且 `team/feedback.py` 有已知的
  死代码缺陷（已在文档中标注，未擅改）。
* 审计日志默认只写到内存流，需要调用方自备 sink；没有服务、调度、指标、告警。
* 平台：核心 macOS/Linux 可跑；当前研究改件的 Windows/Ubuntu 运行时上游记录为
  `NOT_RUN`；状态文件隐私在 Windows 有真实 ACL 后端。
* 评测：R2 完成 120 次正式运行但能力子集是地板效应（`0/72`，三臂同为 0），
  且 120 次中有 23 次 provider 错误造成臂间差异删失；**未建立 Astron 优于通用
  Agent 的结论**。R3 仍在开发集校准，无 final holdout 结论。Generic/Direct 的
  校准成绩不是 Astron 成绩。

### 5. 来源与许可

Astron 是同一代码库的竞赛身份，历史包名 `paios_ce`（上游
`github.com/chengcheng-2006/paios-ce`）；导入路径与 `paios-ce` 别名有意保留，未做
全局改名。许可证 Apache-2.0，版权见 `NOTICE`（`PAIOS CE`, `Copyright 2026 Cheng Cheng`）。
交付快照 `d32d3ec`，包版本 `0.1.0rc2`，`Development Status :: 3 - Alpha`。
AI 辅助开发披露随包保留：`project/docs/aic2026/AI_ASSISTANCE_DISCLOSURE.md`。
