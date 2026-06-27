# API 参考

> 全部 HTTP 端点速查。实现见 `app/main.py`、`app/routers/ai_news.py`、`app/agent_chat.py`。
> 新增端点后记得回这里补一行 + 在 [index 快速导航](../index.md) 补条目。

约定：除特别说明，请求/响应均为 JSON。所有 LLM 相关端点在未配置 key 时返回 **503**。

## 1. 系统 / 静态

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 302 重定向到 `/ui/` |
| GET | `/ui/` | 返回 `static/index.html` |
| GET | `/ui/*` | 静态资源（StaticFiles 托管 `static/`） |
| GET | `/api/health` | 健康检查：`{ok, version, llm_configured, data_dir}` |

## 2. 文章（prefix `/api/ai-news`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/articles` | 分页列表。query：`q` / `pinned_only` / `tier` / `category`（逗号分隔多值）/ `offset` / `limit`（1–100）。返回 `{total, offset, limit, items}`，pinned 置顶、新→旧 |
| POST | `/articles` | 手动新增一篇（`Article` body）；按 id/url 去重；超 400 滚动淘汰（pinned 不淘汰）。也是 fetcher worker 入库的入口 |
| DELETE | `/articles/{aid}` | 删除一篇 |
| POST | `/articles/{aid}/pin` | 收藏/取消收藏（toggle） |
| GET | `/reader/{aid}` | 尽力而为的「阅读原文」：先查 `reader-cache/`，否则代理抓取原 URL 并缓存，返回 HTML（失败 502） |
| POST | `/articles/{aid}/retranslate` | 把翻译状态重置回 `pending`，让翻译 worker 重新翻 |

## 3. 深度解读（prefix `/api/ai-news`）

深度解读是一个**独立内容库**（数据直接来自 `deep-dives/*.json`，不随文章流滚动淘汰）。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/deep-dives` | **列出全部深度解读**（扫 `deep-dives/*.json`，按 `generated_at` 倒序）。每项含 `article_id/title/title_zh/source/url/generated_at/model/is_manual/has_origin_article`。`has_origin_article`=该文章是否仍在 `articles.json`（决定文章流卡片是否能跳来）。前端「🧠 深度解读」视图的数据源 |
| GET | `/articles/{aid}/deep-dive` | 取已生成的深度解读；没有则 `{status:"none"}` |
| POST | `/articles/{aid}/deep-dive` | **LLM** 生成（或重生成）单篇深度解读（带 mermaid 图），存 `deep-dives/{aid}.json`。原文章已淘汰时回退用已存解读的元信息，**仍可重生成**（不再 404）；仅在文章和解读文件都不存在时 404 |
| DELETE | `/articles/{aid}/deep-dive` | 删除深度解读 |
| POST | `/manual-dive` | **LLM** 由用户输入主题生成深度解读（`{topic, context?}`），合成一条 `source="手动输入"` 的 pinned 文章。前端入口在「🧠 深度解读」视图 |

## 4. 今日速报（prefix `/api/ai-news`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/summary/today` | 返回缓存速报 + 今日候选元数据（`cohort_size` / `cohort_preview` / `today`） |
| POST | `/summary/today` | **LLM** 基于最近 30h 文章（最多 25 篇）生成中文速报，存 `summary_today.json` |

## 5. 追踪主题 tracks（prefix `/api/ai-news`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/tracks` | 列追踪主题；为空则写入并返回默认三条（大模型/Agent/Infra） |
| PUT | `/tracks` | 整体覆盖写入（`list[Track]`），自动补 id |

## 6. 指南 guides（prefix `/api/ai-news`）

短笔记型 guides（`guides.json`）与长文型 deep-dive guides（`guides/guide_*.json`）是两套：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/guides` | 列短笔记型 guides |
| POST | `/guides` | upsert 一条短笔记（`Guide` body） |
| DELETE | `/guides/{gid}` | 删一条短笔记 |
| GET | `/guides/long` | 列长文型深度指南（读 `guides/guide_*.json`） |
| GET | `/guides/long/{slug}` | 取单篇长文指南 |
| DELETE | `/guides/long/{slug}` | 删单篇长文指南 |
| POST | `/guides/generate` | **LLM** 按主题生成长文学习指南（`{topic, article_ids?, depth, tags}`，depth=brief/deep），存 `guides/guide_*.json` |

## 7. 数据源 / 抓取 / 翻译（prefix `/api/ai-news`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/sources` | 列 feed 及健康度（合并 `DEFAULT_FEED_SPECS` 与 `sources.json` 元数据 + 每源文章计数） |
| POST | `/fetch` | 立即跑一轮抓取，返回 `{ok, added}` |
| POST | `/translate/run` | 手动跑一批翻译，返回 `{ok, translated}` |

## 8. legacy 直通 chat（prefix `/api/ai-news`）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/chat` | **旧版**无工具直通 LLM（塞最近 ~10 篇做上下文）；`{message, stream}`，stream=true 返回纯文本流。**前端已不用**，保留作 openclaw 兼容 |

## 9. 对话 agent（prefix `/api/agent`）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/chat` | **前端在用**的对话入口：sparrow ReAct agent，`{message, conversation_id?}`，返回 **SSE**（`title`/`tool_call`/`tool_result`/`final`/`error` 事件） |
| GET | `/conversations` | 列历史会话 |
| GET | `/conversations/{conv_id}` | 取单个会话的消息 |
| DELETE | `/conversations/{conv_id}` | 删会话 |

> agent 细节见 [Agent 架构](../architecture/agent-architecture.md)；两个 chat 端点并存的来龙去脉见 [backend-architecture](../architecture/backend-architecture.md) 第 6 节。
