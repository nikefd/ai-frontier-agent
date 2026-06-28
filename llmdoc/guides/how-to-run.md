# 怎么把项目跑起来

> 本地开发 / 验证用。生产部署（Coolify + 自建 rsshub）见 [部署指南](how-to-deploy.md)。

## 前置

- Python ≥ 3.11
- Node ≥ 18 + npm（构建前端用；只跑后端 API 可不装，但 `/ui/` 页面要先构建一次）
- 一个 DeepSeek API key（没有也能跑，但所有 LLM 功能——翻译/速报/解读/指南/对话——返回 503）

## 方式 A：裸机（推荐本地开发）

```bash
cd ~/workspace/ai-frontier-agent

# 1) 建虚拟环境并装依赖（含 sparrow-agent）
python3 -m venv .venv
source .venv/bin/activate
pip install -e .            # 读 pyproject.toml；要跑测试加 -e ".[dev]"

# 2) 构建前端（Vite → static/dist/，后端 serve 这个目录）
cd frontend && npm install && npm run build && cd ..
#   开发时也可改用 `cd frontend && npm run dev` 起 Vite 热更新 server

# 3) 配置（复制模板，填 key）
cp .env.example .env
#   编辑 .env：填 AIF_LLM_API_KEY=<你的 DeepSeek key>
#   本地裸机建议把 AIF_RSSHUB_BASE 改成 https://rsshub.app 或留空
#   （compose 默认的 http://rsshub:1200 只在 docker 网络里有效）

# 4) 起服务
uvicorn app.main:app --host 0.0.0.0 --port 9702 --reload
```

打开 http://127.0.0.1:9702/ （会自动跳 `/ui/`）。改前端代码后需 `npm run build` 重新构建（或用 `npm run dev`）。

### 数据目录

裸机默认数据根是 `~/agent-data`（`AIF_DATA_DIR` 可改），新闻数据在 `~/agent-data/ai-news/`。首次跑是空的——点页面右上「立即抓取」拉第一批，或想要演示数据可手动把 `seed-data/ai-news/` 拷过去：

```bash
mkdir -p ~/agent-data/ai-news
cp -r seed-data/ai-news/. ~/agent-data/ai-news/
```

## 方式 B：Docker compose（最接近生产）

```bash
# .env 里至少填 DEEPSEEK_API_KEY=...（compose 会映射到 AIF_LLM_API_KEY）
docker compose up -d --build
```

这会起三个容器：

- `ai-frontier-agent`（应用，映射 `127.0.0.1:9702`）
- `ai-frontier-rsshub`（自建 RSSHub，绕开公共实例限流/403）
- `ai-frontier-rsshub-redis`（rsshub 缓存）

访问 http://127.0.0.1:9702/ 。数据持久化在命名卷 `ai-frontier-data`（不是 bind mount，见 [部署指南](how-to-deploy.md) 解释为什么）。首次启动 `docker-entrypoint.sh` 会在卷为空时灌入 `seed-data/`。

改完代码重建验证：

```bash
docker compose up -d --build
docker compose logs -f ai-frontier      # 看日志
```

## 常用操作

| 想做什么 | 怎么做 |
|---|---|
| 立即抓一轮 RSS | 页面右上「立即抓取」，或 `curl -XPOST localhost:9702/api/ai-news/fetch` |
| 跑一批翻译 | 文章流工具栏「批量翻译」，或 `curl -XPOST localhost:9702/api/ai-news/translate/run` |
| 健康检查 | `curl localhost:9702/api/health` |
| 单独跑抓取脚本（裸机调试） | `python -m app.workers.ai_news_fetcher` |
| 单独跑翻译脚本（裸机调试） | `python -m app.workers.ai_news_translator` |
| 关掉定时任务 | `.env` 设 `AIF_SCHEDULER_ENABLED=0` |

## 测试

```bash
pip install -e ".[dev]"     # pytest + pytest-asyncio
pytest
```

> 注意：当前仓库 `pyproject.toml` 配了 `testpaths = ["tests"]`，但仓库里**还没有 `tests/` 目录**。`pytest` 会报「找不到测试」。新增测试时先建 `tests/`。

## 排障

| 现象 | 原因 / 处理 |
|---|---|
| 所有 LLM 功能报 503 | 没配 key。检查 `AIF_LLM_API_KEY` 或 `DEEPSEEK_API_KEY`；`GET /api/health` 看 `llm_configured` |
| 大量数据源「抓取失败」 | 多半是 rsshub 路由问题。裸机把 `AIF_RSSHUB_BASE` 指向可用实例；Twitter 源需自建 rsshub + `TWITTER_AUTH_TOKEN`，见 [部署指南](how-to-deploy.md) |
| 启动日志有「agent chat router not loaded」 | sparrow 包没装好。新闻 API 仍可用，但 `/api/agent/chat` 404。`pip install sparrow-agent` |
| 启动日志有「could not sync sparrow-chat.js」 | 同上，sparrow 包问题，对话前端组件拿不到 |
