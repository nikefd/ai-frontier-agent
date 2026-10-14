"""Knowledge cards + spaced repetition review.

Turns articles / deep-dives / manual notes into review cards and schedules them
with SM-2 (see app/srs.py). Per-user storage in ``users/<uid>/review-cards.json``.
Zero LLM cost — card backs reuse existing summaries; scheduling is pure arithmetic.

Split into its own module (not piled into ai_news.py) per the code-quality rules.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import require_user
from ..models import UserPublic
from ..srs import is_due, new_srs, sm2_schedule
from ..storage import read_json, update_json_atomic
from .ai_news import _load_articles, deep_dives_dir, review_cards_file

router = APIRouter(prefix="/api/ai-news", tags=["review"])


def _today() -> str:
    return datetime.now(timezone.utc).astimezone().date().isoformat()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_cards(uid: str) -> list[dict]:
    data = read_json(review_cards_file(uid), [])
    return data if isinstance(data, list) else []


def _card_id(front: str, source_id: str | None) -> str:
    seed = f"{source_id or ''}::{front}::{_now_iso()}"
    return "rc_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


class CardCreate(BaseModel):
    front: str = ""
    back: str = ""
    source_type: str = "manual"          # article | deep-dive | manual
    source_id: str | None = None
    source_url: str | None = None
    tags: list[str] = []


class GradeRequest(BaseModel):
    grade: str                            # forgot | hard | good


def _derive_from_article(aid: str) -> dict | None:
    a = next((x for x in _load_articles() if x.get("id") == aid), None)
    if not a:
        return None
    return {
        "front": a.get("title_zh") or a.get("title") or "(无标题)",
        "back": a.get("summary_zh") or a.get("summary") or "",
        "source_url": a.get("url"),
        "tags": a.get("tags") or [],
    }


def _derive_from_deep_dive(uid: str, aid: str) -> dict | None:
    p = deep_dives_dir(uid) / f"{aid}.json"
    data = read_json(p, None)
    if not isinstance(data, dict):
        return None
    body = (data.get("body") or "").strip()
    # Use the first non-heading paragraph as the back (cheap, no LLM).
    back = ""
    for line in body.splitlines():
        s = line.strip()
        if s and not s.startswith("#") and not s.startswith("```"):
            back = s
            break
    return {
        "front": data.get("article_title_zh") or data.get("article_title") or "(无标题)",
        "back": back or "（点开原解读查看全文）",
        "source_url": data.get("article_url"),
        "tags": [],
    }


@router.get("/review/cards")
def list_cards(user: UserPublic = Depends(require_user)) -> dict:
    cards = _load_cards(user.id)
    cards.sort(key=lambda c: c.get("created_at") or "", reverse=True)
    return {"total": len(cards), "items": cards}


@router.post("/review/cards")
def create_card(req: CardCreate, user: UserPublic = Depends(require_user)) -> dict:
    front = (req.front or "").strip()
    payload = req.model_dump()

    # For article / deep-dive sources, auto-fill front/back from existing content
    # when the client didn't supply them (zero LLM cost).
    if req.source_type == "article" and req.source_id and not (front and req.back):
        derived = _derive_from_article(req.source_id)
        if not derived:
            raise HTTPException(404, "article not found")
        payload.update({k: v for k, v in derived.items() if not payload.get(k)})
    elif req.source_type == "deep-dive" and req.source_id and not (front and req.back):
        derived = _derive_from_deep_dive(user.id, req.source_id)
        if not derived:
            raise HTTPException(404, "deep-dive not found")
        payload.update({k: v for k, v in derived.items() if not payload.get(k)})

    front = (payload.get("front") or "").strip()
    if not front:
        raise HTTPException(400, "front required")

    today = _today()
    card = {
        "id": _card_id(front, req.source_id),
        "front": front,
        "back": (payload.get("back") or "").strip(),
        "source_type": req.source_type,
        "source_id": req.source_id,
        "source_url": payload.get("source_url"),
        "tags": payload.get("tags") or [],
        "created_at": _now_iso(),
        "srs": new_srs(today),
    }
    def mutate(data):
        cards = data if isinstance(data, list) else []
        if req.source_id and any(
            c.get("source_id") == req.source_id and c.get("source_type") == req.source_type
            for c in cards
        ):
            raise HTTPException(409, "这篇已经在复习库里了")
        cards.append(card)
        return cards

    update_json_atomic(review_cards_file(user.id), [], mutate)
    return {"ok": True, "card": card}


@router.delete("/review/cards/{cid}")
def delete_card(cid: str, user: UserPublic = Depends(require_user)) -> dict:
    def mutate(data):
        cards = data if isinstance(data, list) else []
        kept = [card for card in cards if card.get("id") != cid]
        if len(kept) == len(cards):
            raise HTTPException(404, "card not found")
        return kept

    update_json_atomic(review_cards_file(user.id), [], mutate)
    return {"ok": True}


@router.get("/review/due")
def due_cards(user: UserPublic = Depends(require_user)) -> dict:
    today = _today()
    cards = _load_cards(user.id)
    due = [c for c in cards if is_due(c.get("srs") or {}, today)]
    due.sort(key=lambda c: (c.get("srs") or {}).get("due") or "")
    return {"today": today, "due_count": len(due), "total": len(cards), "items": due}


@router.post("/review/cards/{cid}/grade")
def grade_card(cid: str, req: GradeRequest, user: UserPublic = Depends(require_user)) -> dict:
    updated = {}

    def mutate(data):
        cards = data if isinstance(data, list) else []
        card = next((item for item in cards if item.get("id") == cid), None)
        if not card:
            raise HTTPException(404, "card not found")
        try:
            card["srs"] = sm2_schedule(card.get("srs") or new_srs(_today()), req.grade, _today())
        except ValueError as e:
            raise HTTPException(400, str(e))
        updated["card"] = card
        return cards

    update_json_atomic(review_cards_file(user.id), [], mutate)
    return {"ok": True, "card": updated["card"]}
