"""Proactive nudges — the agent suggesting the next step, not waiting to be asked.

Pure rule-based (zero LLM): inspects the user's accumulated signals (pins,
deep-dives, profile/reflection/path existence) and surfaces the 1-2 most useful
"next actions" as dismissible suggestions. Each carries display text + an action
the frontend can route to.

Kept non-pushy: only fires when a threshold makes a suggestion genuinely useful,
returns at most a couple, and the UI lets the user dismiss them.
"""
from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends

from ..auth import current_user_optional
from ..models import UserPublic
from ..storage import read_json
from .ai_news import (
    _load_articles,
    _load_pins,
    learning_paths_dir,
    profile_path,
    reflection_file,
)

router = APIRouter(prefix="/api/ai-news", tags=["suggestions"])

# Thresholds (tuned to fire only when a suggestion is genuinely earned).
_PINS_FOR_PROFILE = 5      # enough pins → worth a portrait
_PINS_FOR_PATH = 5         # ≥5 pins in one category → worth a learning path
_PINS_FOR_REFLECT = 8      # accumulated enough → worth reflecting


def _has_file(p) -> bool:
    return read_json(p, None) is not None


def _has_learning_path(uid: str) -> bool:
    d = learning_paths_dir(uid)
    return d.exists() and any(d.glob("*.json"))


def _build_suggestions(uid: str) -> list[dict]:
    """Ranked nudges. Pure code; each item: {id, text, action, view}."""
    articles = {a.get("id"): a for a in _load_articles()}
    pins = [articles[i] for i in _load_pins(uid) if i in articles]
    n_pins = len(pins)
    out: list[dict] = []

    # 1) Pinned heavily in one category and no learning path yet → propose one.
    if n_pins >= _PINS_FOR_PATH and not _has_learning_path(uid):
        cats = Counter(a.get("category") for a in pins if a.get("category"))
        if cats:
            top_cat, cnt = cats.most_common(1)[0]
            if cnt >= 3:
                out.append({
                    "id": "path-from-pins",
                    "text": f"你已收藏 {cnt} 篇 **{top_cat}** 相关，要不要生成一条学习路径把它们串起来？",
                    "action": "去生成", "view": "learning",
                })

    # 2) Enough pins but no portrait yet → suggest generating it.
    if n_pins >= _PINS_FOR_PROFILE and not _has_file(profile_path(uid)):
        out.append({
            "id": "make-profile",
            "text": f"已收藏 {n_pins} 篇，数据够了 —— 生成你的 **兴趣画像** 看看？",
            "action": "生成画像", "view": "profile",
        })

    # 3) Accumulated activity but never reflected → suggest a review.
    if n_pins >= _PINS_FOR_REFLECT and not _has_file(reflection_file(uid)):
        out.append({
            "id": "first-reflection",
            "text": "这段时间积累了不少，来一次 **本周复盘** 把它沉淀下来？",
            "action": "开始复盘", "view": "reflection",
        })

    return out[:2]  # at most two, never spammy


@router.get("/suggestions")
def get_suggestions(user: UserPublic | None = Depends(current_user_optional)) -> dict:
    if not user:
        return {"items": []}
    return {"items": _build_suggestions(user.id)}
