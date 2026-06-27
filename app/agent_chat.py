"""Conversational agent endpoint — upgrades the old pass-through /chat into a
sparrow-powered ReAct agent with tools, citations, and conversation memory.

Streams Server-Sent Events: tool_call / tool_result / final / error, plus a
title event on the first message. Conversation history is persisted in ui.db via
sparrow's Memory so a refresh restores the full thread.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from sparrow import AgentConfig, Harness, Memory, configure as llm_configure

from .agent_tools import ALL_TOOLS
from .auth import require_user
from .llm_client import llm_configured
from .models import ChatRequest
from .settings import settings

log = logging.getLogger("aif.agent")

router = APIRouter(prefix="/api/agent", tags=["agent"])

UI_DB = settings.data_dir / "ai-news" / "ui.db"

SYSTEM_PROMPT = """You are an AI-frontier research assistant. You help the user \
track the AI landscape: latest papers, model releases, tools, and expert takes \
from a curated set of ~80 RSS sources (official labs, expert blogs, X/Twitter, \
communities).

Rules (must follow):
1. For anything about specific articles/sources/tracks, ALWAYS call a tool first; \
never invent titles, dates, or facts.
2. Answer only from tool results. If the data doesn't have it, say so plainly.
3. Reply in the user's language (Chinese if they write Chinese). Be concise; \
bold key terms; conclusion first.
4. When the user wants to follow a topic continuously, you may propose creating a \
"track" — but only call create_track after they explicitly agree.
5. When asked who you are / what you can do, describe your tools and memory in \
natural language.
"""

# Configure sparrow's LLM client from our settings (DeepSeek).
llm_configure(base_url=settings.llm_base_url, api_key=settings.llm_api_key,
              model=settings.llm_model)

_memory = Memory(str(UI_DB))


def _build_config() -> AgentConfig:
    return AgentConfig(
        system_prompt=SYSTEM_PROMPT,
        tools=ALL_TOOLS,
        recall_provider=_memory.journal_summary_for_prompt,
    )


@router.post("/chat", dependencies=[Depends(require_user)])
async def chat(req: ChatRequest):
    if not llm_configured():
        from fastapi import HTTPException
        raise HTTPException(503, "LLM not configured")

    conv_id = req.conversation_id or ""
    messages = [{"role": "user", "content": req.message}]

    # Persist the user message + auto-title on first turn.
    is_first = False
    if conv_id:
        is_first = _memory.message_count(conv_id) == 0
        _memory.add_message(conv_id, "user", req.message)

    harness = Harness(_build_config(), journal_fn=_memory.journal_append)

    def event_stream():
        # Title event first (best-effort).
        if is_first and conv_id:
            try:
                title = _memory.auto_title(conv_id, req.message)
                yield _sse({"type": "title", "title": title})
            except Exception:
                pass

        tool_steps, final_content, final_citations = [], "", []
        # sparrow's run() expects full message history; load it from memory.
        history = _memory.get_messages(conv_id) if conv_id else messages
        run_msgs = [{"role": m["role"], "content": m["content"]} for m in history] or messages
        for event in harness.run(run_msgs, conversation_id=conv_id):
            yield _sse(event)
            if event.get("type") == "tool_result":
                tool_steps.append({"label": event.get("label", ""), "summary": event.get("summary", "")})
            elif event.get("type") == "final":
                final_content = event.get("content", "")
                final_citations = event.get("citations", [])

        if conv_id and final_content:
            _memory.add_message(conv_id, "assistant", final_content,
                                meta={"citations": final_citations, "tool_steps": tool_steps})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/conversations")
def list_conversations():
    return _memory.list_conversations()


@router.get("/conversations/{conv_id}")
def get_conversation(conv_id: str):
    return {"messages": _memory.get_messages(conv_id)}


@router.delete("/conversations/{conv_id}", dependencies=[Depends(require_user)])
def delete_conversation(conv_id: str):
    return _memory.delete_conversation(conv_id)


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False, default=str)}\n\n"
