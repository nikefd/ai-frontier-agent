"""Agent harness — multi-stage orchestration: ReAct tool loop with citations,
context budgeting, and optional journaling.

Design (the full LLM-harness loop):
- Staged: intent handled by the model, then a ReAct tool loop (the body), then
  a final answer.
- Anti-hallucination: the host's system prompt should require "answer only from
  tool results"; the final answer carries ``citations`` collected from each
  tool result's ``source`` field.
- Event-stream protocol: ``run()`` yields event dicts
  (tool_call / tool_result / final / error); the transport layer (SSE/CLI) only
  serializes them, so orchestration is decoupled from transport.
- Context budget: oversized tool results are truncated; only the last N messages
  of history are kept.

The engine is domain-agnostic: all domain knowledge comes from
:class:`~sparrow.registry.AgentConfig` (system prompt, tools, memory paths).
"""
import json

from .llm import chat, LLMError
from .registry import AgentConfig, ToolRegistry


def _truncate(obj, limit):
    s = json.dumps(obj, ensure_ascii=False, default=str)
    return s if len(s) <= limit else s[:limit] + "…(truncated)"


class Harness:
    """Runs one agent defined by an :class:`AgentConfig`."""

    def __init__(self, config: AgentConfig, *, journal_fn=None):
        """``journal_fn(actor, kind, name, detail, conversation_id)`` is called
        for state-changing tools when provided (and config.enable_journal)."""
        self.config = config
        self.registry: ToolRegistry = config.registry()
        self._journal_fn = journal_fn

    def _system_prompt(self) -> str:
        system = self.config.system_prompt
        # Episodic memory injection: let the host append a recent-activity summary
        if self.config.recall_provider:
            try:
                recall = self.config.recall_provider()
                if recall:
                    system += "\n\n" + recall
            except Exception:
                pass  # recall must never block the conversation
        return system

    def run(self, user_messages, conversation_id=""):
        """Main loop. ``user_messages``: [{"role","content"}, ...]; yields event
        dicts."""
        cfg = self.config
        messages = [{"role": "system", "content": self._system_prompt()}]
        messages += user_messages[-cfg.history_turns:]

        citations = []
        try:
            for _round in range(cfg.max_tool_rounds):
                result = chat(messages, tools=self.registry.openai_specs())

                if not result["tool_calls"]:
                    yield {"type": "final", "content": result["content"],
                           "citations": sorted(set(citations))}
                    return

                # Echo the assistant's tool-call intent back into history
                # (required by the OpenAI protocol)
                messages.append({
                    "role": "assistant",
                    "content": result["content"] or None,
                    "tool_calls": [{"id": tc["id"], "type": "function",
                                    "function": {"name": tc["name"],
                                                 "arguments": json.dumps(tc["arguments"], ensure_ascii=False)}}
                                   for tc in result["tool_calls"]],
                })
                for tc in result["tool_calls"]:
                    tool = self.registry.get(tc["name"])
                    label = tool.label if tool else tc["name"]
                    yield {"type": "tool_call", "name": tc["name"], "label": label,
                           "arguments": tc["arguments"]}

                    # Inject conversation_id into write tools that accept it
                    if tool and tool.writes and isinstance(tc["arguments"], dict):
                        tc["arguments"].setdefault("conversation_id", conversation_id)

                    out = self.registry.run(tc["name"], tc["arguments"])
                    src = out.get("source") if isinstance(out, dict) else None
                    if src:
                        citations.append(src)
                    is_err = isinstance(out, dict) and out.get("error")

                    yield {"type": "tool_result", "name": tc["name"], "label": label,
                           "summary": _summarize(out)}

                    # Episodic memory: journal only meaningful state changes
                    if tool and tool.writes and self._journal_fn and cfg.enable_journal and not is_err:
                        try:
                            self._journal_fn(
                                actor="agent", kind="tool", name=tc["name"],
                                detail=(out.get("message", "") if isinstance(out, dict) else ""),
                                conversation_id=conversation_id)
                        except Exception:
                            pass

                    if tool and tool.writes and not is_err and isinstance(out, dict) and out.get("id"):
                        yield {"type": "panel_created", "id": out.get("id", "")}

                    messages.append({"role": "tool", "tool_call_id": tc["id"],
                                     "content": _truncate(out, cfg.tool_result_max_chars)})

            # Tool-round budget exceeded: force a close-out
            messages.append({"role": "user",
                             "content": "(system: tool-call limit reached; answer now from what you have)"})
            result = chat(messages)
            yield {"type": "final", "content": result["content"],
                   "citations": sorted(set(citations))}
        except LLMError as e:
            yield {"type": "error", "message": str(e)}
        except Exception as e:  # noqa: broad-except
            yield {"type": "error", "message": f"{type(e).__name__}: {e}"}


def _summarize(out) -> str:
    """Summarize a tool result into one human line. Hosts can override by
    setting a ``_summary`` key on their result dict."""
    if isinstance(out, dict):
        if out.get("error"):
            return f"error: {out['error']}"
        if out.get("_summary"):
            return out["_summary"]
        # report the count of the first list found
        for k, v in out.items():
            if isinstance(v, list):
                return f"{len(v)} {k}"
        if out.get("message"):
            return out["message"]
    return "done"
