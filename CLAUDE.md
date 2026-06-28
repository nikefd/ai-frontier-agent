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
- **前端用 Vite 构建**：源码在 `frontend/`（`frontend/src/*.js` + `frontend/index.html` + `frontend/style.css`），`npm run build` 产出带内容指纹的 `static/dist/`，后端 serve 这个目录。**改前端要重新构建才生效**（本地 `cd frontend && npm run dev` 热更新，或 `npm run build`）。`static/dist/` 与 `frontend/node_modules/` 不入 git，由 Docker 多阶段构建生成。
- **对话 agent 运行时已内联**：原 `sparrow` 框架内联在 `app/agent_runtime/`（ReAct Harness / Memory / @tool），零外部依赖，后续会按本项目需要改造。详见 `app/agent_runtime/README.md`。
- **改对话组件 sparrow-chat.js**：它现在是仓库内源码 `frontend/public/sparrow-chat.js`（Vite 构建输出到 `/ui/sparrow-chat.js`），**可以直接改**，但改完要 `npm run build` 重新构建。改对话挂载行为也可改 `frontend/index.html` 的 `SparrowChat.mount({...})`。
- **密钥与登录态绝不入 git**：`AIF_LLM_API_KEY` / `DEEPSEEK_API_KEY` / `TWITTER_AUTH_TOKEN` 都通过环境变量或 `.env`（已 gitignore）注入。
- **怎么跑 / 怎么验证**：本地 `uvicorn app.main:app --port 9702 --reload`，或 `docker compose up -d --build`。健康检查 `GET /api/health`。详见 `llmdoc/guides/how-to-run.md`。
- **抓取依赖自建 rsshub**：很多源走 rsshub，公共实例对 Twitter/GitHub/Anthropic 路由限流/403/404。排查"数据源大面积失败"先看 `llmdoc/guides/how-to-deploy.md` 和 `llmdoc/reference/known-issues.md`。

</project-constraints>

<code-quality>

本节是**防腐铁律**：目标是让代码库在需求不断叠加时仍保持优雅、可维护，不退化成「屎山」。每条都要落实，不是建议。

**改动粒度**

- **一次提交只做一件事**，控制在 ~100 行量级；功能改动与清理/重构**分开提交**，绝不混在一个 diff 里。顺手清理超过 5 分钟就停手、单独开一项做。（理由：reviewer 能分清意图，回滚/merge 都简单。来源：Google eng-practices Small CLs）
- **加功能优先开新模块/新函数，不要往巨型文件继续堆。** 这是 AI 加功能最典型的坏习惯。本项目 `app/routers/ai_news.py` 已 1000+ 行，是反面教材——新功能（如个人画像 `app/routers/profile.py`）应**自成模块**，通过 `include_router` / import 接入，而不是塞进 ai_news。（来源：Augment Code "The 80% Problem"）

**拆分与单一职责**

- **拆分看职责，不只看行数：一个模块/类只该有一个变更理由。** 当一组函数不再共用同一批状态（内聚下降），或同一段业务逻辑开始在多个端点重复，就抽出来。
- **函数只做一件事，参数尽量 ≤3 个。** 参数变多通常意味着函数承担了多重职责，是该分解的早期信号。
- **明确拆分触发条件并当硬规则执行**：单个 router 文件显著偏大（数百行以上）、或业务逻辑跨端点重复，就抽 service 层（`app/services/`）。给「何时重构」一个客观闸门，别拖到文件烂掉。

**分层与依赖方向**

- **守住边界**：router 只管 HTTP（解析请求 / 调用 / 拼响应），业务编排放 service，数据访问统一走 `app/storage.py` 与 `ai_news.py` 的 `_load_*` / 路径函数。router 不直接写裸文件 IO。
- **依赖方向一律向内，禁止循环依赖。** 本项目已有约定：worker / agent_tools **反向 import** `ai_news.py` 的共享函数；`profile.py` 复用其 loader；为避免 import 环，`POST /fetch`、对话标题读取等在**函数体内**才 import。新增模块前先想清楚依赖方向，不确定就先画一下依赖图。
- **中小项目按「功能/领域」组织，而非教条按层切目录。** 不要为了分层把一个功能拆到多个文件夹来回跳。

**不要过度工程化**

- **别提前堆架构**：当前简单结构够用就别引入 service/repository/DDD 全套。等真出现复杂度（逻辑重复、文件过大）再加。重构若新增的复杂度比消除的还多，就放弃这次重构。
- **增量重构，一次只清一处**：要拆就一个端点/一个模块地改，不要「大爆炸式」全量重写。

**安全护栏**

- **不懂的代码不要动。** 搞不清某段为什么这么写（尤其反射 / 字符串查找 / 动态 import / 隐式依赖）时，先查清再改，别「顺手优化」踩坑。
- **需要重构就重构**：发现职责放错位置、归属不清、或在旧路径旁另起平行实现（重复信号），回到源头修复，而不是继续打补丁。维持「每个模块输入/输出/职责清晰」。

</code-quality>

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
