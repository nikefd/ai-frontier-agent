# 前端架构

> 讲清楚这个 **Vite 构建**的零框架 ES module 单页前端怎么组织：模块划分、视图切换、
> 状态管理、和后端怎么对接，以及对话组件为什么不在仓库里。涉及文件：`frontend/index.html`、
> `frontend/src/*.js`、`frontend/style.css`、`frontend/vite.config.js`。

## 1. 总体形态：Vite 构建，零框架

前端是**原生 HTML + ES module，无框架**，但用 **Vite** 做构建（打包 + 内容指纹 + 强缓存）。源码在 `frontend/`，构建产物在 `static/dist/`：

- 源码：`frontend/index.html`（入口）、`frontend/src/*.js`（ES module）、`frontend/style.css`
- 构建：`cd frontend && npm run build` → `static/dist/`（`index.html` + `assets/index-<hash>.{js,css}`，文件名带内容指纹）
- 开发：`npm run dev` 起 Vite dev server（热更新），或 `npm run build` 后由后端 serve

后端 `app/main.py` 在**根路径**托管 `static/dist/`（不再有 `/ui/` 前缀），并用 History 路由：

- `GET /` → `static/dist/index.html`（`Cache-Control: no-cache`，每次校验）= 落地首页
- `GET /assets/*`（指纹文件）→ `max-age=31536000, immutable`（永久强缓存，改动即换名，**根治“看到旧版”**）
- `GET /sparrow-chat.js` → 对话组件（no-cache）
- **SPA catch-all** `GET /{path}`：非 `/api`、非真实静态文件的路径（如 `/feed`、`/reflection`）→ 返回 index.html，交前端路由接管。`/api/*` 由各 router 处理、不会落到这里
- `GET /ui` `/ui/` → 301 跳 `/`（兼容改造前的旧书签）

第三方库 `marked` / `mermaid@10` 仍走 CDN（未纳入打包）。**改前端必须重新构建才生效**。`static/dist/` 与 `frontend/node_modules/` 不入 git，由 Docker 多阶段（Node 构建 → 拷进 Python 镜像）生成。

### 1.1 前端路由（History API）

`nav.js` 维护「视图 ↔ URL 路径」映射：`/`=落地首页，`/feed`/`/foryou`/`/summary`/`/dives`/`/review`/`/reflection`/`/learning`/`/profile`/`/sources`/`/admin` 各对应一个视图。

- `switchView(v)` 切视图 + `history.pushState('/'+v)`；`showLanding()` 回 `/`。
- 启动时 `applyRoute()` 按 `location.pathname` 恢复视图（**刷新/深链直达不丢失当前页**）。
- 监听 `popstate` → 浏览器前进/后退可用。
- 所以每个 tab 有独立可分享的 URL；刷新停在当前 tab；首页和信息站 URL 区分开（`/` vs `/feed`）。

## 2. 模块划分（`frontend/src/`）

ES module，靠 `import` 互相引用，入口是 `index.html` 末尾的 `<script type="module" src="/src/main.js">`（Vite 构建后替换为指纹化的 `/assets/index-<hash>.js`）。

| 模块 | 职责 |
|---|---|
| `main.js` | **入口**：事件绑定（nav/分类/筛选/搜索/分页/工具栏按钮），启动时 `refreshList()`。视图切换委托给 `nav.js` |
| `nav.js` | `switchView(v)`：side-nav 切换 + 按视图触发对应 loader。抽出来打破 `feed.js`/`dives.js` 想切视图却要 import `main.js` 的循环依赖 |
| `state.js` | 共享可变状态单例 `state`（view/cat/filter/q/offset/limit/total/items/selectedId） |
| `api.js` | `api(method, path, body)` fetch 封装 + `renderMermaidInside()`（把 ```` ```mermaid ```` 代码块转成图） |
| `feed.js` | 文章流：列表渲染、卡片 HTML、收藏 `togglePin`、分页 `renderPageNav`。深度解读按钮只**触发跳转**（`jumpToDive`），不再卡片内展开 |
| `dives.js` | **深度解读库**（独立视图）：`loadDives`（拉 `/deep-dives` 渲染列表）、点击展开阅读、删除、重新生成、`manualNewDive`（手动输入主题新建）、`jumpToDive`（从文章流跳来并打开/触发某篇） |
| `views.js` | 次要视图：今日速报 `loadSummary/regenSummary`、数据源健康 `loadSources` |
| `auth.js` | **登录态 + 鉴权 UI**：启动 `GET /api/auth/me`、顶栏登录态、登录/注册弹窗、登出。`api.js` 的 401 经 `setUnauthorizedHandler` 弹登录。登录/登出派发 `aif:auth-changed` 让 `main.js` 重载 |
| `util.js` | DOM helper（`$`/`$$`）、`escapeHtml`、相对时间 `fmtDate`、分类徽章 `catBadge` |
| `sparrow-chat.js` | 对话组件（IIFE，挂 `window.SparrowChat`）。源码在 `frontend/public/`，Vite 原样输出到 `/sparrow-chat.js`（见第 5 节） |

依赖方向：`main.js` → `nav.js` / `feed.js` / `dives.js` / `views.js` → `api.js` / `state.js` / `util.js`。存在受控循环：`nav.js` ⇄ `feed.js`/`dives.js`、`feed.js` → `dives.js`（`jumpToDive`）→ `nav.js`（`switchView`）。这些都是**运行时调用**（事件回调里才执行，加载期只定义函数），ES module 能安全处理。

## 3. 视图与状态

多个视图（左侧 side-nav 切换），都在同一个 `index.html` 里用 `.view-pane` + `.hidden` 显隐：

| 视图 | DOM id | 数据来源 |
|---|---|---|
| 落地首页 | `#view-home` | 无（静态中英双语 hero + 功能介绍） |
| 文章流 | `#view-feed` | `GET /api/ai-news/articles`（分页） |
| 今日速报 | `#view-summary` | `GET/POST /api/ai-news/summary/today` |
| 深度解读 | `#view-dives` | `GET /api/ai-news/deep-dives`（独立内容库，直接扫 `deep-dives/*.json`） |
| 数据源 | `#view-sources` | `GET /api/ai-news/sources` |

`state.js` 的单例对象在模块间共享。文章流的筛选（分类 `cat` / all-pinned-translated 的 `filter` / 搜索 `q`）改变 `state` 后调 `refreshList()` 重新拉数据；分页改 `state.offset`。`translated` 筛选是**前端二次过滤**（后端不支持该参数），所以它只过滤当前页。

落地首页 `#view-home` 不走 side-nav，而是用 `<body>` 上的 `landing-active` 类控制（隐藏应用主体、只显首页）。路由层据 URL 决定：路径 `/` 时 `showLanding()` 加该类；进入某视图（如点「进入」按钮 → `switchView('feed')`）移除该类。点顶栏标题 brand → `showLanding()` 回 `/`。详见 §1.1 路由。

## 4. 关键交互

- **深度解读（与文章流解耦）**：文章流卡片的「深度解读」按钮只**触发跳转**（`feed.js` `jumpToDive`）到独立的深度解读视图——已解读则打开阅读，未解读则在该视图触发生成。阅读、删除、重新生成、手动新建都在 `dives.js` 完成。列表数据来自 `GET /deep-dives`（独立库），点列表项就地展开 `marked.parse` + `renderMermaidInside`。
- **mermaid 渲染**：LLM 产物里的 ```` ```mermaid ```` 代码块，`renderMermaidInside` 把它替换成 `.mermaid` div 再调 `mermaid.run`，`suppressErrors` 容忍语法错。
- **立即抓取 / 批量翻译**：工具栏按钮直接 POST `/fetch` 和 `/translate/run`，完成后 `refreshList`。

## 5. 对话组件 sparrow-chat.js

对话 UI 来自内联的 agent 运行时（原 sparrow 框架，见 `app/agent_runtime/README.md`）：

- `index.html` 末尾 `SparrowChat.mount({...})` 配置 endpoint（`/api/agent/chat`）、会话 API（`/api/agent/conversations`）、中文 i18n 文案、主题色 `#7c3aed`、`localStorage` key `aif_conv_id`。mount 返回的实例存到 `window.__sparrowChat`，供复盘视图「展开聊」调用（`chat.toggle(true)` + 填 input + `send()`）。
- `sparrow-chat.js` 现在是**仓库内源码** `frontend/public/sparrow-chat.js`，Vite 原样输出到 `/sparrow-chat.js`。**可以直接改**，但改完要 `npm run build`。（历史：曾由后端启动时从 sparrow 包同步，内联后该机制已删。）

## 6. 已知小问题

- `views.js` 的数据源页 `SRC_CAT_LABELS` / `SRC_ORDER` 缺 `expert` 和 `x-ai` 两类标签，这两类源会以原始 key 名展示（无 emoji 标签）。

详见 [known-issues](../reference/known-issues.md)。
