# Astron — 技术路线（提交版）

口径：`PRODUCT_SNAPSHOT = d32d3ec1bc49a78d0b14aabb6bf0daf79d3f4d88`，
`R2_EVALUATED_RUNTIME = 13ee283`。本文只描述**当前快照中真实存在的代码**，
末节把“计划”与“已实现”物理分开。

---

## 1. 设计目标与四条不变量

目标不是“让 Agent 更聪明”，而是让 Agent 的动作**可授权、可追溯、可恢复、可验收**。
由此定下四条不允许被破坏的不变量：

| # | 不变量 | 破坏后会怎样 |
| --- | --- | --- |
| I1 | 模型输出只是数据，不携带权限 | 提示词成为唯一防线，绕过无后果 |
| I2 | 副作用之前必须存在“已尝试”的持久事实 | 崩溃后无法区分“没做”和“不知道做没做” |
| I3 | 不确定态不得自动重放 | 重复副作用、外部系统脏数据 |
| I4 | 完成判定权不属于提议方 | 自评成功率，测量与运维双双失真 |

四条不变量各自有代码落点（见 §3），不是流程口号。

## 2. 技术选型与依赖面

| 选择 | 理由 | 代价 |
| --- | --- | --- |
| 纯 Python 标准库 + `pydantic`/`PyYAML`/`jsonschema`/`pytest` | 治理层不应引入框架绑定；无 Provider SDK、无 Web 框架、无 ORM | `pytest` 成为运行时依赖（有界测试工具需要它） |
| SQLite 单文件作为唯一事实源 | 单机、可备份、可用 `sqlite3` 直接读；WAL + `synchronous=FULL` 足够支撑崩溃语义 | 吞吐低于内存循环；不是分布式事实源 |
| 静态风险策略表 + token 级分类器 | 决策可解释、可测试、可 diff；拒绝原因稳定 | 新增动作需要显式登记（刻意制造摩擦） |
| `urllib` 手写 OpenAI 兼容适配 | 提议源保持薄层，不引入 SDK 供应链 | 需自己维护请求契约快照与错误码 |
| JSON Schema 双轨（pydantic 模型 + `schemas/*.json`） | 协议对外可校验，CI 可校验 | 两处需保持同步（由测试保证） |
| src-layout（`src/paios_ce`） | 防止意外 import 未安装包 | `team/` 因此不在 wheel 内（Team 记为实验性的直接后果） |

## 3. 分层实现路线（当前状态）

```text
第 1 层 协议与身份           protocols/models.py · protocols/enums.py · permissions/identity.py
        ↓ 数据形状先行，extra="forbid"，未知字段是错误不是忽略
第 2 层 裁决                 permissions/policy.py（分类+风险表）· permissions/engine.py（决策流）
        ↓ I1：主体由受信代码传入；未知动作最先拒绝
第 3 层 事实                 state/durable.py（schema v2 迁移 + 8 张表）· state/private_files.py
        ↓ I2：授权记录/日志/事件/检查点/核对/验证结论
第 4 层 执行序               runtime/durable_runtime.py（authorize→intent→attempt→effect→terminal）
        ↓ I3：UNCERTAIN 不重放；recover 与 reconcile 分离
第 5 层 效果                 tools/bounded.py（7 个具名操作）· tools/terminal.py（6 个受治理会话）
        ↓ 路径/字节/输出/超时全有界；模型不掌握作用域
第 6 层 循环与验收           agent/native.py（受界提议循环）· agent/verifier.py + maintenance_artifact.py
        ↓ I4：验证器是唯一完成权威
旁支     可选与实验           providers/* · config/* · audit/* · speech/* · team/* · agent/repo_task.py
```

**动作生命周期（状态机即代码）**

```text
RECORDED → AUTHORIZED → ATTEMPT_STARTED → SUCCEEDED | FAILED | UNCERTAIN
UNCERTAIN → (可信观测器) SUCCEEDED | FAILED | RETRY_ELIGIBLE | 仍 UNCERTAIN
RETRY_ELIGIBLE → ATTEMPT_STARTED（仅由后续显式调用触发）
```

**持久布局（SQLite schema v2）**：`authorization_replays`、`runtime_tasks`、`action_journal`、
`action_events`（只追加）、`checkpoints`、`reconciliation_events`、`task_verifications`、
`task_verification_events`。不落盘的内容同样是设计决定：密钥、原始 provider 报文、
请求参数、模型对话内容。

## 4. 关键实现取舍

1. **“拒绝”发生在派发之前，而不是执行之后回滚。** 因此不需要 undo 语义
   （`rollback_supported` 恒 `False` 是这个选择的自然结果，而非遗漏）。
2. **不确定不是错误码，而是状态。** 所以恢复只需要读日志，不需要猜；`NO_EVIDENCE`
   的核对结果保持 `UNCERTAIN`，宁可停住。
3. **能力授予集中在受信构造点。** Single 侧一次性授予整个已登记工具集
   （`tools/bounded.py:104-113`）；按角色/按操作收窄由 Team 层的 profile 承担。
   这一分布写进了限制文档，避免被误读为“Single 已有细粒度授权”。
4. **完成产物契约三处共用。** 同一个 `MaintenanceCompletionArtifactContract` 同时生成
   模型可见说明、工具校验和验证器判据（`maintenance_artifact.py`），消除“提示里一个版本、
   校验里另一个版本”的经典漂移。
5. **只读可批、改写必单。** 批量规则只允许 `workspace.list_files`/`workspace.read_text`
   同轮出现，混合批次在首个动作执行前整体拒绝（`agent/native.py:189-209`），
   这让“模型一次说完”不能变成“模型一次做完”。
6. **Provider 不可信即无影响。** 提议源不 import 状态层与权限层，因此接入新模型
   不扩大执行面。

## 5. 验证路线（不重跑正式 benchmark）

| 层次 | 手段 | 当前状态 |
| --- | --- | --- |
| 契约 | `tests/unit` `tests/security` `tests/state` `tests/runtime` | 全绿（离线） |
| 端到端 | `tests/phase3`、`examples/demos/01` | 一次任务跑到 `VERIFIER_ACCEPTED` |
| 崩溃语义 | `tests/recovery`（真实子进程 `os._exit`）、`examples/demos/03` | `NEEDS_RECONCILIATION` → 核对 → 终态 |
| 交付完整性 | `tools/package_local_validate.py`、`tools/security_local_scan.py`、`tools/validate_security_workflow.py`、`python -m paios_ce.tools.validate_schemas` | 均通过（wheel 构建 + CLI 冒烟 + 安全扫描 + schema 校验） |
| 模型效果 | R2 历史数据（`13ee283`） | **地板效应，无排序结论**；本包不重跑、不改分 |

## 6. 未实现与下一阶段（明确标注为计划，不是能力）

| 项 | 当前状态 | 下一步（未开始实现） |
| --- | --- | --- |
| 通用仓库验证器 | 未实现；打包验证器仅覆盖一个 fixture | 定义验证器接口契约 + 可插拔判据 |
| 持久审计 sink | 默认写内存流 | 追加式审计写器 + 保留策略 |
| 状态查看 CLI | 无子命令，只能读 SQLite 或调 API | `astron state show --db …` 级别的只读入口 |
| Team 产品化 | 未打包、无 CLI、默认 1 轮、无恢复路径 | 打包与入口决策 + resume 语义设计 |
| 跨平台终端 | POSIX pty only | Windows 后端或明确标记不支持 |
| 隔离边界 | 治理非隔离 | 容器/VM 边界方案（研究文档已列为未来边界，不属于当前实现） |
| 重试策略 | 未启用（研究与产品侧均无） | 需先在测量层解决臂间删失问题 |

## 7. 配套阅读

机制细节 [../ARCHITECTURE.md](../ARCHITECTURE.md) · 源码地图 [../SOURCE_MAP.md](../SOURCE_MAP.md) ·
限制清单 [../SECURITY_AND_LIMITATIONS.md](../SECURITY_AND_LIMITATIONS.md) ·
契约文档 [../aic2026/](../aic2026/) · 研究事实与不可得结论
[../EVALUATION_SUMMARY.md](../EVALUATION_SUMMARY.md) ·
评委版 [ONE_PAGE_PROJECT_BRIEF.md](ONE_PAGE_PROJECT_BRIEF.md) ·
创新点 [INNOVATION_POINTS.md](INNOVATION_POINTS.md)
