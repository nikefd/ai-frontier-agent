"""Tool registry and agent configuration — the injection surface of sparrow.

The engine makes *no* assumptions about your domain. You bring your own tools
(plain functions) and a config; the harness wires them into a ReAct loop.

Define a tool with the ``@tool`` decorator::

    from sparrow import tool

    @tool(description="Query latest articles", source="articles.db", label="search")
    def query_articles(track: str = "", limit: int = 10) -> dict:
        rows = ...                       # your implementation
        return {"articles": rows, "source": "articles.db"}

Every tool returns a dict; including a ``source`` key lets the harness collect
citations automatically. Mark state-changing tools with ``writes=True`` so the
harness journals them.

Then assemble a config and run::

    from sparrow import AgentConfig, Harness

    cfg = AgentConfig(system_prompt="You are ...", tools=[query_articles])
    for event in Harness(cfg).run(messages):
        ...
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# Python type -> JSON Schema type
_JSON_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean",
               list: "array", dict: "object"}


@dataclass
class Tool:
    """A registered tool: a callable plus the metadata the LLM/harness need."""
    name: str
    fn: Callable[[dict], Any]
    description: str
    schema: dict
    label: str = ""           # short human label for UI ("search", "查持仓"...)
    source: str = ""          # default citation source if the fn omits one
    writes: bool = False      # True => state-changing => journaled by the harness

    def __call__(self, args: dict) -> Any:
        return self.fn(args or {})


def _build_schema(fn: Callable, explicit: Optional[dict]) -> dict:
    """Derive a JSON Schema for a function's params, unless one is given."""
    if explicit is not None:
        return explicit
    props, required = {}, []
    sig = inspect.signature(fn)
    for pname, p in sig.parameters.items():
        if pname in ("self", "args", "_args"):
            continue
        ann = p.annotation
        jtype = _JSON_TYPES.get(ann, "string")
        props[pname] = {"type": jtype}
        if p.default is inspect.Parameter.empty:
            required.append(pname)
    schema: dict = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return schema


def tool(_fn=None, *, name: str = "", description: str = "", schema: dict = None,
         label: str = "", source: str = "", writes: bool = False):
    """Decorator that turns a function into a :class:`Tool`.

    The function may take either keyword params (introspected into a schema) or a
    single ``args`` dict. Either way the harness calls it as ``fn(args_dict)``.
    """
    def wrap(fn: Callable) -> Tool:
        sig = inspect.signature(fn)
        takes_args_dict = list(sig.parameters) == ["args"] or list(sig.parameters) == ["_args"]

        def adapter(args: dict):
            if takes_args_dict:
                return fn(args)
            # filter to known params so unexpected keys don't crash the call
            valid = {k: v for k, v in (args or {}).items() if k in sig.parameters}
            return fn(**valid)

        return Tool(
            name=name or fn.__name__,
            fn=adapter,
            description=description or (fn.__doc__ or "").strip().split("\n")[0],
            schema=_build_schema(fn, schema if takes_args_dict else schema),
            label=label,
            source=source,
            writes=writes,
        )
    return wrap(_fn) if callable(_fn) else wrap


class ToolRegistry:
    """Holds the tools available to one agent and renders OpenAI tool specs."""

    def __init__(self, tools: list[Tool] = None):
        self._tools: dict[str, Tool] = {}
        for t in tools or []:
            self.add(t)

    def add(self, t: Tool) -> None:
        self._tools[t.name] = t

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> list[str]:
        return list(self._tools)

    def openai_specs(self) -> list[dict]:
        return [{"type": "function",
                 "function": {"name": t.name, "description": t.description,
                              "parameters": t.schema}}
                for t in self._tools.values()]

    def run(self, name: str, arguments: dict) -> Any:
        t = self.get(name)
        if t is None:
            return {"error": f"unknown tool: {name}"}
        try:
            out = t(arguments or {})
            # auto-attach default source if the tool didn't set one
            if isinstance(out, dict) and t.source and "source" not in out:
                out["source"] = t.source
            return out
        except Exception as e:  # noqa: broad-except
            return {"error": f"{type(e).__name__}: {e}"}


@dataclass
class AgentConfig:
    """Everything the engine needs, injected by the host app.

    Nothing here is domain-specific to the engine — finance, news, or anything
    else is expressed purely through these fields.
    """
    system_prompt: str
    tools: list[Tool] = field(default_factory=list)
    max_tool_rounds: int = 6
    tool_result_max_chars: int = 8000
    history_turns: int = 20            # how many recent messages to keep in context
    # Memory / panels (optional). Leave ui_db_path None to disable persistence.
    ui_db_path: Optional[str] = None
    enable_panels: bool = False
    enable_journal: bool = True
    # Optional hook: return a string appended to the system prompt (e.g. a
    # journal/recent-activity summary) so the agent has episodic recall.
    recall_provider: Optional[Callable[[], str]] = None

    def registry(self) -> ToolRegistry:
        return ToolRegistry(self.tools)
