# 配置参考

> 全部配置项。定义在 `app/settings.py`（pydantic-settings），环境变量前缀 **`AIF_`**，
> 也读项目根 `.env`（模板见 `.env.example`）。模块级单例 `settings`。

`docker-compose.yml` 已显式透传调度、认证、防滥用、CORS、SMTP 和 Public URL 配置；在 Coolify 设置同名变量即可进入应用容器。生产至少设置随机 `AIF_SECRET_KEY`，HTTPS 域名设置 `AIF_COOKIE_SECURE=1`。

## 配置项一览

| 环境变量 | 字段 | 默认值 | 说明 |
|---|---|---|---|
| `AIF_HOST` | `host` | `0.0.0.0` | HTTP 绑定地址 |
| `AIF_PORT` | `port` | `9702` | HTTP 端口（Dockerfile/compose 一致用 9702） |
| `AIF_DATA_DIR` | `data_dir` | `~/agent-data`（容器内 `/data`） | 数据根；`ai-news/` 子目录放所有 JSON + ui.db + 缓存。启动时自动 mkdir |
| `AIF_RSSHUB_BASE` | `rsshub_base` | `https://rsshub.app` | RSSHub 实例地址。非公共实例时，加载期把所有 `rsshub.app` 前缀 URL 改写到此。compose 内默认 `http://rsshub:1200` |
| `AIF_LLM_BASE_URL` | `llm_base_url` | `https://api.deepseek.com` | LLM API 地址（OpenAI 兼容） |
| `AIF_LLM_MODEL` | `llm_model` | `deepseek-chat` | 模型名 |
| `AIF_LLM_API_KEY` | `llm_api_key` | `None` | LLM key。**为空时回退读 `DEEPSEEK_API_KEY` 环境变量** |
| `AIF_SCHEDULER_ENABLED` | `scheduler_enabled` | `True` | 是否启用后台抓取/翻译任务 |
| `AIF_AI_NEWS_CRON_HOUR` | `ai_news_cron_hour` | `5` | 分时抓取的锚点小时（Asia/Shanghai） |
| `AIF_AI_NEWS_CRON_MINUTE` | `ai_news_cron_minute` | `0` | 分时抓取分钟 |
| `AIF_AI_NEWS_INTERVAL_HOURS` | `ai_news_interval_hours` | `4` | 抓取间隔；支持 1/2/3/4/6/8/12/24，其它值安全回退为 4 |
| `AIF_FAST_NEWS_CRON_MINUTE` | `fast_news_cron_minute` | `10` | 高时效官方源的抓取分钟 |
| `AIF_FAST_NEWS_INTERVAL_HOURS` | `fast_news_interval_hours` | `1` | 高时效官方源抓取间隔；支持值同上 |
| `AIF_SLOW_NEWS_CRON_HOUR` | `slow_news_cron_hour` | `5` | 发现型来源抓取锚点小时 |
| `AIF_SLOW_NEWS_CRON_MINUTE` | `slow_news_cron_minute` | `20` | 发现型来源抓取分钟 |
| `AIF_SLOW_NEWS_INTERVAL_HOURS` | `slow_news_interval_hours` | `12` | 论文/X/Trending 发现型来源抓取间隔；支持值同上 |
| `AIF_SUMMARY_CRON_HOUR` | `summary_cron_hour` | `6` | 分时速报的锚点小时，默认比抓取晚一小时 |
| `AIF_SUMMARY_CRON_MINUTE` | `summary_cron_minute` | `0` | 分时速报分钟 |
| `AIF_SUMMARY_INTERVAL_HOURS` | `summary_interval_hours` | `4` | 速报刷新间隔；候选指纹不变时不调用 LLM，支持值同上 |
| `AIF_LOG_LEVEL` | `log_level` | `INFO` | 日志级别 |
| `AIF_SECRET_KEY` | `secret_key` | `None` | 会话 cookie 的签名密钥（itsdangerous）。**为空时自动生成并落 `<data_dir>/auth/secret.key`**；生产建议显式配，否则连卷重建/多副本会让会话失效（全员登出） |
| `AIF_SESSION_MAX_AGE_DAYS` | `session_max_age_days` | `30` | 会话有效期（天）；签名 cookie 超时即失效 |
| `AIF_COOKIE_SECURE` | `cookie_secure` | `False` | 是否给会话 cookie 加 `Secure` 标记。**HTTPS 部署设 1**，否则明文 HTTP 下可被嗅探 |
| `AIF_ADMIN_EMAIL` | `admin_email` | `None` | 指定继承老（单用户）数据的邮箱；**为空则第一个注册的账号继承**（且首注册者自动为 admin） |
| `AIF_DAILY_LLM_LIMIT` | `daily_llm_limit` | `50` | 每个已验证用户每天的 LLM 操作额度（防滥用第二道防线，第一道是邮箱验证）。admin 不限；`0`=不限。超额端点返回 **429** |
| `AIF_CORS_ORIGINS` | `cors_origins` | `""` | 允许的跨域来源（逗号分隔）。cookie 鉴权下 `allow_credentials=True`，**不能用 `"*"`**；为空 = 仅同源（内置 UI 够用） |
| `AIF_SMTP_HOST` | `smtp_host` | `""` | 邮箱验证用的 SMTP 服务器。**留空则不发验证邮件**（注册照常） |
| `AIF_SMTP_PORT` | `smtp_port` | `587` | SMTP 端口（STARTTLS） |
| `AIF_SMTP_USER` | `smtp_user` | `""` | SMTP 登录用户名。Gmail 填邮箱；SendGrid 固定填 `apikey` |
| `AIF_SMTP_PASSWORD` | `smtp_password` | `""` | SMTP 密码。**Gmail 用「应用专用密码」非登录密码**；SendGrid 填 API Key。**绝不入 git** |
| `AIF_SMTP_FROM` | `smtp_from` | `""` | 发件人地址；留空则用 `smtp_user` |
| `AIF_PUBLIC_BASE_URL` | `public_base_url` | `""` | 站点公开地址（如 `https://ai.zhangyangbin.com`），用于拼验证链接。**留空则不发验证信**（拼不出链接） |

## 非 `AIF_` 前缀的相关变量

| 环境变量 | 谁用 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 应用（回退） + compose | `AIF_LLM_API_KEY` 为空时的回退来源；compose 同时映射给 `AIF_LLM_API_KEY` |
| `TWITTER_AUTH_TOKEN` | **rsshub 容器**（非本应用） | x.com 登录 cookie，给自建 rsshub 抓 Twitter 路由用。登录凭证，勿入 git |
| `TZ` | compose | 容器时区，设 `Asia/Shanghai` |

## 代码内常量（非环境变量，改需动代码）

这些不是配置项，但常被当成「可调参数」，集中列在这里。都在 `app/routers/ai_news.py`：

| 常量 | 值 | 含义 |
|---|---|---|
| `_ARTICLE_LIMIT` | 400 | 文章滚动历史上限（pinned 不淘汰） |
| `_DAILY_FETCH_CAP` | 150 | 单次抓取全局入库上限 |
| `_PER_FEED_CAP` | 4 | 每源首轮最多进入 4 个轮次；先让各源各取 1 条，再取第 2 条，之后才处理 overflow |
| `_CATEGORY_FETCH_CAPS` | 共 150 | 单轮分类硬上限：vendor 46 / media 20 / blog 16 / paper 14 / community 18 / expert 18 / x-ai 12 / trending 6 |
| `_DEFAULT_TIER_BY_CATEGORY` | 8 类映射 | 运行时按 category 归一化 tier：vendor/blog=high，media/paper/community/expert=med，x-ai/trending=low |
| `_SUMMARY_CATEGORY_CAPS` | 8 类映射 | 速报候选上限；其中 trending=2、x-ai=3，且这两类永不放宽 |
| `DEFAULT_FEED_SPECS` | 93 条 | RSS/Atom/官方 sitemap/API/changelog 清单；加载时补 cadence（12 fast / 52 standard / 29 slow），特殊源另带 format/include_paths/max_per_fetch/source_priority/request_profile/curated |
| `AI_KEYWORDS` | 一组中英词 | med/low 相关性过滤；high、paper 与显式 `curated=true` 的 AI 刊物未命中时仍可接受 |
| `DEFAULT_TRACKS` | 3 条 | tracks.json 为空时的默认追踪主题 |

在 `app/workers/ai_news_translator.py`：

| 常量 | 值 | 含义 |
|---|---|---|
| `BATCH_SIZE` | 8 | 每次富化（翻译+评分+打标签）批量大小 |
| `ENRICHMENT_BACKFILL_LIMIT` | 60 | 实践/事件键字段上线时，自动回填的最近已翻译文章上限；空字符串也视为已处理 |

在 `app/workers/ai_news_fetcher.py`：

| 常量 | 值 | 含义 |
|---|---|---|
| `_SITEMAP_METADATA_LIMIT` | 6 | 每个 sitemap 源最多补全的最新文章页数；读取 Open Graph/meta/JSON-LD，失败保留 sitemap 降级数据 |

## 修改约定

- 新增/改环境变量：改 `app/settings.py` 的 `Settings` 字段 → 同步更新 `.env.example` → 回这张表补一行。
- 调容量参数（如想多留文章、多抓几篇）：改 `ai_news.py` 顶部常量；`_CATEGORY_FETCH_CAPS` 总和当前等于 `_DAILY_FETCH_CAP=150`，新增分类或放宽一类时需重新检查全局预算和测试。
- 加/删源：编辑 `DEFAULT_FEED_SPECS`，注意 `category` 要落在前端已识别的 8 类内（vendor/x-ai/community/expert/blog/media/trending/paper）。没有 RSS 但提供标准 sitemap 的官方站可设 `format="sitemap"` 和 `include_paths`；官方 JSON 或 changelog 页面需在 fetcher 增加小型专用解析器和 format（现有 `qwen_api` / `hf_daily_papers` / `openai_changelog` / `gemini_changelog` 可参考）。`max_per_fetch` 是解析后的单源硬上限，`source_priority` 只影响同轮候选先后，不改变持久化 tier。只有确认整个来源都属于 AI 内容时才设 `curated=true`；只有源站明确拦截抓取器 UA 时才设 `request_profile="browser"`。
