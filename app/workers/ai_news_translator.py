"""Async translation worker for AI-news articles.

Picks up articles with translation_status="pending" in small batches and asks
the LLM for Chinese title + summary. Writes title_zh / summary_zh / status
back to articles.json atomically.

Design notes:
  - Batch of 5 per tick keeps prompt size + latency reasonable
  - Single LLM call per batch (JSON output) — cheaper than 5 separate calls
  - On any failure we mark status=failed; next sweep won't retry unless reset
  - Already-translated rows are skipped
  - Idempotent: if title_zh exists we mark status=ok regardless
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from ..llm_client import LLMUnavailable, chat_complete, llm_configured
from ..routers.ai_news import ARTICLES_FILE, _load_articles
from ..storage import write_json_atomic

log = logging.getLogger("zyb.translator")

BATCH_SIZE = 5

SYSTEM = (
    "你是一名 AI/技术新闻的专业中英翻译员。\n"
    "我会给你一组 RSS 抓取下来的英文文章条目，请把每条的 title 和 summary 翻译成自然、专业、紧凑的中文。\n"
    "规则：\n"
    "- 保留专有名词（OpenAI / GPT-4 / vLLM / RLHF 等）不翻译\n"
    "- 不要营销词、不要加感叹号\n"
    "- summary 限制在 150 字以内，可改写为信息密度更高的中文\n"
    "- 输出必须是单个合法 JSON 数组，每项形如 {\"id\":\"...\",\"title_zh\":\"...\",\"summary_zh\":\"...\"}\n"
    "- 不要带 markdown 代码块标记"
)


def _pick_pending(articles: list[dict], n: int) -> list[dict]:
    out: list[dict] = []
    for a in articles:
        if a.get("title_zh") and a.get("summary_zh"):
            continue
        st = a.get("translation_status")
        if st in ("ok", "failed", "skipped"):
            continue
        out.append(a)
        if len(out) >= n:
            break
    return out


def _build_user_msg(batch: list[dict]) -> str:
    rows = []
    for a in batch:
        rows.append(
            {
                "id": a.get("id"),
                "title": a.get("title") or "",
                "summary": (a.get("summary") or "")[:600],
            }
        )
    return "请翻译以下文章：\n" + json.dumps(rows, ensure_ascii=False)


_JSON_ARRAY_RE = re.compile(r"\[[\s\S]*\]")


def _parse_response(body: str) -> list[dict[str, Any]]:
    body = body.strip()
    if body.startswith("```"):
        # strip code-fence
        body = re.sub(r"^```[a-z]*\n?", "", body)
        body = re.sub(r"\n?```$", "", body)
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        m = _JSON_ARRAY_RE.search(body)
        if not m:
            raise
        data = json.loads(m.group(0))
    if not isinstance(data, list):
        raise ValueError("response is not a JSON array")
    return data


async def translate_once() -> int:
    """Translate one batch. Returns number translated."""
    if not llm_configured():
        return 0
    articles = _load_articles()
    batch = _pick_pending(articles, BATCH_SIZE)
    if not batch:
        return 0
    log.info("translation worker: batch of %d", len(batch))
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": _build_user_msg(batch)},
    ]
    try:
        body = await chat_complete(messages, temperature=0.2, max_tokens=1400)
        parsed = _parse_response(body)
    except (LLMUnavailable, ValueError, json.JSONDecodeError) as e:
        log.warning("translation batch failed: %s", e)
        # Mark this batch failed so we don't loop on them forever
        ids = {a.get("id") for a in batch}
        for a in articles:
            if a.get("id") in ids:
                a["translation_status"] = "failed"
        write_json_atomic(ARTICLES_FILE, articles)
        return 0

    by_id = {p.get("id"): p for p in parsed if isinstance(p, dict)}
    written = 0
    for a in articles:
        if a.get("id") in by_id:
            p = by_id[a["id"]]
            title_zh = (p.get("title_zh") or "").strip()
            summary_zh = (p.get("summary_zh") or "").strip()
            if title_zh:
                a["title_zh"] = title_zh
            if summary_zh:
                a["summary_zh"] = summary_zh
            a["translation_status"] = "ok" if title_zh else "failed"
            written += 1
    # Catch entries that were in batch but missing from response → mark failed
    missing = {a["id"] for a in batch if a.get("id")} - set(by_id.keys())
    for a in articles:
        if a.get("id") in missing:
            a["translation_status"] = "failed"
    write_json_atomic(ARTICLES_FILE, articles)
    log.info("translation worker: persisted %d entries", written)
    return written


if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level="INFO")
    print("translated:", asyncio.run(translate_once()))
