# 前端架构

> 讲清楚这个**零构建**的原生 ES module 单页前端怎么组织：模块划分、视图切换、
> 状态管理、和后端怎么对接，以及对话组件为什么不在仓库里。涉及文件：`static/index.html`、
> `static/js/*.js`、`static/style.css`。

## 1. 总体形态：无构建步骤

前端是**原生 HTML + ES module**，没有打包器、没有框架、没有 npm 构建。后端 `app/main.py` 把 `static/` 直接挂在 `/ui/`：

- `GET /` → 302 跳 `/ui/`
- `GET /ui/` → `static/index.html`
- `/ui/js/*.js`、`/ui/style.css` 由 `StaticFiles` 托管

第三方库走 CDN：`marked`（markdown 渲染）、`mermaid@10`（图）。改前端**刷新即生效**，不需要任何构建命令。

## 2. 模块划分（`static/js/`）

ES module，靠 `import` 互相引用，入口是 `index.html` 末尾的 `<script type="module" src="/ui/js/main.js">`。

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
| `sparrow-chat.js` | **不手动维护**：sparrow 官方对话组件，后端启动时从 sparrow 包拷入（见第 5 节） |

依赖方向：`main.js` → `nav.js` / `feed.js` / `dives.js` / `views.js` → `api.js` / `state.js` / `util.js`。存在受控循环：`nav.js` ⇄ `feed.js`/`dives.js`、`feed.js` → `dives.js`（`jumpToDive`）→ `nav.js`（`switchView`）。这些都是**运行时调用**（事件回调里才执行，加载期只定义函数），ES module 能安全处理。

## 3. 视图与状态

四个视图（左侧 side-nav 切换），都在同一个 `index.html` 里用 `.view-pane` + `.hidden` 显隐：

| 视图 | DOM id | 数据来源 |
|---|---|---|
| 文章流 | `#view-feed` | `GET /api/ai-news/articles`（分页） |
| 今日速报 | `#view-summary` | `GET/POST /api/ai-news/summary/today` |
| 深度解读 | `#view-dives` | `GET /api/ai-news/deep-dives`（独立内容库，直接扫 `deep-dives/*.json`） |
| 数据源 | `#view-sources` | `GET /api/ai-news/sources` |

`state.js` 的单例对象在模块间共享。文章流的筛选（分类 `cat` / all-pinned-translated 的 `filter` / 搜索 `q`）改变 `state` 后调 `refreshList()` 重新拉数据；分页改 `state.offset`。`translated` 筛选是**前端二次过滤**（后端不支持该参数），所以它只过滤当前页。

## 4. 关键交互

- **深度解读（与文章流解耦）**：文章流卡片的「深度解读」按钮只**触发跳转**（`feed.js` `jumpToDive`）到独立的深度解读视图——已解读则打开阅读，未解读则在该视图触发生成。阅读、删除、重新生成、手动新建都在 `dives.js` 完成。列表数据来自 `GET /deep-dives`（独立库），点列表项就地展开 `marked.parse` + `renderMermaidInside`。
- **mermaid 渲染**：LLM 产物里的 ```` ```mermaid ```` 代码块，`renderMermaidInside` 把它替换成 `.mermaid` div 再调 `mermaid.run`，`suppressErrors` 容忍语法错。
- **立即抓取 / 批量翻译**：工具栏按钮直接 POST `/fetch` 和 `/translate/run`，完成后 `refreshList`。

## 5. 对话组件 sparrow-chat.js

对话 UI 不是自己写的，用 sparrow 官方组件：

- `index.html` 末尾 `SparrowChat.mount({...})` 配置 endpoint（`/api/agent/chat`）、会话 API（`/api/agent/conversations`）、中文 i18n 文案、主题色 `#7c3aed`、`localStorage` key `aif_conv_id`。
- `sparrow-chat.js` 文件本身**由后端启动时从 sparrow 包同步**到 `static/js/`（`app/main.py` 的 `_sync_sparrow_assets`），所以**不要手动编辑** `static/js/sparrow-chat.js`——它会在下次启动被覆盖，也已加入 `.gitignore` 不入库。要改对话组件行为，改 `mount` 配置或升级 sparrow 包。

## 6. 已知小问题

- `views.js` 的数据源页 `SRC_CAT_LABELS` / `SRC_ORDER` 缺 `expert` 和 `x-ai` 两类标签，这两类源会以原始 key 名展示（无 emoji 标签）。

详见 [known-issues](../reference/known-issues.md)。
