# Astron — One-Page Project Brief (评委版)

> **模型提议，运行时裁决，验证器验收。**
> An execution-governance runtime that decides whether an agent's action may run,
> and whether its task may be called complete.
> `PRODUCT_SNAPSHOT = d32d3ec` · `R2_EVALUATED_RUNTIME = 13ee283` · Apache-2.0

## 背景

Agent 正在从“回答问题”走向“执行动作”：改代码、跑测试、写文件、调外部系统。
框架层已经能让模型顺利提出工具调用，但**动作的授权、执行事实与完成判定仍由模型侧的输出主导**。
一旦 Agent 接触真实系统，这就从体验问题变成审计与责任问题。

## 痛点

| # | 现象 | 本质 |
| --- | --- | --- |
| 1 | 模型声称“已修复”，文件其实没改或改错位置 | 完成判定交给了被考核的一方 |
| 2 | 白名单形同虚设：模型调出不存在的动作、把破坏性命令塞进“脚本” | 权限写在提示词里，等于没有写 |
| 3 | 进程中途崩溃后无人知道外部副作用是否发生，重跑造成重复执行 | 缺少“尝试已开始”的持久事实 |
| 4 | 事后无法回答“谁授权、执行了什么、谁判定完成” | 状态、决策与结果散落在对话和日志里 |

## Astron 方案

不把治理做进 prompt，而是做成三个**互相独立的代码权威**：

```text
模型 / Provider        →  只产生 ActionRequest 数据，无任何执行权
Astron 运行时           →  权限引擎决定能否执行；持久运行时决定何时算“已尝试”
确定性验证器            →  唯一能宣布任务完成的一方
```

## 三层 authority 思想

| 层 | 持有者 | 能决定 | 不能决定 |
| --- | --- | --- | --- |
| **提议权** | 模型（Mock / OpenAI 兼容 Provider） | 提出动作与参数 | 选身份、授权、执行、宣布完成 |
| **执行裁决权** | `PermissionEngine` + `DurableActionRuntime` | `allow / deny / blocked / confirmation_required`；写 `AUTHORIZED → ATTEMPT_STARTED → SUCCEEDED/FAILED/UNCERTAIN` | 判定任务是否完成 |
| **验收权** | `MaintenanceVerifier`（可注入替换） | 唯一写入 `ACCEPTED/REJECTED` + 原因码 | 修改权限、代模型执行 |

关键设计后果：**动作成功 ≠ 任务完成；模型说“完成” ≠ 任务完成。**
崩溃后系统区分三件常被混为一谈的事——*重建状态*（读日志）、*重新执行*（跑执行器）、
*确认外部副作用*（可信观测器核对）——因此 `UNCERTAIN` 不会触发盲目重试。

## 核心创新

1. **默认拒绝 + 未知动作显式拒绝**：未注册的动作名在任何能力/审批检查之前被阻断
   （`E_UNKNOWN_ACTION`），且不会被关键词“好心”归类成已知动作（token 级匹配，非子串）。
2. **可信主体与幂等身份绑定**：`idempotency key + principal + 请求指纹 + 安全上下文指纹`
   共同决定一次授权能否复用；换主体重用同一 key 直接阻断。
3. **副作用前落盘的尝试事实**：`ATTEMPT_STARTED` 先于任何效果写入 SQLite（WAL +
   `synchronous=FULL` + 文件 owner-private），使“不知道发没发生”成为一个**可查询的状态**。
4. **不确定即停住**：`recover_task` 只分类、`UNCERTAIN` 只由可信 `Reconciler` 落终态。
5. **验证器持有完成权**：结构检查、禁止改动、有界测试、完成产物契约共同决定验收。
6. **治理可离线演示**：无 Key、无网络的完整链路 + 546 项测试（含真实跨进程崩溃恢复）。

## 使用场景

适合任何“模型的动作会产生真实后果且需要可追溯”的场合：仓库自动化维护与修复、
受控文件/配置处理、需要事后审计与恢复能力的长任务、以及需要 harness 不污染测量结果的
Agent 评测。当前包内**已演示**的是仓库维护类任务与有界测试执行；其余是设计支持但尚未实现的方向。

## 当前实现（`d32d3ec`，可复跑）

7 个受限工作区/校验/有界测试工具 · 6 个受治理终端会话（POSIX）· 权限引擎与风险策略表 ·
SQLite 动作日志/检查点/核对事件/验证结论 · 恢复与核对 · 脱敏审计 ·
`RepoTaskRunner` 通用受治理仓库任务 · Mock + 一个显式 OpenAI 兼容提议源 ·
公私有配置优先级 · 可选本地 ASR。Python ≥3.11，无框架依赖。

## 研究证据（supporting evidence，非能力清单）

R2 正式运行 120 次（40 Direct / 40 Single / 40 Team，runtime `13ee283`，
DeepSeek `deepseek-v4-flash`）：`PASS=6 TASK_FAIL=88 PROVIDER_ERROR=23 HARNESS_ERROR=2 TEAM_BLOCKED=1`。
能力子集 `0/72`（三臂各 `0/24`）——**地板效应，无法支持任何排序**；23 次 provider 错误
在不同臂间删失不均（Direct 22.5% / Single 35.0% / Team 0%），若干安全旗标不具备臂间可比性。
因此：**R2 未证明 Astron 优于通用 Agent，也未证明其更安全。** R3 仍在开发集校准，
无 final holdout 结论；Generic/Direct 的校准成绩不是 Astron 成绩。
`d32d3ec` 是 `13ee283` 之后 9 个 commit，**其自身没有正式模型运行证据**。

## 已知边界（不回避）

* 验证器只对**一个固定 fixture** 成立；通用仓库验证器是当前最大空白。
* 有界测试执行是真实 `pytest` 子进程，`terminal_*` 是真实 shell：受限 ≠ 只读 ≠ OS 沙箱。
* 无回滚/补偿（`rollback_supported` 恒 `False`）；`UNCERTAIN` 会等待人工或专用核对器。
* 无常驻服务/调度/指标/告警；审计默认写内存流，持久 sink 需调用方提供。
* Team 更窄但**不是更强**：未打包、无 CLI、默认 1 轮、含一处已知死代码缺陷。
* 平台：核心 macOS/Linux；当前改件 Windows/Ubuntu 运行时记录为 `NOT_RUN`；终端 POSIX only。
* 546 项离线测试通过只证明契约在确定性环境下成立，不证明生产级安全或测量有效性。
