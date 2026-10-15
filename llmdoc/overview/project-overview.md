# AI Frontier Agent — 项目概览

## 1. 定位

- **是什么:** 一个个人「AI 前沿信息站」。后端是 FastAPI 单应用，定时从 ~79 个精选 RSS 源抓取 AI 资讯，自动做中英翻译、生成每日速报、按需生成单篇深度解读，并提供一个 sparrow 驱动的对话式 ReAct agent。
- **目标:** 一个人每天打开一个页面，就能跟住 AI 前沿：官方实验室发布、专家博客、X/Twitter 大 V、社区周刊、arXiv 论文、GitHub 风向；不想读英文有双语，想深挖有深度解读和对话助手。
- **出身:** 从 `zhangyangbin-agents`（即 openclaw-deploy 体系）抽取的「AI 前沿 agent」骨架，砍掉了 finance / climbing 模块，LLM 默认改用 DeepSeek（自包含，不再依赖内网网关 / token 窃取）。代码注释和部分 logger 名仍残留 `zyb` / `zhangyangbin` 字样，属历史遗留（见 [known-issues](../reference/known-issues.md)）。

## 2. 总体描述

后端是**进程内一体化**的 FastAPI 应用：HTTP API + 静态前端托管 + APScheduler 后台任务都跑在同一个 uvicorn 进程里，没有独立 worker 进程，也没有数据库服务。

数据**全部落在文件系统**（JSON + 每用户 SQLite `ui.db`）。覆盖写用 tmp+fsync+rename，读改写用按路径事务锁；当前并发保证以单 uvicorn 进程为边界。

三条主要数据流：

1. **抓取管线** — APScheduler 每天 05:00（可配）拉全部 feed；管理员也能即时触发。详见 [RSS 抓取管线架构](../architecture/rss-pipeline-architecture.md)。
2. **翻译 / LLM 加工** — 每 2 分钟一个翻译 tick 把 `pending` 文章批量译成中文；用户可对单篇生成「深度解读」（带 mermaid 图）、对一组生成「今日速报」、对任意主题生成「深度指南」。
3. **对话 agent** — `/api/agent/chat` 是 sparrow `Harness` 跑的 ReAct agent，带读写工具（查文章/源/track、建 track、收藏），对话历史持久化在 `ui.db`。详见 [Agent 架构](../architecture/agent-architecture.md)。

前端是 **Vite 构建的零框架 ES module** 单页应用，采用阅读优先的信息架构：首页直达今日速报或最新文章，桌面导航按阅读/沉淀/更多分层，文章卡片只突出原文与深度解读。构建产物由后端根路径托管；对话组件是仓库内源码，随前端构建输出。

## 3. 技术栈

| 层级 | 技术 |
|---|---|
| Web 框架 | FastAPI + uvicorn（单进程，`app.main:app`，默认 `:9702`） |
| 后台任务 | APScheduler（`AsyncIOScheduler`，与 FastAPI 共用事件循环，时区 Asia/Shanghai） |
| RSS 抓取 | httpx（异步并发拉取）+ feedparser（解析）+ BeautifulSoup/lxml（摘要去标签） |
| 数据存储 | 文件系统 JSON（原子写）+ SQLite（`ui.db`，对话记忆，只读 URI 模式） |
| LLM | DeepSeek（OpenAI 兼容 `/chat/completions`），自写 httpx 薄封装，不引 openai/anthropic SDK |
| 对话 agent | `app/agent_runtime/`（内联，原 sparrow；`Harness` / `AgentConfig` / `Memory` / `@tool`） |
| 前端 | Vite ES module；精确锁定的 marked + DOMPurify + Mermaid strict；无第三方运行时 CDN |
| 容器化 | 单镜像（python:3.12-slim）+ docker-compose（app + 自建 rsshub + redis） |
| 部署 | Coolify（Traefik 反代，命名卷持久化） |

## 4. 关键外部服务

| 服务 | 用途 | 备注 |
|---|---|---|
| DeepSeek API | 翻译 / 速报 / 深度解读 / 深度指南 / 对话 agent，全部共用一个 key | 未配置 key 时，所有 LLM 端点返回 503，但 RSS 浏览仍可用 |
| RSSHub | Twitter 大 V / GitHub / Anthropic 等路由的 RSS 源 | 公共 `rsshub.app` 对这些路由限流/403/404，需自建私有实例（compose 内置）；Twitter 路由还需 `TWITTER_AUTH_TOKEN` |
| 各 RSS 源 | 79 个精选 feed（官方/媒体/博客/论文/社区/专家/X 大 V/GitHub 风向） | feed 清单硬编码在 `app/routers/ai_news.py` 的 `DEFAULT_FEED_SPECS` |

## 5. 目录结构

| 路径 | 职责 |
|---|---|
| `app/main.py` | FastAPI 入口：挂路由、CORS、静态托管（`static/dist/`）、lifespan 启停 scheduler |
| `app/settings.py` | pydantic-settings 配置（`AIF_` 前缀），模块级单例 `settings` |
| `app/models.py` | pydantic schema：`Article` / `Track` / `Guide` / `ChatMessage` / `ChatRequest` |
| `app/storage.py` | 原子覆盖写 + 锁住完整 JSON 读改写事务 + 只读 SQLite |
| `app/safe_fetch.py` | 阅读器 SSRF 校验、限流式抓取和惰性 HTML 清洗 |
| `app/llm_client.py` | DeepSeek（OpenAI 兼容）薄封装：`chat_complete` / `chat_stream` |
| `app/scheduler.py` | APScheduler：每日抓取 job + 每 2 分钟翻译 tick |
| `app/routers/ai_news.py` | **核心路由**：articles/tracks/guides/sources/summary/deep-dive/manual-dive，以及 feed 清单与关键词表 |
| `app/agent_chat.py` | sparrow ReAct agent 的 `/api/agent/chat` SSE 端点 + 对话管理 |
| `app/agent_tools.py` | agent 的 `@tool`：query_articles/tracks/sources/guides、read_article、create_track、pin_article |
| `app/workers/ai_news_fetcher.py` | 抓取 worker：拉 feed → 关键词打标 → 每源配额 + 全局上限 → 入库 |
| `app/workers/ai_news_translator.py` | 翻译 worker：批量把 pending 文章译成中文 |
| `agent/` | 占位包（`__init__.py` 一行注释，预留「LLM Harness 下个里程碑填充」，当前未用） |
| `frontend/` | 前端源码：`index.html` + `src/`（ES module）+ `style.css` + `public/sparrow-chat.js`；Vite 构建到 `static/dist/` |
| `seed-data/ai-news/` | 镜像内种子数据，首次启动卷为空时灌入（`articles.json` / `tracks.json` / 示例 guides + deep-dives） |
| `Dockerfile` / `docker-compose.yml` / `docker-entrypoint.sh` | 容器化：单镜像 + app/rsshub/redis 三服务 + 种子灌入逻辑 |
| `deploy/` | 当前为空目录（部署托管给 Coolify，无 systemd/nginx 配置入库） |
| `llmdoc/` | 本文档体系 |

## 6. 核心机制速览

- **抓取入库:** 79 feed 异步并发拉取 → 每条关键词打标（`keyword`/`curated`，**不再用于拒绝**，所有源都是精选）→ 每源最多 `_PER_FEED_CAP=4` 篇保证多样性 → 全局 `_DAILY_FETCH_CAP=150` 封顶 → 滚动历史 `_ARTICLE_LIMIT=400`（pinned 不淘汰）。
- **双语翻译:** 翻译 worker每批 8 篇，LLM 一次返回翻译/评分/标签，按 id 原子合并；失败不自动重试，管理员可重置。
- **LLM 产物:** 单篇解读、全局每日速报、主题指南、画像、复盘和学习路径；手动主题解读只进用户库，不插入全局文章流。
- **对话 agent:** sparrow `Harness` ReAct 循环 + 6 个工具（5 读 1 写组）+ 对话记忆（`ui.db`），SSE 推送 `tool_call`/`tool_result`/`final`/`title` 事件，每条工具结果带 `source` 供引用。
- **安全边界:** 全局内容变更仅 admin；LLM Markdown 清洗后显示；阅读器逐跳阻断 SSRF 并只返回惰性 HTML；CSP 等响应头兜底。
