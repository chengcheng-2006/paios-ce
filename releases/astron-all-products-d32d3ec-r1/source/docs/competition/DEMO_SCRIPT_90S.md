# 90 秒演示脚本（可原样执行）

一条链走完评委需要看到的五件事：

```text
model proposal → Astron governance → tool execution → durable record → verifier-controlled completion
```

不展示测试流水账，不放截图，不做 PPT 动画。每步都是真实命令，全部离线（无 Key、无网络）。
计时基于本机 macOS/arm64 + CPython 3.13 实测，含人工停顿总计约 **85 秒**。

## 准备（不计时，提前 2 分钟做完）

```bash
cd project && python3 -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev]"
which astron sqlite3            # 两个都要在 PATH 上
```

把终端字号调大、清屏，然后只设一个共享工作目录：

```bash
export P=$(mktemp -d /tmp/astron-pitch-XXXXXX)
export PYTHONWARNINGS='ignore:Field name "schema" in :UserWarning'
```

---

## 幕 1 · 提议 ≠ 授权（0:00 – 0:12）

> "这是一个模型可以发出的工具调用。"

```bash
astron run-task examples/unknown_action_fixture.json; echo "exit=$?"
```

（屏幕上想只留关键四行，就用：
`astron run-task examples/unknown_action_fixture.json | grep -E '"action_class"|"error_code"|"decision"|"execution_attempted"'`）

只指三个字段：

```text
"action_class": "UNKNOWN_ACTION"      "error_code": "E_UNKNOWN_ACTION"
"decision": "blocked"                 "execution_attempted": false      exit=5
```

> "动作名是模型编的。运行时在任何能力检查、审批检查**之前**显式拒绝它——
> 而且没有执行任何东西。`execution_attempted=false` 就是整个项目的立场。"

*实测 ≈ 1.4 s*

## 幕 2 · 一次真实受治理任务（0:12 – 0:40）

> "现在让它真干活。提议来自离线 Mock，但授权、执行、记录、验收一步都不少。"

```bash
astron maintenance-demo --mode mock --workspace "$P/ws" --state-db "$P/state.sqlite" \
  --task-id pitch | grep -E '"actions"|"status"|"verifier"|read_text|patch_text|test\.|write_artifact|validate'
```

屏幕上会依次出现七个受治理动作与两个判定：

```text
  "actions": [
    "workspace.read_text",
    "workspace.read_text",
    "workspace.read_text",
    "workspace.patch_text",
    "test.run_pytest_bounded",
    "workspace.write_artifact",
    "validate.json"
  "status": "PASS",
  "verifier": "VERIFIER_ACCEPTED"
```

> "模型提议，权限引擎裁决，执行器真的改了文件、真的跑了测试；
> 但**宣布完成的不是我，也不是模型**——是验证器，判据是 `VERIFIER_ACCEPTED`。"

*实测 ≈ 0.6 s*

## 幕 3 · 持久记录：证据在进程之外（0:40 – 0:55）

> "这不是打印出来就没了。"

```bash
sqlite3 "$P/state.sqlite" "select count(*) as governed_actions from action_journal;
select current_state, count(*) from action_journal group by current_state;
select status, reason_code, verifier_version from task_verifications;"
```

```text
8
SUCCEEDED|8
ACCEPTED|VERIFIER_ACCEPTED|phase3-maintenance-verifier-v1
```

> "每个动作都留下授权记录、`ATTEMPT_STARTED`、终态与只追加事件——
> 状态存在这个 SQLite 文件里，不存在于对话历史里。"

*实测 ≈ 0.05 s*

## 幕 4 · 崩溃与不确定（0:55 – 1:20）

> "真正区分框架和运行时的，是死在中间的时候。"

```bash
python examples/demos/03_crash_and_reconcile.py \
  | grep -E "child exit code|classification=|executor_invoked=|error_code=|observation="
```

```text
    child exit code: 72 (72 = killed inside the side-effect window)
    recover_task -> classification=NEEDS_RECONCILIATION
    executor_invoked=False needs_reconciliation=True executor_calls=0
    authorization: blocked error_code=E_IDEMPOTENCY_KEY_REUSE_MISMATCH
    executor_invoked=False executor_calls=0
    observation=CONFIRMED_SUCCEEDED new state=SUCCEEDED
```

（同一屏里还能看到 `ledger still has 1 side effect(s)`：副作用账本自始至终只有一行。）

> "子进程在**副作用之后、终态写入之前**被真实杀死。重启后运行时不猜、不重放：
> 同样的动作再投一次被拒绝（`executor_invoked=False`），换主体重用同一个幂等 key 被阻断，
> 只有可信观测器读到真实证据，动作才落 `SUCCEEDED`——账本始终只有一行。
> **重建状态、重新执行、确认外部副作用是三件事**，都叫 replay 就会重复扣款。"

*实测 ≈ 0.3 s*

## 幕 5 · 收束与边界（1:20 – 1:30）

> "范围说清楚：验证器目前只覆盖一个固定 fixture，通用仓库验证器是最大的空白；
> 有界测试是真实子进程、终端是真实 shell，受限不等于沙箱；`UNCERTAIN` 设计上就会停住。
> 测量层面，R2 的 120 次运行发生在 `13ee283`，能力子集是三臂同为 0 的地板效应，
> **没有证明 Astron 比通用 Agent 更强**；今天演示的是机制与失效语义，全部离线可复跑。"

最后一句回到主题：

> "**模型提议，运行时裁决，验证器验收。**"

---

## 时间分配

| 幕 | 内容 | 秒 |
| --- | --- | --- |
| 1 | 提议被拒绝 | 12 |
| 2 | 受治理任务跑到验收 | 28 |
| 3 | 持久记录 | 15 |
| 4 | 崩溃 → 不确定 → 核对 | 25 |
| 5 | 边界收束 | 10 |
| **合计** | | **≈ 90** |

命令本身只占约 3 秒，其余是讲解停顿；如果现场只剩 60 秒，砍幕 3（口述“记录已落 SQLite”），
不要砍幕 4——那是本项目与其他 Agent 框架的分界。

## 现场兜底

| 状况 | 处置 |
| --- | --- |
| 只剩 45 秒 | 幕 1 + 幕 4（拒绝 + 崩溃核对），一句带过幕 2 |
| 幕 2 报 `REJECTED` | 工作目录被复用了；`export P=$(mktemp -d …)` 重开一个再跑 |
| 幕 4 出现 child stderr | 不在仓库根目录执行；回到 `project/` |
| 没有 `sqlite3` | 跳过幕 3，改用 `python -c` 读 `store.journal_events(...)`，或直接口述 |
| 满屏 pydantic 警告 | 上面 `PYTHONWARNINGS` 未生效；该警告是已知的上游命名告警，只在 stderr，不影响结果 |
| 网络/账号 | 全程不需要；不要临时改成 live 模式 |
