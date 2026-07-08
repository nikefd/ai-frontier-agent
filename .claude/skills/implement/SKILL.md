---
name: implement
description: 根据 Issue 的讨论和方案, 实现功能或修复 Bug, 并创建 PR。
---

# implement

用户确认后 (如 "ok", "/impl")，根据 Issue 实现代码并创建 PR。

> 遵循 `github-comment` 规范。

## 代码质量底线

**必须遵守**：
- 不引入安全漏洞 (SQL 注入、XSS、命令注入等)
- 遵循项目现有代码风格
- 不破坏现有功能（可通过现有测试）

**避免**：
- 过度工程化
- 添加未要求的功能
- 不必要的重构

## 特殊规则

- 分支命名：功能 `feat/{short-description}`、修复 `fix/{short-description}`
- commit message 遵循项目约定（`<scope>: <中文描述>`，scope 用英文小写）
- PR body 必须包含 `Closes #${issue_number}`
- 涉及代码改动后，检查 llmdoc/ 是否需要同步更新

## 模板

```markdown
## ✨ 实现完成 #${issue_number}

| 项目 | 结果 |
|------|------|
| **状态** | ✅ 成功 / ❌ 失败 / ⏸️ 阻塞 |
| **PR** | #{pr_number} |

<details>
<summary><h3>📝 变更摘要</h3></summary>

**分支**: `{branch_name}`

**修改文件**:
- `path/to/file1` - {改动说明}
- `path/to/file2` - {改动说明}

**实现说明**: {简述实现方式}

</details>
```

失败/阻塞时：
```markdown
## ⚠️ 实现尝试 #${issue_number}

| 项目 | 结果 |
|------|------|
| **状态** | ❌ 失败 / ⏸️ 阻塞 |
| **原因** | {说明} |

<details>
<summary><h3>📋 已完成的工作</h3></summary>

{如有部分进展，列出}

</details>
```
