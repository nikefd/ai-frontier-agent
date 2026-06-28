# 已知问题与约束

> 从当前代码（main @ 78739d3）如实记录的坑、约束和历史遗留。改任何一条前先确认影响面。

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

- `static/js/views.js` 的数据源页 `SRC_CAT_LABELS` / `SRC_ORDER` 已覆盖全部 8 类（含 `expert` / `x-ai`）。
- `static/js/sparrow-chat.js` 由后端启动时从 sparrow 包覆盖同步，**手动编辑会被下次启动冲掉**。要改对话组件改 `mount` 配置或升级 sparrow。已加入 `.gitignore` 不入库。

## 10. tests/ 目录刚起步

`pyproject.toml` 配了 `testpaths = ["tests"]` 和 pytest-asyncio。`tests/` 有 `test_feed_personal.py`（个性化排序）、`test_srs.py`（SM-2 调度）、`test_admin.py`（admin 护栏）、`test_email_verify.py`（邮箱验证 + 密码重置 token，含三类 token 隔离）、`test_reflection.py`（复盘 JSON 容错解析）。覆盖率仍低。注意：开发环境不一定装了 `pytest`（`python -m pytest` 可能报 `No module named pytest`）——纯函数测试可 `python -c "import tests.xxx ..."` 跑断言，部分测试额外支持 `python tests/xxx.py` 直接运行（带 `__main__` 入口）。

## 11. `deploy/` 目录为空

仓库根有 `deploy/` 但里面没文件。部署配置（域名/TLS/反代）都托管在 Coolify，不在 git 里。

## 12. `agent/` 是占位包

`agent/__init__.py` 只有一行注释「LLM Harness 下个里程碑填充」。对话 agent 实际实现在 `app/agent_chat.py`（用 PyPI 的 sparrow），`agent/` 当前未被任何代码使用。

## 13. 多用户鉴权：安全要点与约束

鉴权实现在 `app/auth.py`（用户存储 `auth/users.json`、bcrypt 哈希、itsdangerous 签名 cookie、`require_user`/`current_user_optional` 依赖）。几条必须知道的点：

- **`AIF_SECRET_KEY` 生产必须显式配**：留空时启动会自动生成并落 `<data_dir>/auth/secret.key`。容器**重建**（卷不变）时该文件还在 → 没问题；但如果连卷一起重建、或多副本各自生成，会话签名密钥不一致 → 全员被登出。生产环境用 env 显式注入同一个 key。
- **HTTPS 部署设 `AIF_COOKIE_SECURE=1`**：否则会话 cookie 不带 `Secure`，明文 HTTP 下可被嗅探。本地开发默认 0。
- **会话无法主动吊销**：采用无状态签名 cookie，登出只是清浏览器 cookie；服务端不存 session，所以**改密码/踢人无法让已签发 token 立即失效**（只能等过期或换 `AIF_SECRET_KEY`，后者会踢所有人）。需要「登出即失效」再考虑改服务端 session。
- **限流是单进程内存滑窗**：`/login`、`/register` 限 8 次/60s（按 IP + 邮箱）。多副本部署时每副本独立计数，整体阈值 = 单值 × 副本数；且重启清零。够挡暴力破解，不是分布式限流。
- **`X-Forwarded-For` 信任**：限流取 XFF 第一跳作为客户端 IP。**前面必须有可信反代**（Coolify/Traefik）才准；直接裸暴露时 XFF 可伪造，限流可被绕过 IP 维度（邮箱维度仍有效）。
- **防枚举/防时序**：登录对「邮箱不存在」和「密码错」返回**同一文案**（`邮箱或密码错误`），且邮箱不存在时也跑一次 dummy bcrypt 比对，消除时序差。注册对已存在邮箱返回 409 `该邮箱已注册`——这本身是一个枚举面，但注册场景下属可接受取舍。
- **未做**：邮箱验证、找回密码、2FA（需求明确「不必」，留待后续分期，且依赖 SMTP 基建，当前无邮件服务配置）。

## 14. 数据迁移只跑一次（`_legacy` 哨兵）

`app/migrate.py` 的 `migrate_legacy_to_holding()` 启动时把老单用户产物搬到 `<data_dir>/users/_legacy/`，**靠 `_legacy/` 是否存在判断幂等**。首个注册账号（或 `AIF_ADMIN_EMAIL` 指定者）注册时 `inherit_legacy_if_eligible()` 把 `_legacy/` 改名成其 uid 目录。两个隐含约束：

- 迁移**只在 `_legacy/` 不存在时跑**。手动删了 `_legacy/` 又有老数据残留，会再迁一次。
- 若**没人**匹配 `AIF_ADMIN_EMAIL`，`_legacy/` 会一直留着不被继承（数据不丢，但「无主」）。不配 `AIF_ADMIN_EMAIL` 时由首个注册者继承，最稳。

## 15. 静态资源缓存陷阱（已由 Vite 迁移解决）

**历史问题**：前端曾是零构建 ES module，`main.js` 用裸相对 `import` 拉子模块（不带版本串），无法靠 URL 版本号打破缓存；改用 `no-cache` 后又被 Cloudflare 边缘强行覆盖成 `max-age=14400`，导致用户部署后数小时仍看到旧 JS。

**现状（已解决）**：前端迁到 Vite 构建，产物文件名带内容指纹（`assets/index-<hash>.js`）。缓存策略改为：

- `/ui/` 入口 HTML → `Cache-Control: no-cache`（小文件，每次校验）。
- `/ui/assets/*` 指纹文件 → `max-age=31536000, immutable`（永久强缓存）。

因为内容一变文件名就变、入口 HTML 改引用新文件名，**强缓存与“立即生效”不再冲突**，也不再依赖 Cloudflare 配置——边缘的 `max-age` 反而是正确行为。详见 [前端架构](../architecture/frontend-architecture.md) 第 1 节。
