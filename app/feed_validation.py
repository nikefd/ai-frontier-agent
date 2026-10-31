"""Narrow exceptions for verified feeds with legitimate empty editions."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit


def is_valid_empty_arxiv_feed(feed: dict, source_url: str, now: datetime | None = None) -> bool:
    """Accept a recent, intact daily edition, never an empty HTTP body or HTML."""
    source = urlsplit(source_url)
    if source.hostname != "rss.arxiv.org" or not source.path.startswith("/rss/"):
        return False
    if feed.get("version") != "rss20" or feed.get("bozo") or feed.get("entries"):
        return False
    meta = feed.get("feed") or {}
    category = source.path.removeprefix("/rss/")
    if meta.get("title") != f"{category} updates on arXiv.org":
        return False
    self_links = [urlsplit(item.get("href") or "") for item in meta.get("links", []) if item.get("rel") == "self"]
    if not any(link.hostname == source.hostname and link.path == source.path for link in self_links):
        return False
    try:
        updated = parsedate_to_datetime(meta.get("updated") or "")
        if updated.tzinfo is None:
            return False
        age = ((now or datetime.now(timezone.utc)) - updated).total_seconds()
    except (ValueError, TypeError):
        return False
    return -6 * 3600 <= age <= 72 * 3600
