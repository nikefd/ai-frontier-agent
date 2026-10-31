"""Shared deterministic benchmark matching; no storage or router dependencies."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def _parse_date(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(raw)
        except (ValueError, TypeError, OverflowError):
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
    source_url = _event_url(benchmark.get("source_url"))
    event_key = str(benchmark.get("event_key") or "").strip()
    terms = [normalized for term in (benchmark.get("match_terms") or [])
             if (normalized := _normalized_match_text(term))]
    candidates = []
    for article in articles:
        published = _parse_date(article.get("date"))
        if not published or not (occurred - timedelta(hours=24) <= published <= now + timedelta(hours=1)):
            continue
        method = ""
        if source_url and _event_url(article.get("url")) == source_url:
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
            if discovered <= now + timedelta(hours=1):
                candidates.append((discovered, article, method))
    return min(candidates, key=lambda item: item[0]) if candidates else None


def _event_url(value: object) -> str:
    """Different release-note anchors identify different events on one page."""
    base = _normalized_url(value)
    if not base:
        return ""
    parts = urlsplit(str(value))
    query = urlencode(sorted((key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True)
                             if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}))
    return base + ("?" + query if query else "") + ("#" + parts.fragment if parts.fragment else "")


def rule_fingerprint(benchmark: dict) -> str:
    import hashlib
    import json
    rule = {
        "occurred_at": str(_parse_date(benchmark.get("occurred_at"))),
        "source_url": _event_url(benchmark.get("source_url")),
        "event_key": str(benchmark.get("event_key") or "").strip(),
        "match_terms": sorted({_normalized_match_text(term) for term in (benchmark.get("match_terms") or [])}),
    }
    return hashlib.sha256(json.dumps(rule, sort_keys=True).encode()).hexdigest()


def _saved_match(benchmark: dict, now: datetime) -> tuple | None:
    evidence = benchmark.get("evidence")
    if not isinstance(evidence, dict) or evidence.get("version") != 1:
        return None
    if evidence.get("rule_fingerprint") != rule_fingerprint(benchmark):
        return None
    article = evidence.get("article")
    if not isinstance(article, dict):
        return None
    candidate = find_live_match([{**article, "summary": evidence.get("match_text") or ""}], benchmark, now)
    if not candidate or candidate[0] != _parse_date(evidence.get("matched_at")):
        return None
    if candidate[2] != evidence.get("match_method"):
        return None
    return candidate


def find_benchmark_match(articles: list[dict], benchmark: dict, now: datetime) -> tuple | None:
    """Prefer the earliest verified observation, whether live or retained."""
    live = find_live_match(articles, benchmark, now)
    saved = _saved_match(benchmark, now)
    if saved and (not live or saved[0] <= live[0]):
        return (*saved, True)
    return (*live, False) if live else None
