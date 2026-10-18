# 前端架构

> 讲清楚这个 **Vite 构建**的零框架 ES module 单页前端怎么组织：模块划分、视图切换、
> 状态管理、和后端怎么对接，以及对话组件如何随仓库维护。涉及文件：`frontend/index.html`、
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

`marked`、`mermaid`、`DOMPurify` 都以精确版本写入 `package.json` / lockfile 并由 Vite 打包，页面不再执行第三方 CDN 脚本。**改前端必须重新构建才生效**。`static/dist/` 与 `frontend/node_modules/` 不入 git，由 Docker 多阶段（Node 构建 → 拷进 Python 镜像）生成。

### 1.1 前端路由（History API）

`nav.js` 维护「视图 ↔ URL 路径」映射：`/`=落地首页，`/feed`/`/foryou`/`/summary`/`/dives`/`/review`/`/reflection`/`/learning`/`/profile`/`/sources`/`/admin` 各对应一个视图。

- `switchView(v)` 切视图 + `history.pushState('/'+v)`；`showLanding()` 回 `/`。
- 启动时 `applyRoute()` 按 `location.pathname` 恢复视图（**刷新/深链直达不丢失当前页**）。
- 监听 `popstate` → 浏览器前进/后退可用。
- 所以每个 tab 有独立可分享的 URL；刷新停在当前 tab；首页和信息站 URL 区分开（`/` vs `/feed`）。

**移动端导航（≤720px）**：桌面左侧 side-nav 隐藏，改用**底部固定 tab bar**（速报/文章/解读/知识卡/更多）+「更多」底部弹出菜单（为你推荐/复盘/学习路径/画像/数据源/管理）。tab 和 menu 都调同一个 `switchView`，高亮同步。对话仍是右下角悬浮球。

### 1.2 阅读优先的信息架构

页面把最常用的阅读动作放在第一层，低频能力按需展开：

- 根路径首页只提供「看今日速报」和「浏览最新文章」两个入口，不再展示大段双语营销文案和功能卡片。
- 桌面 side-nav 按「阅读」（速报、最新文章、推荐、解读）和「沉淀」（知识卡、复盘、学习路径）分组；画像、数据源、用户管理放入原生 `<details>`「更多」。
- 文章流顶部常驻搜索和最新/重要排序；范围、来源分类和管理员批量翻译收进「筛选」弹层。
- 文章卡片只把「原文」和「深度解读」作为主操作；复制链接、问 AI、加入知识卡和管理员翻译放进卡片「更多」。
- `nav.js` 用 `VIEW_META` 维护视图标题/说明，并在 `<body data-view>` 记录当前视图，供 CSS 控制文章数量等仅与 feed 有关的界面元素。

## 2. 模块划分（`frontend/src/`）

ES module，靠 `import` 互相引用，入口是 `index.html` 末尾的 `<script type="module" src="/src/main.js">`（Vite 构建后替换为指纹化的 `/assets/index-<hash>.js`）。

| 模块 | 职责 |
|---|---|
| `main.js` | **入口**：事件绑定（nav/分类/筛选/搜索/分页/工具栏按钮），补充筛选/卡片 `<details>` 的点击外部和 Esc 收起行为，启动时 `refreshList()`。视图切换委托给 `nav.js` |
| `nav.js` | `switchView(v)`：side-nav 切换 + 按视图触发对应 loader。抽出来打破 `feed.js`/`dives.js` 想切视图却要 import `main.js` 的循环依赖 |
| `state.js` | 共享可变状态单例 `state`（view/cat/filter/q/offset/limit/total/items/selectedId） |
| `api.js` | `api(method, path, body)` fetch 封装 + `renderMermaidInside()`（把 ```` ```mermaid ```` 代码块转成图） |
| `markdown.js` | `marked` 解析后统一经 DOMPurify 白名单清洗；所有 LLM Markdown 和聊天最终答案都走这里 |
| `feed.js` | 文章流：列表渲染、活动筛选标签、卡片 HTML、收藏 `togglePin`、分页 `renderPageNav`。深度解读按钮只**触发跳转**（`jumpToDive`），不再卡片内展开 |
| `dives.js` | **深度解读库**（独立视图）：`loadDives`（拉 `/deep-dives` 渲染列表）、点击展开阅读、删除、重新生成、`manualNewDive`（手动输入主题新建）、`jumpToDive`（从文章流跳来并打开/触发某篇） |
| `views.js` | 次要视图：今日速报 `loadSummary/regenSummary`（含零 LLM“刚刚发生”重大提醒）、数据源健康 `loadSources`（显示分层频率，失败/调度过期置顶、连续失败和最近成功/内容时间） |
| `auth.js` | **登录态 + 鉴权 UI**：启动 `GET /api/auth/me`、顶栏登录态、登录/注册弹窗、登出。`api.js` 的 401 经 `setUnauthorizedHandler` 弹登录。登录/登出派发 `aif:auth-changed` 让 `main.js` 重载 |
| `util.js` | DOM helper、`escapeHtml`、只接受 http(s) 的 `safeExternalUrl`、相对时间和分类徽章 |
| `sparrow-chat.js` | 对话组件（IIFE，挂 `window.SparrowChat`）。源码在 `frontend/public/`，Vite 原样输出到 `/sparrow-chat.js`（见第 5 节） |

依赖方向：`main.js` → `nav.js` / `feed.js` / `dives.js` / `views.js` → `api.js` / `state.js` / `util.js`。存在受控循环：`nav.js` ⇄ `feed.js`/`dives.js`、`feed.js` → `dives.js`（`jumpToDive`）→ `nav.js`（`switchView`）。这些都是**运行时调用**（事件回调里才执行，加载期只定义函数），ES module 能安全处理。

## 3. 视图与状态

多个视图（左侧 side-nav 切换），都在同一个 `index.html` 里用 `.view-pane` + `.hidden` 显隐：

| 视图 | DOM id | 数据来源 |
|---|---|---|
| 落地首页 | `#view-home` | 无（静态精简 hero，直达今日速报或最新文章） |
| 文章流 | `#view-feed` | `GET /api/ai-news/articles`（分页） |
| 今日速报 | `#view-summary` | `GET/POST /api/ai-news/summary/today` |
| 深度解读 | `#view-dives` | `GET /api/ai-news/deep-dives`（独立内容库，直接扫 `deep-dives/*.json`） |
| 数据源 | `#view-sources` | `GET /api/ai-news/sources` |

`state.js` 的单例对象在模块间共享。文章流默认每页 10 篇；筛选（分类 `cat` / all-pinned-translated-hands-on 的 `filter` / 搜索 `q` / 标签 `tag`）改变 `state` 后调 `refreshList()` 重新拉数据，分页改 `state.offset`。收藏、已翻译、可实践都映射为服务端 query，在分页前过滤，因此总数和翻页结果一致。

落地首页 `#view-home` 不走 side-nav，而是用 `<body>` 上的 `landing-active` 类控制（隐藏应用主体、只显首页）。路由层据 URL 决定：路径 `/` 时 `showLanding()` 加该类；首页的 `data-enter-view` 按钮可分别进入 `summary` 或 `feed`，进入视图时移除该类。点顶栏标题 brand → `showLanding()` 回 `/`。详见 §1.1 路由。

## 4. 关键交互

- **深度解读（与文章流解耦）**：文章流卡片按钮跳到独立解读视图；正文先走 `renderMarkdown` 清洗，再交 `renderMermaidInside`。
- **文章卡片降噪**：优先显示中文标题、来源、时间、摘要和最多两个标签；成功翻译不再重复显示状态，失败/待翻译仍保留提示。`hands_on` 非空时显示一条紧凑实践卡，点“带我做”会把原文、建议起点和“15 分钟最小实验 + 前置条件/步骤/验证结果 + 禁止编造”要求预填进对话助手。原文和深度解读保持直接可见，其余动作收进原生 `<details>` 菜单。
- **筛选收纳与反馈**：搜索与最新/重要排序始终可见；收藏/已翻译/可实践范围和全部 8 类来源（含此前漏掉的 `blog`）放进筛选面板，仍由 `main.js` 更新同一份 `state` 并调用 `refreshList()`。已启用的来源、范围和标签会显示为可单独清除的活动标签，避免面板收起后看不出筛选条件。
- **轻量弹层行为**：筛选和卡片「更多」使用原生 `<details>`；选择筛选后自动收起，并由 `main.js` 补充点击外部与 Esc 收起。侧栏「更多」属于持久导航，不参与这套自动关闭逻辑。
- **速报渐进阅读**：`views.js` 在安全 Markdown 渲染和引用链接化之后，把末节旧标题「边角料」或新标题「更多动态」统一转换为默认收起的原生 `<details>`，显示其中条数；展开时保留原有引用链接。移动端去掉速报正文的内层边框和额外水平 padding，避免外层卡片与 reader 双重留白挤压正文。
- **安全 Markdown / mermaid**：LLM/RSS 可控文本不能直接进 `innerHTML`。`markdown.js` 禁止 script/style/iframe/form/svg/img 和事件/样式属性；mermaid 使用 `securityLevel: 'strict'`。普通外链再经 `safeExternalUrl` 限定为 http(s)。
- **立即抓取 / 批量翻译 / 重生成速报**：仅 admin 看得到按钮，后端也用 `require_admin` 强制校验，不能靠改 DOM 绕过。

## 5. 对话组件 sparrow-chat.js

对话 UI 来自内联的 agent 运行时（原 sparrow 框架，见 `app/agent_runtime/README.md`）：

- `main.js` 先把 DOMPurify-backed renderer 暴露为 `window.__renderSafeMarkdown`，再 `SparrowChat.mount({...})`。组件的历史消息和 SSE 最终答案因此与其它 LLM 内容共用同一清洗边界；实例存到 `window.__sparrowChat`。
- `sparrow-chat.js` 现在是**仓库内源码** `frontend/public/sparrow-chat.js`，Vite 原样输出到 `/sparrow-chat.js`。**可以直接改**，但改完要 `npm run build`。（历史：曾由后端启动时从 sparrow 包同步，内联后该机制已删。）

## 6. 安全约束

- 不允许新增直接的 `marked.parse(...) → innerHTML`；必须复用 `renderMarkdown`。
- 不可信 URL 在进入 `href`、`data-url` 或 `window.open` 前必须过 `safeExternalUrl`。
- `admin-only` CSS 使用 `body.is-admin` 显示、`body:not(.is-admin)` 强制隐藏，避免被按钮或移动端布局规则覆盖；它仍只是界面提示，任何全局写操作必须同时有后端 `require_admin`。
- 依赖变更后提交 `package-lock.json`，并运行 `npm audit` 与生产构建。

详见 [known-issues](../reference/known-issues.md)。
