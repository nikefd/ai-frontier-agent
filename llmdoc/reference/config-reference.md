# 配置参考

> 全部配置项。定义在 `app/settings.py`（pydantic-settings），环境变量前缀 **`AIF_`**，
> 也读项目根 `.env`（模板见 `.env.example`）。模块级单例 `settings`。

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
| `AIF_AI_NEWS_CRON_HOUR` | `ai_news_cron_hour` | `7` | 每日抓取小时（Asia/Shanghai） |
| `AIF_AI_NEWS_CRON_MINUTE` | `ai_news_cron_minute` | `30` | 每日抓取分钟 |
| `AIF_LOG_LEVEL` | `log_level` | `INFO` | 日志级别 |

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
| `_PER_FEED_CAP` | 4 | 单次抓取每源最多保留篇数（保证源多样性） |
| `DEFAULT_FEED_SPECS` | 79 条 | RSS feed 清单（url/name/tier/category/description） |
| `AI_KEYWORDS` | 一组中英词 | 关键词打标用（当前只打标不拒绝） |
| `DEFAULT_TRACKS` | 3 条 | tracks.json 为空时的默认追踪主题 |

在 `app/workers/ai_news_translator.py`：

| 常量 | 值 | 含义 |
|---|---|---|
| `BATCH_SIZE` | 5 | 每次翻译批量大小 |

## 修改约定

- 新增/改环境变量：改 `app/settings.py` 的 `Settings` 字段 → 同步更新 `.env.example` → 回这张表补一行。
- 调容量参数（如想多留文章、多抓几篇）：改 `ai_news.py` 顶部常量，注意 `_DAILY_FETCH_CAP` 和 `_PER_FEED_CAP` 的关系（每源先占额，再全局回填）。
- 加/删 RSS 源：编辑 `DEFAULT_FEED_SPECS`，注意 `category` 要落在前端已识别的 8 类内（vendor/x-ai/community/expert/blog/media/trending/paper），否则前端分组标签会以原始 key 显示。
