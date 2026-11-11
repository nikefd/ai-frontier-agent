# 维护真实运行拆解台

公开路由 `/runtime` 已加入 `ROUTE_VIEWS` 和 `OFFLINE_VIEWS`，不等登录检查，不增加后端 API。资料主线参见 [研究记录](../../docs/runtime-research/README.md)。

## 数据流

- `runtime/read-trace.js`：8 MiB、20,000 条限制，JSONL 按真实行号定位，JSON array 用记录序号；无效行保留诊断。
- `trace-adapters.js`：分别适配 Codex exec、rollout、Claude stream-json/transcript。Codex 生命周期按用户 turn + item ID 更新，开始/结束合并；命令完成产生对应结果。CLI item ID 不冒充 API call ID。
- Claude 按消息 ID/块索引更新重复快照；tool_use/tool_result 按 ID 与 parent_tool_use_id 范围关联。流分片留在原始观察，不重复计入完成消息。API 错误与 is_error 优先于看起来成功的 subtype；permission_denials 会生成显式权限事件。
- `analyze-trace.js`：用范围与 ID 分组，重复 ID 不自动关联；标出孤立结果和缺失结果。测试命令退出零只证明这个命令的结果，不证明任务全部正确。
- `runtime-panels.js`：事件筛选、工具/ID/文件/命令查找、双向关联、此前证据、源码入口和原始行号。JSON 和导入 HTML 只转义显示，长文本截断有提示。
- `runtime-cases.js`：已审查公开记录的双语任务、范围、版本与观察点；`runtime-cases/` 中的 JSONL 是真实脱敏采集，不是人工协议示例。变更公开文件必须同步核对观察点行号。
- `source-map.js`：固定上游 commit、文件和行号，记录读过的符号及输入/加工/输出。更新源码快照时重新核验全部入口，不只替换 SHA。

## 证据口径

Codex exec 的 turn.completed usage 是该用户轮次报告，不等于一次模型请求；多用户轮次导入只显示最后带 usage 的轮次，不无条件累加。rollout 的 total_token_usage 使用最后累计快照。Claude 优先展示 final result 报告值；模型消息 usage 在详情单独显示，不与结果重复相加。缺失字段不补零，缓存输入不重复加，费用只显示 CLI 实际报告值。

此前出现的消息/输出只是日志证据，不是重建 prompt。压缩、工具输出截断、动态工具和传输增量都会影响请求。Claude 初始化的 tools 是名称列表，不是完整 schema；permissionMode 是设置，不是一次批准。

## 安全与交互

私人日志只在浏览器内存中处理，不上传、不执行、不自动存储或放进 URL；只 fetch 本站已审查的公开案例。更换输入会撤销公开案例标签，清空会清除 URL 的案例 ID。身份变化清空内存和 DOM；公开案例可按其稳定 ID 重新载入。异步案例加载有代次检查，防止旧响应覆盖新选择。

导入正常请求 JSON/SSE 应使用 `/context`；这里导入的是 Agent 的运行记录。原始记录里的 URL 不自动请求，命令不执行。采集器原始产物只存 `.run/`，JSON/文本写入复用 app.storage 原子写。

## 验证

`cd frontend && npm test` 覆盖生命周期合并、并行/子任务范围、重复和缺失 ID、失败、压缩、累计 usage、无效输入、HTML 转义、源码固定链接和公开真实样本的事实。`npm run build`、`npm audit --audit-level=high` 与后端回归保持现有 CI。

浏览器必须检查：Codex 失败→变更→通过、Claude 认证失败、源码按钮联动、私有导入/清空、大小限制、英文和390px、站内切换不闪首页。不要运行 research/runtime-case 的故障测试当生产回归：它故意保留两项失败用于可复现实验。
