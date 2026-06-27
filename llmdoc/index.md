# AI Frontier Agent — 文档索引

个人 AI 前沿信息站：FastAPI 单应用，定时从 ~79 个精选 RSS 源抓取 AI 资讯，自动中英翻译 + 每日速报 + 按需深度解读，外加一个 sparrow 驱动的对话式 ReAct agent。零数据库（状态全在文件），零构建前端，单进程一体化。

---

## 快速导航

| 如果你需要... | 从这里开始 |
|---|---|
| 了解项目概况、技术栈、目录结构、核心机制 | [项目概览](overview/project-overview.md) |
| **★ 第一次接手，先读这篇** | [项目概览](overview/project-overview.md) ＋ [后端架构](architecture/backend-architecture.md) |
| 本地把项目跑起来（裸机 / Docker） | [运行指南](guides/how-to-run.md) |
| 部署到生产（Coolify + 自建 rsshub） | [部署指南](guides/how-to-deploy.md) |
| 理解整个后端的进程模型 / 启动流程 / 模块依赖 | [后端架构](architecture/backend-architecture.md) |
| 理解「一篇文章从 RSS 到入库到翻译」怎么发生 | [RSS 抓取管线架构](architecture/rss-pipeline-architecture.md) |
| 为什么用「每源配额 + 全局回填」而不是全局 top-N | [RSS 抓取管线架构](architecture/rss-pipeline-architecture.md)（第 2.5 节） |
| 理解对话 agent（sparrow ReAct）怎么工作 / 加工具 | [Agent 架构](architecture/agent-architecture.md) |
| agent 能调哪些工具 | [Agent 架构](architecture/agent-architecture.md)（第 3 节） |
| 改前端 / 理解 ES module 结构 / 视图切换 | [前端架构](architecture/frontend-architecture.md) |
| 深度解读为什么是独立内容库 / 跟文章流怎么解耦 | [前端架构](architecture/frontend-architecture.md)（第 2/4 节）＋ [数据存储参考](reference/data-storage.md)（3.3）＋ [API 参考](reference/api-reference.md)（第 3 节） |
| 为什么不能手动改 `static/js/sparrow-chat.js` | [前端架构](architecture/frontend-architecture.md)（第 5 节） |
| 查全部 HTTP 端点 / 新增一个端点 | [API 参考](reference/api-reference.md) |
| 用户注册登录 / 鉴权守卫 / 会话怎么做 | [认证架构](architecture/auth-architecture.md) |
| 数据怎么按用户隔离 / pin 为什么迁出文章 / 老数据迁移 | [认证架构](architecture/auth-architecture.md)（第 2/5 节）＋ [数据存储参考](reference/data-storage.md) |
| 为什么有两个 `/chat` 端点 | [后端架构](architecture/backend-architecture.md)（第 6 节）＋ [已知问题](reference/known-issues.md)（第 2 条） |
| 查环境变量 / 配置项 / 容量常量 | [配置参考](reference/config-reference.md) |
| 改抓取容量（多留文章 / 多抓几篇 / 加 RSS 源） | [配置参考](reference/config-reference.md)（代码内常量 + 修改约定） |
| 数据存哪 / 各 JSON 文件结构 / Article 字段 | [数据存储参考](reference/data-storage.md) |
| 为什么没有数据库 / 原子写怎么保证并发安全 | [数据存储参考](reference/data-storage.md)（第 4 节）＋ [后端架构](architecture/backend-architecture.md)（第 4 节） |
| 大量数据源抓取失败怎么排查 | [部署指南](guides/how-to-deploy.md)（第 7 节）＋ [已知问题](reference/known-issues.md)（第 4 条） |
| 所有 LLM 功能报 503 | [运行指南](guides/how-to-run.md)（排障）＋ [配置参考](reference/config-reference.md) |
| 代码里的 zyb / zhangyangbin 残留是什么 | [已知问题](reference/known-issues.md)（第 7 条） |
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
| [前端架构](architecture/frontend-architecture.md) | 零构建 ES module、视图/状态、关键交互、sparrow-chat 组件来源 |

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

---

## 文档维护约定

- 新增/改 HTTP 端点 → 更新 [api-reference.md](reference/api-reference.md)
- 新增/改环境变量 → 更新 [config-reference.md](reference/config-reference.md) + `.env.example`
- 改抓取/翻译管线逻辑 → 更新 [rss-pipeline-architecture.md](architecture/rss-pipeline-architecture.md)
- 新增/改 agent 工具 → 更新 [agent-architecture.md](architecture/agent-architecture.md) 第 3 节
- 新增数据文件或改 Article 字段 → 更新 [data-storage.md](reference/data-storage.md)
- 改鉴权 / 守卫 / 会话 / 用户隔离 → 更新 [auth-architecture.md](architecture/auth-architecture.md)
- 发现新坑 → 记入 [known-issues.md](reference/known-issues.md)
- **以上任何更新，同时在本文件「快速导航」补一行入口。** 是否更新文档由用户决定，完成代码改动后先问再改。
