# 怎么把项目跑起来

> 本地开发 / 验证用。生产部署（Coolify + 自建 rsshub）见 [部署指南](how-to-deploy.md)。

## 前置

- Python ≥ 3.11
- Node ≥ 18 + npm（构建前端用；只跑后端 API 可不装，但 `/ui/` 页面要先构建一次）
- 一个 DeepSeek API key（没有也能跑，但所有 LLM 功能——翻译/速报/解读/指南/对话——返回 503）

## 方式 A：裸机（推荐本地开发）

```bash
cd ~/workspace/ai-frontier-agent

# 1) 建虚拟环境并装依赖（agent 运行时已内联，无需额外装 sparrow）
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

# 4) 在交互终端创建首个管理员（密码隐藏输入；已有管理员时跳过）
python -m app.bootstrap_admin --email you@example.com

# 5) 起服务
uvicorn app.main:app --host 0.0.0.0 --port 9702 --reload
```

打开 http://127.0.0.1:9702/ 。改前端代码后需 `npm run build` 重新构建（或用 `npm run dev`）。

### 数据目录

未配环境变量时裸机数据根是 `~/agent-data`；复制 .env.example 后为项目 `./data`（`AIF_DATA_DIR` 可改）。首次跑先执行 bootstrap_admin 创建管理员，再登录点「立即抓取」；也可拷贝演示数据：

```bash
mkdir -p ~/agent-data/ai-news
cp -r seed-data/ai-news/. ~/agent-data/ai-news/
```

## 方式 B：Docker compose（最接近生产）

```bash
# .env 可填 AIF_LLM_API_KEY=...，也支持 DEEPSEEK_API_KEY 回退
docker compose build
docker compose run --rm --no-deps ai-frontier python -m app.bootstrap_admin --email you@example.com
docker compose up -d
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
| 立即抓一轮 RSS | admin 登录后点「立即抓取」（API 同样要求 admin session） |
| 跑一批翻译 | admin 登录后点「批量翻译」（API 同样要求 admin session） |
| 健康检查 | `curl localhost:9702/api/health` |
| 单独跑抓取脚本（裸机调试） | `python -m app.workers.ai_news_fetcher` |
| 单独跑翻译脚本（裸机调试） | `python -m app.workers.ai_news_translator` |
| 关掉定时任务 | `.env` 设 `AIF_SCHEDULER_ENABLED=0` |

## 测试与 CI

```bash
pip install -e ".[dev]"     # pytest + pytest-asyncio
pytest
```

当前安全/业务回归共 183 项；提交前同时运行 `pytest`、`cd frontend && npm run build && npm audit`。

正式 CI 位于 `.github/workflows/ci.yml`，在 PR、`main` 推送及手动触发时运行：

- 后端：Python 3.11、3.12 分别安装 `.[dev]`，执行全部 pytest 和 `compileall`。
- 前端：Node 20 执行 `npm ci`、Vite 生产构建和 `npm audit --audit-level=high`。
- 镜像：后端与前端检查全部通过后，按仓库 `Dockerfile` 构建生产镜像。

工作流只授予 `contents: read`，不读取部署或 LLM secrets；同一分支的新提交会取消旧的未完成运行。AI PR 审查位于独立的 `pr-review.yml`，不替代这些确定性检查。

## 排障

| 现象 | 原因 / 处理 |
|---|---|
| 所有 LLM 功能报 503 | 没配 key。检查 `AIF_LLM_API_KEY` 或 `DEEPSEEK_API_KEY`；`GET /api/health` 看 `llm_configured` |
| 大量数据源「抓取失败」 | 多半是 rsshub 路由问题。裸机把 `AIF_RSSHUB_BASE` 指向可用实例；Twitter 源需自建 rsshub + `TWITTER_AUTH_TOKEN`，见 [部署指南](how-to-deploy.md) |
| 启动日志有「agent chat router not loaded」 | agent 运行时（`app/agent_runtime/`）初始化失败。新闻 API 仍可用，但 `/api/agent/chat` 404。看 warning 详情排查 |
| 对话组件加载不出来 | 确认 `npm run build` 跑过、`/sparrow-chat.js` 可访问 |
