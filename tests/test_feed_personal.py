"""Tests for the personalized feed scoring (pure function, no IO)."""
from app.routers.feed_personal import score_articles


def _arts():
    return [
        {"id": "1", "category": "vendor", "tags": ["LLM"], "title": "OpenAI ships",
         "summary": "about agent", "date": "2026-06-28T01:00:00+00:00"},
        {"id": "2", "category": "media", "tags": [], "title": "random news",
         "summary": "nothing", "date": "2026-06-28T02:00:00+00:00"},
        {"id": "3", "category": "vendor", "tags": ["RAG"], "title": "infra post",
         "summary": "vLLM GPU", "date": "2026-06-28T00:00:00+00:00"},
    ]


def test_relevant_articles_rank_above_unrelated():
    signals = {"categories": {"vendor": 3}, "top_tags": ["llm", "rag"]}
    ranked = score_articles(_arts(), signals, ["vllm", "agent"])
    assert ranked[-1]["id"] == "2"          # unrelated media sinks
    assert ranked[0]["_score"] > 0          # top item has signal
    assert ranked[-1]["_score"] == 0.0


def test_no_signal_keeps_all_zero_and_sorts_by_recency():
    ranked = score_articles(_arts(), {"categories": {}, "top_tags": []}, [])
    assert all(a["_score"] == 0.0 for a in ranked)
    assert ranked[0]["id"] == "2"           # newest first when all tied


def test_category_weight_is_capped():
    # A huge pin count in one category must not produce unbounded score.
    signals = {"categories": {"vendor": 999}, "top_tags": []}
    ranked = score_articles(_arts(), signals, [])
    vendor = next(a for a in ranked if a["id"] == "1")
    assert vendor["_score"] <= 5 * 3.0      # _CATEGORY_CAP * _W_CATEGORY
