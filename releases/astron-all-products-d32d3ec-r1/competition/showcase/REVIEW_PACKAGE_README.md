# Astron：让 Agent 执行更清晰、更可控

Astron 是面向 AI Agent 的执行治理运行时。它把动作授权、受限执行、状态记录和结果验收放进一条清楚的流程，让团队能了解一次工具调用如何被处理，以及任务为何被判定完成。

## 项目优势

- **动作先授权，再执行**：运行时依据能力范围和策略裁决动作，明确记录允许、拒绝或阻断结果。
- **执行过程可追踪**：持久化授权、动作尝试、执行结果和验收事件，便于复核任务经过。
- **异常处理有依据**：结果不确定时先保留状态并核对可信事实，再决定是否继续。
- **完成判定有标准**：验收器检查事先声明的条件和交付物，明确给出验收结果。
- **体验门槛低**：随附离线静态演示、命令行场景动图、技术说明和讲解材料，可直接浏览。

## 流程一览

```text
Agent 提出动作 → 运行时授权 → 受限工具执行 → 记录动作与结果 → 验收器检查 → 任务完成或保留原因
```

## 演示截图

![Astron 执行治理流程演示首页](competition/visual/screenshots/00-overview.png)

| 受治理执行 | 验收与完成 |
| --- | --- |
| ![动作授权和受治理执行](competition/visual/screenshots/01-execution.png) | ![验收标准与完成状态](competition/visual/screenshots/02-verification.png) |

| 异常恢复 | 执行职责 |
| --- | --- |
| ![未知结果核对与恢复](competition/visual/screenshots/03-recovery.png) | ![Agent 与运行时的职责流程](competition/visual/screenshots/04-responsibilities.png) |

## 命令行演示

授权范围内的动作和被明确阻断的未知动作，分别通过下方的本地演示动图展示。

| 授权范围内的演示 | 未知动作阻断演示 |
| --- | --- |
| ![授权执行的命令行演示](demo_assets/paios-ce-allowed-demo.gif) | ![未知动作阻断的命令行演示](demo_assets/paios-ce-blocked-demo.gif) |

## 打开交互演示

需要 Python 3 时，可以在本材料目录运行静态网页服务：

```bash
cd competition
python3 -m http.server 8000
```

然后在浏览器打开 <http://localhost:8000/visual/>。演示包括受治理执行、验收与完成、异常恢复和执行职责四个场景；页面使用本地资源，不连接模型服务或实时运行时。

## 项目材料

- [技术报告](competition/docs/03_TECH_REPORT_CORE.md) · [评审问答](competition/docs/06_JUDGE_QA.md) · [主张与术语说明](competition/docs/07_CLAIM_LANGUAGE_AUTHORITY.md)
- [项目简介](competition/showcase/PROJECT_BRIEF.md) · [答辩提纲](competition/showcase/PRESENTATION_OUTLINE.md) · [演示讲稿](competition/showcase/DEMO_SCRIPT.md) · [常见问题](competition/showcase/FAQ.md)
- [演示页面与本地预览说明](competition/visual/README.md) · [演示证据映射](competition/demo_evidence/06_EVIDENCE_TO_SCREEN_MAP.json)
- [竞赛证据基线](competition/evidence/ASTRON_COMPETITION_EVIDENCE_BASELINE_V1.md)
