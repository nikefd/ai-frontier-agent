"""Async enrichment worker for AI-news articles.

Picks up un-enriched articles in small batches and asks the LLM, in ONE batched
call per batch, for: Chinese title + summary, an importance score (0-10), and
controlled tags. Writes everything back to the GLOBAL articles.json atomically —
so enrichment is computed once and shared across all users (content is global;
only pins/profiles are per-user).

Design notes:
  - One LLM call per batch (JSON array out) — translation + score + tags together,
    so we never pay separate calls for scoring/tagging.
  - Importance lets the feed sort/filter by quality (the "全而能筛出好的" layer).
  - Tags use a CONTROLLED vocabulary (see TAG_VOCAB) so users can filter reliably
    instead of drowning in LLM-invented near-synonyms.
  - On failure we mark status=failed; next sweep won't retry unless reset.
  - Idempotent: already-enriched rows (have title_zh) are skipped.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from ..llm_client import LLMUnavailable, chat_complete, llm_configured
from ..routers.ai_news import ARTICLES_FILE, _load_articles
from ..storage import write_json_atomic

log = logging.getLogger("aif.translator")

BATCH_SIZE = 8

# Controlled tag vocabulary — the LLM must pick from this list, nothing else.
# Keeps tags filterable (no synonym explosion). Mirror in frontend TAG_VOCAB.
TAG_VOCAB = ["发布", "论文", "工具", "开源", "教程", "观点", "融资", "安全", "评测", "应用"]

SYSTEM = (
    "你是一名 AI/技术新闻编辑。我会给你一组 RSS 抓取的英文（或中文）文章条目，"
    "请对每条做三件事：翻译、评重要性、打标签。\n\n"
    "1) 翻译：把 title 和 summary 翻成自然、专业、紧凑的中文。\n"
    "   - 保留专有名词（OpenAI / GPT-4 / vLLM / RLHF 等）不翻译\n"
    "   - 不要营销词、不要感叹号；summary 控制在 150 字内，可改写为信息密度更高的中文\n"
    "   - 若原文已是中文，title_zh/summary_zh 直接整理原文\n"
    "2) 重要性 importance：0-10 整数，评估这条对追 AI 前沿的人有多值得看。\n"
    "   - 9-10：重大模型/产品发布、突破性论文、行业大事\n"
    "   - 6-8：有价值的工具/方法/深度观点/重要更新\n"
    "   - 3-5：一般资讯、增量更新\n"
    "   - 0-2：噪音、闲聊、无实质信息、纯营销\n"
    f"3) tags：从这个固定清单里选 1-3 个最贴切的（**只能用清单里的词**）：{TAG_VOCAB}\n\n"
    "输出必须是单个合法 JSON 数组，每项形如："
    '{"id":"...","title_zh":"...","summary_zh":"...","importance":7,"tags":["发布","工具"]}\n'
    "不要带 markdown 代码块标记。"
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
                "source": a.get("source") or "",
                "category": a.get("category") or "",
            }
        )
    return "请处理以下文章：\n" + json.dumps(rows, ensure_ascii=False)


_JSON_ARRAY_RE = re.compile(r"\[[\s\S]*\]")


def _parse_response(body: str) -> list[dict[str, Any]]:
    body = body.strip()
    if body.startswith("```"):
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


def _clean_importance(v: Any) -> int | None:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return max(0, min(10, n))


def _clean_tags(v: Any) -> list[str]:
    if not isinstance(v, list):
        return []
    return [t for t in v if t in TAG_VOCAB][:3]


async def translate_once() -> int:
    """Enrich one batch (translate + score + tag). Returns number processed."""
    if not llm_configured():
        return 0
    articles = _load_articles()
    batch = _pick_pending(articles, BATCH_SIZE)
    if not batch:
        return 0
    log.info("enrich worker: batch of %d", len(batch))
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": _build_user_msg(batch)},
    ]
    try:
        body = await chat_complete(messages, temperature=0.2, max_tokens=2200)
        parsed = _parse_response(body)
    except (LLMUnavailable, ValueError, json.JSONDecodeError) as e:
        log.warning("enrich batch failed: %s", e)
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
            imp = _clean_importance(p.get("importance"))
            if imp is not None:
                a["importance"] = imp
            tags = _clean_tags(p.get("tags"))
            if tags:
                a["tags"] = tags
            a["translation_status"] = "ok" if title_zh else "failed"
            written += 1
    # Entries in batch but missing from response → mark failed
    missing = {a["id"] for a in batch if a.get("id")} - set(by_id.keys())
    for a in articles:
        if a.get("id") in missing:
            a["translation_status"] = "failed"
    write_json_atomic(ARTICLES_FILE, articles)
    log.info("enrich worker: persisted %d entries", written)
    return written


if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level="INFO")
    print("translated:", asyncio.run(translate_once()))
