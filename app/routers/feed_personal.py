"""Personalized "for you" feed: re-rank today's cohort by a user's profile signals.

Zero extra LLM cost — ranking is pure arithmetic over signals already gathered
for the profile feature (pinned-category distribution, top tags, track keywords).
Anonymous users (or users with no signals) fall back to plain chronological order,
so this endpoint never errors on missing data.

Split into its own module (not piled into ai_news.py) per the code-quality rules;
reuses ai_news' cohort + loaders and profile's signal aggregation.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..models import UserPublic
from ..auth import current_user_optional
from .ai_news import _articles_for_today, _load_tracks, _parse_ts
from .profile import _collect_profile_signals

router = APIRouter(prefix="/api/ai-news", tags=["personal-feed"])

# Scoring weights — tuned so a single strong signal (e.g. a pinned-heavy category)
# outranks recency, but recency still breaks ties between equally-relevant items.
_W_CATEGORY = 3.0   # per pin in that category (capped)
_W_TAG = 2.0        # per matched top-tag
_W_TRACK = 2.5      # per matched track keyword
_CATEGORY_CAP = 5   # don't let one dominant category drown everything else


def _track_keywords(uid: str) -> list[str]:
    kws: list[str] = []
    for t in _load_tracks(uid):
        for k in (t.get("keywords") or []):
            k = (k or "").strip().lower()
            if k:
                kws.append(k)
    return kws


def score_articles(articles: list[dict], signals: dict, track_keywords: list[str]) -> list[dict]:
    """Return articles with a `_score` + `_reasons`, sorted by score then recency.

    Pure function (no IO) so it can be unit-tested in isolation.
    """
    cat_counts = signals.get("categories") or {}
    top_tags = {t.lower() for t in (signals.get("top_tags") or [])}

    scored: list[dict] = []
    for a in articles:
        score = 0.0
        reasons: list[str] = []

        cat = a.get("category")
        if cat and cat in cat_counts:
            hit = min(cat_counts[cat], _CATEGORY_CAP) * _W_CATEGORY
            score += hit
            reasons.append(f"关注领域:{cat}")

        atags = {(t or "").lower() for t in (a.get("tags") or [])}
        tag_hits = atags & top_tags
        if tag_hits:
            score += len(tag_hits) * _W_TAG
            reasons.append("标签:" + "/".join(sorted(tag_hits)))

        if track_keywords:
            hay = ((a.get("title_zh") or "") + " " + (a.get("title") or "")
                   + " " + (a.get("summary") or "")).lower()
            kw_hits = sorted({k for k in track_keywords if k in hay})
            if kw_hits:
                score += len(kw_hits) * _W_TRACK
                reasons.append("追踪:" + "/".join(kw_hits))

        scored.append({**a, "_score": round(score, 2), "_reasons": reasons})

    scored.sort(key=lambda a: (-a["_score"], -_parse_ts(a.get("date") or "")))
    return scored


@router.get("/for-you")
def for_you(
    limit: int = 20,
    user: UserPublic | None = Depends(current_user_optional),
) -> dict:
    """Today's cohort re-ranked for the current user.

    `personalized=False` when there's no user or no usable signal — the UI can
    then show a "pin articles to personalize" hint and the list is plain newest-first.
    """
    limit = max(1, min(limit, 50))
    cohort = _articles_for_today(limit=max(limit, 25))

    if not user:
        return {"personalized": False, "today_count": len(cohort), "items": cohort[:limit]}

    signals = _collect_profile_signals(user.id)
    has_signal = bool(signals["categories"] or signals["top_tags"])
    track_kws = _track_keywords(user.id)

    ranked = score_articles(cohort, signals, track_kws)
    personalized = has_signal or bool(track_kws)
    return {
        "personalized": personalized,
        "today_count": len(cohort),
        "items": ranked[:limit],
    }
