"""A valid no-paper arXiv edition must not mask damaged or stale feeds."""
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import feedparser
import httpx
import pytest

from app.feed_validation import is_valid_empty_arxiv_feed
from app.workers.ai_news_fetcher import _fetch_feed

NOW = datetime(2026, 10, 31, 6, tzinfo=timezone.utc)
URL = "https://rss.arxiv.org/rss/cs.CL"


def _empty(date=NOW):
    return f'''<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>
    <title>cs.CL updates on arXiv.org</title><lastBuildDate>{format_datetime(date)}</lastBuildDate>
    <atom:link href="http://rss.arxiv.org/rss/cs.CL" rel="self" type="application/rss+xml"/>
    </channel></rss>'''.encode()


def test_empty_arxiv_requires_fresh_intact_matching_channel():
    assert is_valid_empty_arxiv_feed(feedparser.parse(_empty()), URL, NOW)
    for body in (b"", b"<html>Blocked</html>", _empty(NOW - timedelta(days=4)),
                 _empty(NOW + timedelta(days=1)), _empty().replace(b'cs.CL', b'cs.AI'),
                 _empty().replace(b'rel="self"', b'rel="alternate"'), _empty()[:-10]):
        assert not is_valid_empty_arxiv_feed(feedparser.parse(body), URL, NOW)


@pytest.mark.asyncio
async def test_only_opted_in_arxiv_empty_edition_counts_as_success():
    body = _empty(datetime.now(timezone.utc))
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body))) as client:
        entries, _, error = await _fetch_feed(client, URL)
        assert entries == [] and error is None
        entries, _, error = await _fetch_feed(client, "https://unknown.test/feed")
        assert entries == [] and error


@pytest.mark.asyncio
async def test_empty_success_recovers_transport_without_fabricating_content_date(monkeypatch):
    import app.workers.ai_news_fetcher as fetcher
    old = {"last_error": "feed contained no parseable entries", "consecutive_failures": 4,
           "latest_entry_at": "2026-10-28T00:00:00Z"}
    saved = {}
    async def empty(_client, _url):
        return [], "arXiv cs.CL", None
    monkeypatch.setattr(fetcher, "_fetch_feed_with_host_policy", empty)
    monkeypatch.setattr(fetcher, "_load_sources_meta", lambda: {URL: old.copy()})
    monkeypatch.setattr(fetcher, "_save_sources_meta", lambda data: saved.update(data))
    assert await fetcher._fetch_once([URL]) == 0
    assert saved[URL]["last_error"] is None
    assert saved[URL]["consecutive_failures"] == 0
    assert saved[URL]["latest_entry_at"] == old["latest_entry_at"]
    assert saved[URL]["quality_samples"][-1]["parsed"] == 0
