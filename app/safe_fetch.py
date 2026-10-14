"""SSRF-safe fetching and inert HTML rendering for the article reader."""
from __future__ import annotations

import asyncio
import html as html_lib
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

MAX_REDIRECTS = 5
MAX_HTML_BYTES = 2_000_000


class UnsafeUrl(ValueError):
    pass


def _parse_http_url(url: str):
    try:
        parsed = urlsplit((url or "").strip())
        _ = parsed.port  # Force validation of malformed/out-of-range ports.
    except ValueError as exc:
        raise UnsafeUrl("invalid URL") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeUrl("only public http(s) URLs are allowed")
    if parsed.username or parsed.password:
        raise UnsafeUrl("URL credentials are not allowed")
    return parsed


def _is_public_ip(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_global
    except ValueError:
        return False


def _resolve_public(host: str, port: int) -> None:
    lowered = host.rstrip(".").lower()
    if lowered == "localhost" or lowered.endswith((".localhost", ".local", ".internal")):
        raise UnsafeUrl("local network addresses are not allowed")
    try:
        literal = ipaddress.ip_address(lowered)
    except ValueError:
        literal = None
    if literal is not None:
        if not literal.is_global:
            raise UnsafeUrl("private or reserved addresses are not allowed")
        return
    try:
        answers = socket.getaddrinfo(lowered, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeUrl("host could not be resolved") from exc
    addresses = {answer[4][0] for answer in answers}
    if not addresses or any(not _is_public_ip(addr) for addr in addresses):
        raise UnsafeUrl("host resolves to a private or reserved address")


async def validate_public_http_url(url: str) -> str:
    parsed = _parse_http_url(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    await asyncio.to_thread(_resolve_public, parsed.hostname or "", port)
    return parsed.geturl()


async def fetch_public_html(url: str) -> tuple[str, str]:
    """Fetch bounded HTML, revalidating every redirect target."""
    current = url
    timeout = httpx.Timeout(15.0, connect=7.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False) as client:
        for _ in range(MAX_REDIRECTS + 1):
            current = await validate_public_http_url(current)
            async with client.stream(
                "GET", current, headers={"User-Agent": "Mozilla/5.0 ai-frontier-agent-reader/1"}
            ) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise httpx.HTTPStatusError(
                            "redirect without location", request=response.request, response=response
                        )
                    current = urljoin(current, location)
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if content_type not in {"text/html", "application/xhtml+xml"}:
                    raise UnsafeUrl("reader only accepts HTML documents")
                declared = response.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > MAX_HTML_BYTES:
                    raise UnsafeUrl("document is too large")
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_HTML_BYTES:
                        raise UnsafeUrl("document is too large")
                    chunks.append(chunk)
                encoding = response.charset_encoding or "utf-8"
                return b"".join(chunks).decode(encoding, errors="replace"), current
        raise UnsafeUrl("too many redirects")


_DROP_TAGS = {
    "base", "button", "embed", "form", "frame", "frameset", "iframe", "input",
    "link", "math", "meta", "noscript", "object", "script", "select", "style",
    "svg", "textarea",
}
_ALLOWED_TAGS = {
    "a", "article", "b", "blockquote", "br", "code", "dd", "div", "dl", "dt",
    "em", "figcaption", "figure", "footer", "h1", "h2", "h3", "h4", "h5", "h6",
    "header", "hr", "i", "li", "main", "nav", "ol", "p", "pre", "section", "small",
    "span", "strong", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "u", "ul",
}


def sanitize_reader_html(raw_html: str, source_url: str) -> str:
    """Return a self-contained, inert same-origin reader document."""
    try:
        safe_source_url = _parse_http_url(source_url).geturl()
    except UnsafeUrl:
        safe_source_url = ""
    soup = BeautifulSoup(raw_html or "", "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else "阅读原文"
    for tag in list(soup.find_all(_DROP_TAGS)):
        tag.decompose()
    for tag in list(soup.find_all(True)):
        if tag.name not in _ALLOWED_TAGS:
            tag.unwrap()
            continue
        kept = {}
        if tag.name == "a":
            href = urljoin(safe_source_url, tag.get("href") or "")
            try:
                parsed = _parse_http_url(href)
            except UnsafeUrl:
                pass
            else:
                kept = {"href": parsed.geturl(), "target": "_blank", "rel": "noopener noreferrer"}
        elif tag.name in {"td", "th"}:
            for attr in ("colspan", "rowspan"):
                value = tag.get(attr)
                if value and str(value).isdigit():
                    kept[attr] = str(value)
        tag.attrs = kept
    body = soup.body or soup
    content = "".join(str(child) for child in body.contents)
    safe_url = html_lib.escape(safe_source_url, quote=True)
    safe_title = html_lib.escape(title, quote=False)
    origin_link = (
        f"<a href='{safe_url}' target='_blank' rel='noopener noreferrer'>打开原站 ↗</a>"
        if safe_source_url
        else "原站地址不可用"
    )
    return (
        "<!doctype html><!-- aif-safe-reader-v2 --><html lang='zh-CN'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{safe_title}</title>"
        "<style>body{max-width:820px;margin:32px auto;padding:0 18px;font:16px/1.7 system-ui,sans-serif;color:#172033}"
        ".origin{padding:10px 12px;background:#f3f4f6;border-radius:8px;overflow-wrap:anywhere}"
        "pre{overflow:auto;background:#f6f8fa;padding:12px}table{border-collapse:collapse;max-width:100%}"
        "td,th{border:1px solid #d0d7de;padding:6px}a{color:#6d28d9}</style></head><body>"
        f"<p class='origin'>安全阅读副本 · {origin_link}</p>"
        f"{content}</body></html>"
    )
