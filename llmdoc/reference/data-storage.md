# 数据存储参考

> 应用没有数据库做主存储，状态全在 `<data_dir>/` 下的一组文件里。**全局数据**在
> `ai-news/`，**认证数据**在 `auth/`，**按用户隔离的产物**在 `users/<uid>/`。
> 路径常量/函数定义在 `app/routers/ai_news.py` 与 `app/auth.py`，读写经 `app/storage.py`。

## 1. 存储根

| 形态 | 数据根 | 全局新闻目录 | 认证 | 用户产物 |
|---|---|---|---|---|
| 裸机 | `~/agent-data`（`AIF_DATA_DIR`） | `~/agent-data/ai-news/` | `~/agent-data/auth/` | `~/agent-data/users/<uid>/` |
| Docker | `/data`（命名卷 `ai-frontier-data`） | `/data/ai-news/` | `/data/auth/` | `/data/users/<uid>/` |

## 2. 文件清单

### 2.1 全局（`ai-news/`，所有用户共享）

| 文件 / 目录 | 类型 | 内容 |
|---|---|---|
| `articles.json` | list | 文章主存储，上限 400（被任一用户 pin 的不淘汰）。每项是 `Article`。**不含 per-user 的 `pinned`/`deep_dive_status`** |
| `sources.json` | dict（按 url 为 key） | 每个 feed 的抓取元数据 |
| `summary_today.json` | dict | 缓存的「今日速报」 |
| `reader-cache/*.html` | 每文件一篇 | 经白名单清洗后的安全阅读副本；旧原始缓存命中时自动迁移 |

### 2.2 认证（`auth/`，全局）

| 文件 | 类型 | 内容 |
|---|---|---|
| `users.json` | list | 用户表，每项 `UserRecord`（含 `password_hash`，bcrypt） |
| `secret.key` | text | 会话签名密钥（`AIF_SECRET_KEY` 为空时自动生成；**勿入 git**） |

### 2.3 按用户隔离（`users/<uid>/`）

| 文件 / 目录 | 类型 | 内容 |
|---|---|---|
| `tracks.json` | list | 该用户的追踪主题；首次读初始化默认 3 条 |
| `pins.json` | list | 该用户 pin 的 article id 列表（pin 从文章对象迁出后的落点） |
| `guides.json` | list | 短笔记型 guides（`Guide`） |
| `guides/guide_*.json` | 每文件一篇 | LLM 生成的长文学习指南 |
| `deep-dives/{aid}.json` | 每文件一篇 | 单篇文章的深度解读（带 mermaid） |
| `profile.json` | dict | 该用户的兴趣画像缓存（按需 LLM 生成，见 §3.7） |
| `review-cards.json` | list | 该用户的知识卡 + SM-2 间隔重复状态（见 §3.8） |
| `usage.json` | dict | 当日 LLM 操作计数 `{date, count}`，跨天自动重置（防滥用限额） |
| `reflection.json` | dict | 该用户最近一次 AI 复盘（recap + 苏格拉底问题，见 §3.9） |
| `learning-paths/<slug>.json` | 每文件一条 | 该用户的分阶段学习路径（见 §3.10） |
| `ui.db` | SQLite | 该用户的 sparrow 对话记忆（会话/消息/journal） |

> `users/_legacy/` 是迁移哨兵目录：启动时老单用户产物先搬到这里，首个注册账号（或 `AIF_ADMIN_EMAIL` 指定者）注册时改名成其 uid 目录继承。详见 [认证架构](../architecture/auth-architecture.md) 与 [已知问题](known-issues.md) 第 14 条。

> 种子数据 `seed-data/ai-news/` 是镜像内的演示数据，首次启动卷为空时由 `docker-entrypoint.sh` 灌入。注意种子里的 `sources.json` 是 `{}`（空），所以首次部署后数据源页全显示「尚未抓取」，跑一轮 fetch 后才有健康数据。

## 3. 数据结构

### 3.1 Article（`articles.json` 每项）

定义见 `app/models.py` 的 `Article`，抓取/翻译/解读过程会补字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | str | `a_` + url 的 sha1 前 12 位 |
| `title` / `url` / `source` | str | 原始标题 / 链接 / 来源名 |
| `date` | str | ISO 时间（发布或入库时间） |
| `summary` | str | 去标签后截断的英文摘要 |
| `tags` | list | 受控词表标签（富化 worker 从 `TAG_VOCAB` 选，最多 3 个） |
| `tier` | str | high/med/low；按来源 category 在启动时归一化，影响抓取相关性门槛和速报排序 |
| `category` | str | vendor/media/expert/x-ai/community/paper/blog/trending |
| `ai_relevance` | str | keyword/curated/unknown；med/low 未命中关键词的 rejected 候选不会入库，只累计在来源 `last_filtered` |
| `title_zh` / `summary_zh` | str | 中文翻译（翻译 worker 写） |
| `translation_status` | str | pending/ok/failed/skipped |
| `importance` | int? | 富化 worker 评的重要性 0-10（用于文章流 `sort=important`）；老文章/未富化为 null |
| `hands_on` | str? | 富化 worker 生成的最小实践建议；仅可操作内容非空，政策/融资/纯观点/信息不足为空。前端“可实践”筛选和“带我做”入口使用 |

> **多用户后**：`pinned` / `deep_dive_status` / `deep_dive_id` **不再持久化到全局 `articles.json`**。`pinned` 现按用户存于 `users/<uid>/pins.json`；`deep_dive_status` 由「该用户的 `deep-dives/{aid}.json` 是否存在」推导。`GET /articles` 在响应里**按当前用户叠加**这三个字段（匿名全为未 pin/无解读）。`manual` 合成文章也不再进全局流（手动解读只进用户深度解读库）。

### 3.1b UserRecord（`auth/users.json` 每项）

定义见 `app/models.py`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | str | `u_` + 16 位 hex |
| `email` | str | 小写归一化，唯一 |
| `password_hash` | str | bcrypt 哈希（含盐）；**永不返回给前端**（响应用 `UserPublic`，无此字段） |
| `role` | str | admin / user；首个注册者为 admin |
| `email_verified` | bool | 邮箱是否已验证；首个 admin 自动 True，其余注册默认 False（软提示，不阻断登录） |
| `created_at` / `last_login_at` | str | ISO 时间 |

### 3.2 sources.json（按 feed url 为 key）

每个值是该源的抓取状态：`last_fetch` / `last_ok` / `last_error` / `eligible` / `last_added` / `last_filtered` / `name` / `tier` / `category`。`GET /sources` 把它和 `DEFAULT_FEED_SPECS` 合并、再叠加每源文章计数后返回。

### 3.3 deep-dives/{aid}.json

`{article_id, article_title, article_title_zh, article_url, article_source, generated_at, model, body}`。`body` 是含一段 mermaid 的 Markdown。

这些文件构成一个**独立内容库**：`GET /deep-dives` 直接扫该目录列出全部，不经过 `articles.json` 过滤，所以原文章被文章流滚动淘汰后，解读仍然在、仍可读、仍可重新生成（`POST /articles/{aid}/deep-dive` 此时回退用本文件的元信息）。前端据 `article_id` 是否仍在 `articles.json` 算出 `has_origin_article`，决定文章流卡片能否跳来查看。`article_source == "手动输入"` 即手动新建（`/manual-dive`）的解读。

### 3.4 guides/guide_*.json（长文指南）

`{id, slug, title, topic, depth, tags, model, generated_at, updated_at, anchors[], body}`。`anchors` 是生成时引用的 RSS 文章。slug 形如 `guide_<sha1前10>`。

### 3.5 summary_today.json

`{generated_at, date, model, cohort_size, cohort_fingerprint, body, cohort[]}`。`body` 是 Markdown 速报，`cohort` 是参与生成的文章列表；`cohort_fingerprint` 是影响输出字段的 SHA-256，用于让分时任务在候选未变化时跳过 LLM。候选来自最近 30 小时，先按规范化标题精确去重（重复报道优先保留官方/高质量来源），再按 importance、来源类别、tier、时效与来源多样性预筛；Trending 最多 2 条、X 最多 3 条。旧缓存没有指纹，下一次分时任务会自动重写一次。

### 3.6 ui.db（SQLite，每用户一个）

由内联 agent 运行时（`app/agent_runtime/`，原 sparrow）的 `Memory` 类管理（建表、读写都在 `memory.py` 内部）。存对话会话、消息、agent journal。**多用户后每用户一个 `users/<uid>/ui.db`**（`Memory` 无 user 维度，故用一库一人做隔离；`agent_chat.py` 的 `_memory_for(uid)` 按 uid 选库并缓存）。应用侧若要只读查它，用 `storage.sqlite_ro`（`mode=ro` URI，多读者共享）。表结构定义在 `app/agent_runtime/memory.py`。

### 3.7 profile.json（个人画像，每用户一个）

`{generated_at, model, signals, body}`。`signals` 是生成时的信号计数 `{pins, deep_dives, tracks, conversations}`，`body` 是结构化中文 Markdown（一句话画像 / 关注领域 / 技术栈倾向 / 活跃度 / 推荐关注）。

由 `POST /api/ai-news/profile` 按需生成：聚合该用户 `pins.json`（标题/标签/来源分布）+ `deep-dives/`（解读主题）+ `tracks.json` + `ui.db` 对话标题，调 LLM 推断。信号全空时不生成（返回 400）。对话标题经 `storage.sqlite_ro` 只读 `ui.db`，避免 import agent_chat 形成循环依赖。

### 3.8 review-cards.json（知识卡 + 间隔重复，每用户一个）

list，每项一张卡：

```json
{
  "id": "rc_<sha1前12>",
  "front": "正面/问题", "back": "背面/答案要点",
  "source_type": "article | deep-dive | manual",
  "source_id": "a_xxx（可空）", "source_url": "原文链接（可空）",
  "tags": [], "created_at": "ISO",
  "srs": {"interval": 0, "ease": 2.5, "reps": 0, "due": "YYYY-MM-DD", "last_review": null}
}
```

`srs` 是 SM-2 调度状态（`app/srs.py`）：`interval` 间隔天数、`ease` 难度系数（≥1.3）、`reps` 连续答对次数、`due` 下次到期日。复习评分 forgot/hard/good → SM-2 质量分 2/3/5，更新这些字段。`POST /review/cards` 从 article/deep-dive 转卡时背面复用现成摘要（**0 LLM**），同源去重。

### 3.9 reflection.json（AI 复盘，每用户一个）

`{generated_at, model, signals, recap, questions[]}`。`signals` 是近 7 天活动计数 `{pins, deep_dives, cards, conversations}`，`recap` 是一段中文回顾，`questions` 是 3-5 个苏格拉底式问题。由 `POST /reflection/generate` 按需生成（`collect_recent_signals` 按时间窗聚合，全空返回 400）。只存最近一次，不做历史归档。

### 3.10 learning-paths/<slug>.json（学习路径，每条一个文件）

`{slug, topic, generated_at, model, based_on_profile, stages[]}`。每个 stage：`{title, goal, learn[], read[], suggest, practice}`，`read` 项是 `{type:"deep-dive"|"article", id, title, url, note}`（**只含库内真实存在的 id**，编造的被 `_resolve_reads` 丢弃）。是 guides 之上的编排层（多阶段路线 vs 单篇长文）。由 `POST /learning-paths/generate` 生成，独立库（像 deep-dives 那样直接扫目录）。

## 4. 并发与原子性

- 覆盖式 JSON 写经 `storage.write_json_atomic`：进程内文件锁 → 写 tmp → fsync → 原子 rename。崩溃不会留半截文件。
- append/toggle/计数/状态合并必须经 `storage.update_json_atomic`，同一把锁覆盖完整读改写，避免并发请求互相覆盖。
- 读经 `storage.read_json`：文件缺失/损坏一律返回 default，不抛异常。
- fetch/translate sweep 各有进程内 asyncio 锁；翻译按 id 合并到最新文章列表。此保证以当前单 uvicorn 进程为边界，不是跨进程事务。
