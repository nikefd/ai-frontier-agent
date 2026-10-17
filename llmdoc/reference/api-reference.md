# API 参考

> 全部 HTTP 端点速查。实现见 `app/main.py`、`app/routers/ai_news.py`、`app/agent_chat.py`。
> 新增端点后记得回这里补一行 + 在 [index 快速导航](../index.md) 补条目。

约定：除特别说明，请求/响应均为 JSON。所有 LLM 相关端点在未配置 key 时返回 **503**。

**鉴权约定**：用户写操作和个人 LLM 端点要求登录；全局内容变更要求 admin（匿名 401、普通用户 403）；用户产物的读未登录返回空。下表「🔒」列：`写` = 登录用户，`admin` = 管理员，`读*` = 按当前用户过滤，空 = 公开读。

## 0. 认证（prefix `/api/auth`）

| 方法 | 路径 | 🔒 | 说明 |
|---|---|---|---|
| POST | `/register` | — | 注册 `{email, password}`；首个账号自动为 admin 并继承老数据；成功下发会话 cookie。限流 8 次/60s |
| POST | `/login` | — | 登录 `{email, password}`；成功下发会话 cookie。错误统一文案防枚举。限流 8 次/60s（按 IP+邮箱） |
| POST | `/logout` | — | 清除会话 cookie |
| GET | `/verify` | — | 邮箱验证落地页（邮件链接指向这里）：`?token=<签名token>`，校验后标记 `email_verified` 并 302 跳 `/ui/?verify=ok|invalid` |
| POST | `/resend-verification` | 写 | 给当前登录用户重发验证邮件（限流）。已验证返回 `{already_verified:true}` |
| POST | `/change-password` | 写 | 已登录改密码 `{old_password, new_password}`。旧密码错/新密码不合规 400；成功后重发会话 cookie |
| POST | `/forgot-password` | — | 发密码重置链接 `{email}`。**防枚举：无论邮箱是否存在都返回 ok**。限流（按 IP+邮箱） |
| POST | `/reset-password` | — | 用重置 token 设新密码 `{token, new_password}`，成功后**自动登录**（下发 cookie + 返回 user）。token 无效/过期 400 |
| GET | `/me` | — | 返回当前用户 `{user: {id,email,role,email_verified} | null}` |

## 0b. 管理后台（prefix `/api/admin`）

仅 admin 可访问（守卫 `require_admin`：非 admin **403**，匿名 **401**）。实现在 `app/routers/admin.py`。

| 方法 | 路径 | 🔒 | 说明 |
|---|---|---|---|
| GET | `/users` | admin | 列全部用户（id/email/role/created_at/last_login + 产物概览 pins/deep_dives/cards，**不含 password_hash**），含 `me`=当前 admin id |
| PATCH | `/users/{uid}/role` | admin | 改角色 `{role: admin/user}`。**不能改自己**（400）；不能把最后一个 admin 降级（400） |
| DELETE | `/users/{uid}` | admin | 删用户 + 其 `users/<uid>/` 产物目录（**不可逆**）。**不能删自己**（400）；不能删最后一个 admin（400） |

> 安全护栏：自删/自降被挡 → 任一时刻系统至少留一个 admin（要操作 admin 自己也得是 admin，单 admin 时只能是自己）。测试见 `tests/test_admin.py`。

## 1. 系统 / 静态

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 返回 Vite 构建的 `static/dist/index.html` |
| GET | `/ui`、`/ui/` | 301 重定向到 `/`（旧链接兼容） |
| GET | `/assets/*` | Vite 指纹静态资源（1 年 immutable 缓存） |
| GET | `/api/health` | 健康检查：`{ok, version, llm_configured, data_dir}` |

## 2. 文章（prefix `/api/ai-news`）

| 方法 | 路径 | 🔒 | 说明 |
|---|---|---|---|
| GET | `/articles` | 读* | 分页列表。query：`q` / `pinned_only` / `translated_only` / `hands_on_only` / `tier` / `category`（逗号分隔多值）/ `tag`（逗号分隔，受控词表）/ `sort`（`newest` 默认 / `important` 按重要性降序，未评分沉底）/ `offset` / `limit`（1–100）。所有筛选均在分页前执行，返回 `{total, offset, limit, items}`。**收藏不再置顶**（按 sort 正常排，仅带 ★ 标识；收藏夹用 `pinned_only` 看）。每项的 `pinned`/`deep_dive_status` 按当前用户叠加；`importance`/`tags`/`hands_on` 由富化 worker写在全局文章上 |
| POST | `/articles` | admin | 手动新增一篇全局文章；按 id/url 去重；超 400 滚动淘汰。fetcher 在进程内直接复用该函数 |
| DELETE | `/articles/{aid}` | admin | 删除一篇全局文章 |
| POST | `/articles/{aid}/pin` | 写 | 收藏/取消收藏（toggle）。pin 存当前用户的 `pins.json`，不写全局文章对象 |
| GET | `/reader/{aid}` | — | 安全阅读副本：只抓公共 http(s)，逐跳防 SSRF，限 HTML/2MB，清洗后缓存返回；不安全 URL 400、上游失败 502 |
| POST | `/articles/{aid}/retranslate` | admin | 清空翻译与实践建议，把全局文章状态重置回 `pending` |

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
| POST | `/summary/today` | admin | **LLM** 强制重生成全局中文速报：基于最近 30h 的质量平衡候选，先按规范化标题兼容去重，再按非空 `event_key` 合并不同标题的同一事件，优先保留一手来源并把其余报道记入 `related_articles`/多源佐证；之后按 importance、来源类别、tier、时效和多样性预筛，Trending 最多 2 条、X 最多 3 条。“值得动手”只使用已审核的 `hands_on`。后台默认每 4 小时调用同一实现，候选指纹不变时跳过 LLM |
| GET | `/for-you` | 读* | **个性化排序**：把今日候选（同速报 cohort）按当前用户画像信号（pin 分类分布 / 高频标签 / track 关键词）加权重排，返回 `{personalized, today_count, items}`，每项带 `_score`/`_reasons`。**纯代码打分，0 LLM 调用**。匿名或无信号时 `personalized:false`、退化为按时间排序 |

> 速报前端会把新标题「更多动态」以及旧缓存里的「边角料」统一渲染为默认收起、带条数的渐进展开区；引用 `[n]` 仍按缓存中的 cohort 链接到原文。`/for-you` 实现在独立模块 `app/routers/feed_personal.py`，打分纯函数 `score_articles()` 有单测（`tests/test_feed_personal.py`）。复用 ai_news 的 `_articles_for_today()` cohort 与 profile 的信号聚合。

## 4b. 知识卡 + 间隔重复（prefix `/api/ai-news`）

把文章 / 深度解读 / 手动笔记转成知识卡，用 SM-2 间隔重复调度。按用户存于 `users/<uid>/review-cards.json`。**0 LLM 成本**：卡片背面复用现成摘要，调度是纯算术。所有端点需登录。

| 方法 | 路径 | 🔒 | 说明 |
|---|---|---|---|
| GET | `/review/cards` | 写 | 列当前用户全部卡片（新→旧），返回 `{total, items}` |
| POST | `/review/cards` | 写 | 新建卡：`{front, back, source_type(article/deep-dive/manual), source_id?, source_url?, tags?}`。source_type=article/deep-dive 且未传 front/back 时**自动从原内容取**中文标题+摘要。同源去重（409），原文不存在 404，缺 front 400 |
| DELETE | `/review/cards/{cid}` | 写 | 删卡 |
| GET | `/review/due` | 写 | 今日到期卡（`due ≤ 今天`）+ 统计，返回 `{today, due_count, total, items}` |
| POST | `/review/cards/{cid}/grade` | 写 | 提交复习评分 `{grade: forgot/hard/good}`，按 SM-2 更新调度，返回更新后的卡 |

> 实现：路由 `app/routers/review.py`；SM-2 算法纯函数在 `app/srs.py`（`sm2_schedule`/`is_due`/`new_srs`），有单测 `tests/test_srs.py`。卡片数据结构见 [data-storage](data-storage.md) §3.8。

## 4c. AI 复盘教练（prefix `/api/ai-news`）

苏格拉底式周复盘：聚合近 7 天活动，LLM 生成回顾 + 几个引导思考的问题。按用户存于 `users/<uid>/reflection.json`。

| 方法 | 路径 | 🔒 | 说明 |
|---|---|---|---|
| GET | `/reflection` | 读* | 取当前用户最近一次复盘（`recap` + `questions`）；无则 `{status:"none"}`；匿名 none |
| POST | `/reflection/generate` | 写 | **LLM** 基于近 7 天 pins/解读/知识卡/对话生成复盘。**先查数据**（全空 400「活动不足」），再查 LLM（未配 503）。存 `reflection.json` |

> 实现：`app/routers/reflection.py`，`collect_recent_signals(uid, now_ts)` 按时间窗聚合（`now_ts` 注入便于测试），`_parse_llm_json` 容错解析模型 JSON（有单测 `tests/test_reflection.py`）。前端「展开聊」复用 sparrow 对话组件（`window.__sparrowChat`），「存为卡片」复用知识卡端点。

## 4d. 主动建议 suggestions（prefix `/api/ai-news`）

agent 主动提议（B2）：基于用户行为信号给「下一步」建议。**纯规则、0 LLM**。

| 方法 | 路径 | 🔒 | 说明 |
|---|---|---|---|
| GET | `/suggestions` | 读* | 返回当前最该提的 1-2 条建议 `{items:[{id,text,action,view}]}`；匿名空 |

> 实现：`app/routers/suggestions.py`，规则示例：收藏 ≥5 篇且某类 ≥3 篇且无学习路径 → 建议生成路径；收藏 ≥5 篇且无画像 → 建议生成画像；收藏 ≥8 篇且无复盘 → 建议复盘。封顶 2 条不刷屏。前端文章流顶部显示为可关闭的建议条（`suggestions.js`），关闭/采纳记 localStorage 不再提示。注意与 `/learning-paths/suggestions`（推荐学习方向）是两个端点，别混。

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

## 6b. 学习路径 learning-paths（prefix `/api/ai-news`）

**分阶段学习路线图**，是 guides 之上的**编排层**（区别：guides 是单主题一篇长文；learning-path 是一个方向的多阶段路线，每阶段引用库内解读/文章）。结合画像定起点，存 `users/<uid>/learning-paths/<slug>.json`。

| 方法 | 路径 | 🔒 | 说明 |
|---|---|---|---|
| GET | `/learning-paths` | 读* | 列当前用户的路径（slug/topic/阶段数/时间）；匿名空 |
| GET | `/learning-paths/suggestions` | 读* | **推荐学习方向**（tracks + top_tags 去重）。**纯代码 0 LLM**，前端渲染成可点 chip 填入输入框。匿名空 |
| GET | `/learning-paths/{slug}` | 读* | 取某条路径详情（stages）；匿名 none |
| POST | `/learning-paths/generate` | 写 | **LLM** 按 `{topic}` + 画像 + 素材库生成分阶段路径。空 topic 400 / 无 LLM 503 / 模型无有效输出 502 |
| DELETE | `/learning-paths/{slug}` | 写 | 删除 |

> 实现：`app/routers/learning.py`。**混合素材策略**：把用户的深度解读+近期文章（带 id）喂给 LLM，stage 的 `read` 只能引用真实 id（`_resolve_reads` 丢弃编造的 id），库存不足时改用 `suggest` 文字建议。纯函数 `_parse_stages`/`_resolve_reads` 有单测 `tests/test_learning.py`。

## 7. 数据源 / 抓取 / 翻译（prefix `/api/ai-news`）

| 方法 | 路径 | 🔒 | 说明 |
|---|---|---|---|
| GET | `/sources` | — | 列 feed 及健康度（合并配置、抓取元数据、当前库文章数/最新内容时间）。每项带 `health_status=healthy/error/stale/never/orphan`、`health_reason`、抓取年龄、连续失败、最近成功/恢复；默认超过 3 个调度间隔未抓取即 `stale`。全局共享 |
| POST | `/fetch` | admin | 立即跑一轮全局抓取：相关性过滤 → 每源分轮 → 分类硬配额 → 全局 150 条上限，返回 `{ok, added}` |
| POST | `/translate/run` | admin | 手动跑一批全局翻译，返回 `{ok, translated}` |

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
