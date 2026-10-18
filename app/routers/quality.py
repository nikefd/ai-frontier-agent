"""Read-only operational quality audit for AI news coverage."""
from __future__ import annotations

from fastapi import APIRouter

from ..quality_report import build_quality_report
from ..storage import read_json
from .ai_news import SUMMARY_FILE, _load_articles, list_sources


router = APIRouter(prefix="/api/ai-news", tags=["ai-news-quality"])


@router.get("/quality/report")
def quality_report() -> dict:
    summary = read_json(SUMMARY_FILE, None)
    return build_quality_report(
        _load_articles(),
        list_sources(),
        summary if isinstance(summary, dict) else None,
    )
