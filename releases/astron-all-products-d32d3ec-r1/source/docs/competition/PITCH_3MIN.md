# 3 分钟路演稿（PITCH_3MIN）

三段式：**问题 → 机制（含 60 秒现场演示）→ 边界与下一步**。
每段给出要说的话（可直接照读）与要放的东西。不写没有依据的数字。

总时长 180 秒；现场演示占 60 秒，讲稿净字数约 420 中文字 + 演示停顿。

---

## 第 1 段 · 问题（0:00 – 0:35）

**说什么**

> "现在所有 Agent 框架都解决了同一件事：让模型顺利提出工具调用。
> 但没有解决另一件事：**动作的授权、执行事实和完成判定，仍然由模型侧的输出主导。**
> 于是有四类必然事故——
> 模型说'已修复'，文件没改；
> 白名单写在提示词里，模型调出一个根本不存在的动作名，框架'好心'地把它当成读操作；
> 进程死在写外部系统的中间，重启后没人知道做没做过，于是重跑一次，重复扣款；
> 事后想回答'谁授权、执行了什么、谁判定完成'，发现这些信息散在对话里。
> Astron 做的就是把这四件事从提示词搬进代码。"

**放什么**：一页四个痛点的表（`ONE_PAGE_PROJECT_BRIEF.md` 的痛点表），无配图。

---

## 第 2 段 · 机制（0:35 – 2:20，其中演示 60 秒）

**先给一句话立场（5 秒）**

> "模型提议，运行时裁决，验证器验收。三个互相独立的权威。"

**再说三层（20 秒）**

> "提议权在模型，它只产出一份 `ActionRequest` 数据；
> 执行裁决权在权限引擎和持久运行时——未知动作、任意 shell、提权、CRITICAL 一律硬阻断，
> 并且授权身份绑定 `幂等 key + 可信主体 + 请求指纹 + 安全上下文指纹`；
> 验收权在确定性验证器，它是唯一能写入'任务完成'的一方。
> 关键推论是：**动作成功不等于任务完成，模型说完成更不等于完成。**"

**然后现场跑（60 秒，命令见 `DEMO_SCRIPT_90S.md`，此处取幕 1 + 幕 2 + 幕 4 的压缩版）**

```bash
astron run-task examples/unknown_action_fixture.json | grep -E '"decision"|"error_code"|"execution_attempted"'; echo "exit=$?"
astron maintenance-demo --mode mock --workspace "$P/ws" --state-db "$P/state.sqlite" --task-id pitch | grep -E '"status"|"verifier"|read_text|patch_text|test\.'
sqlite3 "$P/state.sqlite" "select current_state, count(*) from action_journal group by current_state; select status, reason_code from task_verifications;"
python examples/demos/03_crash_and_reconcile.py | grep -E "child exit code|classification=|executor_invoked=|observation="
```

**边跑边说（每屏一句）**

1. `"decision": "blocked"` + `execution_attempted=false` → "模型编的动作名，在任何授权之前就被拒，什么都没执行。"
2. `"status": "PASS"` / `"verifier": "VERIFIER_ACCEPTED"` → "改写、跑测试都是真的，但宣布完成的是验证器。"
3. `SUCCEEDED|8` + `ACCEPTED|VERIFIER_ACCEPTED` → "八个受治理动作和验收结论落在 SQLite 里，不在对话里。"
4. `child exit code: 72` → `NEEDS_RECONCILIATION` → `executor_invoked=False` → `CONFIRMED_SUCCEEDED`
   → "进程死在副作用之后。运行时不猜、不重放；只有可信观测器读到真实证据才落终态。
   **重建状态、重新执行、确认外部副作用是三件事**——都叫 replay 就会重复扣款。"

**收尾一句（10 秒）**

> "这一切离线可跑：不需要 API Key、不需要网络，546 项测试里包含真实的跨进程崩溃恢复。"

---

## 第 3 段 · 边界与下一步（2:20 – 3:00）

**主动交代（25 秒）——这一段决定评委是否相信你**

> "边界说清楚。
> 第一，验收权是真的，但打包的验证器只覆盖一个固定 fixture，**通用仓库验证器是当前最大的空白**；
> 第二，有界测试是真实子进程、终端是真实 shell，**受限不等于只读，更不等于操作系统沙箱**；
> 第三，没有回滚、没有常驻服务、`UNCERTAIN` 设计上就会停住等人工核对；
> 第四，Team 模式是更窄的权限模型，不是更强的模式，它未打包、无 CLI、默认只有一轮。"

**研究证据，一句话，不展开（10 秒）**

> "评测层我们只做支撑：R2 的 120 次正式运行发生在 `13ee283`，能力子集是三臂同为 0 的
> 地板效应，所以它**没有证明 Astron 优于通用 Agent**；R3 还在开发集校准，没有最终结论。
> 今天展示的是机制与失效语义，不是效果声明。"

**下一步（5 秒）**

> "接下来三件事：可插拔的通用验证器接口、审计 sink、以及给外部副作用定义动作级核对器。"

**结束句**

> "**模型提议，运行时裁决，验证器验收。** 谢谢。"

---

## 执行提示

| 项 | 建议 |
| --- | --- |
| 超时风险 | 第 2 段演示最多 60 秒；若前面超时，砍第 2 段的三层讲解，直接进演示 |
| 冷场风险 | 幕 4 崩溃演示是全场最强的差异化时刻，不要跳过，也不要用录屏替代 |
| 反被问倒 | 把 `DEFENSE_QA.md` 的第 8、9、10 题先背下来（benchmark、R2 全 0、当前限制） |
| 绝对不要 | 说"提升 X% 成功率"、"更安全"、"已用于企业"、"R3 结果" —— 这些在本包中都没有依据 |
| 版本口径 | 全程只说 `PRODUCT_SNAPSHOT = d32d3ec`；提到 R2 数字必须同时说 `13ee283` |

## 配套材料

- 90 秒纯演示流程：[DEMO_SCRIPT_90S.md](DEMO_SCRIPT_90S.md)
- 一页评委简介：[ONE_PAGE_PROJECT_BRIEF.md](ONE_PAGE_PROJECT_BRIEF.md)
- 答辩问答：[DEFENSE_QA.md](DEFENSE_QA.md)
- 10 页 PPT 底稿：[../../../showcase/PRESENTATION_OUTLINE.md](../../../showcase/PRESENTATION_OUTLINE.md)
- 事实边界：[../EVALUATION_SUMMARY.md](../EVALUATION_SUMMARY.md)、[../SECURITY_AND_LIMITATIONS.md](../SECURITY_AND_LIMITATIONS.md)
