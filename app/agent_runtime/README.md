# agent_runtime

这个项目的对话 agent 运行时：ReAct 工具循环（`Harness`）、三层记忆（对话 /
panel / journal，`Memory`，SQLite）、工具注册（`@tool` / `ToolRegistry`）、受限
表达式引擎（`expr`）、LLM 客户端（`llm`）。

## 来源

内联自自研的 `sparrow` 框架（原作为独立 PyPI 包 `sparrow-agent`，本项目作者所
写）。2026-06 内联进仓库，原因：

- 本项目是这套代码的唯一使用方，独立打包带来的「改包→发版→升级」流程纯属负担；
- 消除 `sparrow-chat.js` 启动时从包同步的机制（曾是缓存/同步问题来源）；
- agent 运行时是产品核心资产，集中在仓库里更利于快速迭代。

**后续会按本项目需要逐步改造**（可能改 ReAct 范式、换存储、多 agent 等），不再与
上游 sparrow 保持对应。包内代码仍有 `sparrow` 字样的注释/文档，属内联时原样保留，
改造时顺手清理。

## 使用方

- `app/agent_chat.py` — `/api/agent/chat` 端点，用 `Harness` + `Memory`。
- `app/agent_tools.py` — 用 `@tool` 声明按用户绑定的工具。
- 前端组件 `sparrow-chat.js` 在 `frontend/public/`，由 Vite 构建输出到
  `/ui/sparrow-chat.js`。

零第三方依赖（仅标准库）。
