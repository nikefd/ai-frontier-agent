# 首屏路由故障的受控运行实验

这是站点真实首屏问题的最小复现，不是整个生产仓库。`boot.mjs` 初始有故障；`node --test boot.test.mjs` 应显示两项失败、两项通过。

实验目标是观察 Codex / Claude Code 怎样读取明确指导、先复现测试失败、编辑源文件并验证。测试本身保持不变。不保证模型会按预期成功，不把日志当完整 API 请求。

采集器 `scripts/capture_runtime_case.py` 会复制到被 Git 忽略的 `.run/runtime-captures/<timestamp>-<agent>/workspace`，在副本中运行指定 CLI。原始 JSONL、stderr、前后文件、独立测试与 diff 只落本地；不自动加入网站或 Git。发布前必须检查全部素材，移除私人信息并标注实际 CLI 版本、采集方式、范围与失败状态。

启动实际 Agent 需明确授权；创建复现、阅读 CLI help 和解析日志不需要运行 Agent。
