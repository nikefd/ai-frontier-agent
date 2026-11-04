# 认证架构

> 讲清楚多用户鉴权怎么搭起来：用户存储、密码哈希、会话机制、守卫怎么挂、
> 用户产物怎么按用户隔离、老数据怎么迁移。涉及文件：`app/auth.py`、`app/migrate.py`、
> `app/models.py`，以及被守卫的 `app/routers/ai_news.py` / `app/agent_chat.py`。
> 配置项见 [配置参考](../reference/config-reference.md)；安全约束见 [已知问题](../reference/known-issues.md) 第 13/14 条。

## 1. 权限模型

| 身份 | 能做什么 |
|---|---|
| **未登录** | 浏览全局内容：文章流、今日速报、数据源、单篇阅读。用户产物的读（tracks/deep-dives/guides/conversations）返回**空** |
| **未登录禁止** | 任何用户写操作和任何 LLM 调用 → **401** |
| **普通登录用户** | 可管理自己的 pin/track/guide/解读/卡片等产物；通过验证和额度闸后可调用个人 LLM 功能 |
| **管理员** | 具备普通用户能力；另可新增/删除全局文章、立即抓取、批量翻译、重生成全局速报和管理用户 |

实现：写 & LLM 端点挂 `Depends(require_user)`（匿名 401）；用户产物的读挂 `Depends(current_user_optional)`（匿名得空）；全局只读端点不挂。

**admin 角色**：`require_admin`（`auth.py`）在 `require_user` 之上加 `role == "admin"` 校验（非 admin 403）。除 `/api/admin/*`，会改变全局内容的 `/articles` 新增/删除、`/fetch`、`/translate/run`、`/articles/{aid}/retranslate`、`POST /summary/today` 也挂该守卫。护栏：admin 不能删/降自己、系统至少留一个 admin。前端用 `body.is-admin` 控制管理入口和全局操作按钮显隐。

**个人 LLM 端点的两道防滥用闸**（防未验证小号 / 单用户刷爆 LLM key）：解读、指南、对话、画像、复盘和学习路径挂 `require_llm_quota`，它依次要求邮箱验证并原子消费每日额度；普通用户超 `AIF_DAILY_LLM_LIMIT` 返回 **429**，admin 豁免。全局翻译/速报属于 admin-only 运维操作，定时任务在进程内直接调用实现。

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

原来 `pinned` 写在全局 `articles.json` 每篇文章上 → 多用户后一个人 pin 了所有人都看到。所以 pin 迁成「用户↔文章」关联：存于 `users/<uid>/pins.json`（article id 列表）。`GET /articles` 读全局文章后**按当前用户叠加** `pinned` / `deep_dive_status` / `experiment_status`（后两者分别由该用户的 `deep-dives/{aid}.json` 与 `experiments/{aid}.json` 推导），匿名全为 false/none。文章滚动淘汰（上限 400）的「pinned 不淘汰」保护改为**按所有用户 pins.json 的并集**（`_all_pinned_ids()`）。

## 3. 认证流程

```mermaid
sequenceDiagram
  participant UI as 前端 auth.js
  participant API as /api/auth/*
  participant Store as users.json
  participant Cookie as 签名 cookie

  UI->>API: POST /register {email, password}
  API->>API: 限流 + 校验 + bcrypt 哈希
  API->>Store: 追加 UserRecord（仅 user，管理员已由服务器 CLI 初始化）
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

### 3.1b 邮箱验证（软提示，不阻断登录）

`UserRecord.email_verified`（默认 False，**服务器 CLI 初始化的 admin 为 True**，免得 SMTP 没配好就把自己锁外面）。流程：

- 注册非 admin 用户 → `_send_verification` 用 `itsdangerous` 签一个独立 salt（`aif-email-verify`，与 session token 隔离）的 token（24h），拼成 `<AIF_PUBLIC_BASE_URL>/api/auth/verify?token=…` 发邮件。
- 用户点链接 → `GET /verify` 校验 token → `mark_email_verified` → 302 跳 `/ui/?verify=ok|invalid`，前端弹 toast。
- 未验证用户**仍可登录使用**，只在顶栏显示「📧 未验证」按钮，点击 `POST /resend-verification` 重发。
- 发信走 `app/email.py`（纯 `smtplib`，零依赖）；SMTP 未配置时**优雅降级**（log warning，注册照常，不发信）。配置见 [config-reference](../reference/config-reference.md) 的 `AIF_SMTP_*` / `AIF_PUBLIC_BASE_URL`。

### 3.1c 修改密码 / 忘记密码找回

复用同一套发信 + 签名 token（三类 token 各用独立 salt：`aif-session` / `aif-email-verify` / `aif-pw-reset`，互不能冒用，有测试 `tests/test_email_verify.py`）。

- **改密码**（已登录）`POST /change-password`：校验旧密码 → 校验新密码 → `set_password` 换哈希 → 重发会话 cookie。
- **忘记密码**（未登录）`POST /forgot-password`：签 reset token（独立 salt，**1h** 过期，比验证的 24h 短）→ 邮件发 `<base>/ui/?reset=<token>`。**防枚举**：邮箱是否存在都返回相同 ok，且限流。
- **重置**（未登录）`POST /reset-password`：校验 token → 换哈希 → 自动登录（下发 cookie）。
- 前端：登录弹窗加「忘记密码？」；顶栏 🔑 改密码；落地 `?reset=<token>` 时弹「设置新密码」表单（`auth.js` 的 `openPwModal`）。
- 已知限制：签名 cookie 无法主动吊销，改密码只重发本会话 cookie，**其他设备的旧 session 仍有效至过期**（同第 13 条取舍）。

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
2. **注册时** `inherit_legacy_if_eligible(user)`：若该用户匹配 `AIF_ADMIN_EMAIL`（未配则本地初始化的 admin），把 `_legacy/` 改名成其 uid 目录继承。

约束：没人匹配 `AIF_ADMIN_EMAIL` 时 `_legacy/` 会一直「无主」留存（数据不丢）。不配 `AIF_ADMIN_EMAIL` 时由本地初始化的管理员继承；普通用户即使邮箱匹配也不继承。

## 6. 前端（`frontend/src/auth.js`）

- 启动 `GET /api/auth/me` 取登录态，渲染顶栏（`#auth-slot`）：未登录显示「登录/注册」，登录显示 email + 登出。
- 登录/注册弹窗（零构建，原生 DOM），不引框架。
- `api.js` 统一拦 401 → 弹登录弹窗（`setUnauthorizedHandler`）。
- 登录/登出后派发 `aif:auth-changed` 事件，`main.js` 据此重载视图；登出清 `localStorage` 的 `aif_conv_id` 避免会话串号。

## 7. 安全的首次初始化

公开 `/register` 永远只创建 user；没有管理员时返回 503 并要求部署者本地初始化。`AIF_ADMIN_EMAIL` 仅用于旧数据继承，不授予角色。已有管理员、密码和会话不受升级影响。

在部署者交互终端执行 `python -m app.bootstrap_admin --email you@example.com`。CLI 隐藏输入两次密码，复用邮箱/密码校验；不接受命令行密码，非 TTY 拒绝执行。首个管理员通过服务器受信路径创建并自动验证，已有管理员时拒绝覆盖。CLI 以 Unix 文件锁串行化多次初始化，用户文件修改仍使用 storage 事务；初始化后幂等迁移/继承旧数据。Linux/macOS 可裸机运行，Windows 使用 Docker 交互终端。新部署建议在开放服务前初始化；勿在额外进程并发修改已有生产用户库。

管理员初始化 CLI 支持 `--language en` 使用英文密码提示与结果信息，默认仍为中文；隐藏输入、仅交互终端、首次初始化及已有管理员保护不变。英文 README 的 Docker 与裸机示例均使用此选项。
