Always answer in 简体中文.

<always-step-one>
**STEP ONE IS ALWAYS: READ LLMDOC!**

Before doing ANYTHING else in this repo, you MUST:

1. Check that `llmdoc/` exists, then read `llmdoc/index.md` first.
2. Read EVERY document under `llmdoc/overview/`.
3. Then read the relevant `architecture/` / `guides/` / `reference/` docs for your
   task (the quick-nav table in `index.md` maps "if you need X → read Y").

This is NON-NEGOTIABLE. Documentation first, code second. Do not start editing
until you have read the docs that cover the area you are touching.
</always-step-one>

<llmdoc-structure>

- `llmdoc/index.md` — 主索引和快速导航表，永远先读这个。
- `llmdoc/overview/` — 高层背景，回答"这是什么项目"。该目录所有文档必读。
- `llmdoc/guides/` — 分步操作，回答"我该怎么做 X"（跑起来、部署）。
- `llmdoc/architecture/` — 系统怎么实现，回答"它是怎么工作的"（后端/抓取管线/agent/前端）。
- `llmdoc/reference/` — 事实性查阅，回答"X 的细节是什么"（API 端点、配置项、数据结构、已知问题）。

</llmdoc-structure>

<project-constraints>

本项目特有的硬规则，必须遵守：

- **语言**：与用户用简体中文交流；代码、命令、技术术语、文件名保持英文原文。文档正文用中文。
- **进程模型**：整个后端是**一个** uvicorn 进程（FastAPI + 静态托管 + APScheduler 抓取/翻译共用一个事件循环）。没有独立 worker、没有数据库服务。改动涉及后台任务时记住这一点。
- **存储是文件，不是数据库**：状态全在 `<data_dir>/ai-news/` 下的 JSON + `ui.db`。所有 JSON 写**必须**走 `app/storage.py` 的 `write_json_atomic`（原子写），不要新写裸 `open().write()`。
- **核心模块是 `app/routers/ai_news.py`**：它持有 feed 清单、关键词表、路径常量、容量参数，且被 worker 和 agent tools 反向 import 复用。改它的 `_load_*` / `add_article` 等函数签名前，先查三处调用方（routers / workers / agent_tools）。
- **两个 chat 端点**：`/api/ai-news/chat`（旧，前端不用）vs `/api/agent/chat`（sparrow agent，前端在用）。改对话行为去 `app/agent_chat.py`，别改错。
- **别手动编辑 `static/js/sparrow-chat.js`**：它由后端启动时从 sparrow 包同步覆盖。要改对话组件，改 `static/index.html` 的 `SparrowChat.mount({...})` 配置或升级 sparrow 包。
- **密钥与登录态绝不入 git**：`AIF_LLM_API_KEY` / `DEEPSEEK_API_KEY` / `TWITTER_AUTH_TOKEN` 都通过环境变量或 `.env`（已 gitignore）注入。
- **怎么跑 / 怎么验证**：本地 `uvicorn app.main:app --port 9702 --reload`，或 `docker compose up -d --build`。健康检查 `GET /api/health`。详见 `llmdoc/guides/how-to-run.md`。
- **抓取依赖自建 rsshub**：很多源走 rsshub，公共实例对 Twitter/GitHub/Anthropic 路由限流/403/404。排查"数据源大面积失败"先看 `llmdoc/guides/how-to-deploy.md` 和 `llmdoc/reference/known-issues.md`。

</project-constraints>

<doc-maintenance>

完成代码改动后，检查 llmdoc 是否需要同步更新：

- 新增/改端点 → `llmdoc/reference/api-reference.md`
- 新增/改配置项 → `llmdoc/reference/config-reference.md` + `.env.example`
- 改抓取/翻译管线 → `llmdoc/architecture/rss-pipeline-architecture.md`
- 新增/改 agent 工具 → `llmdoc/architecture/agent-architecture.md`
- 新增数据文件或改 Article 字段 → `llmdoc/reference/data-storage.md`
- 发现新坑 → `llmdoc/reference/known-issues.md`
- 任何更新都同步在 `llmdoc/index.md` 快速导航补一行。

**是否更新文档由用户决定**——完成代码改动后先问，不要自动改 llmdoc。

</doc-maintenance>

<git-conventions>

- commit message 格式：`<scope>: <中文描述>`，scope 用英文小写（如 agent / web / sources / fix / docs / chore）。
- 一次 commit 只做一件事；提交前用 `git diff` 确认改动范围。
- **未经用户要求不要 push。**

</git-conventions>
