"""AI-news RSS fetcher with tier-aware AI-relevance filtering.

Pipeline per entry:
  1. Parse feed → raw entry (title, url, summary, date)
  2. Keyword pre-filter (AI_KEYWORDS allowlist; cn + en)
  3. Tier-based gating:
     - tier=high  → accept (even if no keyword hit; trusted source)
     - tier=med   → accept iff keyword hit (skip LLM to save cost; arXiv/community)
     - tier=low   → accept iff keyword hit (HN keyword stream already pre-filtered;
                    GitHub Changelog only AI-related items)
  4. Persist via add_article() with tier + ai_relevance fields
  5. Mark translation_status="pending" so the translation worker picks it up

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

import feedparser
import httpx
from bs4 import BeautifulSoup

from ..routers.ai_news import (
    DEFAULT_FEEDS,
    DEFAULT_FEED_SPECS,
    FEED_SPEC_BY_URL,
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


def _decide_relevance(entry: dict, tier: str) -> tuple[bool, str]:
    """Accept everything: every feed is now a hand-picked AI source, so the
    keyword pre-filter is disabled. We still tag whether an AI keyword fired
    (a weak UI signal), but it never rejects an article."""
    hit = _is_ai_relevant_keywords(entry.get("title") or "", entry.get("summary") or "")
    return True, ("keyword" if hit else "curated")


async def _fetch_once(feeds: Iterable[str] | None = None) -> int:
    """Pull all feeds → relevance-filter → keep top-N globally (tier × freshness).

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
            accept, reason = _decide_relevance(entry, tier)
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

    # Per-feed quota + global backfill, instead of a single global time-sorted
    # cap. A pure global cap let high-frequency vendor feeds (newest timestamps)
    # crowd out slower-but-valuable sources — e.g. Twitter accounts whose latest
    # post is a few days old never made the top-N and silently never appeared.
    # We now guarantee each feed up to _PER_FEED_CAP of its freshest items, then
    # fill any remaining global budget by recency.
    by_feed: dict[str, list] = {}
    for cand in candidates:
        by_feed.setdefault(cand[4], []).append(cand)
    selected = []
    leftover = []
    for url, cands in by_feed.items():
        cands.sort(key=lambda t: t[1])  # newest first within the feed
        selected.extend(cands[:_PER_FEED_CAP])
        leftover.extend(cands[_PER_FEED_CAP:])
    # Global backfill up to the overall ceiling, newest first.
    leftover.sort(key=lambda t: t[1])
    room = max(0, _DAILY_FETCH_CAP - len(selected))
    selected.extend(leftover[:room])

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
