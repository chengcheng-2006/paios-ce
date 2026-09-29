# Astron — 参赛作品摘要（中文提交版）

`PRODUCT_SNAPSHOT = d32d3ec1bc49a78d0b14aabb6bf0daf79d3f4d88` ·
`R2_EVALUATED_RUNTIME = 13ee283` · Apache-2.0 · Python ≥ 3.11 · 离线可复跑

---

## 一句话（报名正文字数受限时用这段）

**Astron：面向 AI Agent 的可恢复、可验证执行治理运行时——模型提议，运行时裁决，验证器验收。**

## 短摘要（约 200 字）

Agent 框架已经能让模型顺利提出工具调用，但没有解决另一件事：**动作的授权、执行事实与完成
判定仍由模型侧输出主导**。于是出现四类必然事故——声称已改而文件未改、白名单只写在提示词里、
进程死在副作用中间导致重跑重复执行、事后无法回答谁授权谁判定。Astron 把这三项权力从提示词
移入代码：默认拒绝的权限引擎决定动作能否执行（未知动作、任意 shell、提权、CRITICAL 一律硬阻断）；
SQLite 持久动作日志在副作用**之前**落 `ATTEMPT_STARTED`，使不确定成为可查询状态，`UNCERTAIN`
不自动重试、只能由可信核对器落终态；确定性验证器是唯一能宣布任务完成的一方。全部能力可在
无 API Key、无网络条件下复跑。

## 详版摘要

### 背景与痛点

模型驱动 Agent 接触真实系统后，风险不再来自“回答不好”，而来自**权力边界放错位置**：
被考核的一方（模型）同时掌握“是否执行”和“是否完成”的话语权。提示词层面的约束被绕过时没有
任何代码后果；进程内存中的对话历史无法作为崩溃后的事实来源。

### 方案：三个互相独立的权威

| 权威 | 持有者 | 能决定 | 不能决定 |
| --- | --- | --- | --- |
| 提议权 | 模型（Mock / OpenAI 兼容 Provider） | 提出动作与参数 | 选择身份、授权、执行、宣布完成 |
| 执行裁决权 | `PermissionEngine` + `DurableActionRuntime` | `allow / deny / blocked / confirmation_required`；写入动作生命周期 | 判定任务完成 |
| 验收权 | `MaintenanceVerifier`（可注入替换） | 唯一写入 `ACCEPTED / REJECTED` + 原因码 | 修改权限、代模型执行 |

推论：**动作成功 ≠ 任务完成，模型说完成 ≠ 任务完成。**

### 已实现能力（当前快照，均可离线复现）

默认拒绝权限引擎与风险策略表 · 可信主体与幂等授权身份 · SQLite 持久动作生命周期
（授权记录、动作日志、只追加事件、检查点、核对事件、验证结论；WAL + `synchronous=FULL` +
文件 owner-private）· 崩溃恢复分类与不确定态核对 · 7 个受限工作区/校验/有界测试工具 ·
6 个受治理终端会话（POSIX）· 验证后完成与完成产物契约 · `RepoTaskRunner` 通用受治理仓库任务 ·
脱敏审计 · 公私有配置优先级与显式环境变量白名单 · Mock + 一个显式 OpenAI 兼容提议源 ·
可选本地语音转写 · 实验性 Team 角色层。

评测工程（R2/R3 题库、grader、formal runner、校准脚本）是**独立研究层，不是产品能力**，
未随作品包发布。

### 开源与治理

Apache-2.0 许可证与 `NOTICE` 版权归属保留上游原样（`PAIOS CE`, `Copyright 2026 Cheng Cheng`）；
公开仓库 `github.com/chengcheng-2006/paios-ce`；导入路径 `paios_ce` 与 `paios-ce` 命令别名延续
历史命名，未为竞赛包装改名；随包保留 AI 辅助开发披露（Codex 参与实现/测试/文档草拟，
需求、架构、验收与发布决定由人类 Owner 持有，`AI_AUTHORIZED_RELEASE_OR_SUBMISSION=NO`）；
`CONTRIBUTING`、`CODE_OF_CONDUCT`、`SECURITY`、CI workflow、issue/PR 模板、`CITATION.cff`
与源码、测试、文档一同发布。

### 已知边界（主动声明）

* 打包的验证器只对**一个固定 fixture** 成立，通用仓库验证器是当前最大空白。
* 有界测试是真实子进程、终端是真实 shell：**受限不等于只读，更不等于操作系统沙箱**。
* 无回滚/补偿（`rollback_supported` 恒 `False`）；`UNCERTAIN` 设计上会停住等待核对。
* 无常驻服务、调度、指标与告警；审计默认写内存流，持久 sink 需调用方接入。
* Team 是**更窄的权限模型**而非更强的模式：未打包、无 CLI 入口、默认 1 轮。
* 核心 macOS/Linux；当前改件的 Windows/Ubuntu 运行时上游记录为 `NOT_RUN`；终端能力 POSIX only。

### 研究证据（支撑材料，不是效果声明）

R2 在 `13ee283` 上完成 120 次正式运行（40 Direct / 40 Single / 40 Team，DeepSeek
`deepseek-v4-flash`）：`PASS=6 TASK_FAIL=88 PROVIDER_ERROR=23 HARNESS_ERROR=2 TEAM_BLOCKED=1`，
能力子集 `0/72`（三臂各 `0/24`）为地板效应，且 23 次 provider 错误在臂间删失不均。
**因此 R2 未建立 Astron 优于通用 Agent、也未建立其更安全。** R3 仍在开发集校准，
无最终留出集结论；R2 结果不是对本次交付快照 `d32d3ec` 的验证。
