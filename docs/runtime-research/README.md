# Codex / Claude Code 真实运行拆解

> 历史记录：相关三个学习模块已于 2026-11-12 移除；以下不是当前使用说明。新方案见 `docs/live-agent-lab-plan.md`。

日期：2026-11-11。用户明确把主线改为研究真实 Agent 的运行机制，而不是继续扩充模型目录和概念问答。

公开入口 `/runtime`，三种视图：真实日志回放、固定提交的 Codex 源码路线、机制与证据边界。默认源码路线，提供两条真实采集入口；私人文件只在浏览器内存解析。

## 两次受控实验

用户明确授权两种工具各运行一次。实验在独立副本中进行，没有让 Agent 开发本站，也未读取私人会话或发布原始 home 路径。任务是本站“先闪首页再跳转”问题的最小复现，源码位于 `research/runtime-case/`，并非整个生产站。

| 工具 | 实际结果 | 可核查证据 |
|---|---|---|
| Codex CLI 0.166.0 | 完成修复，只修改 boot.mjs，测试未变 | 16 条 CLI 事件；修改前 2 失败/2 通过，修改后 4 通过；命令退出码、文件变更和 diff |
| Claude Code 2.1.283 | 初始化后报认证未就绪，没有执行修复 | 3 条事件；assistant 中的 API 错误；result 同时有 subtype=success 与 is_error=true；没有工具调用 |

两次均由采集器独立复核测试文件字节未改变。不得把 Claude 初始化样例冒充成功工具循环或拿它与 Codex 比速度/能力。

公开脱敏记录在 `frontend/public/runtime-cases/`。会话 ID、绝对目录等已替换；Claude 初始化账号来源等字段已移除。只采集 CLI stdout，没有完整 system prompt、工具 schema 或原始 API 请求。Codex 的 item ID 是 CLI 动作标识，不是模型的 tool_call_id。

## 怎样阅读主案例

1. 读取规则、实现与测试的完成输出，核对模型获得了哪些具体文件证据。
2. 检查第一次测试的 exit_code=1，再定位其后发生的文件修改。
3. 区分文件变更开始与完成；用 git diff 结果核对修改内容。
4. 检查修改后测试的 exit_code=0 与四项通过，最终助手总结只作为后续陈述。
5. 查看最后 turn usage：input_tokens=56,578，cached_input_tokens=49,152。它不是单次请求的上下文长度，不能再把缓存相加，也不能由此还原每轮请求。

这是运行证据的回放，不执行日志中的任何命令。下载的文件只有脱敏记录；真实采集时间戳、模型和成本等未报告字段不补写。

## Codex 源码快照

固定上游提交 `e58bf8f5233b51e7cd1679d947e3028c1ed91b06`，不是用户 CLI 构建的自动审计，源码已逐段阅读核验。每个入口使用 GitHub blob 提交链接与行号。

| 层次 | 路径与符号 | 要研究的区别 |
|---|---|---|
| 全局指导加载 | codex-home/src/instructions/mod.rs · load_from_codex_home | AGENTS.override.md 优先；全局 provider 不等于完整项目目录发现 |
| 用户轮次循环 | core/src/session/turn.rs · run_turn | 一个用户 turn 可以包含多个模型采样与工具步骤 |
| Prompt 投影 | core/src/session/turn.rs · build_prompt | 已注册工具、模型可见规格与增量模式不是同一集合 |
| 请求组装 | core/src/client.rs · build_responses_request | 请求副本可被过滤和重建，持久历史不一定改变 |
| 工具路由 | core/src/tools/router.rs · build_tool_call | 模型返回项被解析为 ToolCall，不代表执行完成 |
| 权限执行 | core/src/tools/orchestrator.rs | 审批、沙箱选择与拒绝后重试由运行时协调 |
| 历史保留 | core/src/context_manager/history.rs · record_annotated_items | rollout 可以保留完整输出，而 live history 被截断 |

Claude Code 侧对照官方导出格式、公开机制说明与实际观察；不声称拥有其闭源内部源码。

## 采集与发布

`scripts/capture_runtime_case.py --agent codex|claude --allow-agent-run` 仅用于明确授权后的实验。先复制故障仓库到被 Git 忽略的 `.run/runtime-captures/`，独立运行前后测试、保存 stdout/stderr、变更与测试文件一致性。180 秒超时；Claude 最多 16 轮并设置 1 USD API budget 参数。该参数不代表对所有计费方式的费用保证。

原始输出只保留本地，绝不自动发布。当前两次授权已使用，不能因失败自行追加第三次运行。后续 Claude 成功轨迹需要先由用户完成 CLI 登录，再明确新的采集范围。不要读取或迁移其他服务的凭证。

发布新案例前逐条审查内容，去掉凭证、私人路径、账号来源、非任务会话和不需要公开的推理内容；保留真实失败、原始顺序与 CLI 报告字段。记录具体 CLI 版本与观察范围，不伪造完整 API 请求。
