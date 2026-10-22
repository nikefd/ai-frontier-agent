"""Public RSS output for the generated AI briefing archive."""
from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime, timezone
from email.utils import format_datetime
from urllib.parse import urlparse
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request, Response

from ..settings import settings
from ..summary_feed import load_public_summaries, summary_identity

router = APIRouter(tags=["rss"])
_ATOM_NS = "http://www.w3.org/2005/Atom"
ET.register_namespace("atom", _ATOM_NS)


def _as_datetime(raw: object) -> datetime:
    try:
        value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _safe_http_url(raw: object) -> str:
    value = str(raw or "").strip()
    return value if urlparse(value).scheme in {"http", "https"} else ""


def _briefing_html(summary: dict) -> str:
    cohort = summary.get("cohort") if isinstance(summary.get("cohort"), list) else []
    urls = {
        index: _safe_http_url(article.get("url"))
        for index, article in enumerate(cohort, 1)
        if isinstance(article, dict)
    }

    def link_citation(match: re.Match[str]) -> str:
        index = int(match.group(1))
        url = urls.get(index)
        if not url:
            return match.group(0)
        return f'<a href="{html.escape(url, quote=True)}">[{index}]</a>'

    blocks: list[str] = []
    for raw_line in str(summary.get("body") or "").splitlines():
        line = re.sub(r"\[(\d+)]", link_citation, html.escape(raw_line.strip()))
        if not line:
            blocks.append("<br>")
        elif line.startswith("## "):
            blocks.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("- "):
            blocks.append(f"<div>• {line[2:]}</div>")
        else:
            blocks.append(f"<div>{line}</div>")
    return "\n".join(blocks)


def build_digest_rss(summaries: list[dict], base_url: str) -> bytes:
    base = base_url.rstrip("/")
    feed_url = f"{base}/rss/digest.xml"
    summary_url = f"{base}/summary"
    root = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(root, "channel")
    ET.SubElement(channel, "title").text = "AI 前沿速报"
    ET.SubElement(channel, "link").text = summary_url
    ET.SubElement(channel, "description").text = "高密度中文 AI 前沿速报，保留可点击的一手来源。"
    ET.SubElement(channel, "language").text = "zh-CN"
    ET.SubElement(channel, "generator").text = "AI Frontier Agent"
    ET.SubElement(
        channel,
        f"{{{_ATOM_NS}}}link",
        {"href": feed_url, "rel": "self", "type": "application/rss+xml"},
    )

    if summaries:
        ET.SubElement(channel, "lastBuildDate").text = format_datetime(
            _as_datetime(summaries[0].get("generated_at")).astimezone(timezone.utc),
        )

    shanghai = ZoneInfo("Asia/Shanghai")
    for summary in summaries:
        generated = _as_datetime(summary.get("generated_at"))
        local_time = generated.astimezone(shanghai)
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = f"AI 前沿速报 · {local_time:%Y-%m-%d %H:%M}"
        ET.SubElement(item, "link").text = summary_url
        guid = ET.SubElement(item, "guid", {"isPermaLink": "false"})
        guid.text = f"urn:ai-frontier:briefing:{summary_identity(summary)}"
        ET.SubElement(item, "pubDate").text = format_datetime(generated.astimezone(timezone.utc))
        ET.SubElement(item, "description").text = _briefing_html(summary)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _digest_response(request: Request, *, head_only: bool = False) -> Response:
    configured = str(settings.public_base_url or "").strip()
    base_url = configured or str(request.base_url)
    summaries = load_public_summaries()
    payload = build_digest_rss(summaries, base_url)
    etag = f'"{hashlib.sha256(payload).hexdigest()}"'
    headers = {
        "Cache-Control": "public, max-age=300",
        "ETag": etag,
    }
    if summaries:
        headers["Last-Modified"] = format_datetime(
            _as_datetime(summaries[0].get("generated_at")).astimezone(timezone.utc),
            usegmt=True,
        )
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    if head_only:
        headers["Content-Length"] = str(len(payload))
    return Response(
        b"" if head_only else payload,
        media_type="application/rss+xml",
        headers=headers,
    )


@router.get("/rss/digest.xml")
def digest_feed(request: Request) -> Response:
    return _digest_response(request)


@router.head("/rss/digest.xml")
def digest_feed_head(request: Request) -> Response:
    return _digest_response(request, head_only=True)
