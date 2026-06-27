# 已知问题与约束

> 从当前代码（main @ 78739d3）如实记录的坑、约束和历史遗留。改任何一条前先确认影响面。

## 1. CORS 全开（`allow_origins=["*"]`）

`app/main.py` 的 CORS 中间件放开所有源（`allow_credentials=False`）。绑公网且前面没有鉴权层时是注入/滥用面。生产靠 Coolify/Traefik + 域名收口；若直接暴露 `:9702` 到公网，先收紧 origin 白名单。

## 2. 两个 chat 端点并存

- `POST /api/ai-news/chat`：旧版无工具直通 LLM，**前端已不用**，保留作 openclaw 兼容。
- `POST /api/agent/chat`：sparrow ReAct agent，**前端实际使用**。

不是 bug，但容易让人改错地方。改对话行为去 `app/agent_chat.py`，不是 `ai_news.py` 的 `chat()`。

## 3. 翻译失败不自动重试

翻译 worker 把失败的文章标 `translation_status="failed"`，**之后不再自动翻**（防死循环）。要重译得 `POST /articles/{aid}/retranslate` 把状态重置回 `pending`。这是设计取舍，但用户可能困惑「为什么这篇一直没中文」。

## 4. 自建 RSSHub 是抓取链路的硬依赖

79 个 feed 里很多走 `rsshub.app`，而公共实例对 Twitter 路由 404、GitHub/Anthropic 路由 403。**不配自建 rsshub（`AIF_RSSHUB_BASE`）的话这些源大面积失败**。Twitter 路由（24 个 x-ai 源）还额外需要 `TWITTER_AUTH_TOKEN`。详见 [部署指南](../guides/how-to-deploy.md)。

## 5. tier 过滤已失效（设计演进残留）

`DEFAULT_FEED_SPECS` 里所有源 tier 都是 `high`，`_decide_relevance()` 永远返回接受。关键词表 `AI_KEYWORDS` 和 tier 分级逻辑保留着但不再用于拒绝文章——只用于打 `ai_relevance` 标签。读代码时别被「关键词过滤」的注释误导，它现在是 no-op 过滤。

## 6. 种子 sources.json 是空的

`seed-data/ai-news/sources.json` 是 `{}`。首次部署后数据源页**全部显示「尚未抓取」**，直到第一轮 fetch 跑完才有健康数据。不是故障。

## 7. 历史命名遗留（zyb / zhangyangbin）

项目从 `zhangyangbin-agents` 抽取，多处仍残留旧名：

- logger 名：`logging.getLogger("zyb.ai_news")` / `"zyb.fetcher"` / `"zyb.translator")`（其它模块已用 `aif.*`）。
- `app/workers/ai_news_fetcher.py` 的 `USER_AGENT` 写死 `"zyb-agents/0.2 (+https://github.com/yourname/zhangyangbin-agents)"`——是占位 URL。
- `app/llm_client.py` 抛 `LLMUnavailable` 的错误文案提到 `ZYB_LLM_API_KEY` / `COPILOT_GITHUB_TOKEN`，**已过时**（现在前缀是 `AIF_`，回退是 `DEEPSEEK_API_KEY`）。文案误导，逻辑无误。

都不影响运行，属命名债。

## 8. `/reader/{aid}` 代理抓取任意 URL

「阅读原文」端点会用服务端 httpx 抓 `article['url']` 并把**原始 HTML** 缓存到 `reader-cache/`。URL 来自 RSS 源（可信度中等）。绑公网时这是一个轻量 SSRF/缓存面，注意别让不可信来源写入 articles 的 url 字段。

## 9. 前端小问题

- `static/js/views.js` 的数据源页 `SRC_CAT_LABELS` / `SRC_ORDER` 缺 `expert` 和 `x-ai` 两类，这两类源以原始 key 名显示（无 emoji 标签）。
- `static/js/sparrow-chat.js` 由后端启动时从 sparrow 包覆盖同步，**手动编辑会被下次启动冲掉**。要改对话组件改 `mount` 配置或升级 sparrow。已加入 `.gitignore` 不入库。

## 10. 没有 tests/ 目录

`pyproject.toml` 配了 `testpaths = ["tests"]` 和 pytest-asyncio，但仓库里**还没有 `tests/`**。`pytest` 会报找不到测试。要写测试先建目录。

## 11. `deploy/` 目录为空

仓库根有 `deploy/` 但里面没文件。部署配置（域名/TLS/反代）都托管在 Coolify，不在 git 里。

## 12. `agent/` 是占位包

`agent/__init__.py` 只有一行注释「LLM Harness 下个里程碑填充」。对话 agent 实际实现在 `app/agent_chat.py`（用 PyPI 的 sparrow），`agent/` 当前未被任何代码使用。
