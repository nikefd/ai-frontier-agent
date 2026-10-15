"""AI-news RSS fetcher with tier-aware AI-relevance filtering.

Pipeline per entry:
  1. Parse feed → raw entry (title, url, summary, date)
  2. Keyword relevance check (AI_KEYWORDS allowlist; cn + en)
  3. Tier-based gating:
     - tier=high  → accept (trusted first-party/editorial source)
     - paper      → accept (the category itself is AI/ML scoped)
     - tier=med/low → accept only on keyword hit
  4. Enforce per-feed diversity, category ceilings, and a hard global ceiling
  5. Persist via add_article() with tier + ai_relevance fields
  6. Mark translation_status="pending" so the translation worker picks it up

Best-effort guarantees retained:
  - one feed failing never blocks others
  - duplicates by url/id are skipped at the storage layer
  - per-feed metadata in sources.json (last_fetch, last_ok, last_error,
    last_added, filtered_count, tier, name)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import unquote, urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup

from ..routers.ai_news import (
    DEFAULT_FEEDS,
    DEFAULT_FEED_SPECS,
    FEED_SPEC_BY_URL,
    _CATEGORY_FETCH_CAPS,
    _DAILY_FETCH_CAP,
    _PER_FEED_CAP,
    _is_ai_relevant_keywords,
    _load_sources_meta,
    _parse_ts,
    _save_sources_meta,
    add_article,
)
from ..models import Article

log = logging.getLogger("aif.fetcher")

USER_AGENT = "ai-frontier-agent/0.2 (RSS fetcher)"
_FETCH_LOCK = asyncio.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_sitemap_entries(content: bytes, include_paths: list[str]) -> list[dict]:
    """Convert selected official sitemap URLs into feed-like entries.

    Some frontier labs publish no RSS but do maintain a dated sitemap. Keeping
    this adapter generic lets us ingest their first-party links without relying
    on a third-party social mirror.
    """
    soup = BeautifulSoup(content, "xml")
    entries: list[dict] = []
    for node in soup.find_all("url"):
        loc_node = node.find("loc")
        if not loc_node:
            continue
        link = loc_node.get_text(strip=True)
        path = urlparse(link).path
        if include_paths and not any(path.startswith(prefix) for prefix in include_paths):
            continue
        slug = unquote(path.rstrip("/").rsplit("/", 1)[-1])
        if not slug:
            continue
        lastmod_node = node.find("lastmod")
        entries.append({
            "title": slug.replace("-", " ").strip().title(),
            "url": link,
            "date": lastmod_node.get_text(strip=True) if lastmod_node else "",
            "summary": "",
            "tags": [],
        })
    entries.sort(key=lambda e: _parse_ts(e.get("date") or ""), reverse=True)
    return entries[:20]


def _parse_sitemap_index(content: bytes) -> list[str]:
    """Return child sitemap URLs from a sitemap index, if present."""
    soup = BeautifulSoup(content, "xml")
    urls: list[str] = []
    for node in soup.find_all("sitemap"):
        loc_node = node.find("loc")
        if loc_node:
            url = loc_node.get_text(strip=True)
            if url:
                urls.append(url)
    return urls


def _parse_qwen_api_entries(payload: dict) -> list[dict]:
    """Convert Qwen's first-party article API into feed-like entries."""
    articles = ((payload.get("data") or {}).get("articles") or [])
    entries: list[dict] = []
    for article in articles:
        title = str(article.get("title") or "").strip()
        path = str(article.get("path") or "").strip()
        if not title or not path:
            continue
        extra = article.get("extra") if isinstance(article.get("extra"), dict) else {}
        summary_raw = str(extra.get("introduction") or extra.get("description") or "")
        summary = BeautifulSoup(summary_raw, "lxml").get_text(" ", strip=True)
        if len(summary) > 280:
            summary = summary[:280] + "…"
        entries.append({
            "title": title,
            "url": f"https://qwen.ai/blog?id={path}",
            "date": str(extra.get("date") or ""),
            "summary": summary,
            "tags": [],
        })
    entries.sort(key=lambda e: _parse_ts(e.get("date") or ""), reverse=True)
    return entries[:20]


async def _entries_from_sitemap(
    client: httpx.AsyncClient,
    root_url: str,
    content: bytes,
    include_paths: list[str],
) -> list[dict]:
    """Parse a urlset or one level of same-host sitemap-index children."""
    child_urls = _parse_sitemap_index(content)
    if not child_urls:
        return _parse_sitemap_entries(content, include_paths)

    root_host = urlparse(root_url).hostname
    child_urls = [u for u in child_urls if urlparse(u).hostname == root_host][:12]

    async def fetch_child(child_url: str) -> bytes | None:
        try:
            response = await client.get(
                child_url, timeout=15.0, headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            return response.content
        except (httpx.HTTPError, asyncio.TimeoutError):
            log.warning("child sitemap %s failed", child_url)
            return None

    payloads = await asyncio.gather(*(fetch_child(u) for u in child_urls))
    by_url: dict[str, dict] = {}
    for payload in payloads:
        if not payload:
            continue
        for entry in _parse_sitemap_entries(payload, include_paths):
            by_url[entry["url"]] = entry
    entries = list(by_url.values())
    entries.sort(key=lambda e: _parse_ts(e.get("date") or ""), reverse=True)
    return entries[:20]


async def _fetch_feed(
    client: httpx.AsyncClient,
    url: str,
) -> tuple[list[dict], str | None, str | None]:
    """Returns (raw_entries, feed_title, error_msg)."""
    try:
        r = await client.get(url, timeout=15.0, headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
    except (httpx.HTTPError, asyncio.TimeoutError) as e:
        log.warning("feed %s failed: %s", url, e)
        return [], None, str(e)
    spec = FEED_SPEC_BY_URL.get(url, {})
    if spec.get("format") == "sitemap":
        entries = await _entries_from_sitemap(
            client, url, r.content, spec.get("include_paths") or [],
        )
        return entries, spec.get("name") or url, None
    if spec.get("format") == "qwen_api":
        try:
            entries = _parse_qwen_api_entries(r.json())
        except ValueError as e:
            return [], spec.get("name") or url, f"invalid Qwen API JSON: {e}"
        return entries, spec.get("name") or url, None

    feed = feedparser.parse(r.content)
    entries: list[dict] = []
    source = feed.feed.get("title") if feed.feed else url
    for ent in feed.entries[:20]:
        link = ent.get("link") or ""
        title = (ent.get("title") or "").strip()
        if not link or not title:
            continue
        summary_raw = ent.get("summary") or ent.get("description") or ""
        text = BeautifulSoup(summary_raw, "lxml").get_text(" ", strip=True)
        summary = (text[:280] + "…") if len(text) > 280 else text
        published = ent.get("published") or ent.get("updated") or ""
        entries.append(
            {
                "title": title,
                "url": link,
                "source": source or url,
                "date": published,
                "summary": summary,
                "tags": [],
            }
        )
    return entries, source, None


def _decide_relevance(entry: dict, tier: str, category: str | None = None) -> tuple[bool, str]:
    """Apply stricter gating as source trust decreases.

    First-party/editorial AI feeds and AI paper categories are curated enough
    to accept directly. Discovery streams (media/community/X/Trending) must
    mention an AI concept, preventing generic popular projects and chatter from
    entering the enrichment queue.
    """
    hit = _is_ai_relevant_keywords(entry.get("title") or "", entry.get("summary") or "")
    if tier == "high" or category == "paper":
        return True, ("keyword" if hit else "curated")
    return hit, ("keyword" if hit else "rejected")


def _select_candidates(candidates: list[tuple], global_cap: int = _DAILY_FETCH_CAP) -> list[tuple]:
    """Select a diverse, category-balanced batch under a true global ceiling.

    Every feed gets a first pass before extra entries from high-volume feeds.
    Category ceilings are hard limits, especially for X and GitHub Trending.
    """
    by_feed: dict[str, list[tuple]] = {}
    for cand in candidates:
        by_feed.setdefault(cand[4], []).append(cand)

    first_pass: list[tuple] = []
    overflow: list[tuple] = []
    feed_lists = list(by_feed.values())
    for cands in feed_lists:
        cands.sort(key=lambda t: (t[0], t[1]))
        overflow.extend(cands[_PER_FEED_CAP:])

    # Layered rounds matter when feeds * per-feed cap exceeds the global cap:
    # take one item from every source before considering a source's second item.
    for depth in range(_PER_FEED_CAP):
        round_items = [cands[depth] for cands in feed_lists if len(cands) > depth]
        round_items.sort(key=lambda t: (t[0], t[1]))
        first_pass.extend(round_items)

    overflow.sort(key=lambda t: (t[0], t[1]))
    selected: list[tuple] = []
    category_counts: dict[str, int] = {}
    seen_urls: set[str] = set()
    for cand in first_pass + overflow:
        if len(selected) >= global_cap:
            break
        url = str(cand[2].get("url") or "")
        if url and url in seen_urls:
            continue
        category = cand[2].get("category") or "community"
        cap = _CATEGORY_FETCH_CAPS.get(category, global_cap)
        if category_counts.get(category, 0) >= cap:
            continue
        selected.append(cand)
        if url:
            seen_urls.add(url)
        category_counts[category] = category_counts.get(category, 0) + 1
    return selected


async def _fetch_once(feeds: Iterable[str] | None = None) -> int:
    """Pull all feeds → relevance-filter → balance by source/category → persist.

    Per-feed counters in ``sources.json`` reflect what made the cut, so a feed
    can have eligible=10 but added=2 if the daily cap pushed it out. Duplicates
    against the rolling history are skipped at the storage layer.
    """
    feeds = list(feeds or DEFAULT_FEEDS)
    meta = _load_sources_meta()
    async with httpx.AsyncClient(follow_redirects=True) as client:
        tasks = [_fetch_feed(client, f) for f in feeds]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Tier ranks (lower number = preferred). Within tier we rank by freshness.
    tier_rank = {"high": 0, "med": 1, "low": 2}
    candidates: list[tuple[float, int, dict, dict]] = []
    # tuples are (sort_key_primary, sort_key_secondary, entry, meta_ref)
    # — sort_key_primary = tier rank
    # — sort_key_secondary = -timestamp (newest first)

    for url, result in zip(feeds, results):
        spec = FEED_SPEC_BY_URL.get(url, {})
        tier = spec.get("tier", "med")
        category = spec.get("category")
        configured_name = spec.get("name")

        m = meta.setdefault(url, {})
        m["last_fetch"] = _now_iso()
        m["tier"] = tier
        if category:
            m["category"] = category
        m["eligible"] = 0
        m["last_added"] = 0
        m["last_filtered"] = 0
        if isinstance(result, Exception):
            m["last_error"] = str(result)
            log.warning("feed %s raised: %s", url, result)
            continue
        entries, source_title, err = result  # type: ignore[misc]
        m["name"] = configured_name or source_title or url
        if err:
            m["last_error"] = err
            continue
        m["last_error"] = None
        m["last_ok"] = _now_iso()

        eligible_count = 0
        filtered_count = 0
        for entry in entries:
            accept, reason = _decide_relevance(entry, tier, category)
            if not accept:
                filtered_count += 1
                continue
            entry["tier"] = tier
            entry["ai_relevance"] = reason
            entry["translation_status"] = "pending"
            if category:
                entry["category"] = category
            if configured_name:
                entry["source"] = configured_name
            ts = _parse_ts(entry.get("date") or "") or 0.0
            candidates.append((tier_rank.get(tier, 9), -ts, entry, m, url))
            eligible_count += 1
        m["eligible"] = eligible_count
        m["last_filtered"] = filtered_count

    selected = _select_candidates(candidates)

    added_total = 0
    for _, _, entry, m, _url in selected:
        try:
            res = add_article(Article(**entry))
            if not res.get("duplicate"):
                m["last_added"] = (m.get("last_added") or 0) + 1
                added_total += 1
        except Exception as e:  # noqa: broad-except
            log.warning("add_article failed for %s: %s", entry.get("url"), e)

    _save_sources_meta(meta)
    log.info(
        "ai-news fetch: candidates=%d capped=%d added=%d across %d feeds",
        len(candidates), len(selected), added_total, len(feeds),
    )
    return added_total


async def fetch_once(feeds: Iterable[str] | None = None) -> int:
    """Serialize fetch sweeps so scheduler and admin-triggered runs cannot overlap."""
    async with _FETCH_LOCK:
        return await _fetch_once(feeds)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level="INFO")
    print("added:", asyncio.run(fetch_once()))
