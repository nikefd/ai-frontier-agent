"""sparrow — a small-but-complete agent harness.

麻雀虽小，五脏俱全 / Small bird, all the organs.

Bring your own tools and a system prompt; sparrow wires them into a ReAct loop
with citations, three-tier memory (conversations / panels / journal), and a
restricted-expression engine for safe computed columns.

    from sparrow import tool, AgentConfig, Harness

    @tool(description="Echo back", source="demo")
    def echo(text: str) -> dict:
        return {"text": text}

    cfg = AgentConfig(system_prompt="You are a helpful assistant.", tools=[echo])
    for event in Harness(cfg).run([{"role": "user", "content": "hi"}]):
        print(event)
"""
from .registry import AgentConfig, Tool, ToolRegistry, tool
from .harness import Harness
from .memory import Memory
from .llm import chat, configure, LLMError
from . import panel_data
from .expr import safe_eval, is_safe_expr

__version__ = "0.2.0"

__all__ = [
    "AgentConfig", "Tool", "ToolRegistry", "tool",
    "Harness", "Memory",
    "chat", "configure", "LLMError",
    "panel_data", "safe_eval", "is_safe_expr",
    "panel_tools",
]


def panel_tools(memory):
    """Return the standard panel-management tools (create / archive / list) bound
    to a :class:`~sparrow.memory.Memory`. Add them to your AgentConfig.tools to
    give the agent "panel as memory" capabilities.
    """
    from .registry import tool as _tool

    @_tool(name="create_panel", writes=True, source="ui.db: panels",
           description="Persist a conversation insight as a dashboard panel. "
                       "Only call after the user explicitly agrees.")
    def create_panel(spec: dict = None, conversation_id: str = "") -> dict:
        import json as _json
        if isinstance(spec, str):
            try:
                spec = _json.loads(spec)
            except (ValueError, TypeError):
                return {"error": "spec must be an object"}
        return memory.create_panel(spec, conversation_id=conversation_id)

    @_tool(name="archive_panel", writes=True, source="ui.db: panels",
           description="Archive a panel (reversible). Requires user confirmation.")
    def archive_panel(id: str = "", conversation_id: str = "") -> dict:
        return memory.archive_panel(id)

    @_tool(name="list_panels", source="ui.db: panels",
           description="List current dashboard panels.")
    def list_panels(include_archived: bool = False) -> dict:
        allp = memory.list_panels(include_archived=include_archived)
        custom = [p for p in allp if p.get("kind") != "builtin"]
        builtin = [p for p in allp if p.get("kind") == "builtin"]
        return {
            "custom_panels": [{"id": p["id"], "title": p["title"], "viz": p["viz"],
                               "status": p["status"], "note": p.get("note", "")} for p in custom],
            "builtin_panels": [{"title": p["title"], "tab": p.get("tab", "")} for p in builtin],
            "summary": f"{len(custom)} custom + {len(builtin)} builtin panels",
        }

    return [create_panel, archive_panel, list_panels]
