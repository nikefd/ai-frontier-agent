"""Read-only deployment audit; independent samples never enter production state."""
from __future__ import annotations

from datetime import date, datetime, timezone
from urllib.parse import urlsplit, urlunsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class IndependentEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=3, max_length=200)
    source_url: HttpUrl
    published_on: date
    verified_on: date
    reason: str = Field(min_length=3, max_length=500)


def _url(value: object) -> str:
    parts = urlsplit(str(value or ""))
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", ""))


def evaluate_samples(events: list[IndependentEvent], articles: list[dict]) -> dict:
    """Measure snapshot presence only: eviction and date precision limit recall."""
    by_url = {_url(item.get("url")): item for item in articles}
    items = []
    for event in events:
        article = by_url.get(_url(event.source_url))
        items.append({
            **event.model_dump(mode="json"),
            "status": "observed" if article else "not_observed",
            "article_id": article.get("id") if article else None,
        })
    return {
        "total": len(items),
        "observed": sum(item["status"] == "observed" for item in items),
        "items": items,
        "limitation": "仅核对当前滚动库的官方 URL；未观察到不等于从未抓到，日期精度为天，不计算准时召回率。",
    }


async def collect_audit(client: httpx.AsyncClient, events: list[IndependentEvent]) -> dict:
    """Collect public API evidence without auth, writes, source fetches or LLMs."""
    snapshot: dict = {"captured_at": datetime.now(timezone.utc).isoformat(), "checks": []}
    payloads = {}
    paths = {
        "health": "/api/health", "sources": "/api/ai-news/sources",
        "quality": "/api/ai-news/quality/report", "summary": "/api/ai-news/summary/today",
    }
    for name, path in paths.items():
        try:
            response = await client.get(path)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list if name == "sources" else dict):
                raise ValueError("unexpected response shape")
            if name == "sources" and not all(isinstance(source, dict) for source in payload):
                raise ValueError("unexpected source shape")
            if name == "summary" and payload.get("summary") is not None and not isinstance(payload["summary"], dict):
                raise ValueError("unexpected summary shape")
            if name == "quality" and not isinstance(payload.get("benchmark_coverage", {}), dict):
                raise ValueError("unexpected benchmark shape")
            payloads[name] = payload
            snapshot["checks"].append({"name": name, "ok": True})
        except (httpx.HTTPError, ValueError) as error:
            snapshot["checks"].append({"name": name, "ok": False, "error": type(error).__name__})
    sources = payloads.get("sources", [])
    snapshot["health"] = {key: payloads.get("health", {}).get(key) for key in ("ok", "version")}
    snapshot["freshness_fields_available"] = bool(sources) and all("content_status" in s for s in sources)
    snapshot["source_issues"] = [
        {key: s.get(key) for key in ("name", "cadence", "health_status", "consecutive_failures", "content_status")}
        for s in sources if s.get("enabled") is not False and (
            s.get("health_status") != "healthy" or s.get("content_status") == "dormant"
        )
    ]
    quality = payloads.get("quality", {})
    snapshot["quality"] = {key: quality.get(key) for key in ("status", "source_health", "pipeline")}
    snapshot["registered_benchmarks"] = (quality.get("benchmark_coverage") or {}).get("total")
    summary = payloads.get("summary", {}).get("summary") or {}
    snapshot["summary"] = {key: summary.get(key) for key in ("generated_at", "date", "cohort_size")}
    try:
        generated = datetime.fromisoformat(str(summary.get("generated_at")).replace("Z", "+00:00"))
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=timezone.utc)
        snapshot["summary"]["age_hours"] = round((datetime.now(timezone.utc) - generated).total_seconds() / 3600, 2)
    except ValueError:
        snapshot["summary"]["age_hours"] = None
    articles: list[dict] = []
    try:
        expected = None
        for offset in range(0, 1000, 100):
            response = await client.get("/api/ai-news/articles", params={"limit": 100, "offset": offset})
            response.raise_for_status()
            page = response.json()
            total, items = page["total"], page["items"]
            if expected is None:
                expected = total
            if total != expected or not isinstance(items, list):
                raise ValueError("article inventory changed during audit")
            articles.extend(items)
            if len(articles) >= total:
                break
            if not items:
                raise ValueError("incomplete article pagination")
        if len(articles) != expected or len({a["id"] for a in articles}) != expected:
            raise ValueError("incomplete or changing article inventory")
        snapshot["checks"].append({"name": "articles", "ok": True})
        snapshot["independent_sample"] = evaluate_samples(events, articles)
        snapshot["article_count"] = len(articles)
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
        snapshot["checks"].append({"name": "articles", "ok": False, "error": type(error).__name__})
        snapshot["independent_sample"] = None
    snapshot["ok"] = all(check["ok"] for check in snapshot["checks"]) and snapshot["health"]["ok"] is True
    return snapshot
