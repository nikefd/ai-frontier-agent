"""Regression tests for source gating and editorial cohort selection."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.routers.ai_news import (
    _CATEGORY_FETCH_CAPS,
    _dedupe_summary_articles,
    _parse_ts,
    _select_summary_cohort,
    _summary_fingerprint,
)
from app.workers.ai_news_fetcher import (
    _decide_relevance,
    _entries_from_sitemap,
    _fetch_feed,
    _fetch_feed_with_host_policy,
    _fetch_once,
    _canonical_feed_url,
    _limit_source_entries,
    _parse_gemini_changelog_entries,
    _parse_github_repositories,
    _parse_github_releases,
    _parse_html_listing_entries,
    _parse_hf_daily_papers,
    _parse_liblib_articles,
    _parse_openai_changelog_entries,
    _parse_openrouter_models,
    _parse_page_metadata,
    _parse_qwen_api_entries,
    _parse_sitemap_index,
    _parse_sitemap_entries,
    _parse_stepfun_news_bundle,
    _request_headers,
    _select_candidates,
)
from app.publication_dates import publication_date_from_url, repair_known_publication_dates
from app.storage import read_json, write_json_atomic


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
    assert _decide_relevance(generic, "med", "community", curated=True) == (True, "curated")


def test_source_registry_uses_ai2_instead_of_unreliable_stanford_sitemap() -> None:
    from app.routers.ai_news import DEFAULT_FEED_SPECS

    urls = {spec["url"] for spec in DEFAULT_FEED_SPECS}
    assert "https://allenai.org/rss.xml" in urls
    assert "https://hai.stanford.edu/sitemap.xml" not in urls


def test_source_registry_includes_verified_official_ai_feeds() -> None:
    from app.routers.ai_news import DEFAULT_FEED_SPECS

    urls = {spec["url"] for spec in DEFAULT_FEED_SPECS}
    by_url = {spec["url"]: spec for spec in DEFAULT_FEED_SPECS}
    assert len(DEFAULT_FEED_SPECS) == 115
    assert len(urls) == len(DEFAULT_FEED_SPECS)
    assert {
        "https://engineering.fb.com/category/ai-research/feed/",
        "https://engineering.fb.com/category/ml-applications/feed/",
        "https://api.github.com/repos/pytorch/pytorch/releases?per_page=20",
        "https://cloudblog.withgoogle.com/products/ai-machine-learning/rss/",
        "https://blog.cloudflare.com/tag/ai/rss/",
        "https://www.together.ai/blog/rss.xml",
        "https://ollama.com/blog/rss.xml",
        "https://developers.openai.com/api/docs/changelog.md",
        "https://platform.claude.com/docs/en/release-notes/feed.xml",
        "https://ai.google.dev/gemini-api/docs/changelog",
        "https://cursor.com/changelog/rss.xml",
        "https://blog.replit.com/feed.xml",
        "https://lovable.dev/blog/rss.xml",
        "https://www.minimax.io/sitemap.xml",
        "https://www.kimi.com/en/blog/",
        "https://docs.cohere.com/v1/changelog",
        "https://huggingface.co/api/daily_papers?limit=100",
        "https://api-docs.deepseek.com/sitemap.xml",
        "https://www.langchain.com/sitemap.xml",
        "https://mlflow.org/blog/rss.xml",
        "https://api.github.com/repos/xai-org/xai-sdk-python/releases?per_page=20",
        "https://api.github.com/repos/huggingface/transformers/releases?per_page=20",
        "https://api.github.com/repos/vllm-project/vllm/releases?per_page=20",
        "https://app.klingai.com/global/blog?tab=product-features",
        "https://api2.liblib.art/api/www/community/article/list?page=1&pageSize=20&type=5",
        "https://manus.im/blog?kind=PRODUCT",
        "https://runway.com/changelog",
        "https://elevenlabs.io/blog/rss.xml",
        "https://stability.ai/news-updates?format=rss",
        "https://www.cerebras.ai/sitemap.xml",
        "https://fireworks.ai/sitemap.xml",
        "https://modal.com/sitemap.xml",
        "https://seed.bytedance.com/sitemap.xml",
        "https://www.pi.website/blog",
        "https://www.stepfun.com/news",
        "https://api.github.com/orgs/zai-org/repos?sort=created&direction=desc&per_page=20",
        "https://openrouter.ai/api/v1/models",
        "https://api.github.com/repos/sgl-project/sglang/releases?per_page=20",
        "https://artificialanalysis.ai/articles",
        "https://metr.org/blog/",
    } <= urls
    assert by_url["https://huggingface.co/api/daily_papers?limit=100"]["source_priority"] == 1
    arxiv_urls = {
        "https://export.arxiv.org/rss/cs.AI",
        "https://export.arxiv.org/rss/cs.CL",
        "https://export.arxiv.org/rss/cs.CV",
        "https://export.arxiv.org/rss/cs.LG",
    }
    assert all(by_url[url]["max_per_fetch"] == 2 for url in arxiv_urls)
    assert all(by_url[url]["host_throttle"] == "arxiv" for url in arxiv_urls)
    assert by_url[
        "https://mshibanami.github.io/GitHubTrendingRSS/daily/all.xml"
    ]["snapshot_date_from_feed"] is True
    assert all(
        by_url[url].get("format") == "html_listing"
        for url in {
            "https://app.klingai.com/global/blog?tab=product-features",
            "https://manus.im/blog?kind=PRODUCT",
            "https://runway.com/changelog",
            "https://www.kimi.com/en/blog/",
            "https://docs.cohere.com/v1/changelog",
        }
    )
    assert "https://ltx.io/release-notes" not in urls


def test_official_html_listing_adapter_handles_linked_and_single_page_updates() -> None:
    linked_page = b'''<a class="card" href="/blog/new-agent">
      <h2 title="Introducing New Agent">Introducing New Agent</h2>
      <span class="date">October 13, 2026</span>
      <p>Build and run a practical workflow.</p>
    </a>'''
    linked = _parse_html_listing_entries(linked_page, "https://startup.test/blog", {
        "item_selector": "a.card", "title_selector": "h2",
        "date_selector": ".date", "summary_selector": "p",
    })
    assert linked == [{
        "title": "Introducing New Agent",
        "url": "https://startup.test/blog/new-agent",
        "date": "2026-10-13T00:00:00+00:00",
        "summary": "Build and run a practical workflow.",
        "tags": [],
    }]

    changelog = b'''<div class="update"><time>Oct 9, 2026</time>
      <h2>Studio Desktop</h2><p>Local video creation update.</p></div>'''
    entries = _parse_html_listing_entries(changelog, "https://studio.test/release-notes", {
        "item_selector": ".update", "title_selector": "h2",
        "date_selector": "time", "summary_selector": "p", "link_mode": "fragment",
    })
    assert entries[0]["url"] == (
        "https://studio.test/release-notes#2026-10-09-studio-desktop"
    )


def test_liblib_official_api_adapter_keeps_truthful_dates_and_links() -> None:
    entries = _parse_liblib_articles({"data": [{
        "uuid": "abc123",
        "title": "LiblibAI 上线新模型",
        "description": "官方产品更新",
        "createTime": 1792371600,
        "updateTime": 1792458000,
    }]})

    assert entries == [{
        "title": "LiblibAI 上线新模型",
        "url": "https://www.liblib.art/teaching/abc123",
        "date": "2026-10-19T01:00:00+00:00",
        "summary": "官方产品更新",
        "tags": [],
    }]


@pytest.mark.asyncio
async def test_daily_trending_uses_truthful_channel_snapshot_date() -> None:
    url = "https://mshibanami.github.io/GitHubTrendingRSS/daily/all.xml"

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == url
        return httpx.Response(200, content=b'''<rss><channel>
          <title>GitHub Daily Trending Repositories</title>
          <pubDate>Thu, 22 Oct 2026 05:37:43 GMT</pubDate>
          <item><title>example/ai-agent</title>
          <link>https://github.com/example/ai-agent</link>
          <description>Open-source AI agent framework</description></item>
        </channel></rss>''')

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        entries, _, error = await _fetch_feed(client, url)

    assert error is None
    assert entries[0]["date"] == "Thu, 22 Oct 2026 05:37:43 GMT"


@pytest.mark.asyncio
async def test_unsorted_rss_is_normalized_to_newest_first() -> None:
    url = "https://blog.replit.com/feed.xml"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b'''<rss><channel><title>Replit</title>
          <item><title>Older</title><link>https://replit.com/blog/older</link>
          <pubDate>Wed, 26 Mar 2025 19:11:36 GMT</pubDate></item>
          <item><title>Newest</title><link>https://replit.com/blog/newest</link>
          <pubDate>Fri, 16 Oct 2026 09:30:00 GMT</pubDate></item>
        </channel></rss>''')

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        entries, _, error = await _fetch_feed(client, url)

    assert error is None
    assert [entry["title"] for entry in entries] == ["Newest", "Older"]


def test_unstable_sources_use_verified_replacements_and_scoped_headers() -> None:
    from app.routers.ai_news import DEFAULT_FEED_SPECS

    by_url = {spec["url"]: spec for spec in DEFAULT_FEED_SPECS}
    assert "https://www.oneusefulthing.org/feed" in by_url
    assert "https://rss.app/feeds/83CQGxSgKZmSqKb5.xml" not in by_url
    assert "https://www.reddit.com/r/MachineLearning/new/.rss" not in by_url
    assert by_url["https://jack-clark.net/feed/"]["curated"] is True
    assert "https://rsshub.app/deepseek/news" not in by_url
    assert "https://rsshub.app/yuque/wikidesign/vngzgk" not in by_url
    assert not any(url.startswith("https://rss.zslren.com/") for url in by_url)
    assert by_url["https://quaily.com/op7418/feed/atom"]["curated"] is True
    assert by_url[
        "https://justlovemaki.github.io/CloudFlare-AI-Insight-Daily/rss.xml"
    ]["curated"] is True
    assert "https://x.ai/sitemap.xml" not in by_url
    assert "https://pytorch.org/blog/feed/" not in by_url
    assert not any(spec["name"] in {"Riley Brown", "vas"} for spec in DEFAULT_FEED_SPECS)
    assert _request_headers(
        "https://api.github.com/repos/pytorch/pytorch/releases?per_page=20",
    )["X-GitHub-Api-Version"] == "2022-11-28"
    assert "Mozilla/5.0" in _request_headers("https://venturebeat.com/category/ai/feed/")["User-Agent"]
    assert _request_headers("https://www.reddit.com/r/LocalLLaMA/.rss")["User-Agent"].startswith(
        "ai-frontier-agent/",
    )


@pytest.mark.asyncio
async def test_transient_feed_failure_is_retried_once(monkeypatch) -> None:
    url = "https://venturebeat.com/category/ai/feed/"
    calls = 0

    async def no_sleep(_delay):
        return None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, content=b"try again")
        return httpx.Response(200, content=b'''<rss><channel><title>PyTorch</title>
          <item><title>PyTorch 3 released</title><link>https://pytorch.org/blog/v3</link></item>
        </channel></rss>''')

    monkeypatch.setattr("app.workers.ai_news_fetcher.asyncio.sleep", no_sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        entries, title, error = await _fetch_feed(client, url)

    assert calls == 2
    assert error is None
    assert title == "PyTorch"
    assert entries[0]["title"] == "PyTorch 3 released"


def test_github_release_adapter_keeps_first_party_release_metadata() -> None:
    entries = _parse_github_releases([
        {
            "name": "PyTorch 2.14.1 Release",
            "tag_name": "v2.14.1",
            "html_url": "https://github.com/pytorch/pytorch/releases/tag/v2.14.1",
            "published_at": "2026-09-30T19:14:48Z",
            "body": "## Highlights\n- Adds [feature](https://pytorch.org/docs/feature).",
            "draft": False,
            "prerelease": False,
        },
        {
            "name": "Ignored draft",
            "html_url": "https://github.com/example/draft",
            "created_at": "2026-10-01T00:00:00Z",
            "draft": True,
        },
    ])

    assert entries == [{
        "title": "PyTorch 2.14.1 Release",
        "url": "https://github.com/pytorch/pytorch/releases/tag/v2.14.1",
        "date": "2026-09-30T19:14:48Z",
        "summary": "Highlights - Adds feature.",
        "tags": ["开源"],
    }]


@pytest.mark.asyncio
async def test_arxiv_feeds_are_serialized_to_avoid_burst_limits(monkeypatch) -> None:
    import app.workers.ai_news_fetcher as fetcher

    active = 0
    max_active = 0

    async def fake_fetch(_client, _url):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return [], "arXiv", None

    monkeypatch.setattr(fetcher, "_fetch_feed", fake_fetch)
    monkeypatch.setattr(fetcher, "_HOST_THROTTLE_SECONDS", 0)
    urls = [
        "https://export.arxiv.org/rss/cs.AI",
        "https://export.arxiv.org/rss/cs.CL",
    ]
    async with httpx.AsyncClient() as client:
        await asyncio.gather(*(
            _fetch_feed_with_host_policy(client, url) for url in urls
        ))

    assert max_active == 1


@pytest.mark.asyncio
async def test_fetch_rejects_missing_and_future_publication_dates(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    entries = [
        {"title": "New LLM valid", "url": "https://example.test/valid",
         "source": "Test feed", "summary": "AI",
         "date": (now - timedelta(hours=1)).isoformat(), "tags": []},
        {"title": "New LLM undated", "url": "https://example.test/undated",
         "source": "Test feed", "summary": "AI", "date": "", "tags": []},
        {"title": "New LLM future", "url": "https://example.test/future",
         "source": "Test feed", "summary": "AI",
         "date": (now + timedelta(days=1)).isoformat(), "tags": []},
    ]
    saved_meta = {}
    persisted = []

    async def fake_fetch(_client, _url):
        return entries, "Test feed", None

    monkeypatch.setattr("app.workers.ai_news_fetcher._fetch_feed", fake_fetch)
    monkeypatch.setattr("app.workers.ai_news_fetcher._load_sources_meta", lambda: {})
    monkeypatch.setattr(
        "app.workers.ai_news_fetcher._save_sources_meta",
        lambda value: saved_meta.update(value),
    )
    monkeypatch.setattr(
        "app.workers.ai_news_fetcher.add_article",
        lambda article: persisted.append(article) or {"ok": True},
    )

    assert await _fetch_once(["https://example.test/feed.xml"]) == 1
    assert [article.url for article in persisted] == ["https://example.test/valid"]
    assert saved_meta["https://example.test/feed.xml"]["last_invalid_date"] == 2


def test_hf_daily_papers_rank_by_curation_signal_and_expose_code() -> None:
    payload = [
        {"paper": {"id": "2610.00001", "title": "Low signal", "upvotes": 2,
                   "submittedOnDailyAt": "2026-10-16T00:00:00Z", "summary": "Abstract"}},
        {"paper": {"id": "2610.00002v2", "title": "High signal", "upvotes": 120,
                   "submittedOnDailyAt": "2026-10-16T00:00:00Z",
                   "ai_summary": "A practical agent benchmark.",
                   "githubRepo": "https://github.com/example/repo", "githubStars": 80}},
    ]
    entries = _parse_hf_daily_papers(payload)

    assert [entry["title"] for entry in entries] == ["High signal", "Low signal"]
    assert entries[0]["url"] == "https://huggingface.co/papers/2610.00002"
    assert entries[0]["_dedupe_url"] == "https://arxiv.org/abs/2610.00002"
    assert "120 community upvotes" in entries[0]["summary"]
    assert "80 GitHub stars" in entries[0]["summary"]
    assert entries[0]["tags"] == ["论文", "开源"]


def test_arxiv_urls_and_raw_feed_caps_are_normalized() -> None:
    assert _canonical_feed_url("http://arxiv.org/abs/2610.00002v3") == (
        "https://arxiv.org/abs/2610.00002"
    )
    entries = [
        {"title": "old", "date": "2026-10-14"},
        {"title": "new", "date": "2026-10-16"},
        {"title": "middle", "date": "2026-10-15"},
    ]
    assert [entry["title"] for entry in _limit_source_entries(
        entries, {"max_per_fetch": 2},
    )] == ["new", "middle"]


def test_openai_changelog_adapter_keeps_individual_updates_and_dates() -> None:
    changelog = b"""# Changelog
## October, 2026
### Oct 16
Feature \xc2\xb7 Model: gpt-live-1

Released [prompt-to-voice](/api/docs/guides/custom-voices) for all API customers.
### Oct 15
Update

Added native [Decisions integration](/api/docs/guides/decisions-voice).
### Oct 15
Feature

Updated the [same guide](/api/docs/guides/decisions-voice) with examples.
"""
    entries = _parse_openai_changelog_entries(changelog)

    assert [entry["date"][:10] for entry in entries] == [
        "2026-10-16", "2026-10-15", "2026-10-15",
    ]
    assert entries[0]["title"] == "Released prompt-to-voice for all API customers."
    assert entries[0]["url"] == "https://developers.openai.com/api/docs/guides/custom-voices"
    assert entries[2]["url"].startswith(
        "https://developers.openai.com/api/docs/changelog#2026-10-15-",
    )


def test_gemini_changelog_adapter_splits_release_note_items() -> None:
    page = b'''<div class="devsite-article-body">
      <h2 id="10-13-2026">October 13, 2026</h2>
      <ul>
        <li><strong>Gemini 4 Argon generally available</strong>: Released
          <a href="/gemini-api/docs/models/gemini-4-argon">Gemini 4 Argon</a>.</li>
        <li><strong>Legacy model deprecation</strong>: Migrate before shutdown.</li>
      </ul>
    </div>'''
    entries = _parse_gemini_changelog_entries(page)

    assert [entry["title"] for entry in entries] == [
        "Gemini 4 Argon generally available", "Legacy model deprecation",
    ]
    assert entries[0]["url"] == "https://ai.google.dev/gemini-api/docs/models/gemini-4-argon"
    assert entries[1]["url"].endswith("#10-13-2026-2")
    assert all(entry["date"].startswith("2026-10-13") for entry in entries)


@pytest.mark.asyncio
async def test_changelog_structure_break_is_reported_as_source_error() -> None:
    url = "https://developers.openai.com/api/docs/changelog.md"

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == url
        return httpx.Response(200, content=b"# Changelog\nUnexpected layout")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        entries, title, error = await _fetch_feed(client, url)

    assert entries == []
    assert title == "OpenAI API Changelog"
    assert error == "OpenAI changelog contained no parseable updates"


@pytest.mark.asyncio
async def test_empty_or_non_feed_response_is_reported_as_source_error() -> None:
    url = "https://example.com/feed.xml"

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html><body>Access denied</body></html>")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        entries, _title, error = await _fetch_feed(client, url)

    assert entries == []
    assert error is not None
    assert error.startswith("feed contained no parseable entries")


def test_official_sitemap_adapter_filters_and_sorts_paths() -> None:
    xml = b"""<?xml version="1.0"?><urlset>
      <url><loc>https://lab.test/careers</loc><lastmod>2026-10-15</lastmod></url>
      <url><loc>https://lab.test/news/older-model</loc><lastmod>2026-10-13</lastmod></url>
      <url><loc>https://lab.test/research/new-safety-work</loc><lastmod>2026-10-14</lastmod></url>
    </urlset>"""
    entries = _parse_sitemap_entries(xml, ["/news/", "/research/"])
    assert [e["title"] for e in entries] == ["New Safety Work", "Older Model"]
    assert all("careers" not in e["url"] for e in entries)


def test_official_sitemap_adapter_excludes_known_non_product_paths() -> None:
    xml = b"""<?xml version="1.0"?><urlset>
      <url><loc>https://lab.test/blog/model-release</loc><lastmod>2026-10-15</lastmod></url>
      <url><loc>https://lab.test/blog/campus-recruitment</loc><lastmod>2026-10-16</lastmod></url>
    </urlset>"""
    entries = _parse_sitemap_entries(
        xml, ["/blog/"], ["/blog/campus-recruitment"],
    )

    assert [entry["title"] for entry in entries] == ["Model Release"]


def test_official_sitemap_adapter_recovers_entries_after_malformed_xml() -> None:
    xml = b"""<?xml version="1.0"?><urlset>
      <url><loc>https://lab.test/about?one=1&amp;two=2</loc></url>
      <broken>&unescaped</broken>
      <url><loc>https://lab.test/blog/model-release</loc><lastmod>2026-10-15</lastmod></url>
    </urlset>"""

    entries = _parse_sitemap_entries(xml, ["/blog/"])

    assert [entry["title"] for entry in entries] == ["Model Release"]


def test_openrouter_model_catalog_becomes_dated_availability_signals() -> None:
    entries = _parse_openrouter_models({"data": [
        {
            "id": "lab/model-new", "name": "Model New", "created": 1792108800,
            "context_length": 200000, "description": "A practical frontier model.",
        },
        {
            "id": "lab/model-old", "name": "Model Old", "created": 1760572800,
            "context_length": 32000,
        },
    ]})

    assert [entry["title"] for entry in entries] == [
        "Available on OpenRouter: Model New",
        "Available on OpenRouter: Model Old",
    ]
    assert entries[0]["url"] == "https://openrouter.ai/lab/model-new"
    assert "200,000 tokens" in entries[0]["summary"]
    assert entries[0]["date"].startswith("2026-10-16")


def test_github_organization_adapter_ignores_forks_and_archived_repositories() -> None:
    entries = _parse_github_repositories([
        {"full_name": "lab/new", "html_url": "https://github.com/lab/new",
         "created_at": "2026-10-16T12:00:00Z", "description": "New model tools."},
        {"full_name": "lab/fork", "html_url": "https://github.com/lab/fork",
         "created_at": "2026-10-17T12:00:00Z", "fork": True},
        {"full_name": "lab/archived", "html_url": "https://github.com/lab/archived",
         "created_at": "2026-10-18T12:00:00Z", "archived": True},
        {"full_name": "lab/old", "html_url": "https://github.com/lab/old",
         "created_at": "2026-10-15T12:00:00Z"},
    ])

    assert [entry["title"] for entry in entries] == ["lab/new", "lab/old"]
    assert entries[0]["tags"] == ["开源"]


def test_stepfun_bundle_adapter_extracts_dated_news_and_decodes_titles() -> None:
    bundle = (
        b'const n=[{slug:"step-older",date:"2026-10-14",dateLabel:"Oct 14",'
        b'title:"Older"},{slug:"step-new",date:"2026-10-16",dateLabel:"Oct 16",'
        b'title:"New \\u6a21\\u578b"}]'
    )
    entries = _parse_stepfun_news_bundle(bundle)

    assert [entry["title"] for entry in entries] == ["New 模型", "Older"]
    assert entries[0]["url"] == "https://www.stepfun.com/news/step-new"
    assert entries[0]["date"].startswith("2026-10-16")


def test_deepseek_sitemap_dates_are_inferred_from_official_news_paths() -> None:
    xml = b"""<?xml version="1.0"?><urlset>
      <url><loc>https://api-docs.deepseek.com/news/news1120</loc></url>
      <url><loc>https://api-docs.deepseek.com/news/news261017</loc></url>
      <url><loc>https://api-docs.deepseek.com/guides/news261018</loc></url>
    </urlset>"""
    entries = _parse_sitemap_entries(xml, ["/news/"])

    assert [entry["url"].rsplit("/", 1)[-1] for entry in entries] == [
        "news261017", "news1120",
    ]
    assert entries[0]["date"].startswith("2026-10-17")
    assert entries[1]["date"].startswith("2024-11-20")
    assert publication_date_from_url("https://example.com/news/news261017") == ""


def test_sitemap_index_extracts_child_sitemaps() -> None:
    xml = b"""<?xml version="1.0"?><sitemapindex>
      <sitemap><loc>https://lab.test/news-sitemap.xml</loc></sitemap>
      <sitemap><loc>https://lab.test/research-sitemap.xml</loc></sitemap>
    </sitemapindex>"""
    assert _parse_sitemap_index(xml) == [
        "https://lab.test/news-sitemap.xml",
        "https://lab.test/research-sitemap.xml",
    ]


def test_official_page_metadata_prefers_editorial_fields_and_jsonld_date() -> None:
    page = b'''<html><head>
      <meta property="og:title" content="Model X &amp; Safety">
      <meta property="og:description" content="  A safer   frontier model. ">
      <script type="application/ld+json">
        {"@type":"NewsArticle","datePublished":"2026-10-16T08:00:00Z"}
      </script>
    </head></html>'''
    assert _parse_page_metadata(page) == {
        "title": "Model X & Safety",
        "summary": "A safer frontier model.",
        "date": "2026-10-16T08:00:00Z",
    }


def test_official_page_metadata_reads_leading_visible_publication_date() -> None:
    page = b'''<html><head><title>Release</title></head><body><article>
      <h1>DeepSeek-R1-Lite Release</h1><p>2024/11/20</p><p>Released today.</p>
    </article></body></html>'''
    parsed = _parse_page_metadata(page)

    assert parsed["title"] == "DeepSeek-R1-Lite Release"
    assert parsed["date"].startswith("2024-11-20")


def test_stored_deepseek_dates_are_repaired_and_stale_summary_invalidated(tmp_path) -> None:
    articles_file = tmp_path / "articles.json"
    summary_file = tmp_path / "summary_today.json"
    write_json_atomic(articles_file, [{
        "id": "a_old", "source": "DeepSeek 新闻",
        "url": "https://api-docs.deepseek.com/news/news1120",
        "date": "2026-10-19T15:10:03+00:00",
    }])
    write_json_atomic(summary_file, {"cohort": [{"id": "a_old"}], "body": "stale"})

    assert repair_known_publication_dates(articles_file, summary_file) == 1
    assert read_json(articles_file, [])[0]["date"].startswith("2024-11-20")
    assert not summary_file.exists()
    assert repair_known_publication_dates(articles_file, summary_file) == 0


def test_today_cohort_never_falls_back_to_old_undated_or_future_items(monkeypatch) -> None:
    import app.routers.ai_news as news

    now = datetime.now(timezone.utc)
    articles = [
        {"id": "recent", "title": "Recent", "url": "https://example.test/recent",
         "source": "Lab", "date": (now - timedelta(hours=2)).isoformat()},
        {"id": "old", "title": "Old", "url": "https://example.test/old",
         "source": "Lab", "date": (now - timedelta(days=3)).isoformat()},
        {"id": "future", "title": "Future", "url": "https://example.test/future",
         "source": "Lab", "date": (now + timedelta(days=1)).isoformat()},
        {"id": "undated", "title": "Undated", "url": "https://example.test/undated",
         "source": "Lab", "date": None},
    ]
    monkeypatch.setattr(news, "_load_articles", lambda: articles)

    assert [article["id"] for article in news._articles_for_today()] == ["recent"]


@pytest.mark.asyncio
async def test_sitemap_entries_are_hydrated_from_official_pages() -> None:
    sitemap = b'''<urlset><url>
      <loc>https://lab.test/news/model-x</loc><lastmod>2026-10-16</lastmod>
    </url></urlset>'''

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://lab.test/news/model-x"
        return httpx.Response(200, content=b'''<html><head>
          <meta property="og:title" content="Introducing Model X">
          <meta name="description" content="First-party release details.">
          <meta property="article:published_time" content="2026-10-15T09:30:00Z">
        </head></html>''')

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        entries = await _entries_from_sitemap(
            client, "https://lab.test/sitemap.xml", sitemap, ["/news/"],
        )

    assert entries == [{
        "title": "Introducing Model X",
        "url": "https://lab.test/news/model-x",
        "date": "2026-10-15T09:30:00Z",
        "summary": "First-party release details.",
        "tags": [],
    }]


def test_qwen_api_adapter_cleans_sorts_and_limits_entries() -> None:
    payload = {"data": {"articles": [
        {"title": "Older", "path": "older", "extra": {
            "date": "2026-10-13T08:00:00+08:00", "introduction": "<b>Old</b> summary",
        }},
        {"title": "Newest", "path": "newest", "extra": {
            "date": "2026-10-15T08:00:00+08:00", "introduction": "<p>New summary</p>",
        }},
    ]}}
    entries = _parse_qwen_api_entries(payload)
    assert [e["title"] for e in entries] == ["Newest", "Older"]
    assert entries[0]["url"] == "https://qwen.ai/blog?id=newest"
    assert entries[0]["summary"] == "New summary"


def test_article_timestamp_accepts_iso_and_rfc822() -> None:
    iso = _parse_ts("2026-10-15T08:00:00+00:00")
    rfc822 = _parse_ts("Thu, 15 Oct 2026 08:00:00 GMT")
    assert iso == rfc822
    assert _parse_ts("not a timestamp") == 0.0


def test_fetch_selection_has_hard_global_and_category_caps() -> None:
    assert sum(_CATEGORY_FETCH_CAPS.values()) == 150
    assert _CATEGORY_FETCH_CAPS["vendor"] == 46
    assert _CATEGORY_FETCH_CAPS["paper"] == 14
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


def test_fetch_selection_deduplicates_urls_across_feeds() -> None:
    duplicate_a = _candidate(10, "vendor", feed="official")
    duplicate_b = _candidate(9, "media", feed="media")
    duplicate_a[2]["url"] = "https://lab.test/release"
    duplicate_b[2]["url"] = "https://lab.test/release"
    unique = _candidate(8, "media", feed="media")
    unique[2]["url"] = "https://media.test/analysis"

    selected = _select_candidates([duplicate_a, duplicate_b, unique], global_cap=3)
    assert [c[2]["url"] for c in selected].count("https://lab.test/release") == 1
    assert len(selected) == 2


def test_curated_paper_wins_over_raw_arxiv_duplicate() -> None:
    curated = _candidate(10, "paper", tier_rank=0, feed="hf-daily")
    curated[2].update({
        "url": "https://huggingface.co/papers/2610.00002",
        "_dedupe_url": "https://arxiv.org/abs/2610.00002",
    })
    raw = _candidate(9, "paper", tier_rank=1, feed="arxiv")
    raw[2]["url"] = "http://arxiv.org/abs/2610.00002v2"

    selected = _select_candidates([raw, curated], global_cap=2)

    assert len(selected) == 1
    assert selected[0][4] == "hf-daily"


def test_summary_exact_headline_dedupe_prefers_official_source() -> None:
    media = {
        "id": "media", "title": "Introducing Model X!", "source": "Media",
        "category": "media", "tier": "med", "importance": 10,
    }
    official = {
        "id": "official", "title": "Introducing Model X", "source": "Lab",
        "category": "vendor", "tier": "high", "importance": 8,
    }
    result = _dedupe_summary_articles([media, official])
    assert len(result) == 1
    assert result[0]["id"] == "official"
    assert result[0]["related_articles"][0]["source"] == "Media"


def test_summary_event_dedupe_keeps_official_and_records_corroboration() -> None:
    media = {
        "id": "media", "title": "Model X changes the coding market", "source": "Media",
        "category": "media", "tier": "med", "importance": 10,
        "event_key": "lab-release-model-x", "url": "https://media.test/x",
    }
    official = {
        "id": "official", "title": "Introducing Model X", "source": "Lab",
        "category": "vendor", "tier": "high", "importance": 8,
        "event_key": "lab-release-model-x", "url": "https://lab.test/x",
    }
    result = _dedupe_summary_articles([media, official])
    assert len(result) == 1
    assert result[0]["id"] == "official"
    assert result[0]["related_articles"] == [{
        "id": "media", "title": "Model X changes the coding market",
        "source": "Media", "url": "https://media.test/x",
    }]


def test_exact_headline_dedupe_survives_partial_event_key_backfill() -> None:
    legacy = {
        "id": "legacy", "title": "Introducing Model X", "source": "Media",
        "category": "media", "importance": 9,
    }
    enriched = {
        "id": "official", "title": "Introducing Model X", "source": "Lab",
        "category": "vendor", "importance": 8, "event_key": "lab-release-model-x",
    }
    result = _dedupe_summary_articles([legacy, enriched])
    assert len(result) == 1
    assert result[0]["id"] == "official"


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


def test_summary_fingerprint_is_stable_and_tracks_material_changes() -> None:
    article = {
        "id": "a1", "title": "Model X", "summary": "Released today",
        "source": "Lab", "category": "vendor", "importance": 9,
        "hands_on": "Try the playground", "url": "https://lab.test/x",
    }
    original = _summary_fingerprint([article])
    assert original == _summary_fingerprint([dict(article)])
    assert original != _summary_fingerprint([{**article, "hands_on": "Run the quickstart"}])


@pytest.mark.asyncio
async def test_scheduled_summary_skips_unchanged_cohort_but_manual_force_runs(
    tmp_path, monkeypatch,
) -> None:
    import app.routers.ai_news as news

    article = {
        "id": "a1", "title": "Model X", "summary": "Released today",
        "source": "Lab", "category": "vendor", "importance": 9,
        "hands_on": "Try the playground", "url": "https://lab.test/x",
    }
    calls = 0

    async def fake_chat(*args, **kwargs):
        nonlocal calls
        calls += 1
        return "briefing"

    monkeypatch.setattr(news, "SUMMARY_FILE", tmp_path / "summary_today.json")
    monkeypatch.setattr(news, "_articles_for_today", lambda limit=25: [article])
    monkeypatch.setattr(news, "chat_complete", fake_chat)
    monkeypatch.setattr(news, "archive_summary", lambda payload: [])

    assert await news.build_today_summary() is not None
    assert await news.build_today_summary() is None
    assert await news.build_today_summary(force=True) is not None
    assert calls == 2


def test_article_actionable_and_translated_filters_apply_before_pagination(
    tmp_path, monkeypatch,
) -> None:
    import app.routers.ai_news as news

    articles = [
        {"id": "a1", "title": "Actionable", "url": "https://example.com/1",
         "source": "test", "translation_status": "ok", "hands_on": "运行最小样例。"},
        {"id": "a2", "title": "Opinion", "url": "https://example.com/2",
         "source": "test", "translation_status": "ok", "hands_on": ""},
        {"id": "a3", "title": "Pending", "url": "https://example.com/3",
         "source": "test", "translation_status": "pending", "hands_on": None},
    ]
    articles_file = tmp_path / "articles.json"
    write_json_atomic(articles_file, articles)
    monkeypatch.setattr(news, "ARTICLES_FILE", articles_file)

    common = dict(q=None, pinned_only=False, tier=None, category=None, tag=None,
                  sort="newest", offset=0, limit=1, user=None)
    actionable = news.list_articles(
        translated_only=False, hands_on_only=True, **common,
    )
    translated = news.list_articles(
        translated_only=True, hands_on_only=False, **common,
    )

    assert actionable["total"] == 1
    assert [a["id"] for a in actionable["items"]] == ["a1"]
    assert translated["total"] == 2
    assert len(translated["items"]) == 1
