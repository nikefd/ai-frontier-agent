"""Small parsers for high-value official pages with non-generic markup."""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag


_LUMA_SIGNAL_CATEGORIES = {"Product", "Engineering"}


def _luma_card(anchor: Tag) -> Tag | None:
    node = anchor.parent
    for _ in range(4):
        if not isinstance(node, Tag):
            return None
        if node.name == "div" and "group" in (node.get("class") or []):
            return node
        node = node.parent
    return None


def _luma_date(card: Tag) -> str:
    for node in card.find_all("span"):
        text = node.get_text(" ", strip=True)
        for date_format in ("%b %d, %Y", "%B %d, %Y"):
            try:
                return datetime.strptime(text, date_format).replace(
                    tzinfo=timezone.utc,
                ).isoformat()
            except ValueError:
                continue
    return ""


def parse_luma_news_entries(content: bytes, source_url: str) -> list[dict]:
    """Extract Luma product/engineering releases and reject SEO/company noise."""
    soup = BeautifulSoup(content, "lxml")
    entries: list[dict] = []
    seen_urls: set[str] = set()
    source_host = urlsplit(source_url).hostname
    for anchor in soup.select("a.card-link[href^='/news/']"):
        card = _luma_card(anchor)
        if card is None:
            continue
        labels = {node.get_text(" ", strip=True) for node in card.find_all("span")}
        if not labels.intersection(_LUMA_SIGNAL_CATEGORIES):
            continue
        title = " ".join(anchor.get_text(" ", strip=True).split())
        link = urljoin(source_url, str(anchor.get("href") or "")).split("#", 1)[0]
        date = _luma_date(card)
        if (
            len(title) < 4
            or not date
            or urlsplit(link).hostname != source_host
            or link in seen_urls
        ):
            continue
        entries.append({
            "title": title,
            "url": link,
            "date": date,
            "summary": "",
            "tags": [],
        })
        seen_urls.add(link)
    entries.sort(key=lambda entry: entry["date"], reverse=True)
    return entries[:20]
