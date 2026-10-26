"""Conservative parser for dated first-party update listing pages."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag


_DATE_PATTERNS = (
    re.compile(r"\b(20\d{2})[-/.](0?[1-9]|1[0-2])[-/.](0?[1-9]|[12]\d|3[01])\b"),
    re.compile(r"\b(20\d{2})年(0?[1-9]|1[0-2])月(0?[1-9]|[12]\d|3[01])日"),
)
_MONTH_FORMATS = ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y")
_MONTH_PATTERN = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\s+\d{1,2},\s+20\d{2}\b",
    re.IGNORECASE,
)


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _date(value: object) -> str:
    text = _clean(value)
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except ValueError:
        pass
    for pattern in _DATE_PATTERNS:
        match = pattern.search(text)
        if match:
            try:
                return datetime(
                    *(int(part) for part in match.groups()), tzinfo=timezone.utc,
                ).isoformat()
            except ValueError:
                return ""
    month_match = _MONTH_PATTERN.search(text)
    month_value = month_match.group(0) if month_match else text
    for date_format in _MONTH_FORMATS:
        try:
            return datetime.strptime(month_value, date_format).replace(
                tzinfo=timezone.utc,
            ).isoformat()
        except ValueError:
            continue
    return ""


def _same_site(left: str, right: str) -> bool:
    left_host = (urlsplit(left).hostname or "").lower()
    right_host = (urlsplit(right).hostname or "").lower()
    return bool(left_host and right_host) and (
        left_host == right_host
        or left_host.endswith(f".{right_host}")
        or right_host.endswith(f".{left_host}")
    )


def _dated_container(anchor: Tag) -> Tag | None:
    node: Tag | None = anchor
    for _ in range(5):
        if node is None:
            return None
        time_node = node.find("time")
        time_value = time_node.get("datetime") if time_node else ""
        if _date(time_value or (time_node.get_text(" ") if time_node else "")):
            return node
        text = node.get_text(" ", strip=True)
        if len(text) <= 1200 and _date(text):
            return node
        parent = node.parent
        node = parent if isinstance(parent, Tag) and parent.name in {
            "article", "li", "div", "section", "a",
        } else None
    return None


def parse_auto_listing_entries(content: bytes, source_url: str) -> list[dict]:
    """Extract same-site linked updates only when title and date are explicit."""
    soup = BeautifulSoup(content, "lxml")
    entries: list[dict] = []
    seen_urls: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        link = urljoin(source_url, str(anchor.get("href") or "").strip()).split("#", 1)[0]
        parsed = urlsplit(link)
        if parsed.scheme not in {"http", "https"} or not _same_site(link, source_url):
            continue
        if link.rstrip("/") == source_url.split("#", 1)[0].rstrip("/") or link in seen_urls:
            continue
        container = _dated_container(anchor)
        if container is None:
            continue
        heading = container.find(["h1", "h2", "h3", "h4"])
        if heading:
            heading_anchor = (
                heading if heading.name == "a" and heading.get("href")
                else heading.find("a", href=True) or heading.find_parent("a", href=True)
            )
            primary_anchor = heading_anchor or container.find("a", href=True)
            if primary_anchor is not anchor:
                continue
        title = _clean(
            (heading.get("title") or heading.get_text(" ")) if heading
            else (anchor.get("title") or anchor.get_text(" "))
        )
        time_node = container.find("time")
        date = _date(
            (time_node.get("datetime") or time_node.get_text(" ")) if time_node
            else container.get_text(" ", strip=True)
        )
        if len(title) < 4 or not date:
            continue
        summary_node = container.find("p")
        summary = _clean(summary_node.get_text(" ") if summary_node else "")
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
    entries.sort(key=lambda entry: entry["date"], reverse=True)
    return entries[:20]
