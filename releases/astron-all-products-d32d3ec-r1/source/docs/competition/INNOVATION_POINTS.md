# Astron — 创新点（提交版）

每条给：**主张 → 代码落点 → 与常见做法的差异 → 明确不声称什么**。
第 4 列不是谦虚，而是防止评委把机制听成效果。口径：`PRODUCT_SNAPSHOT = d32d3ec`。

---

## 1. 未知动作显式拒绝，且优先于一切策略与审批

**主张**：未注册的动作名不进入任何已知类别，而是**在能力检查、所有者检查、确认通道之前**被硬阻断，
并携带稳定错误码 `E_UNKNOWN_ACTION`。分类是 **token 级匹配而非子串匹配**，
因此 `upload_data` 不会因包含 `load`/`read` 而被“好心”归成读操作。

**落点**：`permissions/engine.py:284-296`（`UNKNOWN_ACTION` 分支在最前）、
`permissions/policy.py:206-282`（`classify`，精确操作映射 + token 匹配）、
`docs/aic2026/BOUNDED_TOOLS.md`。

**差异**：多数工具白名单是“不在表里就拒绝或报错”，但拒绝发生在**分类之后**——一旦分类是启发式的，
误归类就把未注册动作接进了受信任通道。

**不声称**：不声称这能防住已被授权工具被“滥用”；那是作用域与预算问题，另有机制。

---

## 2. 授权身份绑定：幂等 key 不能跨主体复用

**主张**：一次授权由 `idempotency key + 可信主体 + 规范化请求指纹 + 当前安全上下文指纹`
四元组决定。完全一致的重投恢复原决定；任何一项不一致 → `E_IDEMPOTENCY_KEY_REUSE_MISMATCH`
并阻断，且**不覆盖原始记录**。授权记录本身落在 SQLite 里，因此跨进程同样只有一个权威。

**落点**：`permissions/identity.py`、`engine.py:345`（`_check_replay`）、`engine.py:436`
（`_authorize_durably`）、`state/durable.py:617`（`authorize_replay`）；
现场证据 `examples/demos/03_crash_and_reconcile.py` 第 3b 步。

**差异**：常见做法把“幂等”做成调用方自觉传入的一个字段。这里幂等 key 是**身份的一部分**，
并且主体由受信代码提供——模型 JSON 里任何 `owner_identity`/`actor`/`user` 字段都无权威。

**不声称**：不声称任意外部系统 exactly-once；只声称 Astron 一侧不重复派发。

---

## 3. 副作用之前落盘的尝试事实，使“不确定”成为可查询状态

**主张**：执行器被调用前先写 `AUTHORIZED` 再写 `ATTEMPT_STARTED`；结束后写
`SUCCEEDED`/`FAILED`。执行器抛异常、终态写入失败、或恢复时发现有尝试无终态，一律落
`UNCERTAIN` 并返回 `needs_reconciliation=True`——**不自动重试**。

**落点**：`runtime/durable_runtime.py:71-152`；`state/durable.py:740,815,838,855`；
存储契约 `state/durable.py:251-290`（`foreign_keys=ON` + WAL + `synchronous=FULL` 全部实测校验，
SQLite 不授予就拒绝打开）；`state/private_files.py`（`0o600` / Windows ACL SDDL，权限不合规 fail-closed）。

**差异**：多数 harness 的“恢复”是把会话历史重放给模型。这里恢复读的是**动作日志**，
不依赖模型回忆，也不依赖进程内存。

**不声称**：不声称所有故障都能自动恢复；`UNCERTAIN` 的解决需要人工或动作级观测器。

---

## 4. 三种操作被明确拆开（这是防重复执行的核心概念）

| 操作 | 语义 | API | 会调用执行器吗 |
| --- | --- | --- | --- |
| 重建状态 | 重启后读出实际发生了什么 | `recover_task` | 不会 |
| 重新执行 | 对合法可运行状态再跑一次 | `execute`（仅 `AUTHORIZED`/`RETRY_ELIGIBLE`） | 会 |
| 确认外部副作用 | 用可信证据判定那一步到底做没做 | `reconcile` + `Reconciler.observe` | 不会 |

**主张**：把这三件事统称 “replay” 是重复副作用类事故的根源；Astron 在 API 层就分开，
因此“核对”不会变成“再执行一次”。

**落点**：`runtime/durable_runtime.py:102-112,154-166`、`state/durable.py:864,901`；
契约文档 `docs/aic2026/RECOVERY_SEMANTICS.md`。

**不声称**：不声称存在通用核对器。核对器必须由使用者针对具体动作类别编写；写不出来的动作类别就不该开通。

---

## 5. 完成权外置：模型自述不产生任何完成效果

**主张**：`ACCEPTED` 只能由确定性验证器写入，且写入即为持久事实
（`task_verifications` + `verifier_version` + 原因码）。通用 runner 更彻底：模型文本
`done`/`fixed`/`completed` 只映射为 `AGENT_STOPPED`，**不返回任何“已解决”判定**。

**落点**：`agent/verifier.py:33-129`（结构检查、禁止改动白名单、有界测试、完成产物契约）、
`state/durable.py:1016`、`agent/repo_task.py`（`AGENT_STOPPED` / `BUDGET_EXHAUSTED`）、
`agent/native.py:254`（循环结束后**必定**调用验证器）。

**差异**：不是“提示模型别撒谎”，而是模型没有可写的完成通道。

**不声称**：不声称验证器是通用的——它当前只对一个固定 fixture 成立，这是产品最大空白。

---

## 6. 受限工具面：把“模型给参数”这件事压到最小

**主张**：模型只能给**具名操作 + 受校验的参数**；路径、作用域、能力、超时、幂等 key
全部由受信代码构造。路径检查包含相对 POSIX 约束、`..` 拒绝、逐层祖先符号链接检查与
resolve 后再验证仍在根内；写入走 `tempfile` + `fsync` + `os.replace` 原子替换；
读/列表/输出/产物字节与条数全部有界；有界 pytest 用固定解释器、固定目标、空插件自动加载、
`terminate`→`kill` 升级超时处置。

**落点**：`tools/bounded.py:60-77,170-313,315-448,451-465`；边界值汇总见
`docs/CONFIGURATION.md` 末表。

**不声称**：不声称这是沙箱（见 `docs/SECURITY_AND_LIMITATIONS.md`）。

---

## 7. 能力粒度：一处声明，五处落实（加工具的摩擦是设计出来的）

**主张**：新增一个工具必须同时改动模型可见 schema、受信归一化、执行处理器和风险分类——
四个不同责任方，加一处能力授予，共五个改动点。缺少任何一处即不成立。

**落点**：`docs/DEVELOPER_GUIDE.md` §3 逐点列出文件与函数。

**差异**：装饰器一行注册工具的方案，把“模型能问什么”和“系统允许什么”合并成一处，
这正是权限漂移的入口。

**不声称**：不声称扩展很省事；刻意不省事。

---

## 8. 实验性 Team：把权限按角色收窄，但不复制一套运行时

**主张**：Team 的角色层不复刻权限系统。`RoleScopedToolRuntime` 是
`BoundedToolRuntime` 的子类，只重建引擎的能力集与主体；`SUPERVISOR` 能力集为**空集**，
`AUDITOR/VERIFIER` 只有读+测试；完成请求若不是 `VERIFIER` 角色发出则直接抛
`CompletionAuthorityViolation`；内存态运行事实必须与持久日志一致，否则投影断言报错。

**落点**：`team/adapters/tool_authority.py:77-173`、`team/authority.py:106`、
`team/verifier.py:80-85`、`team/journal.py:161-185`。

**不声称**：不声称 Team 更强。它未打包、无 CLI、默认 1 轮，且在 R2 历史里是最弱的一臂。

---

## 9. 离线可验证的治理：机制不需要 API Key 也能被审计

**主张**：完整链路（提议 → 归一化 → 授权 → 尝试 → 效果 → 终态 → 验收）以及真实跨进程崩溃
与核对，都可在无网络、无凭据条件下复跑；4 个演示脚本产物只落在临时目录。

**落点**：`examples/demos/`（4 个脚本 + README）、`tests/recovery/test_process_crash_recovery.py`
（真实子进程 `os._exit` 崩溃窗口）、`tests/security/`（未知动作、身份硬阻断、脱敏不变式）；
当前副本 `546 passed, 1 skipped`。

**不声称**：不声称离线绿灯等于生产级安全或模型效果——它只说明契约在确定性环境下成立。

---

## 反过度声称对照表（提交材料统一口径）

| 容易被写成的话 | 本包实际允许的说法 |
| --- | --- |
| “防止 Agent 出错” | 防止**未经授权的动作被执行**、防止**不确定动作被盲目重放**、防止**模型自我宣布完成** |
| “沙箱级隔离” | 治理（governance），非隔离（containment）；不可信代码仍需容器 |
| “exactly-once” | Astron 一侧不重复派发；外部系统需动作级核对器 |
| “已验证提升成功率” | R2 能力子集三臂同为 0（地板效应），未建立任何提升结论 |
| “企业可用/已部署” | 无客户、无部署记录、无用户量；上游文档明确不声称 production readiness |
| “最新快照已被评测” | 评测发生在 `13ee283`；`d32d3ec` 自身无正式模型运行证据 |
