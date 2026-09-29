# Astron 中文可视化演示

四屏离线静态演示，用于展示 Astron 的执行治理流程：受治理的动作执行、验收器确认完成、异常后的核对恢复，以及 Agent 与运行时的职责关系。

## 本地预览

```bash
cd competition
python3 -m http.server 8000
```

从项目交付目录运行命令，再访问 [http://localhost:8000/visual/](http://localhost:8000/visual/)。页面使用本地 CSS、JavaScript、回放数据和证据映射文件，不需要构建步骤或外部依赖。它不会连接实时模型服务，也不会启动 Astron 运行时。

## 页面

- [01 · 受治理执行](SCREEN_01_EXECUTION_PROOF.html)
- [02 · 验收器控制完成](SCREEN_02_VERIFIER_CONTROL.html)
- [03 · 异常恢复与核对](SCREEN_03_ACTION_AWARE_RECOVERY.html)
- [04 · 执行职责说明](SCREEN_04_GENERIC_AGENT_VS_ASTRON.html)

各页截图见 [`screenshots/`](screenshots/)；命令行演示动图和架构图见项目总览 README。
