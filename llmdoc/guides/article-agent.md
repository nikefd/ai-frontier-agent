# 文章页真实 Agent 检索

2026-11-12 首版。入口在 `/feed` 顶部「让 Agent 帮我找文章」，不恢复已移除的三个学习模块。

## 使用与边界

已验证邮箱的登录用户输入研究任务后，使用既有 DeepSeek 配置及 AI 额度真实运行。现有 Harness 自动决定搜索词、读取对象与结束；最多四轮带工具调用及一轮收尾。工具仅 `query_articles`、`read_article`，不允许写收藏/追踪、不访问 shell，也不是全网搜索。文章工具提供本站保存的摘要、已有个人解读，不保证有原文全文；原文链接单独打开。结果卡来自实际工具输出，模型回答与这些卡片分开展示。

本版是基础工具循环的真实可视化，尚无规划器、多 Agent、独立核验、单步控制或分支。停止会阻止后续调用，正在发送的 provider 请求可能继续消耗；同用户只能有一个此类运行，取消时仍等待在途请求退出才解除占用。页面刷新清除记录，运行不写对话记忆。

## 架构

- `app/agent_runtime/llm.py`：`request_payload` 是请求正文单一组装点；可观察运行把同一正文交给 `chat(prepared_payload=...)`。只捕获 JSON 正文，无认证头。
- `harness.py`：`trace=True` 增加 model_request/model_response、原始工具输出、实际截断回填；事件保存独立快照。工具事件带 turn/call_id，下一轮确实使用该 tool_call_id 与 content。未开启 trace 的旧聊天保留原有摘要事件。
- `app/agent_research.py`：身份/额度、只读工具选择、研究提示、并发占用、断连取消与 SSE；阻塞 provider 与工具在工作线程执行，不阻塞单 uvicorn 的事件循环。复用现有 `build_tools` 与 Harness，没有第二套 Agent 引擎。
- `frontend/src/article-agent/run-state.js`：SSE 分块解码与事件投影，文章只从成功工具结果提取并按 ID 合并。
- `run-view.js`：回答/文章、上下文→模型→工具流程、可点选时间线、请求消息与工具 schema 检查器。实际发出正文可以完整展开。token 只累计 API 已报告的输入/输出，不再加缓存 token；缺失时不伪装零。
- `article-agent.js`：表单、fetch/AbortController、状态与 DOM 交互；身份变化中止并清空私有记录。样式局部作用域，移动端先显示过程再显示回答。

## 验证

自动测试覆盖捕获正文与实际发送一致、早期事件不被后续消息修改、call_id/回填一致、截断、取消、只读工具集、鉴权/重复运行、SSE 跨字节解码、只从真实工具结果生成卡片。Mock 测试不能代替真实 DeepSeek 验收；真实运行另行记录结果，不把预写回复展示为线上 Agent 输出。

浏览器需检查：未登录入口、实际调用/结果/下一轮请求、选择时间线、原文及站内查看链接、停止/清空/身份变化、中英文、390px、恶意 HTML 转义。
