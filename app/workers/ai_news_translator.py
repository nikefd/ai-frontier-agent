"""Async enrichment worker for AI-news articles.

Picks up un-enriched articles in small batches and asks the LLM, in ONE batched
call per batch, for: Chinese title + summary, an importance score (0-10),
controlled tags, an event-cluster key, and an optional hands-on next step. Writes everything back to
the GLOBAL articles.json atomically —
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

import asyncio
import json
import logging
import re
from typing import Any

from ..llm_client import LLMUnavailable, chat_complete, llm_configured
from ..routers.ai_news import ARTICLES_FILE, _load_articles
from ..storage import update_json_atomic

log = logging.getLogger("aif.translator")

BATCH_SIZE = 8
ENRICHMENT_BACKFILL_LIMIT = 60
_TRANSLATE_LOCK = asyncio.Lock()

# Controlled tag vocabulary — the LLM must pick from this list, nothing else.
# Keeps tags filterable (no synonym explosion). Mirror in frontend TAG_VOCAB.
TAG_VOCAB = ["发布", "论文", "工具", "开源", "教程", "观点", "融资", "安全", "评测", "应用"]

SYSTEM = (
    "你是一名 AI/技术新闻编辑。我会给你一组 RSS 抓取的英文（或中文）文章条目，"
    "请对每条做五件事：翻译、评重要性、打标签、识别事件、判断是否值得动手实践。\n\n"
    "1) 翻译：把 title 和 summary 翻成自然、专业、紧凑的中文。\n"
    "   - 保留专有名词（OpenAI / GPT-4 / vLLM / RLHF 等）不翻译\n"
    "   - 不要营销词、不要感叹号；summary 控制在 150 字内，可改写为信息密度更高的中文\n"
    "   - 若原文已是中文，title_zh/summary_zh 直接整理原文\n"
    "2) 重要性 importance：0-10 整数，评估这条对追 AI 前沿的人有多值得看。\n"
    "   - 9-10：重大模型/产品发布、突破性论文、行业大事\n"
    "   - 6-8：有价值的工具/方法/深度观点/重要更新\n"
    "   - 3-5：一般资讯、增量更新\n"
    "   - 0-2：噪音、闲聊、无实质信息、纯营销\n"
    "   - 结合 source/category 判断证据层级：官方一手发布和扎实研究优先；"
    "GitHub Trending、社区热度、单条社交观点本身不等于重要\n"
    "   - 论文可结合 HF Daily Papers 票数、代码可用性与摘要判断；这些是策展信号，"
    "不能替代对方法新颖性、证据和实际影响的判断\n"
    f"3) tags：从这个固定清单里选 1-3 个最贴切的（**只能用清单里的词**）：{TAG_VOCAB}\n"
    "4) event_key：为明确、可复述的新闻事件生成稳定的英文小写键，格式为“核心实体-动作-对象”，"
    "例如 openai-release-gpt-5。同一批里报道同一事件的条目必须给完全相同的键。"
    "泛泛观点、教程合集、无明确事件或无法判断时返回空字符串。不得把来源名或营销措辞当事件。\n"
    "5) hands_on：仅当内容是可试用的模型/API/工具/开源项目/教程，或能做小型复现实验时，"
    "给一个 20-80 字的中文最小实践步骤；政策、融资、纯观点、信息不足时返回空字符串。\n"
    "   - 只能依据输入内容，不得编造命令、参数、URL、模型名、版本号或不存在的能力\n"
    "   - 用动词开头，说明先做什么、观察什么结果；不要写泛泛的“阅读原文/持续关注”\n\n"
    "输出必须是单个合法 JSON 数组，每项形如："
    '{"id":"...","title_zh":"...","summary_zh":"...","importance":7,'
    '"tags":["发布","工具"],"event_key":"acme-release-model-x",'
    '"hands_on":"用一个最小样例试跑该工具，并记录延迟与输出质量。"}\n'
    "不要带 markdown 代码块标记。"
)


def _pick_pending(articles: list[dict], n: int) -> list[dict]:
    out: list[dict] = []
    for index, a in enumerate(articles):
        if a.get("title_zh") and a.get("summary_zh"):
            # One-time bounded backfill for recent articles enriched before
            # hands_on/event_key existed. Empty strings mean processed.
            if (
                index < ENRICHMENT_BACKFILL_LIMIT
                and a.get("translation_status") == "ok"
                and (a.get("hands_on") is None or a.get("event_key") is None)
            ):
                out.append(a)
                if len(out) >= n:
                    break
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


def _clean_hands_on(v: Any) -> str:
    """Keep a compact single-step hint; empty means not genuinely actionable."""
    if not isinstance(v, str):
        return ""
    text = re.sub(r"\s+", " ", v).strip()
    return text[:120]


def _clean_event_key(v: Any) -> str:
    """Normalize a conservative LLM event key; empty means do not cluster."""
    if not isinstance(v, str):
        return ""
    key = v.strip().casefold()
    key = re.sub(r"[^a-z0-9]+", "-", key).strip("-")
    if key in {"", "none", "unknown", "other", "n-a", "na"}:
        return ""
    parts = [part for part in key.split("-") if part][:8]
    if len(parts) < 3:
        return ""
    return "-".join(parts)[:96]


async def _translate_once() -> int:
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
        body = await chat_complete(messages, temperature=0.2, max_tokens=3000)
        parsed = _parse_response(body)
    except (LLMUnavailable, ValueError, json.JSONDecodeError) as e:
        log.warning("enrich batch failed: %s", e)
        ids = {a.get("id") for a in batch}

        def mark_failed(data):
            latest = data if isinstance(data, list) else []
            for article in latest:
                if article.get("id") in ids:
                    article["translation_status"] = "failed"
            return latest

        update_json_atomic(ARTICLES_FILE, [], mark_failed)
        return 0

    by_id = {p.get("id"): p for p in parsed if isinstance(p, dict)}
    missing = {a["id"] for a in batch if a.get("id")} - set(by_id.keys())
    written = 0

    def merge_results(data):
        nonlocal written
        latest = data if isinstance(data, list) else []
        for a in latest:
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
                a["event_key"] = _clean_event_key(p.get("event_key"))
                a["hands_on"] = _clean_hands_on(p.get("hands_on"))
                a["translation_status"] = "ok" if title_zh else "failed"
                written += 1
            elif a.get("id") in missing:
                a["translation_status"] = "failed"
        return latest

    update_json_atomic(ARTICLES_FILE, [], merge_results)
    log.info("enrich worker: persisted %d entries", written)
    return written


async def translate_once() -> int:
    """Serialize enrichment sweeps so a scheduler and admin trigger cannot overlap."""
    async with _TRANSLATE_LOCK:
        return await _translate_once()


if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level="INFO")
    print("translated:", asyncio.run(translate_once()))
