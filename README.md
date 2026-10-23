# AI Frontier Agent — 个人 AI 前沿信息站

分层抓取 115 个 AI 源：模型/API/重要 AI 初创公司等 27 个高时效官方源每小时更新，61 个常规资讯源每 4 小时更新，论文、X 与 GitHub Trending 等 27 个发现型源每 12 小时更新。除常规新闻外，还直接跟踪独立模型基准、安全评测、具身智能、模型 API 可用性和官方开源仓库，让“重要但不热门”的信号不再被 GitHub Trending 淹没。内容经过相关性过滤、同事件聚类与分类配额，再做双语翻译和可实践性判断；今日速报会直接标出近 36 小时的模型发布、API 弃用、安全事件与重要开源，并保留可点击的一手来源，也可通过 `/rss/digest.xml` 全文订阅。同一事件的不同标题会合并并保留多源佐证；论文结合 Hugging Face Daily Papers 票数、开源代码和 GitHub stars 筛选，同时保留受限的 arXiv 长尾发现。可实践文章还能按需生成结构化实验卡，保存进度与结果笔记，再把完整实验上下文交给 AI 逐步带练。数据源页持续体检高时效源健康、高影响事件露出、富化积压和发现延迟，并以近 30 天的有效事件、独家贡献、首发现、重要性和时效计算可解释的来源价值评分；样本不足不会误判为低价值。管理员还可登记“绝不能漏”的真实事件，系统按期限区分准时命中、迟到、漏报与观察中，给出绝对召回率；近 7 天已抓到的官方高影响事件会自动成为待确认候选。空白/伪 RSS 与无可信发布日期的条目都会被拒绝，不再显示“假健康”或用抓取时间冒充发布时间。候选未变化时跳过速报 LLM 调用。

## 组成

| 层 | 位置 | 说明 |
|---|---|---|
| FastAPI 应用 | `app/` | 单进程一体化：HTTP API + 静态托管 + APScheduler 抓取/翻译（入口 `app.main:app`，默认 `:9702`） |
| RSS 管线 | `app/workers/` | 异步抓取（每源配额 + 全局上限）+ 批量翻译 worker |
| 对话 agent | `app/agent_chat.py` + `app/agent_tools.py` | sparrow 驱动的 ReAct agent，带工具/引用/对话记忆 |
| 前端 | `frontend/` → `static/dist/` | Vite 构建的原生 ES module 单页 + sparrow-chat 对话组件 |
| 数据 | `<data_dir>/ai-news/` + `<data_dir>/users/<uid>/` | 全局资讯与按用户隔离的 JSON（原子写）+ SQLite 对话记忆，无数据库服务 |
| 容器化 | `Dockerfile` / `docker-compose.yml` | 单镜像 + 自建 rsshub + redis 三服务 |
| CI | `.github/workflows/ci.yml` | PR 与 main 推送自动跑 Python 3.11/3.12 测试、前端构建/审计和生产镜像构建 |
| 文档 | `llmdoc/` | 面向人和 AI 的架构/指南/参考（**改代码前先读**） |

## 快速开始（裸机）

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env          # 填 AIF_LLM_API_KEY=<DeepSeek key>；本地建议 AIF_RSSHUB_BASE=https://rsshub.app
uvicorn app.main:app --host 0.0.0.0 --port 9702 --reload
```

打开 http://127.0.0.1:9702/ ，注册首个账号（自动成为 admin），点管理员可见的「立即抓取」拉第一批数据。

## 快速开始（Docker，最接近生产）

```bash
# .env 填 DEEPSEEK_API_KEY=...（要 Twitter 源再填 TWITTER_AUTH_TOKEN=...）
docker compose up -d --build
```

起三个容器：应用（`127.0.0.1:9702`）+ 自建 RSSHub + redis。数据持久化在命名卷 `ai-frontier-data`，首次启动自动灌入 `seed-data/`。

> 没配 LLM key 也能跑——RSS 浏览正常，翻译/速报/解读/对话返回 503。

## 部署

用 [Coolify](https://coolify.io/)（Traefik 反代 + 命名卷持久化）。部分 X 源走 RSSHub，所以 compose 自带私有实例；Twitter 路由还需 `TWITTER_AUTH_TOKEN`。Anthropic/Cohere/Mistral 等无稳定 RSS 的官方源读取 sitemap 并补全页面元数据，xAI/PyTorch/Transformers/vLLM 读取官方 GitHub Releases API，Qwen 读取官方文章 API；OpenAI/Gemini 官方更新日志由专用解析器逐条拆分，Claude Platform/Cursor 读取官方 changelog RSS。详见 [llmdoc/guides/how-to-deploy.md](llmdoc/guides/how-to-deploy.md)。

## RSS 订阅

把 `/rss/digest.xml` 加入任意 RSS 阅读器即可订阅完整中文速报。每次候选集发生实质变化都会生成一个稳定条目，引用编号直接链接一手来源；服务保留最近 30 天、最多 180 个版本，并用 ETag/Last-Modified 避免阅读器重复下载。RSS 只包含全局速报，不包含任何用户画像、收藏或实验记录。

## 质量门禁

GitHub Actions 会在每个 PR、`main` 推送和手动触发时运行确定性 CI：后端在 Python 3.11/3.12 上执行全部测试和字节码编译，前端在 Node 20 上执行锁文件安装、生产构建和高危依赖审计；全部通过后再构建生产 Docker 镜像。详细命令见 [运行指南](llmdoc/guides/how-to-run.md#测试与-ci)。

## 开源状态

仓库正在做公开前准备，目前尚未选择许可证，也没有开放外部贡献。示例配置和种子数据已经匿名化，贡献与安全报告规范已补齐；公开前仍需完成安全的管理员初始化、专业历史密钥扫描并在 AGPL-3.0 与 Apache-2.0 之间确认许可证。详见[开源准备清单](llmdoc/reference/open-source-readiness.md)。

## 文档导航（llmdoc）

第一次接手这个项目，**先读 [llmdoc/index.md](llmdoc/index.md)**，那里有完整的快速导航表。常用入口：

- 项目全貌：[llmdoc/overview/project-overview.md](llmdoc/overview/project-overview.md)
- 后端怎么搭的：[llmdoc/architecture/backend-architecture.md](llmdoc/architecture/backend-architecture.md)
- 抓取管线怎么运转：[llmdoc/architecture/rss-pipeline-architecture.md](llmdoc/architecture/rss-pipeline-architecture.md)
- 对话 agent：[llmdoc/architecture/agent-architecture.md](llmdoc/architecture/agent-architecture.md)
- HTTP 端点速查：[llmdoc/reference/api-reference.md](llmdoc/reference/api-reference.md)
- 配置项：[llmdoc/reference/config-reference.md](llmdoc/reference/config-reference.md)
- 坑与约束：[llmdoc/reference/known-issues.md](llmdoc/reference/known-issues.md)

## 技术栈

FastAPI · uvicorn · APScheduler · httpx · feedparser · BeautifulSoup · pydantic-settings · SQLite · 内联 agent runtime · DeepSeek（LLM）· Vite ES module 前端（marked + DOMPurify + Mermaid strict）。
