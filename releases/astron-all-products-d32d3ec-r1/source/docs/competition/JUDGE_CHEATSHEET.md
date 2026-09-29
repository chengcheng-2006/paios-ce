# Astron — 评委速览（60 秒）

## 一句话

**模型提议，运行时裁决，验证器验收。**
Astron 把 Agent 的“能不能执行”和“算不算完成”这两项权力，从模型手里移交给代码。

## 30 秒版本（如果只有 30 秒）

| | 常见做法 | Astron |
| --- | --- | --- |
| 谁能执行动作 | 工具白名单写在提示词里，模型给参数 | 权限引擎按能力+作用域+风险裁决；模型只提名 |
| 动作名不在表里 | 报错或被“就近归类” | 最先显式拒绝：`E_UNKNOWN_ACTION`，且不执行任何东西 |
| 进程死在中间 | 只能重跑，可能重复副作用 | 副作用**之前**已落 `ATTEMPT_STARTED`；重启后是 `UNCERTAIN`，不自动重试 |
| 谁宣布任务完成 | 模型自己说 | 确定性验证器；模型说 `done` 只是 `AGENT_STOPPED` |

## 60 秒版本：三个权威

```text
提议权   模型 / Provider        只产出 ActionRequest 数据
执行裁决权 PermissionEngine      allow / deny / blocked / confirmation_required
         + DurableActionRuntime  AUTHORIZED → ATTEMPT_STARTED → SUCCEEDED|FAILED|UNCERTAIN
验收权   MaintenanceVerifier    唯一能写 ACCEPTED / REJECTED 的一方
```

关键概念区分（这是本项目最“硬”的一点）：**重建状态**（读日志）、**重新执行**（跑执行器）、
**确认外部副作用**（可信观测器核对）是三件不同的事，被拆成三个 API。统称 replay 就会重复扣款。

## 现在能看到什么（现场，无需网络、无需 API Key）

```bash
astron run-task examples/unknown_action_fixture.json     # 未知动作被拒，execution_attempted=false
astron maintenance-demo --mode mock …                    # 真实改文件+跑测试 → VERIFIER_ACCEPTED
sqlite3 state.sqlite 'select * from action_events'       # 授权/尝试/终态全在进程之外
python examples/demos/03_crash_and_reconcile.py          # 真实进程中途被杀 → 核对后才落终态
```

## 三个数字（含它们**不**代表什么）

| 数字 | 含义 | 不代表 |
| --- | --- | --- |
| `546` | 当前交付副本离线测试通过数（1 项文件系统条件跳过） | 不代表生产级安全或模型效果 |
| `7 + 6` | 已登记的受限工具数 + 受治理终端会话数，全部有界 | 不代表工具很多或功能很全——刻意小而显式 |
| `120 / 0` | R2 正式运行 120 次（40 Direct / 40 Single / 40 Team）；能力子集 `0/72` | **不代表 Astron 更强**：三臂同为 0 是地板效应，另有 23 次 provider 错误造成臂间差异删失 |

## 版本口径（评委若要追问“测的是哪个版本”）

```text
PRODUCT_SNAPSHOT      = d32d3ec   ← 今天演示的这份代码
R2_EVALUATED_RUNTIME  = 13ee283   ← 被评测的那个 runtime（相差 9 个 commit）
```
R2 的结果**不是**对 `d32d3ec` 的验证；`d32d3ec` 自身没有正式模型运行证据。R3 仍在开发集校准，
**没有最终留出集结论**。

## 已知边界（我们主动说，不留给评委发现）

* 验证器只覆盖**一个固定 fixture**——通用仓库验证器是当前最大空白。
* 有界测试是真实子进程、终端是真实 shell：**受限 ≠ 只读 ≠ 操作系统沙箱**。
* 无回滚、无常驻服务/调度/指标；`UNCERTAIN` 会停住等人工或专用核对器。
* Team 是**更窄的权限模型**，不是更强的模式：未打包、无 CLI、默认 1 轮。

## 五分钟延伸

一页简介 [ONE_PAGE_PROJECT_BRIEF.md](ONE_PAGE_PROJECT_BRIEF.md) ·
创新点 [INNOVATION_POINTS.md](INNOVATION_POINTS.md) ·
技术路线 [TECHNICAL_ROUTE.md](TECHNICAL_ROUTE.md) ·
答辩问答 [DEFENSE_QA.md](DEFENSE_QA.md) ·
研究证据边界 [../EVALUATION_SUMMARY.md](../EVALUATION_SUMMARY.md)

## 四条不要在本项目里找的东西（避免误问）

没有 UI/前端（无界面是设计选择，展示靠 CLI 与真实产物）；没有模型训练或模型效果对比；
没有客户、部署量、营收或获奖记录；没有 R3 最终结果（还没做，也不允许用开发集成绩代替）。
