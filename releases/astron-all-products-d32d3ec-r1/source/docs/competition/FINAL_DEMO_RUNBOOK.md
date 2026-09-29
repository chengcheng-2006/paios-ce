# Astron — 最终演示 Runbook（操作版）

面向操作者：按顺序执行即可，不需要临场判断。讲稿与停顿设计见
[DEMO_SCRIPT_90S.md](DEMO_SCRIPT_90S.md)（90 秒）与 [PITCH_3MIN.md](PITCH_3MIN.md)（3 分钟路演）。

```text
PRODUCT_SNAPSHOT      = d32d3ec1bc49a78d0b14aabb6bf0daf79d3f4d88
R2_EVALUATED_RUNTIME  = 13ee283
本 runbook 全流程：无 API Key、无网络、无外部服务、无真实用户数据；
副作用只发生在临时目录内（fixture 文件 + SQLite + 一个 ledger 文件）。
```

---

## A. T-10 分钟预检（必须全绿才开始）

```bash
cd project
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev]"

export PYTHONWARNINGS='ignore:Field name "schema" in :UserWarning'   # 屏蔽已知的上游 pydantic 命名告警
which astron                                   # 必须有输出
astron --help | head -3                         # 七个子命令可见
astron health > /dev/null && echo READY        # 期望 READY
command -v sqlite3 >/dev/null && echo "sqlite3 OK" || echo "sqlite3 MISSING → 用 D 节兜底"
```

| 预检项 | 期望 | 不合格时 |
| --- | --- | --- |
| `pip install -e` 成功 | 无报错 | 检查 Python 版本 `>=3.11`；不要用系统 3.9 |
| `astron` 在 PATH | 有路径 | 未激活 venv |
| `astron health` | 退出码 0 | 看 stderr；通常是依赖未装全 |
| `sqlite3` 可用 | 可用 | 见 D 节兜底（已实测两种） |
| 终端宽度 | ≥ 100 列 | JSON 换行会打断讲解节奏 |
| 屏幕投影字号 | 调大 2 档 | 评委看不到 `"execution_attempted": false` 就等于没演示 |

**不要临时改网络模式、不要现场接 Provider、不要现场 pip install 新东西。**

## B. 命令顺序（整段可粘贴，实测命令耗时 ≈ 2.4 秒）

**必须在 bash 里执行**（`echo "exit=${PIPESTATUS[0]}"` 读的是管道首端命令的退出码）。
zsh 用户先进 `bash`，或把该行换成 zsh 写法 `echo "exit=$pipestatus[1]"`；
否则屏幕上 `exit=` 会是空值（这是 shell 差异，不是 Astron 的行为）。

```bash
export P=$(mktemp -d /tmp/astron-demo-XXXXXX)          # ① 一次性共享工作目录

astron run-task examples/unknown_action_fixture.json \
  | grep -E '"action_class"|"error_code"|"decision"|"execution_attempted"'
echo "exit=${PIPESTATUS[0]}"                            # ② 提议被拒，期望 exit=5

astron maintenance-demo --mode mock \
  --workspace "$P/ws" --state-db "$P/state.sqlite" --task-id pitch \
  | grep -E '"actions"|"status"|"verifier"|read_text|patch_text|test\.|write_artifact|validate'
                                                         # ③ 受治理任务跑到验收

sqlite3 "$P/state.sqlite" \
  "select current_state, count(*) from action_journal group by current_state;
   select status, reason_code, verifier_version from task_verifications;"
                                                         # ④ 持久记录（进程之外）

python examples/demos/03_crash_and_reconcile.py \
  | grep -E "child exit code|classification=|executor_invoked=|error_code=|observation="
                                                         # ⑤ 崩溃 → 不确定 → 核对
```

时间分配（含讲）：**② 12 s → ③ 28 s → ④ 15 s → ⑤ 25 s → 收束 10 s ≈ 90 s**。

## C. 每步：屏幕会看到什么 + 说一句什么

### ② 未知动作被拒

```text
"action_class": "UNKNOWN_ACTION"
"error_code": "E_UNKNOWN_ACTION"
"decision": "blocked"
"execution_attempted": false
exit=5
```

> 说："动作名是模型编的。运行时在任何能力检查、审批检查**之前**显式拒绝它，
> 而且什么都没执行——`execution_attempted=false` 就是本项目的立场。"

⚠️ 不要说成“模型出错了”；重点是**权力在运行时**，不在模型。

### ③ 一次真实受治理任务

```text
  "actions": [
    "workspace.read_text",     ×3
    "workspace.patch_text",
    "test.run_pytest_bounded",
    "workspace.write_artifact",
    "validate.json"
  "status": "PASS",
  "verifier": "VERIFIER_ACCEPTED"
```

> 说："三个只读调用允许一批，改写动作每个独占一轮；文件真的改了、测试真的跑了。
> 但宣布完成的不是我、也不是模型——是验证器。"

必须补一句（防止误读）：**"这里的提议来自离线 Mock，所以这一步测的是运行时，不是模型智力。"**

### ④ 持久记录

```text
SUCCEEDED|8
ACCEPTED|VERIFIER_ACCEPTED|phase3-maintenance-verifier-v1
```

> 说："八个受治理动作和验收结论落在 SQLite 里。进程退出后证据还在——
> 这就是为什么崩溃后可以判断，而不是靠模型回忆。"

### ⑤ 崩溃与核对

```text
    child exit code: 72 (72 = killed inside the side-effect window)
    recover_task -> classification=NEEDS_RECONCILIATION
    executor_invoked=False needs_reconciliation=True executor_calls=0
    authorization: blocked error_code=E_IDEMPOTENCY_KEY_REUSE_MISMATCH
    executor_invoked=False executor_calls=0
    observation=CONFIRMED_SUCCEEDED new state=SUCCEEDED
```

> 说："子进程在**副作用之后、终态写入之前**被真实杀死。重启后运行时不猜、不重放：
> 同主体重投被拒，换主体重用幂等 key 被阻断，只有可信观测器读到真实证据才落终态，
> 而副作用账本始终只有一行。"
> 收这一段的关键词：**重建状态、重新执行、确认外部副作用是三件事。**

## D. `sqlite3` 不可用时的兜底（两种，均已实测）

兜底 1 — 标准库一行，不需要任何 CLI：

```bash
python -c "import sqlite3; d=sqlite3.connect('$P/state.sqlite'); d.row_factory=sqlite3.Row; \
print([(r['current_state'], r['n']) for r in d.execute('select current_state, count(*) as n from action_journal group by current_state')]); \
print([dict(r) for r in d.execute('select status, reason_code from task_verifications')])"
```

输出：
```text
[('SUCCEEDED', 8)]
[{'status': 'ACCEPTED', 'reason_code': 'VERIFIER_ACCEPTED'}]
```

兜底 2 — 用产品自身的状态 API（同时顺带展示“状态是可编程读取的事实”）：

```bash
python -c "
import sqlite3, sys
from paios_ce.state import SQLiteDurableStateStore
jid = sqlite3.connect('$P/state.sqlite').execute('select journal_id from action_journal limit 1').fetchone()[0]
with SQLiteDurableStateStore('$P/state.sqlite') as s:
    print([(e.state.value, e.event_kind) for e in s.journal_events(jid)])"
```

输出：
```text
[('RECORDED', 'JOURNAL_RECORDED'), ('AUTHORIZED', 'AUTHORIZATION_RECORDED'),
 ('ATTEMPT_STARTED', 'ATTEMPT_STARTED'), ('SUCCEEDED', 'TERMINAL_SUCCEEDED')]
```

兜底 3 — 都没有 Python 交互条件时：**跳过 ④，口述“记录已落入 SQLite，问答环节可现场读回”**，
不要放静态截图。

## E. 现场异常处置

| 现象 | 原因 | 处置 |
| --- | --- | --- |
| `exit=` 打印为空 | 当前 shell 是 zsh，`${PIPESTATUS[0]}` 不适用 | 输入 `bash` 进入 bash 再跑，或改用 `$pipestatus[1]` |
| ③ 报 `"status": "REJECTED"` | 工作目录被复用（fixture 已被改过） | `export P=$(mktemp -d …)` 重开，重跑 ③④ |
| ③ 报 `CONFIGURATION_ERROR` | `--workspace`/`--state-db` 路径父目录不可建或已存在同名文件 | 换新的 `$P` |
| ⑤ 有 `child stderr` 输出 | 不在 `project/` 根目录执行 | `cd project` 后重跑 |
| ② 或 ③ 出现满屏 `UserWarning` | A 节的 `PYTHONWARNINGS` 未生效 | 忽略即可：这是已知上游命名告警，只在 stderr，不影响结果 |
| `ModuleNotFoundError: team` | Team 不在 wheel 内 | 只有跑 04 号 Team 演示才会碰到：`PYTHONPATH=src:.` |
| 评委要求看代码 | — | 直接开 `src/paios_ce/runtime/durable_runtime.py` 第 71-100 行，一个函数讲完整个裁决+持久化边界 |
| 只剩 45 秒 | — | 跑 ② + ⑤，一句带过 ③，**不要跳过 ⑤** |
| 完全没有终端条件 | — | 讲 ②③④⑤ 四段输出（本文件 C 节即为逐字预期输出）；**不得**改用假界面或演示无关产品截图 |

## F. 禁止声称清单（每一步都要遵守）

| 绝对不说 | 为什么 | 可以这样说 |
| --- | --- | --- |
| “Astron 提升了任务成功率 X%” | R2 能力子集三臂同为 0，无排序结论 | “机制可复跑；效果尚未被证明” |
| “Astron 比 Direct/其他 Agent 更强、更安全” | 安全旗标不具臂间可比性，`unsafe_replay` 方差为 0 | “今天展示的是机制与失效语义” |
| “这是沙箱 / 只读执行环境” | 有界测试是真实子进程，终端是真实 shell | “这是治理，不是隔离；不可信代码仍需容器” |
| “保证 exactly-once” | 只保证本侧不重复派发 | “不重复派发；外部副作用需要动作级核对器” |
| “已用于/服务某企业、有 N 用户” | 无客户、无部署、无用户量 | “适用场景是 X，但本包未演示” |
| “获得某奖项/认证/生产级就绪” | 上游文档明确不声称 production readiness | “Alpha / EXPERIMENTAL 定位，见 SUPPORT_MATRIX” |
| “R3 结果显示……” | R3 仍在开发集校准，无最终留出集结论 | “R3 未出最终结果” |
| “这份代码就是被测版本” | 评测发生在 `13ee283` | “演示代码是 `d32d3ec`；R2 测的是 `13ee283`，相差 9 个 commit” |
| “通用 Agent 都能直接接入” | 打包验证器只覆盖一个 fixture | “通用验证器接口是当前最大空白” |
| 演示 live 模型效果 | 现场不调用真实 Provider | 若被问：可接，但需显式端点/模型名/环境变量名，且不回落 Mock |

## G. 收束（最后 10 秒，逐字）

> “范围说在前面：验证器目前只覆盖一个固定 fixture，通用仓库验证器还没有；
> 受限执行不是沙箱；不确定态设计上就会停住等核对。
> 评测层我们只做支撑，R2 没有证明 Astron 更强，R3 还没有最终结论。
> **模型提议，运行时裁决，验证器验收。**”

## H. 演示后 30 秒内可交付的证据

```bash
ls -l "$P" "$P/ws/.astron-artifacts"                 # 产物清单
cat "$P/ws/.astron-artifacts/change_summary.json"    # 完成产物（验证器判据之一）
cat "$P/ws/maintenance_config.py"                    # 真的被改过的那一行
```

保留 `$P` 直到答辩结束：评委要求“再看一遍”时，直接读回比重新解释更有说服力。
`$P` 在 `/tmp` 下，清理即 `rm -rf "$P"`；仓库目录内不会残留任何演示产物。
