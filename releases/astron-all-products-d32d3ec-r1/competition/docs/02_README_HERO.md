# Astron README hero draft

> 版本边界：本材料依据历史证据基线 `11c6114f6ec0504628f912ebde9ba53821badb03`；只支持该基线对应的陈述，不构成 ZIP 中 `d32d3ec1bc49a78d0b14aabb6bf0daf79d3f4d88` 快照的运行或测试证据。详见同目录 README。


## Headline

# AI 说完成，不等于任务真的完成。

## Subheadline

Astron 是面向通用 Tool-Calling Agent 的执行治理运行时。它把模型提出的动作变成可授权、可追踪、可恢复、可验证的执行事实。

## How it works

```text
模型提出动作 → 可信运行时授权并记录 → Verifier 核验验收条件 → 任务完成
```

## Three contributions

### Trusted Execution Separation（可信执行分离）

模型提议；运行时按可信身份、权限和范围授权。

### Verifier-Controlled Completion（Verifier 控制完成）

声明条件通过后，Verifier 才接受并记录任务完成。

### Action-Aware Recovery（面向动作事实的恢复）

依据动作事实核对；没有证据不盲目重试。该主张由与 Live Proof 分开的已测窗口留存运行时和确定性故障证据支持。

## Real evidence

`ASTRON_REAL_MODEL_END_TO_END_PROOF_V1`：一项受控任务记录 5 次 Provider 调用、5 次模型决策和 5 个提议工具动作；五个动作均获授权、执行并记入日志。`MAX_RPS` 从 `10` 改为 `20`，交付物 SHA-256 独立复算后与耐久记录匹配；两项条件通过后 Verifier 接受，任务成功。

## Limitation

单次成功不是统计可靠性证据；恢复来自与上述实跑分开的已测窗口留存运行时和确定性故障证据，不代表原始故障输出已重新播放或复查。无公平通用 Tool-Calling Agent 对照或生产规模证据，不主张任意系统 exactly-once。请求 `deepseek-flash`，Provider 返回的模型身份未记录。零越界写入的观察范围限于应用记录与执行前后工作区快照，不是操作系统级审计。留存测试日志不是当前提交的全量测试收据，本次未重跑测试。
