# 认证架构

> 讲清楚多用户鉴权怎么搭起来：用户存储、密码哈希、会话机制、守卫怎么挂、
> 用户产物怎么按用户隔离、老数据怎么迁移。涉及文件：`app/auth.py`、`app/migrate.py`、
> `app/models.py`，以及被守卫的 `app/routers/ai_news.py` / `app/agent_chat.py`。
> 配置项见 [配置参考](../reference/config-reference.md)；安全约束见 [已知问题](../reference/known-issues.md) 第 13/14 条。

## 1. 权限模型

| 身份 | 能做什么 |
|---|---|
| **未登录** | 浏览全局内容：文章流、今日速报、数据源、单篇阅读。用户产物的读（tracks/deep-dives/guides/conversations）返回**空** |
| **未登录禁止** | 任何写（pin/track/guide/删除/fetch/translate）和任何 **LLM 调用**（深度解读/手动新建/速报/指南/对话 agent）→ **401** |
| **登录后** | 可写、可调 LLM，且产物只属于自己 |

实现：写 & LLM 端点挂 `Depends(require_user)`（匿名 401）；用户产物的读挂 `Depends(current_user_optional)`（匿名得空）；全局只读端点不挂。

## 2. 数据切分

只有**用户产物**按用户独立，其余全局共享。

| 全局共享（`ai-news/`） | 按用户独立（`users/<uid>/`） |
|---|---|
| `articles.json` 文章主存储 | `tracks.json` 追踪主题 |
| `sources.json` 抓取健康 | `pins.json` 收藏的 article id |
| `summary_today.json` 今日速报 | `guides.json` + `guides/` 指南 |
| `reader-cache/` | `deep-dives/` 深度解读 |
| | `ui.db` 对话记忆 |

认证数据在 `auth/`（`users.json` + `secret.key`），全局。目录细节见 [数据存储参考](../reference/data-storage.md)。

### 2.1 pin 为什么要迁出文章对象

原来 `pinned` 写在全局 `articles.json` 每篇文章上 → 多用户后一个人 pin 了所有人都看到。所以 pin 迁成「用户↔文章」关联：存于 `users/<uid>/pins.json`（article id 列表）。`GET /articles` 读全局文章后**按当前用户叠加** `pinned` / `deep_dive_status`（后者由该用户的 `deep-dives/{aid}.json` 是否存在推导），匿名全为 false/none。文章滚动淘汰（上限 400）的「pinned 不淘汰」保护改为**按所有用户 pins.json 的并集**（`_all_pinned_ids()`）。

## 3. 认证流程

```mermaid
sequenceDiagram
  participant UI as 前端 auth.js
  participant API as /api/auth/*
  participant Store as users.json
  participant Cookie as 签名 cookie

  UI->>API: POST /register {email, password}
  API->>API: 限流 + 校验 + bcrypt 哈希
  API->>Store: 追加 UserRecord（首个=admin）
  API->>API: migrate.inherit_legacy_if_eligible()
  API->>Cookie: Set-Cookie aif_session (httponly)
  API-->>UI: {user: UserPublic}
  Note over UI: 后续请求自动带 cookie

  UI->>API: POST /login {email, password}
  API->>API: 限流 + 统一错误 + 必跑哈希比对
  API->>Cookie: Set-Cookie
  API-->>UI: {user}
```

### 3.1 密码哈希

`bcrypt`（自带盐）。`hash_password` / `verify_password` 在 `auth.py`。密码超 72 字节按 bcrypt 规则截断。

### 3.2 会话：无状态签名 cookie

用 `itsdangerous.URLSafeTimedSerializer` 签 `{"uid": uid}` 写入 `aif_session` cookie（**httponly + samesite=lax**，HTTPS 下 + secure）。每请求依赖从 cookie 读 token → 校验签名/过期 → 得 uid → 查 `users.json`。

- 签名密钥 `AIF_SECRET_KEY`：为空时自动生成落 `auth/secret.key`（生产建议显式配，否则连卷重建/多副本会全员登出）。
- **无服务端 session 表** → 登出只清浏览器 cookie，已签发 token 无法主动吊销（只能等过期或换密钥）。取舍见 [已知问题](../reference/known-issues.md) 第 13 条。

### 3.3 防枚举 / 防时序

登录对「邮箱不存在」和「密码错」返回**同一文案**，且邮箱不存在时也跑一次 dummy bcrypt 比对消除时序差。`/login` `/register` 加内存滑窗限流（8 次/60s，按 IP + 邮箱）。

## 4. 对话隔离

sparrow 的 `Memory` 无 user/namespace 维度（`conversations`/`messages`/`journal` 表只认 `conversation_id`，`list_conversations` 不过滤、journal 全局）。所以用**每用户一个 `ui.db`** 做隔离：`agent_chat.py` 的 `_memory_for(uid)` 按 uid 选 `users/<uid>/ui.db` 并缓存 `Memory` 实例。会话列表/读取/删除都基于该用户的 Memory。

agent 工具也按用户绑定：`agent_tools.build_tools(uid)` 每请求构造一组绑定 uid 的工具闭包（读全局 articles 但 pin 状态、tracks/guides/deep-dives 都用该 uid）。

## 5. 数据迁移（老单用户数据归谁）

`app/migrate.py` 两步：

1. **启动时** `migrate_legacy_to_holding()`（幂等，靠 `users/_legacy/` 是否存在判断）：把老的 `ai-news/` 下 `tracks.json` / `guides.json` / `guides/` / `deep-dives/` / `ui.db` 搬到 `users/_legacy/`；从 `articles.json` 抽出 `pinned=True` 的 id 写进 `_legacy/pins.json` 并剥离每篇的 `pinned`；丢弃 `manual` 合成文章（其解读已在 `_legacy/deep-dives/`）。
2. **注册时** `inherit_legacy_if_eligible(user)`：若该用户匹配 `AIF_ADMIN_EMAIL`（未配则首个注册的 admin），把 `_legacy/` 改名成其 uid 目录继承。

约束：没人匹配 `AIF_ADMIN_EMAIL` 时 `_legacy/` 会一直「无主」留存（数据不丢）。不配 `AIF_ADMIN_EMAIL` 由首注册者继承最稳。

## 6. 前端（`static/js/auth.js`）

- 启动 `GET /api/auth/me` 取登录态，渲染顶栏（`#auth-slot`）：未登录显示「登录/注册」，登录显示 email + 登出。
- 登录/注册弹窗（零构建，原生 DOM），不引框架。
- `api.js` 统一拦 401 → 弹登录弹窗（`setUnauthorizedHandler`）。
- 登录/登出后派发 `aif:auth-changed` 事件，`main.js` 据此重载视图；登出清 `localStorage` 的 `aif_conv_id` 避免会话串号。
