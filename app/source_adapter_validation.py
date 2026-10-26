"""SSRF-safe production validation for discovered page-based sources."""
from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from .auto_listing import parse_auto_listing_entries
from .safe_fetch import fetch_public_document


_UPDATE_TOKENS = {"blog", "news", "changelog", "release-notes", "releases", "research", "updates"}


def _same_site(left: str, right: str) -> bool:
    left_host = (urlsplit(left).hostname or "").lower()
    right_host = (urlsplit(right).hostname or "").lower()
    return bool(left_host and right_host) and (
        left_host == right_host
        or left_host.endswith(f".{right_host}")
        or right_host.endswith(f".{left_host}")
    )


async def _sitemap_locations(raw: bytes, sitemap_url: str, source_url: str) -> list[str]:
    soup = BeautifulSoup(raw, "xml")
    locations = [
        node.find("loc").get_text(strip=True)
        for node in soup.find_all("url") if node.find("loc")
    ]
    if locations:
        return locations
    child_urls = [
        node.find("loc").get_text(strip=True)
        for node in soup.find_all("sitemap") if node.find("loc")
    ]
    children = await asyncio.gather(*(
        fetch_public_document(child_url, 1_000_000)
        for child_url in child_urls[:4] if _same_site(child_url, source_url)
    ), return_exceptions=True)
    for result in children:
        if isinstance(result, Exception):
            continue
        child_raw, final_url, _, _ = result
        if not _same_site(final_url, sitemap_url):
            continue
        child = BeautifulSoup(child_raw, "xml")
        locations.extend(
            node.find("loc").get_text(strip=True)
            for node in child.find_all("url") if node.find("loc")
        )
    return locations


def _include_paths(locations: list[str], source_url: str) -> list[str]:
    counts: dict[str, int] = {}
    for location in locations:
        parts = [part for part in urlsplit(location).path.split("/") if part]
        for index, part in enumerate(parts[:-1]):
            if part.lower() in _UPDATE_TOKENS:
                prefix = "/" + "/".join(parts[:index + 1]) + "/"
                counts[prefix] = counts.get(prefix, 0) + 1
                break
    source_parent = urlsplit(source_url).path.rsplit("/", 1)[0].rstrip("/") + "/"
    prioritized = []
    if source_parent != "/" and any(
        urlsplit(location).path.startswith(source_parent) for location in locations
    ):
        prioritized.append(source_parent)
    ranked = sorted(counts, key=lambda prefix: (-counts[prefix], len(prefix), prefix))
    return list(dict.fromkeys([*prioritized, *ranked]))[:4]


async def _validate_sitemap(url: str, source_url: str) -> dict | None:
    try:
        raw, final_url, _, _ = await fetch_public_document(url, 1_000_000)
    except Exception:
        return None
    if not _same_site(final_url, source_url):
        return None
    locations = [
        item for item in await _sitemap_locations(raw, final_url, source_url)
        if _same_site(item, source_url)
    ]
    include_paths = _include_paths(locations, source_url)
    if not include_paths:
        return None
    matching = [
        item for item in locations
        if any(urlsplit(item).path.startswith(prefix) for prefix in include_paths)
    ]
    pages = await asyncio.gather(*(
        fetch_public_document(item, 1_000_000) for item in matching[:6]
    ), return_exceptions=True)
    from .workers.ai_news_fetcher import _parse_page_metadata

    dated = 0
    for result in pages:
        if isinstance(result, Exception):
            continue
        page_raw, page_url, content_type, _ = result
        if _same_site(page_url, source_url) and content_type in {
            "text/html", "application/xhtml+xml",
        } and _parse_page_metadata(page_raw).get("date"):
            dated += 1
    if not dated:
        return None
    return {
        "url": final_url, "kind": "sitemap", "ready": True,
        "entry_count": len(matching), "dated_entries": dated, "latest_at": None,
        "adapter": {"format": "sitemap", "include_paths": include_paths},
        "evidence": f"接入前验证；匹配 {len(matching)} 个内容 URL，抽样确认 {dated} 个真实发布日期",
        "next_step": "可按 fast 官方 Sitemap 接入",
    }


async def _validate_update_page(url: str, source_url: str) -> dict | None:
    try:
        raw, final_url, content_type, _ = await fetch_public_document(url, 1_000_000)
    except Exception:
        return None
    if not _same_site(final_url, source_url) or content_type not in {
        "text/html", "application/xhtml+xml",
    }:
        return None
    entries = parse_auto_listing_entries(raw, final_url)
    if len(entries) < 2:
        return None
    return {
        "url": final_url, "kind": "update_page", "ready": True,
        "entry_count": len(entries), "dated_entries": len(entries),
        "latest_at": entries[0]["date"], "adapter": {"format": "auto_listing"},
        "evidence": f"接入前验证；识别 {len(entries)} 个带日期的同站更新卡片",
        "next_step": "可按 fast 官方更新页接入",
    }


async def validate_page_adapter(url: str, source_url: str, kind: str) -> dict | None:
    if kind == "sitemap":
        return await _validate_sitemap(url, source_url)
    if kind == "update_page":
        return await _validate_update_page(url, source_url)
    return None
