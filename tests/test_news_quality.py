"""Regression tests for source gating and editorial cohort selection."""
from __future__ import annotations

from app.routers.ai_news import (
    _CATEGORY_FETCH_CAPS,
    _parse_ts,
    _select_summary_cohort,
)
from app.workers.ai_news_fetcher import (
    _decide_relevance,
    _parse_sitemap_entries,
    _select_candidates,
)


def _candidate(i: int, category: str, tier_rank: int = 0, feed: str | None = None) -> tuple:
    entry = {
        "id": f"a{i}",
        "title": f"item {i}",
        "category": category,
        "date": f"2026-10-15T{i % 24:02d}:00:00+00:00",
    }
    return (tier_rank, -float(i), entry, {}, feed or f"feed-{i}")


def test_discovery_streams_require_ai_keyword() -> None:
    generic = {"title": "A popular terminal emulator", "summary": "Fast and colorful"}
    ai_item = {"title": "New open-source LLM inference engine", "summary": "Runs on GPU"}

    assert _decide_relevance(generic, "high", "vendor")[0] is True
    assert _decide_relevance(generic, "low", "trending") == (False, "rejected")
    assert _decide_relevance(ai_item, "low", "trending") == (True, "keyword")


def test_official_sitemap_adapter_filters_and_sorts_paths() -> None:
    xml = b"""<?xml version="1.0"?><urlset>
      <url><loc>https://lab.test/careers</loc><lastmod>2026-10-15</lastmod></url>
      <url><loc>https://lab.test/news/older-model</loc><lastmod>2026-10-13</lastmod></url>
      <url><loc>https://lab.test/research/new-safety-work</loc><lastmod>2026-10-14</lastmod></url>
    </urlset>"""
    entries = _parse_sitemap_entries(xml, ["/news/", "/research/"])
    assert [e["title"] for e in entries] == ["New Safety Work", "Older Model"]
    assert all("careers" not in e["url"] for e in entries)


def test_article_timestamp_accepts_iso_and_rfc822() -> None:
    iso = _parse_ts("2026-10-15T08:00:00+00:00")
    rfc822 = _parse_ts("Thu, 15 Oct 2026 08:00:00 GMT")
    assert iso == rfc822
    assert _parse_ts("not a timestamp") == 0.0


def test_fetch_selection_has_hard_global_and_category_caps() -> None:
    candidates = [
        *[_candidate(i, "vendor", 0) for i in range(200)],
        *[_candidate(1000 + i, "trending", 2) for i in range(40)],
        *[_candidate(2000 + i, "x-ai", 2) for i in range(40)],
    ]

    selected = _select_candidates(candidates)
    assert len(selected) <= 150
    for category in ("vendor", "trending", "x-ai"):
        count = sum(c[2]["category"] == category for c in selected)
        assert count <= _CATEGORY_FETCH_CAPS[category]


def test_fetch_selection_gives_each_feed_a_first_pass() -> None:
    candidates = [
        _candidate(100, "vendor", feed="busy"),
        _candidate(99, "vendor", feed="busy"),
        _candidate(98, "vendor", feed="busy"),
        _candidate(97, "vendor", feed="busy"),
        _candidate(96, "vendor", feed="busy"),
        _candidate(1, "vendor", feed="slow-but-important"),
    ]
    selected = _select_candidates(candidates, global_cap=2)
    assert {c[4] for c in selected} == {"busy", "slow-but-important"}


def test_summary_cohort_caps_trending_and_preserves_source_diversity() -> None:
    articles = []
    for i in range(10):
        articles.append({
            "id": f"trend-{i}", "source": f"trend-{i}", "category": "trending",
            "tier": "low", "importance": 10, "date": f"2026-10-15T{i:02d}:00:00+00:00",
        })
    for i in range(8):
        articles.append({
            "id": f"vendor-{i}", "source": f"lab-{i}", "category": "vendor",
            "tier": "high", "importance": 8, "date": f"2026-10-15T{i:02d}:00:00+00:00",
        })

    selected = _select_summary_cohort(articles, limit=10)
    assert len(selected) == 10
    assert sum(a["category"] == "trending" for a in selected) == 2
    assert sum(a["category"] == "vendor" for a in selected) == 8


def test_summary_cohort_never_relaxes_discovery_ceiling() -> None:
    articles = [{
        "id": f"trend-{i}", "source": "trending", "category": "trending",
        "tier": "low", "importance": 10, "date": f"2026-10-15T{i:02d}:00:00+00:00",
    } for i in range(10)]

    selected = _select_summary_cohort(articles, limit=10)
    assert len(selected) == 2
