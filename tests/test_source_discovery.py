from __future__ import annotations

import pytest

from app.source_discovery import discover_official_sources


@pytest.mark.asyncio
async def test_discovery_validates_same_site_feed_sitemap_and_update_page(monkeypatch) -> None:
    homepage = b"""<html><head>
      <link rel="alternate" type="application/rss+xml" href="/feed.xml">
      <link rel="alternate" type="application/rss+xml" href="/comments/feed/">
    </head><body>
      <a href="/changelog">Changelog</a>
      <a href="/research/tool">Research tool</a>
      <a href="/institutional/inference-simulator/">Research simulator</a>
      <a href="/newsletter-subscription-policy/">Newsletter policy</a>
      <a href="https://tracker.example/changelog">External changelog</a>
    </body></html>"""
    feed = b"""<rss version="2.0"><channel><title>Lab</title>
      <item><title>Release</title><link>https://lab.test/news/release</link>
      <pubDate>Fri, 23 Oct 2026 10:00:00 GMT</pubDate></item>
    </channel></rss>"""
    sitemap = b"""<urlset><url><loc>https://lab.test/news/a</loc><lastmod>2026-10-23</lastmod></url></urlset>"""
    changelog = b"""<html><body><a href="/changelog/a">A</a><a href="/changelog/b">B</a>
      <time>2026-10-23</time><time>2026-10-20</time></body></html>"""
    documents = {
        "https://lab.test/news/model": (homepage, "text/html"),
        "https://lab.test/": (homepage, "text/html"),
        "https://lab.test/feed.xml": (feed, "application/rss+xml"),
        "https://lab.test/comments/feed/": (feed, "application/rss+xml"),
        "https://lab.test/sitemap.xml": (sitemap, "application/xml"),
        "https://lab.test/changelog": (changelog, "text/html"),
        "https://lab.test/research/tool": (
            changelog, "https://lab.test/institutional/tool", "text/html", "utf-8"
        ),
        "https://lab.test/newsletter-subscription-policy/": (changelog, "text/html"),
    }

    async def fake_fetch(url: str, _max_bytes: int):
        if url not in documents:
            raise RuntimeError("not found")
        document = documents[url]
        if len(document) == 4:
            return document
        body, content_type = document
        return body, url, content_type, "utf-8"

    monkeypatch.setattr("app.source_discovery.fetch_public_document", fake_fetch)
    result = await discover_official_sources("https://lab.test/news/model")

    by_kind = {item["kind"]: item for item in result}
    assert by_kind["rss"]["ready"] is True
    assert by_kind["rss"]["dated_entries"] == 1
    assert by_kind["sitemap"]["ready"] is False
    assert by_kind["update_page"]["entry_count"] >= 2
    assert all("tracker.example" not in item["url"] for item in result)
    assert all("comments" not in item["url"] for item in result)
    assert all("inference-simulator" not in item["url"] for item in result)
    assert all("institutional/tool" not in item["url"] for item in result)
    assert all("newsletter-subscription-policy" not in item["url"] for item in result)


@pytest.mark.asyncio
async def test_discovery_deduplicates_redirected_final_urls(monkeypatch) -> None:
    homepage = b"""<html><head>
      <link rel="alternate" type="application/rss+xml" href="/rss.xml">
    </head></html>"""
    feed = b"""<rss version="2.0"><channel><item><title>Release</title>
      <pubDate>Fri, 23 Oct 2026 10:00:00 GMT</pubDate></item></channel></rss>"""

    async def fake_fetch(url: str, _max_bytes: int):
        if url in {"https://lab.test/news/model", "https://lab.test/"}:
            return homepage, url, "text/html", "utf-8"
        if url in {"https://lab.test/rss.xml", "https://lab.test/feed"}:
            return feed, "https://lab.test/feed/", "application/rss+xml", "utf-8"
        raise RuntimeError("not found")

    monkeypatch.setattr("app.source_discovery.fetch_public_document", fake_fetch)
    result = await discover_official_sources("https://lab.test/news/model")

    assert [item["url"] for item in result] == ["https://lab.test/feed/"]


@pytest.mark.asyncio
async def test_discovery_drops_unvalidated_guesses(monkeypatch) -> None:
    async def fake_fetch(url: str, _max_bytes: int):
        if url.endswith("/") or "/news/" in url:
            return b"<html><body>No feeds here</body></html>", url, "text/html", "utf-8"
        raise RuntimeError("not found")

    monkeypatch.setattr("app.source_discovery.fetch_public_document", fake_fetch)
    assert await discover_official_sources("https://quiet.test/news/item") == []
