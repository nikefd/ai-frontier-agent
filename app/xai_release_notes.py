"""Parse the official API timeline, using publication sections rather than mtime."""
from datetime import datetime, timezone
import re

from bs4 import BeautifulSoup


def _section_years(headings: list) -> dict:
    """Resolve omitted years backwards from explicit month/year boundaries."""
    years = {}
    year, previous_month = None, None
    for heading in reversed(headings):
        match = re.fullmatch(r"([A-Za-z]+)(?:\s+(\d{4}))?", heading.get_text(" ", strip=True))
        try:
            month = datetime.strptime(match[1], "%B").month if match else None
        except ValueError:
            month = None
        if month is None:
            year, previous_month = None, None
            continue
        if match[2]:
            year = int(match[2])
        elif year is not None and previous_month is not None and month < previous_month:
            year += 1
        if year is not None:
            years[id(heading)] = year
        previous_month = month
    return years


def parse_xai_release_notes(content: bytes, source_url: str) -> list[dict]:
    """Read dated cards with real page anchors; ambiguous dates fail closed."""
    soup = BeautifulSoup(content, "lxml")
    main = soup.find("main")
    if main is None:
        return []
    years = _section_years(main.select("h2"))
    entries = []
    seen = set()
    for heading in main.select("h3[id]"):
        year = years.get(id(heading.find_previous("h2")))
        card = heading.find_parent("div", class_="grid")
        date_node = card.find("div", recursive=False) if card else None
        if year is None or date_node is None:
            continue
        date_text = date_node.get_text(" ", strip=True)
        published = None
        for pattern in ("%B %d %Y", "%b %d %Y"):
            try:
                published = datetime.strptime(f"{date_text} {year}", pattern).replace(tzinfo=timezone.utc)
                break
            except ValueError:
                continue
        anchor = heading.get("id")
        title = heading.get_text(" ", strip=True)
        if published is None or not title or anchor in seen:
            continue
        summary = " ".join(p.get_text(" ", strip=True) for p in card.select("p,li"))
        entries.append({"title": title, "url": f"{source_url}#{anchor}",
                        "date": published.isoformat(), "summary": summary[:280], "tags": []})
        seen.add(anchor)
    entries.sort(key=lambda item: item["date"], reverse=True)
    return entries[:20]
