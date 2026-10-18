# 已知问题与约束

> 从当前 main 如实记录的坑、约束和历史遗留。改任何一条前先确认影响面。

## 1. CORS 全开（`allow_origins=["*"]`）

> ✅ 已收紧（多用户鉴权一期）。`app/main.py` 现在用 `allow_origins=settings.cors_origin_list`
> + `allow_credentials=True`（cookie 鉴权必需）。默认 `AIF_CORS_ORIGINS` 为空 = 仅同源
> （内置 UI 够用）。若有跨域前端，配 `AIF_CORS_ORIGINS=https://a.com,https://b.com`。
> **注意**：`allow_credentials=True` 时不能再用 `"*"`，否则浏览器拒绝带 cookie 的请求。

## 2. 两个 chat 端点并存

- `POST /api/ai-news/chat`：旧版无工具直通 LLM，**前端已不用**，保留作 openclaw 兼容。
- `POST /api/agent/chat`：sparrow ReAct agent，**前端实际使用**。

不是 bug，但容易让人改错地方。改对话行为去 `app/agent_chat.py`，不是 `ai_news.py` 的 `chat()`。

## 3. 翻译失败不自动重试

翻译 worker 把失败的文章标 `translation_status="failed"`，**之后不再自动翻**（防死循环）。要重译得 `POST /articles/{aid}/retranslate` 把状态重置回 `pending`。这是设计取舍，但用户可能困惑「为什么这篇一直没中文」。

## 4. X 来源仍依赖自建 RSSHub

92 个源里仍有大量 X 路由走 RSSHub；公共实例可能 404/限流，24 个 x-ai 源还需要 `TWITTER_AUTH_TOKEN`。不配自建 RSSHub 时主要损失社交信号，官方/研究/媒体 RSS、Anthropic/Cohere/Mistral/xAI 官方 sitemap、Qwen 官方 API 与 OpenAI/Gemini changelog 仍可工作。Mistral/xAI sitemap 若在部署网络超时，只会记录该源失败，不阻塞其它来源。详见 [部署指南](../guides/how-to-deploy.md)。

## 5. tier 与分类配额已恢复生效

> ✅ 已修复。来源启动时按 category 归一化为 high/med/low；med/low 必须命中 `AI_KEYWORDS`（paper 例外），并受 `_CATEGORY_FETCH_CAPS` 限制。Trending 从 5 路重叠源减为 1 路，每轮最多 6 条；速报候选再限制为最多 2 条。调整 tier、关键词或配额时需运行 `tests/test_news_quality.py`，避免发现源重新淹没一手信息。

## 6. 种子 sources.json 是空的

`seed-data/ai-news/sources.json` 是 `{}`。首次部署后数据源页**全部显示「尚未抓取」**，直到第一轮 fetch 跑完才有健康数据。不是故障。

## 7. 历史命名遗留（zyb / zhangyangbin）

项目从 `zhangyangbin-agents` 抽取，多处仍残留旧名：

- logger 名：`logging.getLogger("zyb.ai_news")` / `"zyb.fetcher"` / `"zyb.translator")`（其它模块已用 `aif.*`）。
- `app/workers/ai_news_fetcher.py` 的 `USER_AGENT` 写死 `"zyb-agents/0.2 (+https://github.com/yourname/zhangyangbin-agents)"`——是占位 URL。
- `app/llm_client.py` 抛 `LLMUnavailable` 的错误文案提到 `ZYB_LLM_API_KEY` / `COPILOT_GITHUB_TOKEN`，**已过时**（现在前缀是 `AIF_`，回退是 `DEEPSEEK_API_KEY`）。文案误导，逻辑无误。

都不影响运行，属命名债。

## 8. `/reader/{aid}` SSRF / 原始 HTML（已修复）

现由 `app/safe_fetch.py` 限定公共 http(s)，拒绝私网/回环/metadata/凭据 URL，每次重定向重新校验 DNS，并限制 HTML 类型与 2 MB。返回前白名单清洗，旧缓存也会惰性迁移；不再把远端主动 HTML 放到本站同源执行。全局文章新增/删除同时收紧为 admin-only。

## 9. 前端小问题

- `frontend/src/views.js` 的数据源页 `SRC_CAT_LABELS` / `SRC_ORDER` 已覆盖全部 8 类（含 `expert` / `x-ai`）；单源失败、连续失败和调度过期会分开显示并在分类内置顶。来源很久没发文章本身不算故障。
- `frontend/public/sparrow-chat.js` 是仓库内源码（原 sparrow 组件，agent 运行时内联后纳入）。可直接改，但改完要 `npm run build` 才生效。

## 10. tests/ 目录刚起步

`pyproject.toml` 配了 pytest/pytest-asyncio。当前 78 项测试覆盖内容质量配额、官方 sitemap/index 与页面元数据补全、Qwen API、OpenAI/Gemini changelog、URL/标题/事件去重及多源佐证、实践建议与事件键清洗/持久化/旧数据回填、分时调度、速报指纹、来源健康分类、文章服务端筛选/分页、时间解析、排序、SRS、admin 护栏、认证安全、复盘、学习路径和额度。仍不是完整覆盖；用 `pip install -e ".[dev]" && pytest` 运行。

## 11. `deploy/` 目录为空

仓库根有 `deploy/` 但里面没文件。部署配置（域名/TLS/反代）都托管在 Coolify，不在 git 里。

## 12. `agent/` 是占位包

`agent/__init__.py` 只有占位注释。对话 agent 实际实现在 `app/agent_chat.py` + `app/agent_runtime/`（sparrow 运行时已内联），`agent/` 当前未被使用。

## 13. 多用户鉴权：安全要点与约束

鉴权实现在 `app/auth.py`（用户存储 `auth/users.json`、bcrypt 哈希、itsdangerous 签名 cookie、`require_user`/`current_user_optional` 依赖）。几条必须知道的点：

- **`AIF_SECRET_KEY` 生产必须显式配**：留空时启动会自动生成并落 `<data_dir>/auth/secret.key`。容器**重建**（卷不变）时该文件还在 → 没问题；但如果连卷一起重建、或多副本各自生成，会话签名密钥不一致 → 全员被登出。生产环境用 env 显式注入同一个 key。
- **HTTPS 部署设 `AIF_COOKIE_SECURE=1`**：否则会话 cookie 不带 `Secure`，明文 HTTP 下可被嗅探。本地开发默认 0。
- **会话无法主动吊销**：采用无状态签名 cookie，登出只是清浏览器 cookie；服务端不存 session，所以**改密码/踢人无法让已签发 token 立即失效**（只能等过期或换 `AIF_SECRET_KEY`，后者会踢所有人）。需要「登出即失效」再考虑改服务端 session。
- **限流是单进程内存滑窗**：`/login`、`/register` 限 8 次/60s（按 IP + 邮箱）。多副本部署时每副本独立计数，整体阈值 = 单值 × 副本数；且重启清零。够挡暴力破解，不是分布式限流。
- **`X-Forwarded-For` 信任**：限流取 XFF 第一跳作为客户端 IP。**前面必须有可信反代**（Coolify/Traefik）才准；直接裸暴露时 XFF 可伪造，限流可被绕过 IP 维度（邮箱维度仍有效）。
- **防枚举/防时序**：登录对「邮箱不存在」和「密码错」返回**同一文案**（`邮箱或密码错误`），且邮箱不存在时也跑一次 dummy bcrypt 比对，消除时序差。注册对已存在邮箱返回 409 `该邮箱已注册`——这本身是一个枚举面，但注册场景下属可接受取舍。
- **已做**：邮箱验证（验证后才能用 LLM 功能）、找回密码、改密码、每日 LLM 额度限制。**未做**：2FA。
- **全局写边界**：文章增删、手动抓取/翻译/重译/速报重生成仅 admin；普通用户只写自己的产物。前端隐藏按钮只是体验层，后端守卫才是安全边界。

## 14. 数据迁移只跑一次（`_legacy` 哨兵）

`app/migrate.py` 的 `migrate_legacy_to_holding()` 启动时把老单用户产物搬到 `<data_dir>/users/_legacy/`，**靠 `_legacy/` 是否存在判断幂等**。首个注册账号（或 `AIF_ADMIN_EMAIL` 指定者）注册时 `inherit_legacy_if_eligible()` 把 `_legacy/` 改名成其 uid 目录。两个隐含约束：

- 迁移**只在 `_legacy/` 不存在时跑**。手动删了 `_legacy/` 又有老数据残留，会再迁一次。
- 若**没人**匹配 `AIF_ADMIN_EMAIL`，`_legacy/` 会一直留着不被继承（数据不丢，但「无主」）。不配 `AIF_ADMIN_EMAIL` 时由首个注册者继承，最稳。

## 15. 静态资源缓存陷阱（已由 Vite 迁移解决）

**历史问题**：前端曾是零构建 ES module，`main.js` 用裸相对 `import` 拉子模块（不带版本串），无法靠 URL 版本号打破缓存；改用 `no-cache` 后又被 Cloudflare 边缘强行覆盖成 `max-age=14400`，导致用户部署后数小时仍看到旧 JS。

**现状（已解决）**：前端迁到 Vite 构建，产物文件名带内容指纹（`assets/index-<hash>.js`）。缓存策略改为：

- `/` 入口 HTML → `Cache-Control: no-cache`（小文件，每次校验）。
- `/assets/*` 指纹文件 → `max-age=31536000, immutable`（永久强缓存）。

## 16. 前端主动内容 XSS（已修复）

历史上 LLM Markdown 直接 `marked.parse → innerHTML`，Mermaid 为 loose，且库从 CDN 加载。现统一走 `markdown.js` 的 DOMPurify 白名单，Mermaid strict，普通外链只接受 http(s)，依赖精确锁定并随 Vite 打包；服务端再以 CSP/`nosniff` 等响应头兜底。`npm audit` 当前为 0。

## 17. JSON 原子 rename 不等于事务（已修复，仍限单进程）

历史 `write_json_atomic` 只能防文件写一半，不能防并发读改写丢更新。现在计数、toggle、append 和翻译合并用 `update_json_atomic` 锁住完整事务，fetch/translate sweep 也避免同进程重叠。锁仍是进程内锁；如果未来开多个 uvicorn worker，需迁到 SQLite/数据库或跨进程锁。

因为内容一变文件名就变、入口 HTML 改引用新文件名，**强缓存与“立即生效”不再冲突**，也不再依赖 Cloudflare 配置——边缘的 `max-age` 反而是正确行为。详见 [前端架构](../architecture/frontend-architecture.md) 第 1 节。
