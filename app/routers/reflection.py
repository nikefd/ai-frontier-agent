"""AI reflection coach — Socratic weekly review.

Aggregates the user's *recent* (last N days) activity — pins, deep-dives,
review cards, conversation topics — and asks the LLM for a short recap plus a
few Socratic questions that prompt self-reflection (questions, not answers).
The user can then take any question into the chat agent to go deeper.

Reuses ai_news loaders + profile's conversation reader. Split into its own
module per the code-quality rules.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from ..llm_client import LLMUnavailable, chat_complete, llm_configured
from ..models import UserPublic
from ..auth import require_user, current_user_optional
from ..settings import settings
from ..storage import read_json, sqlite_ro, write_json_atomic
from .ai_news import (
    _load_articles,
    _load_pins,
    _parse_ts,
    deep_dives_dir,
    reflection_file,
    review_cards_file,
    user_dir,
)

router = APIRouter(prefix="/api/ai-news", tags=["reflection"])

_WINDOW_DAYS = 7

REFLECTION_SYSTEM = (
    "你是一位苏格拉底式的个人成长教练。我会给你某个用户最近一周在一个 AI 资讯站上的"
    "活动信号（收藏的文章、生成的深度解读、做的知识卡、聊过的话题）。\n\n"
    "请输出严格的 JSON（不要 markdown 代码块包裹），结构：\n"
    '{"recap": "一段话回顾本周关注重点（不超过 120 字，结论先行，关键词加粗用 **）",\n'
    ' "questions": ["问题1", "问题2", "问题3"]}\n\n'
    "要求：\n"
    "- questions 是 3-5 个**苏格拉底式问题**：只提问、不给答案，引导用户自我反思、"
    "把输入和自己的目标/工作/思考联系起来。\n"
    "- 问题要具体到用户本周的实际关注点，不要空泛（差：你学到了什么；好：你这周连续"
    "看了好几篇 Agent 编排，这和你手上的项目能怎么结合？）。\n"
    "- 中文；技术术语保留英文；信号稀少时也至少给 3 个能引发思考的问题。"
)


def _recent_conversation_titles(uid: str, since_ts: float, limit: int = 30) -> list[str]:
    db = user_dir(uid) / "ui.db"
    out: list[str] = []
    try:
        with sqlite_ro(db) as conn:
            rows = conn.execute(
                "SELECT title, updated_at FROM conversations ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            for r in rows:
                if not r["title"] or r["title"] == "New chat":
                    continue
                if _parse_ts(r["updated_at"] or "") >= since_ts:
                    out.append(r["title"])
    except Exception:
        return []
    return out


def collect_recent_signals(uid: str, now_ts: float, window_days: int = _WINDOW_DAYS) -> dict:
    """Activity in the last `window_days`. `now_ts` injected for testability."""
    since = now_ts - window_days * 86400
    articles_by_id = {a.get("id"): a for a in _load_articles()}

    # Pins have no pin-time; approximate "recent" by the article's own date.
    pins: list[str] = []
    for aid in _load_pins(uid):
        a = articles_by_id.get(aid)
        if a and _parse_ts(a.get("date") or "") >= since:
            pins.append(a.get("title_zh") or a.get("title") or "")
    pins = [p for p in pins if p]

    dives: list[str] = []
    ddir = deep_dives_dir(uid)
    if ddir.exists():
        for p in ddir.glob("*.json"):
            d = read_json(p, None)
            if isinstance(d, dict) and _parse_ts(d.get("generated_at") or "") >= since:
                dives.append(d.get("article_title_zh") or d.get("article_title") or "")
    dives = [d for d in dives if d]

    cards_data = read_json(review_cards_file(uid), [])
    cards = [c.get("front", "") for c in cards_data
             if isinstance(c, dict) and _parse_ts(c.get("created_at") or "") >= since]
    cards = [c for c in cards if c]

    conversations = _recent_conversation_titles(uid, since)

    return {
        "counts": {
            "pins": len(pins), "deep_dives": len(dives),
            "cards": len(cards), "conversations": len(conversations),
        },
        "pins": pins[:30],
        "deep_dive_topics": dives[:30],
        "card_fronts": cards[:30],
        "conversation_topics": conversations[:30],
    }


def _build_prompt(sig: dict) -> str:
    c = sig["counts"]
    def lst(xs):
        return "\n".join(f"- {x}" for x in xs) or "（无）"
    return (
        f"本周信号：收藏 {c['pins']} / 深度解读 {c['deep_dives']} / "
        f"知识卡 {c['cards']} / 对话 {c['conversations']}\n\n"
        f"收藏的文章：\n{lst(sig['pins'])}\n\n"
        f"生成的深度解读：\n{lst(sig['deep_dive_topics'])}\n\n"
        f"做的知识卡：\n{lst(sig['card_fronts'])}\n\n"
        f"聊过的话题：\n{lst(sig['conversation_topics'])}\n\n"
        "请基于以上生成本周复盘。"
    )


def _now_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/reflection")
def get_reflection(user: UserPublic | None = Depends(current_user_optional)) -> dict:
    if not user:
        return {"status": "none"}
    data = read_json(reflection_file(user.id), None)
    if not isinstance(data, dict) or not data.get("questions"):
        return {"status": "none"}
    return {"status": "ok", **data}


@router.post("/reflection/generate")
async def generate_reflection(user: UserPublic = Depends(require_user)) -> dict:
    # Check for data first so a no-activity user gets the actionable 400 rather
    # than a misleading 503 when the LLM happens to be unconfigured.
    sig = collect_recent_signals(user.id, _now_ts())
    c = sig["counts"]
    if c["pins"] + c["deep_dives"] + c["cards"] + c["conversations"] == 0:
        raise HTTPException(400, "本周还没有足够的活动：先读几篇、收藏或和助手聊几句，再来复盘")
    if not llm_configured():
        raise HTTPException(503, "LLM not configured")

    messages = [
        {"role": "system", "content": REFLECTION_SYSTEM},
        {"role": "user", "content": _build_prompt(sig)},
    ]
    try:
        raw = await chat_complete(messages, max_tokens=900, temperature=0.6)
    except LLMUnavailable as e:
        raise HTTPException(503, str(e))

    recap, questions = _parse_llm_json(raw)
    payload = {
        "generated_at": _now_iso(),
        "model": settings.llm_model,
        "signals": c,
        "recap": recap,
        "questions": questions,
    }
    write_json_atomic(reflection_file(user.id), payload)
    return {"status": "ok", **payload}


def _parse_llm_json(raw: str) -> tuple[str, list[str]]:
    """Tolerant parse of the model's JSON (strip code fences, fall back gracefully)."""
    s = (raw or "").strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if "```" in s[3:] else s.strip("`")
        s = s[s.find("{"):]
    try:
        obj = json.loads(s[s.find("{"): s.rfind("}") + 1])
        recap = str(obj.get("recap", "")).strip()
        qs = [str(q).strip() for q in obj.get("questions", []) if str(q).strip()]
        if qs:
            return recap, qs
    except Exception:
        pass
    # Fallback: treat the whole text as recap with one generic question.
    return s[:200], ["回顾这一周，你最想深入思考或采取行动的是哪一点？"]
