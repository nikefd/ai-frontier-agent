# 后端架构

> 讲清楚 FastAPI 这个**单进程一体化**应用是怎么搭起来的：进程模型、模块职责、
> 启动流程、存储层为什么这么设计。具体端点清单见 [API 参考](../reference/api-reference.md)；
> 配置项见 [配置参考](../reference/config-reference.md)。

## 1. 进程模型：一个 uvicorn 进程包办一切

整个后端是**一个** uvicorn 进程，里面同时跑着：

- HTTP API（`/api/*`）
- 静态前端托管（`/ui/*`）
- APScheduler 后台任务（抓取 + 翻译），与 FastAPI **共用同一个 asyncio 事件循环**

没有独立 worker 进程，没有消息队列，没有数据库服务。这是刻意的「克隆即可跑」取向——代价是抓取/翻译/LLM 调用都和 Web 请求共享同一进程的事件循环（IO 密集、异步，所以单进程够用；但 CPU 密集任务会阻塞，目前没有这类任务）。

启动命令（容器与裸机一致）：

```
uvicorn app.main:app --host 0.0.0.0 --port 9702
```

## 2. 启动流程（`app/main.py`）

```mermaid
flowchart TD
  start([uvicorn 启动]) --> lifespan[lifespan: 进入]
  lifespan --> log[配置 logging]
  log --> sched[scheduler.start：注册抓取+翻译 job]
  sched --> ready{应用就绪，处理请求}
  ready -->|关闭| stop[scheduler.stop]

  subgraph 模块加载期（import 时）
    mount_news[挂载 ai_news 路由]
    mount_agent[尝试挂载 agent_chat 路由<br/>失败仅告警，新闻 API 不受影响]
    sync[_sync_sparrow_assets：<br/>拷贝 sparrow-chat.js 到 static/js/]
    mount_ui[挂载 /ui 静态目录]
  end
```

几个关键设计点：

- **agent 路由是「软挂载」**：`app/main.py` 用 try/except 包住 `from .agent_chat import router`。如果 sparrow 包缺失或初始化失败，只打一条 warning，**新闻 API 照常工作**。这让「没装 sparrow 也能浏览新闻」成立。
- **sparrow-chat.js 启动时自动同步**：`_sync_sparrow_assets()` 在 import 期从 sparrow 包里 `asset_path("sparrow-chat.js")` 拷到 `static/js/`。好处是 sparrow 升级后前端组件自动跟着更新，不用手动维护一份拷贝。
- **`/` 与 `/ui` 的挂载顺序**：先显式注册 `GET /` → redirect 到 `/ui/`、`GET /ui/` → 返回 index.html，**再** `app.mount("/ui", StaticFiles(...))`。顺序很重要，否则 StaticFiles 会吃掉 `/ui/` 导致重定向逻辑失效。
- **CORS 当前是 `allow_origins=["*"]`**（`allow_credentials=False`）。绑公网且前面没有鉴权时要收紧，见 [known-issues](../reference/known-issues.md)。

## 3. 模块职责与依赖方向

```
main.py ──┬─> routers/ai_news.py ──┬─> models.py
          │                        ├─> storage.py
          │                        ├─> llm_client.py
          │                        └─> settings.py
          ├─> agent_chat.py ───────┬─> agent_tools.py ──> routers/ai_news.py（复用其 _load_* 与常量）
          │                        ├─> llm_client.py / settings.py
          │                        └─> sparrow（Harness/AgentConfig/Memory/tool）
          └─> scheduler.py ────────> workers/ai_news_fetcher.py ──> routers/ai_news.py（复用 add_article 等）
                                     workers/ai_news_translator.py ──> routers/ai_news.py
```

**`routers/ai_news.py` 是事实上的核心模块**，不只是路由：

- 它持有 feed 清单（`DEFAULT_FEED_SPECS`）、关键词表（`AI_KEYWORDS`）、所有文件路径常量（`ARTICLES_FILE` 等）、容量参数（`_ARTICLE_LIMIT` / `_DAILY_FETCH_CAP` / `_PER_FEED_CAP`）。
- worker 和 agent tools 都**反向 import** 它的 `_load_articles()` / `add_article()` / `_parse_ts()` 等内部函数来复用逻辑（带下划线但被跨模块使用，属约定俗成的「包内公开」）。改这些函数签名时注意三处调用方。

为避免 import 环：`POST /fetch` 和 `POST /translate/run` 在**函数体内**才 import worker（`from ..workers.ai_news_fetcher import fetch_once`），而不是模块顶部。

## 4. 存储层（`app/storage.py`）

应用**不用数据库做主存储**，状态都在文件里。存储层只有两个职责，但都是为并发安全服务：

### 4.1 原子 JSON 写：`write_json_atomic`

抓取 worker、翻译 worker、HTTP 请求可能同时写 `articles.json`。实现：

1. 进程内按路径加 `threading.Lock`（`_FILE_LOCKS`）
2. 写到同目录的临时文件 → `flush` + `os.fsync`
3. `os.replace(tmp, path)` 原子 rename（同文件系统下原子）

效果：任何崩溃都不会留下半截 JSON 文件。读端 `read_json` 对 `FileNotFoundError` / `JSONDecodeError` / `OSError` 一律返回传入的 default，不抛异常。

> 设计注释里明确对比了上游 openclaw 的反面教材——那边每个端点各自 `JSON.stringify + writeFileSync`，撞过半写文件的 bug。这里集中做一次。

### 4.2 只读 SQLite：`sqlite_ro`

`ui.db`（sparrow 对话记忆）用 `file:...?mode=ro` URI 打开，多读者可共享。数据库不存在时返回 `:memory:` 空连接，让调用方拿到空结果而非崩溃。

> 注意：sparrow 的 `Memory` 自己管对 `ui.db` 的**写**；`storage.sqlite_ro` 是为「应用其它地方只读查 ui.db」准备的通用工具。

## 5. LLM 客户端（`app/llm_client.py`）

刻意**不引 openai / anthropic SDK**，因为目标端点都是 OpenAI 兼容的 `/chat/completions`，httpx 又已经在依赖里（抓取用）。提供两个函数：

- `chat_complete(messages, *, model, temperature, max_tokens)` — 非流式，返回字符串
- `chat_stream(messages, ...)` — 异步生成器，逐段 yield SSE delta

未配置 key 时抛 `LLMUnavailable`，路由层捕获后返回 503。`llm_configured()` 是各端点的前置门卫。

> 注意 sparrow agent 走的是 sparrow 自己的 LLM 客户端（`agent_chat.py` 里用 `sparrow.configure(...)` 配的），**不经过** `llm_client.py`。`llm_client.py` 只服务于新闻路由的翻译/速报/解读/指南/legacy chat。

## 6. 两套对话端点并存

| 端点 | 实现 | 用途 |
|---|---|---|
| `POST /api/ai-news/chat` | `ai_news.py`，无工具的直通 LLM（塞最近 10 篇做上下文） | 早期遗留 / openclaw 兼容，**前端当前不用** |
| `POST /api/agent/chat` | `agent_chat.py`，sparrow ReAct + 工具 + 记忆，SSE | **前端实际使用**的对话入口 |

详见 [Agent 架构](agent-architecture.md)。两者并存属历史演进，见 [known-issues](../reference/known-issues.md)。
