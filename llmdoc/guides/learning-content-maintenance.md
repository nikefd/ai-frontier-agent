# 学习内容维护

公开入口为 `/academy` 与 `/context`，复用现有中英界面与 Vite 构建；不增加 API、账号或后端存储。

## 模型目录

编辑 `frontend/src/academy/models.json`。稳定 `id` 不随显示名修改；记录 provider/family/task/access、官方 source、verified_on 与 verification。能力、上下文、价格、许可、生命周期和迁移关系只有核验后填写，未知用 null 或 not-verified。开放权重不等于开源许可。专用图像/音视频接口不可因提供方有 Chat API 就标注 Chat 协议。超过 30 天显示需复核，不自动声明下架。

每次从官方模型卡/API 文档核验；不以聚合商排名或发布日期推断可用性。目录协议链接只提供占位模型教学，不代表该型号执行测试。

## Agent 与案例

`agents.js` 分 product/framework/pattern，提供公开来源、部件与关联案例 ID；`agent-components.js` 负责部件解释。闭源产品仅解释公开部分。

`lessons.js` 包含双语学习目标、前置概念、练习、自检与固定请求轨迹。轨迹必须注明人工教学数据，最终答复为预写示例。新增步骤需同时更新步骤标签；失败保留错误证据并用新 ID 重试。只保存 `aif_academy_progress_v1` 的案例完成布尔标记，原始请求和测验答案不持久化。

模型链接 `/academy?model=<id>`、Agent 链接 `?tab=agents&agent=<id>`、案例链接 `?tab=lessons&lesson=<id>`；请求深链 `/context?protocol=<chat|claude|responses|gemini>&case=<id>&step=<0-based>`。可以附带 `lang=en|zh`。`learning-links.js` 用确定性名称匹配资讯；不调用 LLM。

## 解析与安全边界

请求适配器 `request-adapters.js`，分析/差异 `inspect-request.js`，流事件 `inspect-stream.js`，可选请求关联 `stream-association.js`，显示 `inspect-panels.js`，交互 `context-workbench.js`。导入在浏览器内存处理，不上传、执行、自动读取 URL 或保存。清空、刷新或身份变化移除内存输入。

请求 1 MiB，200 消息/100 工具/500 块；流 2 MiB/5000 事件。紧凑 JSON 的 UTF-8 字节不是 token；独立块合计不含包装分隔符。参数树展开 properties/items 到 6 层，组合 schema 保留原文。工具按 ID 和先后顺序关联；Gemini 无 ID 时明确警告名称匹配不唯一。引用服务端历史不能重建完整上下文。

流支持四种协议的常见文本/函数调用片段、usage、stop/error，未知事件保留。Gemini partialArgs 扩展不重组；thinking/signature 原样保留，不推断隐藏内容。没有时间戳不计算耗时；未核验费率不算成本。JSON 展示截断有提示，完整原始数据仍在编辑器。

## 验证与发布

1. `cd frontend && npm test`：目录 ID/来源/关联、四协议往返、调用异常、流分片/中断、转义和本地进度。
2. `npm run build` 与 `npm audit --omit=dev`；仓库根 `.venv/bin/pytest -q` 回归。
3. 浏览器验证中英目录、比较、Agent 部件、案例步骤→解剖台、自检保存/重置、文件导入、错误输入、390px 横向溢出和已有资讯入口。
4. 同步 README、计划状态和文档索引。按项目既有授权提交推送，检查 CI 与实际部署产物。
