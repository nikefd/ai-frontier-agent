"""Read AI Studio's dated Markdown release notes without inferring dates."""
from datetime import datetime, timezone
import html
import re
from urllib.parse import urljoin


def _plain(value: str) -> str:
    value = re.sub(r"\[([^\]]+)\]\([^\s)]+\)", r"\1", value)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"[`*_~]", "", value))).strip()


def parse_gemini_markdown(content: bytes, source_url: str) -> list[dict]:
    entries, seen = [], set()
    published, anchor, lines = None, "", []

    def flush() -> None:
        if published is None or not lines:
            return
        block = " ".join(lines)
        summary = _plain(block)
        strong = re.match(r"\*\*(.+?)\*\*", block)
        title = _plain(strong[1]) if strong else summary
        links = re.findall(r"\[[^\]]+\]\(([^\s)]+)\)", block)
        link = urljoin(source_url, links[0]) if links else ""
        if not link or link in seen:
            link = f"{source_url}#{anchor}"
        if not title or link in seen:
            return
        seen.add(link)
        entries.append({"title": title[:157] + "…" if len(title) > 160 else title,
                        "url": link, "date": published.isoformat(),
                        "summary": summary[:280] + "…" if len(summary) > 280 else summary,
                        "tags": []})

    for line in content.decode("utf-8", errors="replace").splitlines():
        if line.startswith("## "):
            flush()
            lines, published, anchor = [], None, ""
            heading = re.fullmatch(
                r'##\s+([A-Za-z]+ \d{1,2}, \d{4})(?:\s+\{%\s*id="([^"]+)"\s*%\})?\s*', line,
            )
            if heading:
                try:
                    published = datetime.strptime(heading[1], "%B %d, %Y").replace(tzinfo=timezone.utc)
                    anchor = heading[2] or published.strftime("%m-%d-%Y")
                except ValueError:
                    pass
        elif re.match(r"^[*+-]\s+", line):
            flush()
            lines = [re.sub(r"^[*+-]\s+", "", line)]
        elif lines and (not line.strip() or line.startswith((" ", "\t"))):
            lines.append(line.strip())
        else:
            flush()
            lines = []
    flush()
    entries.sort(key=lambda entry: entry["date"], reverse=True)
    return entries[:20]
