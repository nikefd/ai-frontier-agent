# API 参考

> 全部 HTTP 端点速查。实现见 `app/main.py`、`app/routers/ai_news.py`、`app/agent_chat.py`。
> 新增端点后记得回这里补一行 + 在 [index 快速导航](../index.md) 补条目。

约定：除特别说明，请求/响应均为 JSON。所有 LLM 相关端点在未配置 key 时返回 **503**。

**鉴权约定（多用户后）**：写操作（POST/PUT/DELETE）和所有 LLM 端点要求登录，未登录返回 **401**；只读端点公开（用户产物的读如 tracks/deep-dives/conversations 未登录返回**空**）。下表「🔒」列标注：`写` = 需登录写，`读*` = 按当前用户过滤的读（匿名得空），空 = 公开读。鉴权细节见 [认证架构](../architecture/auth-architecture.md)。

## 0. 认证（prefix `/api/auth`）

| 方法 | 路径 | 🔒 | 说明 |
|---|---|---|---|
| POST | `/register` | — | 注册 `{email, password}`；首个账号自动为 admin 并继承老数据；成功下发会话 cookie。限流 8 次/60s |
| POST | `/login` | — | 登录 `{email, password}`；成功下发会话 cookie。错误统一文案防枚举。限流 8 次/60s（按 IP+邮箱） |
| POST | `/logout` | — | 清除会话 cookie |
| GET | `/me` | — | 返回当前用户 `{user: {id,email,role} | null}` |

## 1. 系统 / 静态

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 302 重定向到 `/ui/` |
| GET | `/ui/` | 返回 `static/index.html` |
| GET | `/ui/*` | 静态资源（StaticFiles 托管 `static/`） |
| GET | `/api/health` | 健康检查：`{ok, version, llm_configured, data_dir}` |

## 2. 文章（prefix `/api/ai-news`）

| 方法 | 路径 | 🔒 | 说明 |
|---|---|---|---|
| GET | `/articles` | 读* | 分页列表。query：`q` / `pinned_only` / `tier` / `category`（逗号分隔多值）/ `offset` / `limit`（1–100）。返回 `{total, offset, limit, items}`，pinned 置顶、新→旧。**每项的 `pinned`/`deep_dive_status` 按当前用户叠加**（匿名全为未 pin/无解读） |
| POST | `/articles` | 写 | 手动新增一篇（`Article` body）；按 id/url 去重；超 400 滚动淘汰（被**任一用户** pin 的不淘汰）。也是 fetcher worker 入库的入口 |
| DELETE | `/articles/{aid}` | 写 | 删除一篇（全局文章） |
| POST | `/articles/{aid}/pin` | 写 | 收藏/取消收藏（toggle）。pin 存当前用户的 `pins.json`，不写全局文章对象 |
| GET | `/reader/{aid}` | — | 尽力而为的「阅读原文」：先查 `reader-cache/`，否则代理抓取原 URL 并缓存，返回 HTML（失败 502） |
| POST | `/articles/{aid}/retranslate` | 写 | 把翻译状态重置回 `pending`，让翻译 worker 重新翻 |

## 3. 深度解读（prefix `/api/ai-news`）

深度解读是一个**按用户独立的内容库**（数据来自该用户的 `users/<uid>/deep-dives/*.json`，不随文章流滚动淘汰）。

| 方法 | 路径 | 🔒 | 说明 |
|---|---|---|---|
| GET | `/deep-dives` | 读* | **列出当前用户的全部深度解读**（扫其 `deep-dives/*.json`，按 `generated_at` 倒序）。匿名返回空。每项含 `article_id/title/title_zh/source/url/generated_at/model/is_manual/has_origin_article`。`has_origin_article`=该文章是否仍在全局 `articles.json` |
| GET | `/articles/{aid}/deep-dive` | 读* | 取当前用户已生成的深度解读；没有则 `{status:"none"}` |
| POST | `/articles/{aid}/deep-dive` | 写 | **LLM** 生成（或重生成）当前用户的单篇深度解读（带 mermaid 图），存其 `deep-dives/{aid}.json`。原文章已淘汰时回退用已存解读的元信息仍可重生成 |
| DELETE | `/articles/{aid}/deep-dive` | 写 | 删除当前用户的该深度解读 |
| POST | `/manual-dive` | 写 | **LLM** 由用户输入主题生成深度解读（`{topic, context?}`），只写当前用户的深度解读库（`source="手动输入"`），**不再插入全局文章流** |

## 3b. 个人画像（prefix `/api/ai-news`）

按用户独立的「兴趣画像」缓存（`users/<uid>/profile.json`），聚合该用户的 pins / deep-dives / tracks / 对话标题做 LLM 推断。

| 方法 | 路径 | 🔒 | 说明 |
|---|---|---|---|
| GET | `/profile` | 读* | 取当前用户缓存画像；无则 `{status:"none"}`；匿名 `{status:"none"}`。命中含 `generated_at/model/signals/body`（`body` 为结构化中文 Markdown） |
| POST | `/profile` | 写 | **LLM** 聚合 pins/深度解读主题/tracks/对话标题生成画像，存 `profile.json`。信号全空（pins+深度解读+对话=0）返回 **400**；LLM 未配置 **503** |

> 实现在独立模块 `app/routers/profile.py`（从 ai_news 拆出，复用其 loader / 路径函数）。信号聚合见 `_collect_profile_signals(uid)`；对话标题用 `storage.sqlite_ro` 只读该用户 `ui.db`，**不 import agent_chat** 以避免 `agent_chat → agent_tools → ai_news` 循环依赖。

## 4. 今日速报（prefix `/api/ai-news`）

| 方法 | 路径 | 🔒 | 说明 |
|---|---|---|---|
| GET | `/summary/today` | — | 返回缓存速报 + 今日候选元数据（`cohort_size` / `cohort_preview` / `today`）。全局共享 |
| POST | `/summary/today` | 写 | **LLM** 基于最近 30h 文章（最多 25 篇）生成中文速报，存全局 `summary_today.json` |
| GET | `/for-you` | 读* | **个性化排序**：把今日候选（同速报 cohort）按当前用户画像信号（pin 分类分布 / 高频标签 / track 关键词）加权重排，返回 `{personalized, today_count, items}`，每项带 `_score`/`_reasons`。**纯代码打分，0 LLM 调用**。匿名或无信号时 `personalized:false`、退化为按时间排序 |

> `/for-you` 实现在独立模块 `app/routers/feed_personal.py`，打分纯函数 `score_articles()` 有单测（`tests/test_feed_personal.py`）。复用 ai_news 的 `_articles_for_today()` cohort 与 profile 的信号聚合。

## 5. 追踪主题 tracks（prefix `/api/ai-news`）

| 方法 | 路径 | 🔒 | 说明 |
|---|---|---|---|
| GET | `/tracks` | 读* | 列当前用户的追踪主题；匿名返回空。新用户首次读会初始化默认三条（大模型/Agent/Infra） |
| PUT | `/tracks` | 写 | 整体覆盖写入当前用户的 tracks（`list[Track]`），自动补 id |

## 6. 指南 guides（prefix `/api/ai-news`）

短笔记型 guides（`users/<uid>/guides.json`）与长文型 deep-dive guides（`users/<uid>/guides/guide_*.json`）是两套，均按用户独立：

| 方法 | 路径 | 🔒 | 说明 |
|---|---|---|---|
| GET | `/guides` | 读* | 列当前用户的短笔记型 guides；匿名空 |
| POST | `/guides` | 写 | upsert 一条短笔记（`Guide` body） |
| DELETE | `/guides/{gid}` | 写 | 删一条短笔记 |
| GET | `/guides/long` | 读* | 列当前用户的长文型深度指南；匿名空 |
| GET | `/guides/long/{slug}` | 读* | 取当前用户的单篇长文指南 |
| DELETE | `/guides/long/{slug}` | 写 | 删当前用户的单篇长文指南 |
| POST | `/guides/generate` | 写 | **LLM** 按主题生成长文学习指南（`{topic, article_ids?, depth, tags}`，depth=brief/deep），存当前用户的 `guides/guide_*.json` |

## 7. 数据源 / 抓取 / 翻译（prefix `/api/ai-news`）

| 方法 | 路径 | 🔒 | 说明 |
|---|---|---|---|
| GET | `/sources` | — | 列 feed 及健康度（合并 `DEFAULT_FEED_SPECS` 与 `sources.json` 元数据 + 每源文章计数）。全局共享 |
| POST | `/fetch` | 写 | 立即跑一轮抓取，返回 `{ok, added}` |
| POST | `/translate/run` | 写 | 手动跑一批翻译，返回 `{ok, translated}` |

## 8. legacy 直通 chat（prefix `/api/ai-news`）

| 方法 | 路径 | 🔒 | 说明 |
|---|---|---|---|
| POST | `/chat` | 写 | **旧版**无工具直通 LLM（塞最近 ~10 篇做上下文）；`{message, stream}`，stream=true 返回纯文本流。**前端已不用**，保留作 openclaw 兼容 |

## 9. 对话 agent（prefix `/api/agent`）

| 方法 | 路径 | 🔒 | 说明 |
|---|---|---|---|
| POST | `/chat` | 写 | **前端在用**的对话入口：sparrow ReAct agent，`{message, conversation_id?}`，返回 **SSE**（`title`/`tool_call`/`tool_result`/`final`/`error` 事件）。工具按当前用户绑定数据源 |
| GET | `/conversations` | 读* | 列当前用户的历史会话（其独立 `ui.db`）；匿名空 |
| GET | `/conversations/{conv_id}` | 读* | 取当前用户某会话的消息；匿名空 |
| DELETE | `/conversations/{conv_id}` | 写 | 删当前用户的会话 |

> agent 细节见 [Agent 架构](../architecture/agent-architecture.md)；两个 chat 端点并存的来龙去脉见 [backend-architecture](../architecture/backend-architecture.md) 第 6 节。
