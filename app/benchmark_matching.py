"""Shared deterministic benchmark matching; no storage or router dependencies."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit


def _parse_date(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalized_match_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", text)


def _normalized_url(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return ""
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return ""
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", ""))


def find_live_match(articles: list[dict], benchmark: dict, now: datetime) -> tuple | None:
    occurred = _parse_date(benchmark.get("occurred_at"))
    if occurred is None:
        return None
    source_url = _normalized_url(benchmark.get("source_url"))
    event_key = str(benchmark.get("event_key") or "").strip()
    terms = [normalized for term in (benchmark.get("match_terms") or [])
             if (normalized := _normalized_match_text(term))]
    candidates = []
    for article in articles:
        published = _parse_date(article.get("date"))
        if not published or not (occurred - timedelta(hours=24) <= published <= now + timedelta(hours=1)):
            continue
        method = ""
        if source_url and _normalized_url(article.get("url")) == source_url:
            method = "source_url"
        elif event_key and str(article.get("event_key") or "").strip() == event_key:
            method = "event_key"
        elif terms:
            haystack = _normalized_match_text(" ".join(str(article.get(field) or "") for field in (
                "title", "title_zh", "summary", "summary_zh",
            )))
            if all(term in haystack for term in terms):
                method = "match_terms"
        if method:
            discovered = _parse_date(article.get("ingested_at")) or published
            candidates.append((discovered, article, method))
    return min(candidates, key=lambda item: item[0]) if candidates else None
