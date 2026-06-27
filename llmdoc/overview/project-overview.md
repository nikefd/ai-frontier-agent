# AI Frontier Agent — 项目概览

## 1. 定位

- **是什么:** 一个个人「AI 前沿信息站」。后端是 FastAPI 单应用，定时从 ~79 个精选 RSS 源抓取 AI 资讯，自动做中英翻译、生成每日速报、按需生成单篇深度解读，并提供一个 sparrow 驱动的对话式 ReAct agent。
- **目标:** 一个人每天打开一个页面，就能跟住 AI 前沿：官方实验室发布、专家博客、X/Twitter 大 V、社区周刊、arXiv 论文、GitHub 风向；不想读英文有双语，想深挖有深度解读和对话助手。
- **出身:** 从 `zhangyangbin-agents`（即 openclaw-deploy 体系）抽取的「AI 前沿 agent」骨架，砍掉了 finance / climbing 模块，LLM 默认改用 DeepSeek（自包含，不再依赖内网网关 / token 窃取）。代码注释和部分 logger 名仍残留 `zyb` / `zhangyangbin` 字样，属历史遗留（见 [known-issues](../reference/known-issues.md)）。

## 2. 总体描述

后端是**进程内一体化**的 FastAPI 应用：HTTP API + 静态前端托管 + APScheduler 后台任务都跑在同一个 uvicorn 进程里，没有独立 worker 进程，也没有数据库服务。

数据**全部落在文件系统**（`<data_dir>/ai-news/` 下的一组 JSON 文件 + 一个 SQLite `ui.db`），靠原子写（写 `.tmp` 再 rename）保证并发安全。这意味着「克隆即可跑」「卷挂载即持久化」，不需要 Postgres / Redis（自建 rsshub 那条链路除外）。

三条主要数据流：

1. **抓取管线** — APScheduler 每天 07:30（可配）拉全部 feed，关键词打标 + 每源配额 + 全局上限后入库 `articles.json`；用户也能点「立即抓取」即时触发。详见 [RSS 抓取管线架构](../architecture/rss-pipeline-architecture.md)。
2. **翻译 / LLM 加工** — 每 2 分钟一个翻译 tick 把 `pending` 文章批量译成中文；用户可对单篇生成「深度解读」（带 mermaid 图）、对一组生成「今日速报」、对任意主题生成「深度指南」。
3. **对话 agent** — `/api/agent/chat` 是 sparrow `Harness` 跑的 ReAct agent，带读写工具（查文章/源/track、建 track、收藏），对话历史持久化在 `ui.db`。详见 [Agent 架构](../architecture/agent-architecture.md)。

前端是**零构建的原生 ES module**单页应用，由后端 `/ui/` 直接托管；对话组件用 sparrow 官方的 `sparrow-chat.js`（启动时从 sparrow 包拷进 `static/js/`）。

## 3. 技术栈

| 层级 | 技术 |
|---|---|
| Web 框架 | FastAPI + uvicorn（单进程，`app.main:app`，默认 `:9702`） |
| 后台任务 | APScheduler（`AsyncIOScheduler`，与 FastAPI 共用事件循环，时区 Asia/Shanghai） |
| RSS 抓取 | httpx（异步并发拉取）+ feedparser（解析）+ BeautifulSoup/lxml（摘要去标签） |
| 数据存储 | 文件系统 JSON（原子写）+ SQLite（`ui.db`，对话记忆，只读 URI 模式） |
| LLM | DeepSeek（OpenAI 兼容 `/chat/completions`），自写 httpx 薄封装，不引 openai/anthropic SDK |
| 对话 agent | `sparrow-agent`（PyPI；`Harness` / `AgentConfig` / `Memory` / `@tool`） |
| 前端 | 原生 HTML + ES module（无打包），marked + mermaid（CDN），sparrow-chat.js 组件 |
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
| `app/main.py` | FastAPI 入口：挂路由、CORS、静态托管、lifespan 启停 scheduler、同步 sparrow-chat.js |
| `app/settings.py` | pydantic-settings 配置（`AIF_` 前缀），模块级单例 `settings` |
| `app/models.py` | pydantic schema：`Article` / `Track` / `Guide` / `ChatMessage` / `ChatRequest` |
| `app/storage.py` | 原子 JSON 读写 + 只读 SQLite 连接，跨模块共享 |
| `app/llm_client.py` | DeepSeek（OpenAI 兼容）薄封装：`chat_complete` / `chat_stream` |
| `app/scheduler.py` | APScheduler：每日抓取 job + 每 2 分钟翻译 tick |
| `app/routers/ai_news.py` | **核心路由**：articles/tracks/guides/sources/summary/deep-dive/manual-dive，以及 feed 清单与关键词表 |
| `app/agent_chat.py` | sparrow ReAct agent 的 `/api/agent/chat` SSE 端点 + 对话管理 |
| `app/agent_tools.py` | agent 的 `@tool`：query_articles/tracks/sources/guides、read_article、create_track、pin_article |
| `app/workers/ai_news_fetcher.py` | 抓取 worker：拉 feed → 关键词打标 → 每源配额 + 全局上限 → 入库 |
| `app/workers/ai_news_translator.py` | 翻译 worker：批量把 pending 文章译成中文 |
| `agent/` | 占位包（`__init__.py` 一行注释，预留「LLM Harness 下个里程碑填充」，当前未用） |
| `static/` | 前端：`index.html` + `js/`（ES module）+ `style.css`；`js/sparrow-chat.js` 启动时自动同步 |
| `seed-data/ai-news/` | 镜像内种子数据，首次启动卷为空时灌入（`articles.json` / `tracks.json` / 示例 guides + deep-dives） |
| `Dockerfile` / `docker-compose.yml` / `docker-entrypoint.sh` | 容器化：单镜像 + app/rsshub/redis 三服务 + 种子灌入逻辑 |
| `deploy/` | 当前为空目录（部署托管给 Coolify，无 systemd/nginx 配置入库） |
| `llmdoc/` | 本文档体系 |

## 6. 核心机制速览

- **抓取入库:** 79 feed 异步并发拉取 → 每条关键词打标（`keyword`/`curated`，**不再用于拒绝**，所有源都是精选）→ 每源最多 `_PER_FEED_CAP=4` 篇保证多样性 → 全局 `_DAILY_FETCH_CAP=150` 封顶 → 滚动历史 `_ARTICLE_LIMIT=400`（pinned 不淘汰）。
- **双语翻译:** 翻译 worker 每 2 分钟挑 5 篇 `pending`，单次 LLM 调用返回 JSON 数组，写回 `title_zh`/`summary_zh`；失败标 `failed` 不自动重试（需手动 retranslate）。
- **LLM 产物分三类:** 单篇深度解读（带 mermaid 图，存 `deep-dives/{aid}.json`）、每日速报（存 `summary_today.json`）、主题深度指南（存 `guides/guide_*.json`）。还支持「手动输入」主题生成深度解读（合成一条 pinned 文章）。
- **对话 agent:** sparrow `Harness` ReAct 循环 + 6 个工具（5 读 1 写组）+ 对话记忆（`ui.db`），SSE 推送 `tool_call`/`tool_result`/`final`/`title` 事件，每条工具结果带 `source` 供引用。
- **存储即并发安全:** 所有 JSON 写经 `write_json_atomic`（tmp + fsync + rename + 进程内文件锁），SQLite 默认只读 URI 模式，多读者共享。
