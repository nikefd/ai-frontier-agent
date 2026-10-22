# 开源准备清单

> 状态日期：2026-10-22。当前仓库仍为私有；本页用于在切换可见性前收口风险。

## 已完成

- 当前树的 `.env.example`、项目描述与文档示例已去除个人邮箱、生产域名和旧项目名称。
- 生产密钥、认证数据与用户目录均通过环境变量/数据卷注入，并已由 `.gitignore` 排除。
- 对全部 Git patch 历史约 2.4 MB 做了高置信模式扫描：私钥、GitHub PAT、OpenAI 风格 key、AWS access key、Google API key、Slack token 均为 0 命中。这是启发式基线，不替代正式的 Gitleaks/TruffleHog 扫描。
- 内联 `agent_runtime` 与 `sparrow-chat.js` 由项目作者自研；仓库选择许可证后可随项目统一授权，不存在待追溯的未知代码来源。
- 已补 `CONTRIBUTING.md` 与 `SECURITY.md`；正式公开后应启用 GitHub Private vulnerability reporting。
- 仓库种子数据已收敛为中性空数据与默认追踪主题，不再分发抓取文章、LLM 速报、深度解读或指南样例。

## 公开前 P0

1. **选择许可证并添加 `LICENSE`**：若希望托管服务修改也必须公开，选 AGPL-3.0；若优先生态传播和企业采用，选 Apache-2.0。
2. **修复首个管理员抢注**：当前空实例的第一个注册账号自动成为 admin。公开部署文档不能假设管理员一定先访问；应增加一次性 bootstrap secret、CLI 初始化或“验证指定邮箱后晋升 admin”的流程。
3. **运行专业历史扫描**：用 Gitleaks/TruffleHog 对所有分支、tag 和 dangling history 再扫一次。当前历史仍包含已删除的个人邮箱/域名示例；这不是密钥，但若希望完全匿名，需要在公开前单独批准并执行历史重写。
4. **确认发布边界**：代码仓库公开不等于生产数据公开。`<data_dir>`、Coolify 配置、SMTP、LLM key、Twitter cookie 和用户数据必须继续保持私有。

## 推荐发布步骤

1. 完成 P0 管理员 bootstrap 与测试。
2. 确认 AGPL-3.0 或 Apache-2.0，添加 `LICENSE` 与 README 徽标。
3. 跑完整测试、前端审计、Docker 构建和专业 secret scan。
4. 检查 GitHub Actions、Issue/PR 模板和安全报告入口，不把生产 secrets 暴露给 fork PR。
5. 创建首个版本 tag，再把仓库从 private 切换为 public；生产实例和数据卷不做可见性变更。

## 非阻塞后续

- 提供一键部署模板和最小公开演示站。
- 将信源适配器拆成更易贡献的模块，并为新增源提供 fixture 测试模板。
- 增加来源许可/robots/转载边界说明；本站只发布自己的摘要与指向原文的链接，不镜像来源全文。
