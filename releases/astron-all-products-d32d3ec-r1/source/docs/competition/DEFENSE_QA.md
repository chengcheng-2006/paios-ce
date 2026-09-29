# DEFENSE_QA — 答辩问答（评委视角）

每题给：**直接答案 → 代码/文档依据 → 一句边界声明**。
所有事实口径均为 `PRODUCT_SNAPSHOT = d32d3ec1bc49a78d0b14aabb6bf0daf79d3f4d88`，
所有 R2 数字口径均为 `R2_EVALUATED_RUNTIME = 13ee283ce8b6121af14b1bf0f1f9deefe1484cf2`。

---

## 1. 和普通 Agent 框架 / ReAct 有什么区别？

**答**：ReAct 及多数框架规定“模型如何思考与调用工具”；Astron 规定“**动作被允许产生后果之前必须经过谁，
以及谁有权宣布任务结束**”。它不做规划策略、不做反思循环、不做图编排。

**依据**：模型输出仅被当作 `ActionRequest` 数据（`tools/bounded.py:170-199` 由受信代码构造请求，
模型不掌握 `filesystem_scope`/`required_permissions`/`idempotency_key`）；裁决在
`permissions/engine.py:501`；副作用前后的持久边界在 `runtime/durable_runtime.py:71-152`；
完成权在 `agent/verifier.py:33`。

**边界**：两者不是替代关系。Astron 可以处在任何提议循环的下方；本包内没有做任何框架横向对比测试。

---

## 2. 为什么不直接依赖更强的模型？

**答**：因为要解决的三类问题不在模型一侧：**授权、事实、验收**。更强的模型仍然不能成为“被考核者同时是判分者”。
提示词里的白名单在被绕过时没有任何代码层后果；内存里的对话在进程死掉后不留下“那一步到底做没做”的证据。

**依据**：`agent/native.py:44-46` 的系统提示明确要求模型“不要声称成功，验证器决定完成”——
但这条要求**不依赖模型遵守**：完成判定由 `agent/verifier.py` 独立执行；
崩溃事实由 `state/durable.py` 的 `ATTEMPT_STARTED`/`UNCERTAIN` 记录，不依赖模型回忆。

**边界**：这不意味着模型无关紧要。提议质量决定任务能否通过；Astron 只保证质量之外的三件事。

---

## 3. 和 LangGraph / OpenHands / Claude Code 是什么关系？

**答**：**层次不同，可叠加，不是同类竞品。**
LangGraph 是编排/状态图框架；OpenHands 是自主软件工程 Agent 系统；Claude Code 是面向用户的编码 Agent 产品。
Astron 是一个执行治理运行时——它不编排、不做 IDE/CLI 体验、不提供自主编码策略。

三点确实不同的设计承诺（都有代码落点）：

1. **未知动作显式拒绝优先于一切策略与审批**（`permissions/policy.py:206-282` +
   `engine.py:284-296`，稳定错误码 `E_UNKNOWN_ACTION`），且分类是 token 级匹配而非子串，
   避免 `upload_*` 被“好心”归成读操作。
2. **副作用之前落盘的尝试事实 + 不确定态不自动重试**（`durable_runtime.py:102-135`、
   `state/durable.py:864,901`）：恢复、重放、确认外部副作用被拆成三个不同 API。
3. **完成权外置且可注入替换**（`agent/verifier.py`、`NativeAgent(..., verifier=…)`），
   模型自述只映射 `AGENT_STOPPED`（`agent/repo_task.py`）。

**边界（必须主动说）**：上述三个产品都各自具备权限/确认相关机制，我不声称它们没有；
本项目**没有**对它们做过任何对照实验或性能比较，因此这里只谈设计位置，不谈优劣排名。
研究层（R2/R3）里的 `Direct`/`Generic` 是**为测量而搭的基线 scaffold**，也不是这些产品。

---

## 4. Astron 是不是沙箱？

**不是。这是本项目最重要的一条边界。**

**依据**：
- `test.run_pytest_bounded` 用真实解释器执行 `python -m pytest tests -q`，只有命令、cwd、超时
  和输出被固定（`tools/bounded.py:420-448`）。fixture 里的测试做什么，就用你普通用户的权限做什么。
- `terminal_open` 启动真实 `/bin/zsh`（无则 `/bin/sh`）pty 会话，后续命令在其中 `eval`
  （`tools/terminal.py:236-256`）；约束是 cwd 归一化 + 破坏性/管理命令正则阻断 + 默认拒绝网络命令 +
  仅允许 `SIGINT` + 输出截断与脱敏。且模型提供的 `env` 会**覆盖**会话默认变量（含 `PATH`）。
- 代码自己的表述：`TerminalPolicy` 写明“intentionally not described as an OS sandbox；
  container isolation remains the future … boundary”。

**结论**：Astron 提供的是**治理（governance）**——决定要不要派发一个动作、留下什么记录、由谁验收；
它不提供**隔离（containment）**。要跑不可信代码，仍需容器/虚拟机/用户级隔离，且要自己写动作级核对器。

---

## 5. 如何防止重复执行？

**答**：四道独立的闸，不是一个开关：

| 机制 | 位置 | 效果 |
| --- | --- | --- |
| 幂等身份绑定 | `permissions/identity.py` + `engine.py:345` | `key + principal + 请求指纹 + 安全上下文指纹` 一致才复用原决定；不一致 → `E_IDEMPOTENCY_KEY_REUSE_MISMATCH`（阻断） |
| 持久授权记录 | `state/durable.py:617` | 跨进程也只有一个权威授权记录；并发首授权由 SQLite 串行化 |
| 状态机守卫 | `durable_runtime.py:102-112` | 仅 `AUTHORIZED`/`RETRY_ELIGIBLE` 可执行；已 `SUCCEEDED/FAILED/UNCERTAIN` 一律不再调用执行器 |
| 不确定不重试 | `state/durable.py:864` + `reconcile:901` | `UNCERTAIN` 只能由可信观测器落终态；`NO_EVIDENCE` 保持不确定 |

**现场证据**：`python examples/demos/03_crash_and_reconcile.py` ——
同主体重投被拒（`executor_invoked=False`、账本仍 1 行）、换主体重用 key 被阻断、核对确认后才落 `SUCCEEDED`。

**边界**：这保证的是“Astron 这一侧不重复派发”，**不保证任意外部系统 exactly-once**。
外部是否重复，取决于该类动作有没有可读取的证据（需要你自己写 `Reconciler`）。

---

## 6. 网络中断怎么办？

**分三种情况，行为不同：**

1. **Provider 请求中断**（提议阶段，尚无副作用）：`NativeAgent` 捕获异常，记录
   `provider_error`（稳定错误码，96 字符内）与 `provider_diagnostics`，循环结束并**仍然调用验证器**
   （`agent/native.py:180-184`、`254`）。失败不会被包装成成功，也不回落到 Mock。
2. **动作执行中断/进程被杀**：因为 `ATTEMPT_STARTED` 先于效果落盘，重启后 `recover_task`
   返回 `NEEDS_RECONCILIATION`；此时系统**停住**，等待可信核对器。
3. **写终态时数据库不可用**：`record_terminal` 失败会返回 `needs_reconciliation=True` 并附
   `state_error`（`durable_runtime.py:144-151`）——即使副作用已经返回，也不报告“安全完成”。

**边界**：本包没有内置重试策略（研究层 R2/R3 明确记录 `NOT_ENABLED`），
因为重试在臂间会造成差异删失；产品侧同样只提供显式恢复入口，不自动重试。

---

## 7. Team 为什么还是 experimental？

**答**：五个可核对的具体原因，不是谦虚：

1. **未打包**：`pyproject.toml` 的 `packages.find` 只含 `src/`，`pip install .` 之后没有 `team`。
2. **无入口**：`src/paios_ce` 内没有任何对 `team` 的引用，CLI 七个子命令都到不了 Team。
3. **默认只有一轮**：`TeamScheduler.__init__` 的 `max_executor_rounds=1`；模块常量
   `MAX_EXECUTOR_ROUNDS=4` 只被（研究层的）benchmark adapter 使用。
4. **无恢复路径**：`TeamScheduler.run` 每次新建内存 `TeamState`/`Mailbox`；`ActionLifecycle.recover`
   目前只有测试调用。
5. **已知缺陷**：`team/feedback.py:37` 引用了未导入的名字，调用即 `NameError`（死代码，按快照原样保留）。

**同时要说清它已经真实做到的事**：角色化权限是真的——`SUPERVISOR` 的能力集是空集，
`AUDITOR/VERIFIER` 只有读+测试（`team/adapters/tool_authority.py:77-119`），
且它复用**同一个**权限引擎、同一个 SQLite 状态库、同一个验证器；只有 `VERIFIER` 角色能请求完成
（`team/verifier.py:80-85`）。可跑：`PYTHONPATH=src:. python examples/demos/04_team_offline_run.py`。

**边界**：Team 不是“更强的模式”。R2 历史里它是能力 `0/24`、压力 `0/16` 且有一次 `TEAM_BLOCKED` 的那一臂。

---

## 8. Benchmark 是否证明 Astron 比 Direct 更强？

**没有。这是明确结论，不是含蓄结论。**

R2（runtime `13ee283`，DeepSeek `deepseek-v4-flash`，120 次正式运行 = 40 Direct / 40 Single / 40 Team）：

```text
互斥主结果：PASS=6  TASK_FAIL=88  PROVIDER_ERROR=23  HARNESS_ERROR=2  TEAM_BLOCKED=1
能力子集  ：0/72（Direct 0/24 · Single 0/24 · Team 0/24）——地板效应
压力子集  ：Direct 2/16 · Single 4/16 · Team 0/16（仅 8 个唯一用例）
删失      ：PROVIDER_ERROR 占比 Direct 22.5% / Single 35.0% / Team 0%（臂间不均）
不可比信号：unsafe_replay 在 118 次运行中方差为 0；recovery_result 在 Direct 40/40 NOT_APPLICABLE；
            verifier_accepted 在 Direct 40/40 为 null；forbidden_change_detected 在 Team 40/40 缺失；
            duration_seconds 退化不可用
```

地板效应意味着任务对三臂同样不可解，**不存在可排序的差异**；臂间差异删失意味着通过率不可直接比较；
安全旗标退化/缺失意味着不能声称更安全；时长指标退化意味着不能声称更快。压力子集 8 个唯一用例上的
2/4/0 属于噪声，不足以支撑排名。

**边界**：R3 仍在开发集校准，无 final holdout 结论；Generic/Direct 的校准成绩是**基线 scaffold** 的成绩，
不是 Astron 成绩；本交付快照 `d32d3ec` 自身不携带任何正式模型运行证据。

---

## 9. 为什么 R2 capability 全是 0？

**答**：因为任务集对当时的所有臂都过难（叠加当时的传输不稳定），这正是它被称为地板效应（floor effect）
的原因——不是“Astron 挡住了成功”，也不是“模型失败暴露了 Astron 的缺陷”，而是**这道测量没有区分度**。

**证据链**：三臂同为 `0/24`，包括不含任何 Astron 治理的 `Direct` 臂。若差异来自 Astron 的权限或验证逻辑，
`Direct` 臂不会同为 0。同时 120 次里有 23 次 `PROVIDER_ERROR`，删失在臂间不均。

**这个结果如何被使用**：它是 R3 测量设计的输入（提高任务可区分度、统一预算与传输处理、
补齐观测组件），**不是**产品能力声明，也不是产品缺陷认定的依据——因为该实验测的是端到端通过率，
无法归因到 harness 或模型。

**边界**：R2 数据被永久冻结，不重跑、不改分、不挑结果；我们不因为结果不好看而删除它，
也不把它包装成 Astron 的成绩。

---

## 10. 当前最主要的限制是什么？

按影响排序（详见 [../SECURITY_AND_LIMITATIONS.md](../SECURITY_AND_LIMITATIONS.md)）：

1. **验证器只覆盖一个固定 fixture**（`agent/verifier.py` 自称“fixed oracle”）——通用仓库验证器是最大空白。
2. **受限 ≠ 隔离**：真实 pytest 子进程 + 真实 shell 会话；不是 OS 沙箱。
3. **无回滚/补偿**：`rollback_supported` 对所有已发布操作为 `False`。
4. **`UNCERTAIN` 需要人工或专用核对器**，没有内置通用核对器。
5. **无常驻化组件**：没有服务、调度、指标、告警；审计默认只写内存流，持久 sink 要自己接。
6. **Team 未打包、无 CLI、默认 1 轮**。
7. **平台**：核心 macOS/Linux；终端 POSIX only；当前改件的 Windows/Ubuntu 运行时上游记录 `NOT_RUN`。
8. **文档漂移**：`SUPPORT_MATRIX.md` 缺 `terminal_*`/`RepoTaskRunner`/`team/` 条目、`maintenance-baseline`
   未列、测试数与 `rc.1/rc.2` 版本口径与 `pyproject.toml` 不一致；`providers/__init__.py` 注释仍称只有 Mock。
   （这些按原样保留并在清单中登记，未在交付包里擅自改写。）

**边界**：546 项离线测试通过只说明契约在确定性环境下成立，不等于生产级安全，也不等于故障都能自动恢复。

---

## 11. 企业里有什么实际使用场景？

**已有演示、可直接复用的**：受治理的仓库维护任务——读文件、精确替换一处、跑有界测试、
产出结构化变更说明并通过可信 schema 验收；破坏性或未知动作被拒；进程被杀后能从日志判定该步是否发生。

**设计上支持、但本快照尚未实现（不得当作已交付）**：

| 场景 | 现在有什么 | 还缺什么 |
| --- | --- | --- |
| 依赖升级 / lint / 类型清理等规模化仓库维护 | 治理链路、diff 捕获、预算（`RepoTaskRunner`） | 通用验证器 |
| 受控文件处理（保留期、脱敏、私有状态） | 脱敏审计、owner-private 状态文件（POSIX mode / Windows ACL） | 文档级工作流与策略配置 |
| 可恢复长任务 | 动作日志、检查点、恢复分类、核对 | 调度器/队列/服务化 |
| 外部副作用（消息、支付、部署） | 权限层的硬阻断 + 不确定语义 | 动作级 `Reconciler`；当前这些类别是**硬阻断**的 |
| 事后审计 | `action_events` 只追加事件、`task_verifications` 结论 | 持久审计 sink（默认写内存） |

**审计视角的价值主张（可以讲的）**：一旦出事故，`sqlite3 state.sqlite 'select * from action_events'`
能回答“谁授权、尝试了什么、由谁判定完成”——这是对话日志回答不了的。

**边界**：本项目没有任何企业客户、部署记录、用户量或营收；`PUBLIC_RELEASE_BOUNDARY.md` 明确不声称
production readiness、SLA 或 fitness。

---

## 12. 为什么这个项目属于 “AI + 开源”？

**答**：三点都可核查。

1. **AI 系统的一部分，而不是套壳**：它解决的是 Agent 从“能调用工具”到“能被信任地执行”之间的那段工程问题，
   属于 AI 基础设施层。
2. **真实开源形态**：Apache-2.0 许可证与 `NOTICE` 版权归属保留上游原样；
   公开仓库 `github.com/chengcheng-2006/paios-ce`；有 `CONTRIBUTING.md`、`CODE_OF_CONDUCT.md`、
   `SECURITY.md`、CI workflow、issue/PR 模板、`CITATION.cff`；测试与文档随源码一起发布；
   导入路径 `paios_ce` 与 `paios-ce` 别名延续历史命名，未为竞赛包装而改名。
3. **AI 辅助开发且如实披露**：随包保留
   [../aic2026/AI_ASSISTANCE_DISCLOSURE.md](../aic2026/AI_ASSISTANCE_DISCLOSURE.md)，
   写明 Codex 参与了实现/测试/文档草拟、DeepSeek 仅作为受限提议源、
   需求/架构/验收/发布决定由人类 Owner 持有，且
   `AI_AUTHORIZED_RELEASE_OR_SUBMISSION=NO`。

**边界**：开源治理文件是上游真实存在的，不是为参赛临时补的壳；本项目没有获得任何奖项或认证，
也不声称符合某个未知赛事的具体条款。

---

## 13. （备用）这个交付包本身做了什么？是新的 release 吗？

**答**：不是。它是**同一份已提交快照的交付整理**：源码来自
`feature/generic-repo-runner-r1` @ `d32d3ec`（`git archive` 导出，未混入任何未提交改动）。
整理层只做了三件事：(a) 按导入依赖剔除研究评测层（840 个文件，产品代码对其零引用）；
(b) 新增离线演示与文档；(c) 修正文档间的版本与入口口径漂移（登记在
`../../../manifest/RELEASE_MANIFEST.json`）。
核心源码、权限语义、完成判定、工具权限**一律未改**；未 push、未打 tag、未发布、未报名。

## 14. （备用）成本在哪里？

三处。**延迟与写入量**：每个动作在产生效果前后至少各写一次持久事实，吞吐低于纯内存循环。
**模型轮次成本**：只读调用最多 4 个一批，任何改写动作独占一轮，因此 7 个动作至少需要 5 轮提议，
再加一轮“返回空调用”来收尾——本快照的离线演示正好用满默认的 `max_steps=6`
（`agent/native.py:122-126`，可配 1-12；`task_timeout_seconds` 默认 60、可配 1-300）。
**人工成本**：`UNCERTAIN` 会停住，需要人或动作级核对器来解决——这是设计选择，代价是偶尔不自动。

---

## 快答索引

| 如果只能答一句 | 说这句 |
| --- | --- |
| 你解决了什么 | 动作的授权、执行事实与完成判定从模型侧移到运行时侧 |
| 最强的证据 | 真实进程死在副作用之后：`NEEDS_RECONCILIATION` → `executor_invoked=False` → `CONFIRMED_SUCCEEDED`，账本只有一行 |
| 最大的空白 | 通用仓库验证器还不存在，打包的验证器只覆盖一个 fixture |
| 最容易被误会 | 受限执行不是沙箱；Team 不是更强；R2 没证明更强；`d32d3ec` 没有正式运行证据 |
