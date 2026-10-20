"""Trusted publication-date inference and targeted stored-data repairs."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .settings import settings
from .storage import read_json, write_json_atomic

_DEEPSEEK_NEWS_PATH = re.compile(r"^/news/news(?P<stamp>\d{4}|\d{6})/?$")


def publication_date_from_url(url: str) -> str:
    """Return a trusted ISO date only for URL schemes whose dates are documented.

    DeepSeek's first six API-news slugs used MMDD in 2024; later slugs use
    YYMMDD. Restricting the rule to the official host prevents accidental date
    guesses for unrelated numeric URLs.
    """
    parsed = urlparse(str(url or ""))
    if parsed.hostname != "api-docs.deepseek.com":
        return ""
    match = _DEEPSEEK_NEWS_PATH.fullmatch(parsed.path)
    if not match:
        return ""
    stamp = match.group("stamp")
    raw = f"2024{stamp}" if len(stamp) == 4 else f"20{stamp}"
    try:
        published = datetime.strptime(raw, "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return ""
    return published.isoformat()


def repair_known_publication_dates(
    articles_file: Path | None = None,
    summary_file: Path | None = None,
) -> int:
    """Repair known deterministic dates and invalidate summaries that used them.

    This startup repair is idempotent. It intentionally touches only official
    DeepSeek news URLs whose path encodes the publication date.
    """
    articles_path = articles_file or (
        settings.data_dir / "ai-news" / "articles.json"
    )
    summary_path = summary_file or (
        settings.data_dir / "ai-news" / "summary_today.json"
    )
    articles = read_json(articles_path, [])
    if not isinstance(articles, list):
        return 0

    changed_ids: set[str] = set()
    for article in articles:
        inferred = publication_date_from_url(str(article.get("url") or ""))
        if inferred and article.get("date") != inferred:
            article["date"] = inferred
            if article.get("id"):
                changed_ids.add(str(article["id"]))
    if not changed_ids:
        return 0

    write_json_atomic(articles_path, articles)
    summary = read_json(summary_path, None)
    cohort_ids = {
        str(item.get("id")) for item in ((summary or {}).get("cohort") or [])
        if isinstance(item, dict) and item.get("id")
    }
    if changed_ids & cohort_ids:
        summary_path.unlink(missing_ok=True)
    return len(changed_ids)
