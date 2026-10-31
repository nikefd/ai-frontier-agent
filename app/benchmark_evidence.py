"""Retain compact benchmark observations independently of article eviction."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from .benchmark_matching import _parse_date, _normalized_match_text, find_benchmark_match, rule_fingerprint
from .storage import read_json, update_json_atomic


_ARTICLE_FIELDS = ("id", "title", "title_zh", "url", "source", "date", "ingested_at", "event_key")


def retain_match(benchmark: dict, articles: list[dict], now: datetime) -> bool:
    match = find_benchmark_match(articles, benchmark, now)
    if match is None or match[3]:
        return False
    matched_at, article, method, _ = match
    benchmark["evidence"] = {
        "version": 1, "rule_fingerprint": rule_fingerprint(benchmark),
        "recorded_at": now.isoformat(), "matched_at": matched_at.isoformat(),
        "match_method": method,
        "time_basis": "ingested_at" if _parse_date(article.get("ingested_at")) else "published_at",
        "article": {key: article.get(key) for key in _ARTICLE_FIELDS},
        "match_text": _normalized_match_text(" ".join(str(article.get(key) or "") for key in (
            "title", "title_zh", "summary", "summary_zh",
        ))) if method == "match_terms" else "",
    }
    return True


def record_benchmark_matches(path: Path, articles: list[dict], now: datetime | None = None) -> int:
    """Merge under the benchmark lock; a later duplicate cannot replace an earlier hit."""
    if not articles:
        return 0
    current = now or datetime.now(timezone.utc)
    items = read_json(path, [])
    if not isinstance(items, list):
        return 0
    changed_ids = {
        item.get("id") for item in items
        if isinstance(item, dict)
        and (occurred := _parse_date(item.get("occurred_at")))
        and current - timedelta(days=30) <= occurred <= current + timedelta(hours=1)
        and retain_match(dict(item), articles, current)
    }
    if not changed_ids:
        return 0
    changed = 0

    def merge(latest):
        nonlocal changed
        for item in latest if isinstance(latest, list) else []:
            if item.get("id") in changed_ids and retain_match(item, articles, current):
                changed += 1
        return latest

    update_json_atomic(path, [], merge)
    return changed
