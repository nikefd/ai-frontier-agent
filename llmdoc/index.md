# AI Frontier Agent — 文档索引

个人 AI 前沿信息站：FastAPI 单应用，定时从 116 个分层 RSS、官方 sitemap/API/changelog/官网更新页抓取 AI 资讯，经相关性过滤、跨源去重、分类配额和质量排序后生成双语文章流与每日速报，外加按需深度解读、结构化实验卡和 ReAct agent。来源同时覆盖官方发布、独立基准、安全评测、具身智能、模型 API 可用性与开源工程；论文侧以 Hugging Face Daily Papers 策展信号为主、arXiv 长尾发现为辅。文件型主存储、Vite 构建前端、单进程一体化。

---

## 快速导航

2026-11-12：运行拆解、模型与 Agent 学习库、上下文解剖台已移除；[真实 Agent 可视化实验台提案](../docs/live-agent-lab-plan.md) 尚未实现。


| 如果你需要... | 从这里开始 |
|---|---|
| 了解项目概况、技术栈、目录结构、核心机制 | [项目概览](overview/project-overview.md) |
| **★ 第一次接手，先读这篇** | [项目概览](overview/project-overview.md) ＋ [后端架构](architecture/backend-architecture.md) |
| 本地把项目跑起来（裸机 / Docker） | [运行指南](guides/how-to-run.md) |
| 理解或修改 PR/main 的正式 CI 质量门禁 | [运行指南](guides/how-to-run.md)（测试与 CI）＋ `.github/workflows/ci.yml` |
| 只读生产验收、独立官方样本与基准发现方式 | [生产验收指南](guides/production-audit.md) ＋ `evaluation/` |
| 数据卷备份、校验、隔离恢复演练与环境配置边界 | [备份恢复指南](guides/backup-and-restore.md) ＋ `app/backup.py` |
| 部署到生产（Coolify + 自建 rsshub） | [部署指南](guides/how-to-deploy.md) |
| 理解整个后端的进程模型 / 启动流程 / 无前端产物启动 / 模块依赖 | [后端架构](architecture/backend-architecture.md) |
| 理解「一篇文章从 RSS 到入库到翻译」怎么发生 | [RSS 抓取管线架构](architecture/rss-pipeline-architecture.md) |
| 理解信源分层、分类硬配额、每源轮次和 150 条全局上限 | [RSS 抓取管线架构](architecture/rss-pipeline-architecture.md)（第 2.2-2.5 节） |
| 理解官方 sitemap/API/changelog/GitHub Releases、页面元数据补全、跨源 URL 去重与速报事件聚类 | [RSS 抓取管线架构](architecture/rss-pipeline-architecture.md)（第 2.2/2.5/2.7/3/4 节） |
| 理解发布时间可信规则、sitemap `lastmod` 为何不能当发布时间、无日期条目为何不入库、历史错误日期如何修复 | [RSS 抓取管线架构](architecture/rss-pipeline-architecture.md)（第 2.5-2.7/4 节）＋ [数据存储参考](reference/data-storage.md)（3.1）＋ [已知问题](reference/known-issues.md)（第 18/24 条） |
| 理解重要论文雷达、HF 策展信号、arXiv 限流与论文去重 | [RSS 抓取管线架构](architecture/rss-pipeline-architecture.md)（第 2.2/2.5/2.7 节） |
| 理解今日速报为什么不会被 Trending/X 淹没 | [RSS 抓取管线架构](architecture/rss-pipeline-architecture.md)（第 4 节）＋ [API 参考](reference/api-reference.md)（第 4 节） |
| 理解全天分时抓取 / 速报刷新 / 未变化跳过 LLM | [RSS 抓取管线架构](architecture/rss-pipeline-architecture.md)（第 2.1/4 节）＋ [配置参考](reference/config-reference.md) |
| 理解分层刷新 / “刚刚发生”重大提醒 / 各层健康阈值 | [RSS 抓取管线架构](architecture/rss-pipeline-architecture.md)（第 2.1/2.2/2.5/4 节）＋ [API 参考](reference/api-reference.md)（第 4/7 节） |
| 基准命中留存、淘汰保护、规则失效与入库时间依据 | [数据存储参考](reference/data-storage.md#32a-coverage-benchmarksjson必达事件基准) ＋ `app/benchmark_evidence.py` |
| 修改基准的 URL/事件键/关键词确定性匹配 | [后端架构](architecture/backend-architecture.md) ＋ `app/benchmark_matching.py` |
| 检查来源覆盖 / 噪声率 / 价值评分 / 必达候选 / 绝对召回 / 漏报根因诊断、未接入来源发现、RSS/Sitemap/更新页半自动接入与自定义源停用/删除、JS 官网专用适配、单源复测和处理闭环 / 高影响事件漏出 / 富化积压 / 发现延迟 | [RSS 抓取管线架构](architecture/rss-pipeline-architecture.md)（第 2.2/2.5/5 节）＋ [API 参考](reference/api-reference.md)（第 7 节）＋ [数据存储参考](reference/data-storage.md)（2.1/3.2b）＋ `app/quality_report.py` / `app/source_discovery.py` / `app/source_adapter_validation.py` / `app/source_activation.py` / `app/auto_listing.py` / `app/official_page_adapters.py` / `app/source_management.py` / `app/custom_sources.py` |
| 找出可实践内容 / 理解实践建议怎么生成 / “带我做”如何接 AI | [RSS 抓取管线架构](architecture/rss-pipeline-architecture.md)（第 3/4 节）＋ [前端架构](architecture/frontend-architecture.md)（第 3/4 节）＋ [数据存储参考](reference/data-storage.md)（3.1） |
| 结构化实验卡怎么生成 / 外链如何防幻觉 / 进度笔记存哪 | [API 参考](reference/api-reference.md)（第 4e 节）＋ [数据存储参考](reference/data-storage.md)（3.11）＋ `app/routers/experiments.py` |
| 理解对话 agent（sparrow ReAct）怎么工作 / 加工具 | [Agent 架构](architecture/agent-architecture.md) |
| agent 能调哪些工具 | [Agent 架构](architecture/agent-architecture.md)（第 3 节） |
| 准备中英文社区介绍、Show HN 短帖和演示提纲 | [宣传文案包](../docs/launch-kit.md) |
| 中英文 README、语言切换、界面消息目录与双语速报 | [前端架构](architecture/frontend-architecture.md#7-中英文界面与内容边界) ＋ `app/locale.py` ＋ `app/briefing_languages.py` |
| 排查深链接先闪首页、站内学习链接整页刷新和 session 加载时序 | [前端架构](architecture/frontend-architecture.md#8-学习实验模块已移除2026-11-12) ＋ `frontend/src/route-links.js` / `frontend/public/route-shell.js` |
| 改前端 / 理解 ES module 结构 / 视图切换 / Vite 构建 | [前端架构](architecture/frontend-architecture.md) |
| 理解阅读优先的信息架构 / 首页入口 / 导航分层 / 文章卡片操作 | [前端架构](architecture/frontend-architecture.md)（第 1.2/3/4 节） |
| 搜索筛选链接分享、刷新与语言切换后恢复条件 | [前端架构](architecture/frontend-architecture.md)（第 3 节）＋ `frontend/src/feed-route.js` |
| 排查文章分页 / 活动筛选标签 / `<details>` 弹层收起行为 | [前端架构](architecture/frontend-architecture.md)（第 3/4 节）＋ `frontend/src/state.js` / `main.js` / `feed.js` |
| 理解今日速报的引用链接 / “更多动态”折叠 / 移动端版式 | [前端架构](architecture/frontend-architecture.md)（第 4 节）＋ [API 参考](reference/api-reference.md)（第 4 节） |
| 订阅今日速报 RSS / 理解速报历史与缓存 | [API 参考](reference/api-reference.md)（RSS 订阅）＋ [数据存储参考](reference/data-storage.md)（3.5）＋ `app/routers/rss.py` |
| 深度解读为什么是独立内容库 / 跟文章流怎么解耦 | [前端架构](architecture/frontend-architecture.md)（第 2/4 节）＋ [数据存储参考](reference/data-storage.md)（3.3）＋ [API 参考](reference/api-reference.md)（第 3 节） |
| 个人画像怎么来 / 聚合了哪些信号 / 存哪 | [API 参考](reference/api-reference.md)（第 3b 节）＋ [数据存储参考](reference/data-storage.md)（3.7） |
| 「为你推荐」怎么排序 / 为什么不花 LLM | [API 参考](reference/api-reference.md)（第 4 节 `/for-you`）＋ `app/routers/feed_personal.py` |
| 知识卡 / 间隔重复 / SM-2 怎么调度 | [API 参考](reference/api-reference.md)（第 4b 节）＋ [数据存储参考](reference/data-storage.md)（3.8）＋ `app/srs.py` |
| AI 复盘教练 / 苏格拉底问题 / 怎么接对话 | [API 参考](reference/api-reference.md)（第 4c 节）＋ [数据存储参考](reference/data-storage.md)（3.9）＋ `app/routers/reflection.py` |
| 学习路径 / 和 guides 的区别 / 分阶段编排 | [API 参考](reference/api-reference.md)（第 6b 节）＋ [数据存储参考](reference/data-storage.md)（3.10）＋ `app/routers/learning.py` |
| agent 主动建议怎么触发 / 规则 | [API 参考](reference/api-reference.md)（第 4d 节）＋ `app/routers/suggestions.py` |
| PR 自动审查机器人怎么工作 / 改审查规范 | `.github/workflows/pr-review.yml`（触发）＋ `scripts/pr_review.py`（执行）＋ `.claude/skills/pr-review/SKILL.md`（**规范单一来源，改这里**） |
| 如何修改 sparrow-chat.js / 安全渲染如何接入 | [前端架构](architecture/frontend-architecture.md)（第 5/6 节） |
| 查全部 HTTP 端点 / 新增一个端点 | [API 参考](reference/api-reference.md) |
| 新实例安全初始化管理员、注册 503 与旧数据继承 | [认证架构](architecture/auth-architecture.md#7-安全的首次初始化) ＋ `app/bootstrap_admin.py` |
| 用户注册登录 / 鉴权守卫 / 会话怎么做 | [认证架构](architecture/auth-architecture.md) |
| 邮箱验证 / SMTP 怎么配 / 重发链接 | [认证架构](architecture/auth-architecture.md)（3.1b）＋ [配置参考](reference/config-reference.md)（`AIF_SMTP_*`）＋ `app/email.py` |
| 修改密码 / 忘记密码找回 / 重置 token | [认证架构](architecture/auth-architecture.md)（3.1c）＋ [API 参考](reference/api-reference.md)（0 节 change/forgot/reset） |
| admin 用户管理 / admin 守卫 / 护栏 | [认证架构](architecture/auth-architecture.md)（第 1 节）＋ [API 参考](reference/api-reference.md)（0b 节）＋ `app/routers/admin.py` |
| XSS / Markdown / Mermaid / CSP 安全边界 | [前端架构](architecture/frontend-architecture.md)（第 4/6 节）＋ [后端架构](architecture/backend-architecture.md)（第 2/4b 节） |
| reader SSRF 防护与安全 HTML 缓存 | [后端架构](architecture/backend-architecture.md)（第 4b 节）＋ [API 参考](reference/api-reference.md)（reader） |
| 数据怎么按用户隔离 / pin 为什么迁出文章 / 老数据迁移 | [认证架构](architecture/auth-architecture.md)（第 2/5 节）＋ [数据存储参考](reference/data-storage.md) |
| 为什么有两个 `/chat` 端点 | [后端架构](architecture/backend-architecture.md)（第 6 节）＋ [已知问题](reference/known-issues.md)（第 2 条） |
| 查环境变量 / 配置项 / 容量常量 | [配置参考](reference/config-reference.md) |
| 改抓取容量（多留文章 / 多抓几篇 / 加 RSS 源） | [配置参考](reference/config-reference.md)（代码内常量 + 修改约定） |
| 数据存哪 / 各 JSON 文件结构 / Article 字段 | [数据存储参考](reference/data-storage.md) |
| 为什么没有数据库 / 原子读改写怎么避免丢更新 | [数据存储参考](reference/data-storage.md)（第 4 节）＋ [后端架构](architecture/backend-architecture.md)（第 4 节） |
| Gemini 更新日志 HTML → AI Studio Markdown 迁移与重定向链接 | [RSS 抓取管线架构](architecture/rss-pipeline-architecture.md)（第 2.5 节）＋ `app/gemini_release_notes.py` |
| xAI 官网生产 403、官方 API 更新日志与时间线年份推导 | [RSS 抓取管线架构](architecture/rss-pipeline-architecture.md#xai-官方模型api-更新) ＋ `app/xai_release_notes.py` |
| arXiv 合法空日更、分类/构建时间校验与官方 RSS 主机 | [RSS 抓取管线架构](architecture/rss-pipeline-architecture.md#arxiv-的合法空日更) ＋ `app/feed_validation.py` |
| 大量数据源抓取失败怎么排查 | [部署指南](guides/how-to-deploy.md)（第 7 节）＋ [已知问题](reference/known-issues.md)（第 4 条） |
| 理解单源连续失败 / 调度过期 / 来源最新内容与疑似停更状态 | [RSS 抓取管线架构](architecture/rss-pipeline-architecture.md)（第 2.5/2.7 节）＋ [数据存储参考](reference/data-storage.md)（3.2） |
| 所有 LLM 功能报 503 | [运行指南](guides/how-to-run.md)（排障）＋ [配置参考](reference/config-reference.md) |
| 查历史命名、开源发布与验收状态 | [已知问题](reference/known-issues.md)（第 7 条）＋ [开源准备清单](reference/open-source-readiness.md) |
| 准备公开仓库 / 选择许可证 / 做发布前审计 | [开源准备清单](reference/open-source-readiness.md) |
| 坑 / 历史遗留 / 安全注意面 | [已知问题](reference/known-issues.md) |

---

## 概述

| 文档 | 描述 |
|---|---|
| [项目概览](overview/project-overview.md) | 定位、出身、技术栈、外部服务、目录结构、核心机制速览 |

## 架构

| 文档 | 描述 |
|---|---|
| [后端架构](architecture/backend-architecture.md) | 单进程一体化模型、启动流程、模块职责与依赖方向、存储层、LLM 客户端、两套 chat 端点 |
| [RSS 抓取管线架构](architecture/rss-pipeline-architecture.md) | 抓取→打标→每源配额→全局回填→入库→翻译，端到端数据流与设计理由 |
| [Agent 架构](architecture/agent-architecture.md) | sparrow ReAct agent：工具注入、对话记忆（ui.db）、SSE 事件、system prompt 铁律 |
| [认证架构](architecture/auth-architecture.md) | 多用户鉴权：权限模型、用户存储、bcrypt 哈希、签名 cookie 会话、守卫、数据按用户隔离、老数据迁移 |
| [前端架构](architecture/frontend-architecture.md) | Vite 构建 + 内容指纹、零框架 ES module、视图/状态、关键交互、sparrow-chat 组件来源 |

## 指南

| 文档 | 描述 |
|---|---|
| [运行指南](guides/how-to-run.md) | 裸机 / Docker 两种跑法、数据目录、常用操作、测试、排障 |
| [部署指南](guides/how-to-deploy.md) | Coolify 拓扑、为什么自建 rsshub、环境变量、命名卷持久化、排障 |

## 参考

| 文档 | 描述 |
|---|---|
| [API 参考](reference/api-reference.md) | 全部 HTTP 端点速查（系统/文章/解读/速报/track/指南/源/agent） |
| [配置参考](reference/config-reference.md) | `AIF_` 环境变量、相关非前缀变量、代码内容量常量、修改约定 |
| [数据存储参考](reference/data-storage.md) | 文件清单、Article/sources/deep-dive 等数据结构、ui.db、原子写 |
| [已知问题](reference/known-issues.md) | CORS、双 chat 端点、翻译不重试、rsshub 依赖、命名遗留、空目录等 |
| [开源准备清单](reference/open-source-readiness.md) | 当前完成项、公开前 P0、许可证取舍与发布步骤 |

---

## 文档维护约定

- 新增/改 HTTP 端点 → 更新 [api-reference.md](reference/api-reference.md)
- 新增/改环境变量 → 更新 [config-reference.md](reference/config-reference.md) + `.env.example`
- 改抓取/翻译管线逻辑 → 更新 [rss-pipeline-architecture.md](architecture/rss-pipeline-architecture.md)
- 新增/改 agent 工具 → 更新 [agent-architecture.md](architecture/agent-architecture.md) 第 3 节
- 新增数据文件或改 Article 字段 → 更新 [data-storage.md](reference/data-storage.md)
- 改鉴权 / 守卫 / 会话 / 用户隔离 → 更新 [auth-architecture.md](architecture/auth-architecture.md)
- 发现新坑 → 记入 [known-issues.md](reference/known-issues.md)
- **以上任何更新，同时在本文件「快速导航」补一行入口。** 当前项目约定：代码改动验证通过后默认同步文档、提交并推送，不再单独确认；破坏性操作、敏感配置或产品取舍仍需先确认。
