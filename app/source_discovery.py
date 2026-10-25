"""SSRF-safe discovery and validation of official source candidates."""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit, urlunsplit

import feedparser
from bs4 import BeautifulSoup

from .safe_fetch import fetch_public_document

_DISCOVERY_LIMIT = 10
_COMMON_PATHS = ("/feed", "/feed.xml", "/rss.xml", "/atom.xml", "/sitemap.xml")
_UPDATE_TOKENS = ("blog", "news", "changelog", "release-notes", "releases", "research", "updates")


def _origin(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def _same_site(candidate: str, source_url: str) -> bool:
    left = (urlsplit(candidate).hostname or "").lower()
    right = (urlsplit(source_url).hostname or "").lower()
    return bool(left and right) and (
        left == right or left.endswith(f".{right}") or right.endswith(f".{left}")
    )


def _normalized_candidate_url(url: str) -> str:
    parsed = urlsplit(url)
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))


def _path_has_update_token(path: str) -> bool:
    segments = (part for part in path.lower().split("/") if part)
    return any(
        segment == token or segment.startswith(f"{token}-") or segment.endswith(f"-{token}")
        for segment in segments
        for token in _UPDATE_TOKENS
    )


def _published_at(entry: dict) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime(*parsed[:6], tzinfo=timezone.utc)


def _html_candidates(raw: bytes, page_url: str, source_url: str) -> list[tuple[str, str, str]]:
    soup = BeautifulSoup(raw, "lxml")
    found: list[tuple[str, str, str]] = []
    for link in soup.find_all("link", href=True):
        rel = {str(value).lower() for value in (link.get("rel") or [])}
        media_type = str(link.get("type") or "").lower()
        if "alternate" in rel and media_type in {"application/rss+xml", "application/atom+xml"}:
            found.append((urljoin(page_url, link["href"]), "feed", "页面声明的 RSS/Atom"))
    for link in soup.find_all("a", href=True):
        target = urljoin(page_url, link["href"])
        path = (urlsplit(target).path or "").lower()
        if _same_site(target, source_url) and _path_has_update_token(path):
            found.append((target, "update_page", "官网导航中的更新入口"))
    return found


async def _inspect_candidate(seed: tuple[str, str, str], source_url: str) -> dict | None:
    url, hint, evidence = seed
    try:
        raw, final_url, content_type, encoding = await fetch_public_document(url, 1_000_000)
    except Exception:  # An unavailable guess is not a candidate.
        return None
    if not _same_site(final_url, source_url):
        return None
    final_path = urlsplit(final_url).path.lower()
    final_path_parts = {part for part in final_path.split("/") if part}
    if hint == "feed" and "comments" in final_path_parts:
        return None
    if hint == "update_page" and not _path_has_update_token(final_path):
        return None
    parsed = feedparser.parse(raw)
    if parsed.entries:
        dates = [date for entry in parsed.entries if (date := _published_at(entry))]
        kind = "atom" if b"<feed" in raw[:1000].lower() else "rss"
        return {
            "url": final_url,
            "kind": kind,
            "ready": bool(dates),
            "entry_count": len(parsed.entries),
            "dated_entries": len(dates),
            "latest_at": max(dates).isoformat() if dates else None,
            "evidence": f"{evidence}；可解析 {len(parsed.entries)} 条，其中 {len(dates)} 条带日期",
            "next_step": "可按 fast 官方源接入" if dates else "需先解决条目发布时间缺失",
        }
    soup = BeautifulSoup(raw, "xml")
    sitemap_urls = soup.find_all("url")
    if sitemap_urls:
        return {
            "url": final_url,
            "kind": "sitemap",
            "ready": False,
            "entry_count": len(sitemap_urls),
            "dated_entries": sum(node.find("lastmod") is not None for node in sitemap_urls),
            "latest_at": None,
            "evidence": f"{evidence}；有效 sitemap，包含 {len(sitemap_urls)} 个 URL",
            "next_step": "选择稳定内容路径，并从落地页提取真实发布日期",
        }
    if hint != "update_page" or content_type not in {"text/html", "application/xhtml+xml"}:
        return None
    html = raw.decode(encoding, errors="replace")
    page = BeautifulSoup(html, "lxml")
    relevant_links = {
        urljoin(final_url, link.get("href") or "")
        for link in page.find_all("a", href=True)
        if any(token in str(link.get("href") or "").lower() for token in _UPDATE_TOKENS)
    }
    visible_items = max(len(page.find_all("article")), len(relevant_links))
    if visible_items < 2:
        return None
    dated = len(page.find_all("time")) + len(re.findall(r"\b20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}\b", html))
    return {
        "url": final_url,
        "kind": "update_page",
        "ready": False,
        "entry_count": visible_items,
        "dated_entries": dated,
        "latest_at": None,
        "evidence": f"{evidence}；页面可访问并发现约 {visible_items} 个更新入口",
        "next_step": "配置 html_listing 选择器并验证每条真实发布日期",
    }


async def discover_official_sources(source_url: str) -> list[dict]:
    """Find same-site source candidates from an official benchmark URL."""
    origin = _origin(source_url)
    page_urls = list(dict.fromkeys((source_url, f"{origin}/")))
    pages = await asyncio.gather(
        *(fetch_public_document(url, 1_000_000) for url in page_urls),
        return_exceptions=True,
    )
    seeds: list[tuple[str, str, str]] = []
    for result in pages:
        if isinstance(result, Exception):
            continue
        raw, final_url, content_type, _ = result
        if content_type in {"text/html", "application/xhtml+xml"}:
            seeds.extend(_html_candidates(raw, final_url, source_url))
    source_path = (urlsplit(source_url).path or "").lower()
    if _path_has_update_token(source_path):
        seeds.append((source_url, "update_page", "基准指向的官方更新页面"))
    seeds.extend(
        (f"{origin}{path}", "sitemap" if "sitemap" in path else "feed", "官网常见入口探测")
        for path in _COMMON_PATHS
    )
    unique: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for url, hint, evidence in seeds:
        normalized = url.split("#", 1)[0]
        if normalized in seen or not _same_site(normalized, source_url):
            continue
        seen.add(normalized)
        unique.append((normalized, hint, evidence))
        if len(unique) >= _DISCOVERY_LIMIT:
            break
    inspected = await asyncio.gather(
        *(_inspect_candidate(seed, source_url) for seed in unique)
    )
    candidates: list[dict] = []
    final_seen: set[str] = set()
    for item in inspected:
        if not item:
            continue
        normalized = _normalized_candidate_url(item["url"])
        if normalized in final_seen:
            continue
        final_seen.add(normalized)
        candidates.append(item)
    return sorted(
        candidates,
        key=lambda item: (not item["ready"], {"rss": 0, "atom": 0, "sitemap": 1}.get(item["kind"], 2), item["url"]),
    )[:6]


async def validate_discovered_feed(url: str, source_url: str) -> dict | None:
    """Revalidate a stored RSS/Atom candidate immediately before activation."""
    item = await _inspect_candidate((url, "feed", "接入前重新验证"), source_url)
    if not item or item.get("kind") not in {"rss", "atom"} or not item.get("ready"):
        return None
    return item
