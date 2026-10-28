"""AI-news RSS fetcher with tier-aware AI-relevance filtering.

Pipeline per entry:
  1. Parse feed → raw entry (title, url, summary, date)
  2. Keyword relevance check (AI_KEYWORDS allowlist; cn + en)
  3. Tier-based gating:
     - tier=high  → accept (trusted first-party/editorial source)
     - paper/explicitly curated AI feeds → accept
     - tier=med/low → accept only on keyword hit
  4. Enforce per-feed diversity, category ceilings, and a hard global ceiling
  5. Persist via add_article() with tier + ai_relevance fields
  6. Mark translation_status="pending" so the translation worker picks it up

Best-effort guarantees retained:
  - one feed failing never blocks others; empty/non-feed responses are failures
  - duplicates by url/id are skipped at the storage layer
  - per-feed metadata in sources.json (last_fetch, last_ok, last_error,
    last_added, filtered_count, tier, name)
"""
from __future__ import annotations

import asyncio
import html
import json
import logging
import re
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import unquote, urljoin, urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup

from ..auto_listing import parse_auto_listing_entries
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
from ..official_page_adapters import parse_luma_news_entries
from ..publication_dates import publication_date_from_url

log = logging.getLogger("aif.fetcher")

USER_AGENT = "ai-frontier-agent/0.2 (RSS fetcher)"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"
)
_FETCH_LOCK = asyncio.Lock()
_HOST_FETCH_LOCKS = {"arxiv": asyncio.Lock()}
_HOST_THROTTLE_SECONDS = 1.0
_SITEMAP_METADATA_LIMIT = 6
_QUALITY_SAMPLE_LIMIT = 30


def _request_headers(source_url: str, *, accept: str | None = None) -> dict[str, str]:
    """Return source-specific headers without making every feed impersonate a browser.

    Reddit accepts a descriptive feed-reader UA but several CDN-protected
    publishers reject it. Their registry entries explicitly opt into the
    browser profile so one workaround cannot regress another source.
    """
    spec = FEED_SPEC_BY_URL.get(source_url, {})
    headers = {
        "User-Agent": BROWSER_USER_AGENT if spec.get("request_profile") == "browser" else USER_AGENT,
    }
    if accept:
        headers["Accept"] = accept
    if urlparse(source_url).hostname == "api.github.com":
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    if spec.get("request_profile") == "browser":
        headers["Accept-Language"] = "en-US,en;q=0.8"
    return headers


async def _get_source(
    client: httpx.AsyncClient,
    url: str,
    *,
    source_url: str,
    timeout: float = 15.0,
    accept: str | None = None,
) -> httpx.Response:
    """GET once, with one bounded retry for rate limits and transient upstreams."""
    headers = _request_headers(source_url, accept=accept)
    response = await client.get(url, timeout=timeout, headers=headers)
    if response.status_code in {429, 500, 502, 503, 504}:
        retry_after = response.headers.get("retry-after", "")
        try:
            delay = min(1.0, max(0.1, float(retry_after)))
        except ValueError:
            delay = 0.35
        await asyncio.sleep(delay)
        response = await client.get(url, timeout=timeout, headers=headers)
    return response


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_quality_sample(meta: dict, sample: dict) -> None:
    history = meta.get("quality_samples")
    if not isinstance(history, list):
        history = []
    cleaned = [item for item in history if isinstance(item, dict) and item.get("at")]
    meta["quality_samples"] = [*cleaned, sample][-_QUALITY_SAMPLE_LIMIT:]


def _parse_sitemap_entries(
    content: bytes,
    include_paths: list[str],
    exclude_paths: list[str] | None = None,
) -> list[dict]:
    """Convert selected official sitemap URLs into feed-like entries.

    Some frontier labs publish no RSS but do maintain a dated sitemap. Keeping
    this adapter generic lets us ingest their first-party links without relying
    on a third-party social mirror.
    """
    soup = BeautifulSoup(content, "xml")
    # A few official generators emit malformed XML after an otherwise valid
    # prefix.  BeautifulSoup's strict XML backend silently stops there, so
    # recover with the tolerant lxml HTML parser when URL nodes were lost.
    raw_url_count = len(re.findall(br"<url(?:\s|>)", content, flags=re.IGNORECASE))
    if len(soup.find_all("url")) < raw_url_count:
        soup = BeautifulSoup(content, "lxml")
    entries: list[dict] = []
    for node in soup.find_all("url"):
        loc_node = node.find("loc")
        if not loc_node:
            continue
        link = loc_node.get_text(strip=True)
        path = urlparse(link).path
        if include_paths and not any(path.startswith(prefix) for prefix in include_paths):
            continue
        if exclude_paths and any(path.startswith(prefix) for prefix in exclude_paths):
            continue
        slug = unquote(path.rstrip("/").rsplit("/", 1)[-1])
        if not slug:
            continue
        lastmod_node = node.find("lastmod")
        modified = lastmod_node.get_text(strip=True) if lastmod_node else ""
        entries.append({
            "title": slug.replace("-", " ").strip().title(),
            "url": link,
            # Sitemap lastmod means the page changed, not that the article was
            # published then.  Keep it only as a discovery-order hint; a page
            # without trusted publication metadata must remain undated.
            "date": publication_date_from_url(link),
            "summary": "",
            "tags": [],
            "_sitemap_lastmod": modified,
        })
    entries.sort(
        key=lambda e: _parse_ts(e.get("_sitemap_lastmod") or e.get("date") or ""),
        reverse=True,
    )
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


def _clean_metadata_text(value: object) -> str:
    text = html.unescape(str(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def _parse_page_metadata(content: bytes) -> dict[str, str]:
    """Extract useful editorial fields from an official article page."""
    soup = BeautifulSoup(content, "lxml")

    def meta(*, prop: str | None = None, name: str | None = None) -> str:
        attrs = {"property": prop} if prop else {"name": name}
        node = soup.find("meta", attrs=attrs)
        return _clean_metadata_text(node.get("content")) if node else ""

    result = {
        "title": meta(prop="og:title") or meta(name="twitter:title"),
        "summary": meta(prop="og:description") or meta(name="description"),
        "date": meta(prop="article:published_time"),
    }

    # Many vendor blogs expose the canonical publication date only in JSON-LD.
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            payload = json.loads(script.string or script.get_text() or "")
        except (json.JSONDecodeError, TypeError):
            continue
        stack = payload if isinstance(payload, list) else [payload]
        while stack:
            item = stack.pop()
            if not isinstance(item, dict):
                continue
            graph = item.get("@graph")
            if isinstance(graph, list):
                stack.extend(graph)
            result["title"] = result["title"] or _clean_metadata_text(item.get("headline"))
            result["summary"] = result["summary"] or _clean_metadata_text(item.get("description"))
            result["date"] = result["date"] or _clean_metadata_text(item.get("datePublished"))
            if all(result.values()):
                break
        if all(result.values()):
            break

    if not result["title"] and soup.title:
        result["title"] = _clean_metadata_text(soup.title.get_text(" ", strip=True))
    # Some marketing sites publish only the company name in og:title while
    # the article's real headline is the first h1.
    heading = soup.find("h1")
    heading_text = _clean_metadata_text(heading.get_text(" ", strip=True)) if heading else ""
    if heading_text and (not result["title"] or (
        len(result["title"].split()) == 1 and len(heading_text) > len(result["title"])
    )):
        result["title"] = heading_text
    if not result["date"]:
        article = soup.find("article") or soup.find("main")
        leading_text = (
            _clean_metadata_text(article.get_text(" ", strip=True)[:500])
            if article
            else ""
        )
        visible_date = re.search(
            r"\b(20\d{2})[/-](0?[1-9]|1[0-2])[/-](0?[1-9]|[12]\d|3[01])\b",
            leading_text,
        )
        if visible_date:
            year, month, day = (int(part) for part in visible_date.groups())
            try:
                result["date"] = datetime(year, month, day, tzinfo=timezone.utc).isoformat()
            except ValueError:
                pass
    if len(result["summary"]) > 280:
        result["summary"] = result["summary"][:280] + "…"
    return result


async def _hydrate_sitemap_entries(
    client: httpx.AsyncClient,
    root_url: str,
    entries: list[dict],
) -> list[dict]:
    """Hydrate the newest sitemap links without making a source mandatory."""
    root_host = urlparse(root_url).hostname

    async def hydrate(entry: dict) -> dict:
        link = str(entry.get("url") or "")
        parsed = urlparse(link)
        if parsed.scheme not in {"http", "https"} or parsed.hostname != root_host:
            return entry
        try:
            response = await _get_source(
                client, link, source_url=root_url, timeout=15.0,
                accept="text/html",
            )
            response.raise_for_status()
            metadata = _parse_page_metadata(response.content)
        except (httpx.HTTPError, asyncio.TimeoutError, ValueError):
            log.warning("sitemap page metadata %s failed", link)
            return entry
        enriched = dict(entry)
        for field in ("title", "summary", "date"):
            if metadata.get(field):
                enriched[field] = metadata[field]
        return enriched

    limit = min(len(entries), _SITEMAP_METADATA_LIMIT)
    hydrated = await asyncio.gather(*(hydrate(entry) for entry in entries[:limit]))
    result = [*hydrated, *entries[limit:]]
    result.sort(
        key=lambda entry: _parse_ts(
            entry.get("date") or entry.get("_sitemap_lastmod") or "",
        ),
        reverse=True,
    )
    return [
        {key: value for key, value in entry.items() if key != "_sitemap_lastmod"}
        for entry in result
    ]


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


def _parse_liblib_articles(payload: dict) -> list[dict]:
    """Convert LiblibAI's first-party tutorial API into feed-like entries."""
    articles = payload.get("data") or []
    if not isinstance(articles, list):
        return []
    entries: list[dict] = []
    for article in articles:
        if not isinstance(article, dict):
            continue
        title = _clean_metadata_text(article.get("title"))
        article_id = str(article.get("uuid") or "").strip()
        # Editing an old tutorial must not make it look newly published.
        timestamp = article.get("releaseDate") or article.get("createTime")
        try:
            published = datetime.fromtimestamp(float(timestamp), tz=timezone.utc).isoformat()
        except (TypeError, ValueError, OSError):
            published = ""
        if not title or not article_id or not published:
            continue
        summary = _clean_metadata_text(
            article.get("description") or article.get("content"),
        )
        if len(summary) > 280:
            summary = summary[:280] + "…"
        entries.append({
            "title": title,
            "url": f"https://www.liblib.art/teaching/{article_id}",
            "date": published,
            "summary": summary,
            "tags": [],
        })
    entries.sort(key=lambda entry: _parse_ts(entry["date"]), reverse=True)
    return entries[:20]


def _parse_openrouter_models(payload: dict) -> list[dict]:
    """Convert OpenRouter's model catalog into dated availability signals."""
    models = payload.get("data") or []
    if not isinstance(models, list):
        return []
    entries: list[dict] = []
    for model in models:
        if not isinstance(model, dict):
            continue
        model_id = str(model.get("id") or "").strip()
        name = _clean_metadata_text(model.get("name") or model_id)
        try:
            published = datetime.fromtimestamp(
                float(model.get("created")), tz=timezone.utc,
            ).isoformat()
        except (TypeError, ValueError, OSError):
            published = ""
        if not model_id or not name or not published:
            continue
        try:
            context = int(model.get("context_length") or 0)
        except (TypeError, ValueError):
            context = 0
        description = _clean_metadata_text(model.get("description"))
        signal = f"OpenRouter API availability; context window {context:,} tokens."
        summary = f"{signal} {description}" if description else signal
        if len(summary) > 280:
            summary = summary[:280] + "…"
        entries.append({
            "title": f"Available on OpenRouter: {name}",
            "url": f"https://openrouter.ai/{model_id}",
            "date": published,
            "summary": summary,
            "tags": ["模型"],
        })
    entries.sort(key=lambda entry: _parse_ts(entry["date"]), reverse=True)
    return entries[:20]


def _parse_github_repositories(payload: list[dict]) -> list[dict]:
    """Convert newly created first-party repositories into release signals."""
    entries: list[dict] = []
    for repository in payload:
        if not isinstance(repository, dict) or repository.get("fork") or repository.get("archived"):
            continue
        full_name = _clean_metadata_text(repository.get("full_name") or repository.get("name"))
        link = str(repository.get("html_url") or "").strip()
        published = str(repository.get("created_at") or "").strip()
        if not full_name or not link or not published:
            continue
        summary = _clean_metadata_text(repository.get("description"))
        if len(summary) > 280:
            summary = summary[:280] + "…"
        entries.append({
            "title": full_name,
            "url": link,
            "date": published,
            "summary": summary,
            "tags": ["开源"],
        })
    entries.sort(key=lambda entry: _parse_ts(entry["date"]), reverse=True)
    return entries[:20]


def _parse_stepfun_news_bundle(content: bytes) -> list[dict]:
    """Extract dated StepFun articles embedded in its versioned SPA bundle."""
    source = content.decode("utf-8", errors="replace")
    pattern = re.compile(
        r'\{slug:"(?P<slug>[^"]+)",date:"(?P<date>20\d{2}-\d{2}-\d{2})",'
        r'dateLabel:"[^"]*",title:"(?P<title>(?:\\.|[^"])*)"',
    )
    entries: list[dict] = []
    seen_urls: set[str] = set()
    for match in pattern.finditer(source):
        slug = match.group("slug")
        try:
            title = json.loads(f'"{match.group("title")}"')
        except json.JSONDecodeError:
            title = match.group("title")
        title = _clean_metadata_text(title)
        date = _normalize_html_listing_date(match.group("date"))
        link = f"https://www.stepfun.com/news/{slug}"
        if not title or not date or link in seen_urls:
            continue
        entries.append({
            "title": title,
            "url": link,
            "date": date,
            "summary": "",
            "tags": [],
        })
        seen_urls.add(link)
    entries.sort(key=lambda entry: _parse_ts(entry["date"]), reverse=True)
    return entries[:20]


def _normalize_html_listing_date(value: str) -> str:
    """Normalize human-facing dates used by official product update pages."""
    cleaned = " ".join(value.split())
    for date_format in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(cleaned, date_format).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return ""


def _listing_fragment(date: str, title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80]
    return f"{date[:10]}-{slug}".strip("-")


def _parse_html_listing_entries(content: bytes, source_url: str, spec: dict) -> list[dict]:
    """Parse dated cards from a first-party blog or product changelog.

    Selectors live beside each source in the registry so this adapter remains
    small and auditable. A source may use its real card link or stable synthetic
    fragments on a single-page changelog when individual entries have no URL.
    """
    soup = BeautifulSoup(content, "lxml")
    entries: list[dict] = []
    seen_urls: set[str] = set()
    for item in soup.select(str(spec.get("item_selector") or "")):
        title_node = item.select_one(str(spec.get("title_selector") or ""))
        date_node = item.select_one(str(spec.get("date_selector") or ""))
        title = _clean_metadata_text(title_node.get("title") or title_node.get_text(" ")) \
            if title_node else ""
        date = _normalize_html_listing_date(date_node.get_text(" ") if date_node else "")
        if not title or not date:
            continue

        if spec.get("link_mode") == "fragment":
            link = f"{source_url.split('#', 1)[0]}#{_listing_fragment(date, title)}"
        else:
            link_node = item if item.name == "a" and item.get("href") else None
            if link_node is None and spec.get("link_selector"):
                link_node = item.select_one(str(spec["link_selector"]))
            href = str(link_node.get("href") or "").strip() if link_node else ""
            link = urljoin(source_url, href) if href else ""
        if not link or link in seen_urls:
            continue

        summary = ""
        if spec.get("summary_selector"):
            summary_node = item.select_one(str(spec["summary_selector"]))
            summary = _clean_metadata_text(summary_node.get_text(" ") if summary_node else "")
        if len(summary) > 280:
            summary = summary[:280] + "…"
        entries.append({
            "title": title,
            "url": link,
            "date": date,
            "summary": summary,
            "tags": [],
        })
        seen_urls.add(link)

    entries.sort(key=lambda entry: _parse_ts(entry["date"]), reverse=True)
    return entries[:20]


def _canonical_feed_url(value: str) -> str:
    """Normalize arXiv paper links so curated and category feeds can dedupe."""
    parsed = urlparse(value)
    if parsed.hostname in {"arxiv.org", "www.arxiv.org"} and parsed.path.startswith("/abs/"):
        path = re.sub(r"v\d+$", "", parsed.path)
        return f"https://arxiv.org{path}"
    return value


def _parse_hf_daily_papers(payload: list[dict]) -> list[dict]:
    """Rank Hugging Face's community-curated daily papers with useful signals."""
    ranked: list[tuple[tuple[float, int, int, int], dict]] = []
    for item in payload:
        paper = item.get("paper") if isinstance(item, dict) else None
        if not isinstance(paper, dict):
            continue
        paper_id = str(paper.get("id") or "").strip()
        title = _clean_metadata_text(paper.get("title"))
        if not paper_id or not title:
            continue
        submitted = str(
            paper.get("submittedOnDailyAt") or paper.get("publishedAt")
            or item.get("publishedAt") or ""
        )
        try:
            upvotes = max(0, int(paper.get("upvotes") or 0))
        except (TypeError, ValueError):
            upvotes = 0
        repo = str(paper.get("githubRepo") or "").strip()
        try:
            stars = max(0, int(paper.get("githubStars") or 0))
        except (TypeError, ValueError):
            stars = 0
        signal = f"HF Daily Papers: {upvotes} community upvotes"
        if repo:
            signal += f"; code available ({stars} GitHub stars)"
        abstract = _clean_metadata_text(paper.get("ai_summary") or paper.get("summary"))
        summary = f"{signal}. {abstract}" if abstract else f"{signal}."
        if len(summary) > 280:
            summary = summary[:280] + "…"
        paper_slug = re.sub(r"v\d+$", "", paper_id)
        entry = {
            "title": title,
            "url": f"https://huggingface.co/papers/{paper_slug}",
            "_dedupe_url": _canonical_feed_url(f"https://arxiv.org/abs/{paper_id}"),
            "date": submitted,
            "summary": summary,
            "tags": ["论文"] + (["开源"] if repo else []),
        }
        score = (_parse_ts(submitted), upvotes, int(bool(repo)), stars)
        ranked.append((score, entry))
    ranked.sort(key=lambda row: row[0], reverse=True)
    return [entry for _, entry in ranked[:20]]


def _limit_source_entries(entries: list[dict], spec: dict) -> list[dict]:
    """Apply an optional hard per-source cap after parsing, newest first."""
    try:
        limit = int(spec.get("max_per_fetch") or 0)
    except (TypeError, ValueError):
        return entries
    if limit <= 0:
        return entries
    return sorted(entries, key=lambda entry: _parse_ts(entry.get("date") or ""), reverse=True)[:limit]


def _plain_markdown(value: str) -> str:
    """Collapse the small Markdown subset used by official changelogs."""
    text = re.sub(r"\[([^\]]+)\]\([^\s)]+(?:\s+[^)]*)?\)", r"\1", value)
    text = re.sub(r"[`*_~]", "", text)
    return _clean_metadata_text(text)


def _parse_github_releases(payload: list[dict]) -> list[dict]:
    """Convert first-party GitHub releases into feed-like entries."""
    entries: list[dict] = []
    for release in payload:
        if not isinstance(release, dict) or release.get("draft"):
            continue
        title = _clean_metadata_text(release.get("name") or release.get("tag_name"))
        url = str(release.get("html_url") or "").strip()
        published = str(release.get("published_at") or release.get("created_at") or "")
        if not title or not url or not published:
            continue
        body_raw = re.sub(
            r"(?m)^\s{0,3}#{1,6}\s*",
            "",
            str(release.get("body") or ""),
        )
        body = _plain_markdown(body_raw)
        if release.get("prerelease"):
            body = f"Pre-release. {body}" if body else "Pre-release."
        if len(body) > 280:
            body = body[:280] + "…"
        entries.append({
            "title": title,
            "url": url,
            "date": published,
            "summary": body,
            "tags": ["开源"],
        })
    entries.sort(key=lambda entry: _parse_ts(entry.get("date") or ""), reverse=True)
    return entries[:20]


def _parse_openai_changelog_entries(content: bytes) -> list[dict]:
    """Turn OpenAI's official Markdown changelog into dated feed entries."""
    base_url = "https://developers.openai.com/api/docs/changelog"
    lines = content.decode("utf-8", errors="replace").splitlines()
    year: int | None = None
    current_date: datetime | None = None
    current_lines: list[str] = []
    blocks: list[tuple[datetime, list[str]]] = []

    def flush() -> None:
        if current_date and current_lines:
            blocks.append((current_date, list(current_lines)))

    for line in lines:
        month_match = re.fullmatch(r"##\s+[A-Za-z]+,\s+(\d{4})\s*", line)
        if month_match:
            flush()
            current_date = None
            current_lines = []
            year = int(month_match.group(1))
            continue
        day_match = re.fullmatch(r"###\s+([A-Za-z]{3})\s+(\d{1,2})\s*", line)
        if day_match and year:
            flush()
            try:
                current_date = datetime.strptime(
                    f"{day_match.group(1)} {day_match.group(2)} {year}", "%b %d %Y",
                ).replace(tzinfo=timezone.utc)
            except ValueError:
                current_date = None
            current_lines = []
            continue
        if current_date:
            current_lines.append(line)
    flush()

    entries: list[dict] = []
    used_urls: set[str] = set()
    for published, block_lines in blocks:
        chunks = [_plain_markdown(line) for line in block_lines if line.strip()]
        chunks = [chunk for chunk in chunks if chunk]
        if not chunks:
            continue
        body = next((
            chunk for chunk in chunks
            if not re.match(r"^(Feature|Update|Fix|Deprecation|Announcement)\b", chunk)
        ), chunks[0])
        sentence = re.split(r"(?<=[.!?])\s+", body, maxsplit=1)[0]
        title = sentence[:157] + "…" if len(sentence) > 160 else sentence
        summary = " ".join(chunks)
        if len(summary) > 280:
            summary = summary[:280] + "…"
        raw_links = re.findall(r"\[[^\]]+\]\(([^\s)]+)", "\n".join(block_lines))
        link = urljoin(base_url, raw_links[0]) if raw_links else ""
        if not link or link in used_urls:
            suffix = sum(1 for entry in entries if entry["date"] == published.isoformat()) + 1
            link = f"{base_url}#{published.date().isoformat()}-{suffix}"
        used_urls.add(link)
        entries.append({
            "title": title,
            "url": link,
            "date": published.isoformat(),
            "summary": summary,
            "tags": [],
        })
        if len(entries) >= 20:
            break
    return entries


def _parse_gemini_changelog_entries(content: bytes) -> list[dict]:
    """Turn Gemini API release-note list items into feed-like entries."""
    base_url = "https://ai.google.dev/gemini-api/docs/changelog"
    soup = BeautifulSoup(content, "lxml")
    body = soup.select_one(".devsite-article-body") or soup
    entries: list[dict] = []
    used_urls: set[str] = set()
    for heading in body.find_all("h2"):
        heading_id = str(heading.get("id") or "")
        try:
            published = datetime.strptime(
                heading.get_text(" ", strip=True), "%B %d, %Y",
            ).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        node = heading.find_next_sibling()
        item_number = 0
        while node and node.name != "h2":
            if node.name == "ul":
                for item in node.find_all("li", recursive=False):
                    item_number += 1
                    summary = _clean_metadata_text(item.get_text(" ", strip=True))
                    if not summary:
                        continue
                    strong = item.find("strong")
                    title = _clean_metadata_text(
                        strong.get_text(" ", strip=True) if strong else summary,
                    )
                    if len(title) > 160:
                        title = title[:157] + "…"
                    if len(summary) > 280:
                        summary = summary[:280] + "…"
                    anchor = item.find("a", href=True)
                    link = urljoin(base_url, str(anchor.get("href"))) if anchor else ""
                    if not link or link in used_urls:
                        link = f"{base_url}#{heading_id or published.date().isoformat()}-{item_number}"
                    used_urls.add(link)
                    entries.append({
                        "title": title,
                        "url": link,
                        "date": published.isoformat(),
                        "summary": summary,
                        "tags": [],
                    })
                    if len(entries) >= 20:
                        return entries
            node = node.find_next_sibling()
    return entries


async def _entries_from_sitemap(
    client: httpx.AsyncClient,
    root_url: str,
    content: bytes,
    include_paths: list[str],
    exclude_paths: list[str] | None = None,
) -> list[dict]:
    """Parse a urlset or one level of same-host sitemap-index children."""
    child_urls = _parse_sitemap_index(content)
    if not child_urls:
        entries = _parse_sitemap_entries(content, include_paths, exclude_paths)
        return await _hydrate_sitemap_entries(client, root_url, entries)

    root_host = urlparse(root_url).hostname
    child_urls = [u for u in child_urls if urlparse(u).hostname == root_host][:12]

    async def fetch_child(child_url: str) -> bytes | None:
        try:
            response = await _get_source(
                client, child_url, source_url=root_url, timeout=15.0,
                accept="application/xml,text/xml;q=0.9,*/*;q=0.5",
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
        for entry in _parse_sitemap_entries(payload, include_paths, exclude_paths):
            by_url[entry["url"]] = entry
    entries = list(by_url.values())
    entries.sort(
        key=lambda e: _parse_ts(e.get("_sitemap_lastmod") or e.get("date") or ""),
        reverse=True,
    )
    return await _hydrate_sitemap_entries(client, root_url, entries[:20])


async def _fetch_feed(
    client: httpx.AsyncClient,
    url: str,
) -> tuple[list[dict], str | None, str | None]:
    """Returns (raw_entries, feed_title, error_msg)."""
    try:
        spec = FEED_SPEC_BY_URL.get(url, {})
        accept = (
            "application/vnd.github+json"
            if spec.get("format") in {"github_releases", "github_repositories"}
            else (
                "application/json"
                if spec.get("format") in {"openrouter_models"}
                else (
                    "application/rss+xml,application/atom+xml,application/xml,"
                    "text/xml;q=0.9,*/*;q=0.5"
                )
            )
        )
        r = await _get_source(
            client, url, source_url=url, timeout=float(spec.get("timeout") or 15.0),
            accept=accept,
        )
        r.raise_for_status()
    except (httpx.HTTPError, asyncio.TimeoutError) as e:
        log.warning("feed %s failed: %s", url, e)
        return [], None, str(e)
    spec = FEED_SPEC_BY_URL.get(url, {})
    if spec.get("format") == "sitemap":
        entries = await _entries_from_sitemap(
            client, url, r.content, spec.get("include_paths") or [],
            spec.get("exclude_paths") or [],
        )
        error = None if entries else "sitemap contained no matching parseable pages"
        return entries, spec.get("name") or url, error
    if spec.get("format") == "html_listing":
        entries = _parse_html_listing_entries(r.content, url, spec)
        error = None if entries else "official HTML listing contained no parseable updates"
        return entries, spec.get("name") or url, error
    if spec.get("format") == "auto_listing":
        entries = parse_auto_listing_entries(r.content, url)
        error = None if entries else "official update page contained no dated linked updates"
        return entries, spec.get("name") or url, error
    if spec.get("format") == "luma_news":
        entries = parse_luma_news_entries(r.content, url)
        error = None if entries else "Luma page contained no product or engineering updates"
        return entries, spec.get("name") or url, error
    if spec.get("format") == "stepfun_news":
        soup = BeautifulSoup(r.content, "lxml")
        script = soup.select_one("script[type='module'][src*='/assets/index-']")
        bundle_url = urljoin(url, str(script.get("src") or "")) if script else ""
        if not bundle_url or urlparse(bundle_url).hostname != urlparse(url).hostname:
            return [], spec.get("name") or url, "StepFun page exposed no same-host news bundle"
        try:
            bundle = await _get_source(
                client, bundle_url, source_url=url, timeout=30.0,
                accept="application/javascript,text/javascript;q=0.9,*/*;q=0.5",
            )
            bundle.raise_for_status()
        except (httpx.HTTPError, asyncio.TimeoutError) as e:
            return [], spec.get("name") or url, f"StepFun news bundle failed: {e}"
        entries = _parse_stepfun_news_bundle(bundle.content)
        error = None if entries else "StepFun bundle contained no parseable news"
        return entries, spec.get("name") or url, error
    if spec.get("format") == "qwen_api":
        try:
            entries = _parse_qwen_api_entries(r.json())
        except ValueError as e:
            return [], spec.get("name") or url, f"invalid Qwen API JSON: {e}"
        error = None if entries else "Qwen API contained no parseable articles"
        return entries, spec.get("name") or url, error
    if spec.get("format") == "liblib_articles":
        try:
            entries = _parse_liblib_articles(r.json())
        except ValueError as e:
            return [], spec.get("name") or url, f"invalid LiblibAI API JSON: {e}"
        error = None if entries else "LiblibAI API contained no parseable articles"
        return entries, spec.get("name") or url, error
    if spec.get("format") == "openrouter_models":
        try:
            entries = _parse_openrouter_models(r.json())
        except ValueError as e:
            return [], spec.get("name") or url, f"invalid OpenRouter model JSON: {e}"
        error = None if entries else "OpenRouter API contained no dated models"
        return entries, spec.get("name") or url, error
    if spec.get("format") == "hf_daily_papers":
        try:
            payload = r.json()
            if not isinstance(payload, list):
                raise ValueError("expected a JSON list")
            entries = _parse_hf_daily_papers(payload)
        except ValueError as e:
            return [], spec.get("name") or url, f"invalid Hugging Face papers JSON: {e}"
        error = None if entries else "Hugging Face Daily Papers contained no parseable papers"
        return entries, spec.get("name") or url, error
    if spec.get("format") == "github_releases":
        try:
            payload = r.json()
            if not isinstance(payload, list):
                raise ValueError("expected a JSON list")
            entries = _parse_github_releases(payload)
        except ValueError as e:
            return [], spec.get("name") or url, f"invalid GitHub releases JSON: {e}"
        error = None if entries else "GitHub releases contained no parseable releases"
        return entries, spec.get("name") or url, error
    if spec.get("format") == "github_repositories":
        try:
            payload = r.json()
            if not isinstance(payload, list):
                raise ValueError("expected a JSON list")
            entries = _parse_github_repositories(payload)
        except ValueError as e:
            return [], spec.get("name") or url, f"invalid GitHub repositories JSON: {e}"
        error = None if entries else "GitHub organization contained no parseable repositories"
        return entries, spec.get("name") or url, error
    if spec.get("format") == "openai_changelog":
        entries = _parse_openai_changelog_entries(r.content)
        error = None if entries else "OpenAI changelog contained no parseable updates"
        return entries, spec.get("name") or url, error
    if spec.get("format") == "gemini_changelog":
        entries = _parse_gemini_changelog_entries(r.content)
        error = None if entries else "Gemini changelog contained no parseable updates"
        return entries, spec.get("name") or url, error

    feed = feedparser.parse(r.content)
    entries: list[dict] = []
    source = feed.feed.get("title") if feed.feed else url
    # Daily ranking feeds describe one dated snapshot whose items do not have
    # individual publication times. For explicitly opted-in sources, the
    # channel date is the truthful publication time of every ranked item.
    feed_snapshot_date = ""
    if spec.get("snapshot_date_from_feed") and feed.feed:
        feed_snapshot_date = feed.feed.get("published") or feed.feed.get("updated") or ""
    for ent in feed.entries:
        link = _canonical_feed_url(ent.get("link") or "")
        title = (ent.get("title") or "").strip()
        if not link or not title:
            continue
        summary_raw = ent.get("summary") or ent.get("description") or ""
        text = BeautifulSoup(summary_raw, "lxml").get_text(" ", strip=True)
        summary = (text[:280] + "…") if len(text) > 280 else text
        published = ent.get("published") or ent.get("updated") or feed_snapshot_date
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
    entries.sort(key=lambda entry: _parse_ts(entry.get("date") or ""), reverse=True)
    entries = entries[:20]
    if not entries:
        parser_error = str(getattr(feed, "bozo_exception", "") or "").strip()
        detail = f": {parser_error[:180]}" if parser_error else ""
        return [], source, f"feed contained no parseable entries{detail}"
    return entries, source, None


async def _fetch_feed_with_host_policy(
    client: httpx.AsyncClient,
    url: str,
) -> tuple[list[dict], str | None, str | None]:
    """Serialize opt-in same-host feeds so they do not trigger burst limits."""
    spec = FEED_SPEC_BY_URL.get(url, {})
    lock = _HOST_FETCH_LOCKS.get(str(spec.get("host_throttle") or ""))
    if lock is None:
        return await _fetch_feed(client, url)
    async with lock:
        result = await _fetch_feed(client, url)
        await asyncio.sleep(_HOST_THROTTLE_SECONDS)
        return result


def _decide_relevance(
    entry: dict,
    tier: str,
    category: str | None = None,
    curated: bool = False,
) -> tuple[bool, str]:
    """Apply stricter gating as source trust decreases.

    First-party/editorial AI feeds and AI paper categories are curated enough
    to accept directly. Discovery streams (media/community/X/Trending) must
    mention an AI concept, preventing generic popular projects and chatter from
    entering the enrichment queue.
    """
    hit = _is_ai_relevant_keywords(entry.get("title") or "", entry.get("summary") or "")
    if tier == "high" or category == "paper" or curated:
        return True, ("keyword" if hit else "curated")
    return hit, ("keyword" if hit else "rejected")


def _matches_title_keywords(entry: dict, keywords: list[str]) -> bool:
    """Apply an explicit title allowlist to broad first-party feeds."""
    title = str(entry.get("title") or "").casefold()
    for keyword in keywords:
        needle = str(keyword).strip().casefold()
        if not needle:
            continue
        if len(needle) <= 3 and needle.isalnum():
            if re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", title):
                return True
        elif needle in title:
            return True
    return False


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
        dedupe_url = str(cand[2].get("_dedupe_url") or _canonical_feed_url(url))
        if dedupe_url and dedupe_url in seen_urls:
            continue
        category = cand[2].get("category") or "community"
        cap = _CATEGORY_FETCH_CAPS.get(category, global_cap)
        if category_counts.get(category, 0) >= cap:
            continue
        selected.append(cand)
        if dedupe_url:
            seen_urls.add(dedupe_url)
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
        tasks = [_fetch_feed_with_host_policy(client, f) for f in feeds]
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
        m["last_invalid_date"] = 0
        if isinstance(result, Exception):
            m["last_error"] = str(result)
            m["last_error_at"] = m["last_fetch"]
            m["consecutive_failures"] = int(m.get("consecutive_failures") or 0) + 1
            log.warning("feed %s raised: %s", url, result)
            continue
        entries, source_title, err = result  # type: ignore[misc]
        m["name"] = configured_name or source_title or url
        if err:
            m["last_error"] = err
            m["last_error_at"] = m["last_fetch"]
            m["consecutive_failures"] = int(m.get("consecutive_failures") or 0) + 1
            continue
        if m.get("consecutive_failures"):
            m["last_recovered_at"] = m["last_fetch"]
        m["last_error"] = None
        m["last_ok"] = _now_iso()
        m["consecutive_failures"] = 0
        entries = _limit_source_entries(entries, spec)

        eligible_count = 0
        filtered_count = 0
        invalid_date_count = 0
        latest_allowed_ts = datetime.now(timezone.utc).timestamp() + 6 * 3600
        for entry in entries:
            title_keywords = spec.get("title_keywords") or []
            if title_keywords and not _matches_title_keywords(entry, title_keywords):
                filtered_count += 1
                continue
            accept, reason = _decide_relevance(
                entry, tier, category, curated=bool(spec.get("curated")),
            )
            if not accept:
                filtered_count += 1
                continue
            ts = _parse_ts(entry.get("date") or "")
            if not ts or ts > latest_allowed_ts:
                invalid_date_count += 1
                continue
            entry["tier"] = tier
            entry["ai_relevance"] = reason
            entry["translation_status"] = "pending"
            if category:
                entry["category"] = category
            if configured_name:
                entry["source"] = configured_name
            source_priority = int(spec.get("source_priority") or 0)
            candidates.append((tier_rank.get(tier, 9) - source_priority, -ts, entry, m, url))
            eligible_count += 1
        m["eligible"] = eligible_count
        m["last_filtered"] = filtered_count
        m["last_invalid_date"] = invalid_date_count
        _record_quality_sample(m, {
            "at": m["last_fetch"],
            "parsed": len(entries),
            "accepted": eligible_count,
            "filtered": filtered_count,
            "invalid_date": invalid_date_count,
        })

    selected = _select_candidates(candidates)

    added_total = 0
    for _, _, entry, m, _url in selected:
        try:
            article_payload = {key: value for key, value in entry.items() if not key.startswith("_")}
            res = add_article(Article(**article_payload))
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
