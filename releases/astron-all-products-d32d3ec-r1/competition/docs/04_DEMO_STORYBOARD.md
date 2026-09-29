# Astron 演示分镜

> 版本边界：本材料依据历史证据基线 `11c6114f6ec0504628f912ebde9ba53821badb03`；只支持该基线对应的陈述，不构成 ZIP 中 `d32d3ec1bc49a78d0b14aabb6bf0daf79d3f4d88` 快照的运行或测试证据。详见同目录 README。


> 依据：`ASTRON_COMPETITION_EVIDENCE_BASELINE_V1`。比较对象为通用 Tool-Calling Agent；全片最多三幕，只使用该基线记载的事实与证据。恢复内容标明为独立的留存运行时与已测故障窗口证据，不剪辑成 Live Proof 的一部分。

## Scene 1 — 真实成功任务（ASTRON_REAL_MODEL_END_TO_END_PROOF_V1）

**画面**

- 展示任务约束：只将 `src/limiter.py` 中 `MAX_RPS` 从 `10` 改为 `20`，保留其他两个常量，并交付报告。
- 并列展示五次 Provider 调用、五次模型决策、五次受治理动作，以及授权、动作日志和成功回执的记录摘要。
- 展示改动前后值与交付物摘要核对结果。交付物 SHA-256：`3c0a0c51248b9f9431bc869d8e6776b8ce882d0479ae9dba33eb4e258652c173`。

**旁白**

> “在一个受控仓库任务中，真实模型提出五次决策，Astron 对五次动作进行授权和记录。`MAX_RPS` 从 10 调整到 20，交付物摘要与耐久记录相符。”

**屏幕限定语**

> “本次请求模型 ID 为 `deepseek-flash`；Provider 返回的 model 字段未记录，服务端实际模型身份未知。未观察到范围外工作区写入，依据仅限应用记录与执行前后工作区快照比较；这不是操作系统级或全进程文件审计。”

## Scene 2 — 完成权由 Verifier 决定

**画面**

- 显示同一 Live Proof 中的事件顺序：`PROPOSE_COMPLETE` → `VERIFICATION_STARTED` → `VERIFICATION_RESULT: ACCEPT` → `VERIFICATION_ACCEPTED` → `TASK_SUCCEEDED`。
- 显示 `AC-CeilingRaised=PASS`、`AC-ReportDelivered=PASS` 及耐久验收状态 `ACCEPTED`。

**旁白**

> “模型先提出完成。两项预先声明的条件通过核验并被耐久接受后，任务才进入成功状态。AI 说完成，不等于任务真的完成。”

## Scene 3 — 面向动作事实的恢复（运行时 / 已测故障窗口演示；非 Live Proof）

**画面**

- 标题明确标记：**运行时 / 已测故障窗口演示；独立故障证据，不是成功 Live Proof 片段**。
- 用状态示意展示：动作尝试已持久化 → 进程在副作用后、终态写入前退出 → `UNCERTAIN` → 可信外部核对 → 根据核对结果决定状态；`NO_EVIDENCE` 不触发重试。
- 展示留存固定故障矩阵 `15/15` 摘要以及运行时测试覆盖的退出窗口。注明原始逐进程输出目录目前不可用，当前审查无法逐条复查或重放；不得呈现为逐事件录屏或声称有可播放故障轨迹。

**旁白**

> “恢复能力来自独立的确定性故障注入证据。没有可信终态时，Astron 将动作标为不确定并先要求核对；本次成功实跑没有发生崩溃或重启。”

**屏幕限定语**

> “恢复语义由留存故障矩阵摘要和运行时测试支持，限于已测故障窗口；原始逐进程输出当前不可复查。不代表任意外部系统 exactly-once，也不证明生产规模可靠性。”
