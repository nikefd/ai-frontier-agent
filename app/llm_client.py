"""Thin LLM client wrapper.

We deliberately do NOT import openai/anthropic — keep dependencies light. The
endpoints we hit are all OpenAI-compatible (`/chat/completions` returning
either JSON or SSE chunks), and httpx is already in the dep tree for the news
fetcher. Streaming is implemented as an async generator yielding text deltas.

Auth: `Authorization: Bearer <token>`. Default endpoint is DeepSeek
(`https://api.deepseek.com`), which is OpenAI-compatible.
"""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import httpx

from .settings import settings

log = logging.getLogger("aif.llm")


class LLMUnavailable(RuntimeError):
    pass


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.llm_base_url.rstrip("/"),
        headers={
            "Authorization": f"Bearer {settings.llm_api_key or ''}",
            "Content-Type": "application/json",
        },
        timeout=httpx.Timeout(60.0, read=180.0),
    )


async def chat_complete(
    messages: list[dict],
    *,
    model: str | None = None,
    temperature: float = 0.4,
    max_tokens: int = 1024,
) -> str:
    """Non-streaming convenience wrapper."""
    if not settings.llm_api_key:
        raise LLMUnavailable("LLM api key is not configured (set AIF_LLM_API_KEY or DEEPSEEK_API_KEY)")
    payload = {
        "model": model or settings.llm_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    async with _client() as c:
        r = await c.post("/chat/completions", json=payload)
        r.raise_for_status()
        data = r.json()
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as e:
        log.warning("Unexpected LLM payload: %s", data)
        raise LLMUnavailable(f"Malformed LLM response: {e}") from e


async def chat_stream(
    messages: list[dict],
    *,
    model: str | None = None,
    temperature: float = 0.4,
    max_tokens: int = 1024,
) -> AsyncIterator[str]:
    """Yield text deltas as they arrive. Server-Sent Events format."""
    if not settings.llm_api_key:
        raise LLMUnavailable("LLM api key is not configured")
    payload = {
        "model": model or settings.llm_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    async with _client() as c:
        async with c.stream("POST", "/chat/completions", json=payload) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                body = line[5:].strip()
                if body == "[DONE]":
                    return
                try:
                    chunk = json.loads(body)
                except json.JSONDecodeError:
                    continue
                try:
                    delta = chunk["choices"][0]["delta"].get("content")
                except (KeyError, IndexError, TypeError):
                    delta = None
                if delta:
                    yield delta


def llm_configured() -> bool:
    return bool(settings.llm_api_key)
