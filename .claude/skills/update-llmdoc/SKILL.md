---
name: update-llmdoc
description: >
  定时自动维护 llmdoc 项目文档的 Skill。由 GitHub Actions schedule 触发（也支持
  workflow_dispatch 手动触发），收集指定时间范围内（默认过去 24 小时）合并到目标分支的
  提交记录和 PR 内容，分析代码变更是否涉及功能新增、接口变更或架构调整，如果需要则自动
  更新 llmdoc/ 下的对应文档并创建 PR。不改变外部行为的变更（bug 修复、重构、依赖升级等）
  会被跳过。更新完成后输出结构化 JSON 结果。
---

# update-llmdoc

根据目标分支最近的代码变更，自动更新 llmdoc 文档。单仓库模式。

## 概览

- **作用**: 保持 `llmdoc/` 项目文档与代码实现同步，减少人工维护成本
- **触发方式**: GitHub Actions `schedule`（每天定时）或 `workflow_dispatch` 手动触发
- **时间窗口**: 默认检查过去 24 小时内的提交，手动触发时可自定义 `since_period` 参数
- **输出**: 结构化 JSON（包含 `description`、`total_files_updated`、`pr_url`）

## 执行流程

### 1. 收集变更

```bash
git fetch origin {target_branch}
git log --since="{since_period}" origin/{target_branch} --oneline
```

> `{target_branch}` 从 prompt 中获取，默认为 `main`。

### 2. 分析变更

1. **读取提交记录**: `git log --since="{since_period}" origin/{target_branch} --pretty=format:"- %h %s (%an)"`
2. **读取合并 PR 信息**: `git log --since="{since_period}" origin/{target_branch} --merges --pretty=format:"%s"`
3. **读取变更统计**: `git diff {first_commit}^..{last_commit} --stat`
4. **读取代码 diff**: `git diff {first_commit}^..{last_commit}`（关注核心逻辑变更）
5. **读取当前 llmdoc**: 阅读 `llmdoc/index.md` 和所有相关文档

### 3. 判断是否需要更新

以下变更**需要更新文档**：
- 新增功能或模块
- 修改现有功能的行为或接口
- API 变更（新增/修改/删除端点）
- 架构调整
- 重要的配置变更

以下变更**不需要更新文档**：
- 纯 bug 修复（不改变接口或行为）
- 代码重构（不改变外部行为）
- 依赖版本升级
- 测试代码变更
- CI/CD 配置变更
- 注释或日志修改

### 4. 更新文档

- **只更新确实受影响的文档**，不做不必要的修改
- 保持与现有文档一致的风格和结构（中文）
- 新功能 → 在对应 architecture/ 或 guides/ 文档中添加说明
- 行为变更 → 更新对应文档的描述
- 重大变更 → 更新 index.md 导航

### 5. 提交推送并创建 PR

目标分支通常有分支保护，**必须创建新分支并提 PR**，不能直接推送到目标分支。

分支命名规则：`docs/auto-update-llmdoc-{MMDD}-{HHmm}`（月日时分，避免同一天多次运行时分支名冲突）。

```bash
BRANCH="docs/auto-update-llmdoc-$(date +%m%d-%H%M)"
git checkout -b $BRANCH origin/{target_branch}
git add llmdoc/
git commit -m "docs: 自动更新 llmdoc 文档

基于过去 {since_period} {target_branch} 分支的代码变更自动生成
Auto-updated by GitHub Actions"
git push origin $BRANCH
# 创建 PR（gh 工具，GITHUB_TOKEN 已注入）
gh pr create --title "docs: 自动更新 llmdoc 文档 $(date +%Y-%m-%d)" \
  --body "基于过去 {since_period} \`{target_branch}\` 分支的代码变更自动生成。" \
  --base {target_branch} --head $BRANCH
```

> `gh pr create` 输出的 PR URL 需要记录下来，放入最终输出的 `pr_url` 字段。

### 6. 输出报告

用 `echo` 输出处理结果（不需要发 GitHub 评论）。

## 特殊规则

- **无 llmdoc 跳过**: 如果仓库没有 `llmdoc/` 目录，跳过
- **无变更跳过**: 如果无提交或变更不需要更新文档，跳过
- **diff 过大截断**: 如果 diff 超过 500 行，聚焦于 `--stat` 和提交信息来理解变更
- **保守更新**: 宁可少更新，也不要错误更新。不确定时不更新
- **必须创建 PR**: 更新文档后必须推送新分支并执行 `gh pr create`，不得直接推送到目标分支
- **PR URL 输出**: 将 `gh pr create` 返回的 PR URL 记录到 `pr_url` 字段
