"""LLM client layer — OpenAI-compatible (e.g. DeepSeek), stdlib-only, with
streaming and tool-call support.

Design:
- Single entry point: every LLM call goes through ``chat()`` so token usage and
  latency are recorded in one place.
- Streaming and non-streaming share one signature; tool-call deltas are
  aggregated automatically.
- Retries and timeouts are handled here; the harness layer above stays unaware.

Configuration is read from environment variables by default and can be
overridden with ``configure()`` so a host app can inject its own credentials
without touching env state.
"""
import json
import os
import time
import urllib.request
import urllib.error

# ── Config (env defaults; override via configure()) ──────────────────
_CFG = {
    "base_url": os.environ.get("SPARROW_LLM_BASE_URL")
    or os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    "api_key": os.environ.get("SPARROW_LLM_API_KEY")
    or os.environ.get("DEEPSEEK_API_KEY", ""),
    "model": os.environ.get("SPARROW_LLM_MODEL")
    or os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
}

USAGE_LOG = []  # [(ts, prompt_tokens, completion_tokens, latency_ms)]


def configure(*, base_url=None, api_key=None, model=None):
    """Override LLM credentials/model at runtime. Unset args keep their value."""
    if base_url is not None:
        _CFG["base_url"] = base_url
    if api_key is not None:
        _CFG["api_key"] = api_key
    if model is not None:
        _CFG["model"] = model


class LLMError(Exception):
    pass


def _request(payload: dict):
    req = urllib.request.Request(
        f"{_CFG['base_url'].rstrip('/')}/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_CFG['api_key']}",
        },
    )
    return urllib.request.urlopen(req, timeout=120)


def chat(messages, tools=None, temperature=0.3, max_tokens=2000,
         response_format=None, on_delta=None, retries=2):
    """Call the LLM. When ``on_delta`` is set, stream (text deltas only). Returns
    a unified structure:
        {"content": str, "tool_calls": [{"id","name","arguments"}], "usage": {...}}
    """
    if not _CFG["api_key"]:
        raise LLMError("LLM api key is not configured (SPARROW_LLM_API_KEY / DEEPSEEK_API_KEY)")
    payload = {
        "model": _CFG["model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": on_delta is not None,
    }
    if tools:
        payload["tools"] = tools
    if response_format:
        payload["response_format"] = response_format

    last_err = None
    for attempt in range(retries + 1):
        t0 = time.time()
        try:
            resp = _request(payload)
            if on_delta is None:
                data = json.loads(resp.read())
                msg = data["choices"][0]["message"]
                usage = data.get("usage", {})
                USAGE_LOG.append((time.time(), usage.get("prompt_tokens", 0),
                                  usage.get("completion_tokens", 0),
                                  int((time.time() - t0) * 1000)))
                return {
                    "content": msg.get("content") or "",
                    "tool_calls": [
                        {"id": tc["id"], "name": tc["function"]["name"],
                         "arguments": json.loads(tc["function"]["arguments"] or "{}")}
                        for tc in (msg.get("tool_calls") or [])
                    ],
                    "usage": usage,
                }
            # Streaming: aggregate text and tool-call deltas
            content_parts = []
            tool_acc = {}   # index -> {id, name, arguments_str}
            for raw in resp:
                line = raw.decode().strip()
                if not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if chunk == "[DONE]":
                    break
                delta = json.loads(chunk)["choices"][0].get("delta", {})
                if delta.get("content"):
                    content_parts.append(delta["content"])
                    on_delta(delta["content"])
                for tc in delta.get("tool_calls") or []:
                    acc = tool_acc.setdefault(tc["index"], {"id": "", "name": "", "arguments_str": ""})
                    if tc.get("id"):
                        acc["id"] = tc["id"]
                    fn = tc.get("function", {})
                    if fn.get("name"):
                        acc["name"] = fn["name"]
                    if fn.get("arguments"):
                        acc["arguments_str"] += fn["arguments"]
            USAGE_LOG.append((time.time(), 0, 0, int((time.time() - t0) * 1000)))
            return {
                "content": "".join(content_parts),
                "tool_calls": [
                    {"id": a["id"], "name": a["name"],
                     "arguments": json.loads(a["arguments_str"] or "{}")}
                    for a in tool_acc.values()
                ],
                "usage": {},
            }
        except (urllib.error.URLError, json.JSONDecodeError, KeyError, TimeoutError) as e:
            last_err = e
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise LLMError(f"LLM call failed (after {retries} retries): {last_err}")
