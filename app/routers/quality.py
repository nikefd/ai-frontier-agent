"""Operational quality audit and admin-managed must-not-miss benchmarks."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import require_admin
from ..models import UserPublic
from ..quality_report import build_quality_report
from ..storage import read_json, update_json_atomic
from .ai_news import AINEWS_DIR, SUMMARY_FILE, _load_articles, list_sources


router = APIRouter(prefix="/api/ai-news", tags=["ai-news-quality"])
BENCHMARKS_FILE = AINEWS_DIR / "coverage-benchmarks.json"


class BenchmarkCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    occurred_at: datetime
    source_url: str = Field(default="", max_length=500)
    event_key: str = Field(default="", max_length=160)
    match_terms: list[str] = Field(default_factory=list, max_length=8)
    deadline_hours: int = Field(default=24, ge=1, le=168)


def _load_benchmarks() -> list[dict]:
    payload = read_json(BENCHMARKS_FILE, [])
    return payload if isinstance(payload, list) else []


@router.get("/quality/report")
def quality_report() -> dict:
    summary = read_json(SUMMARY_FILE, None)
    return build_quality_report(
        _load_articles(),
        list_sources(),
        summary if isinstance(summary, dict) else None,
        _load_benchmarks(),
    )


@router.get("/quality/benchmarks")
def list_benchmarks(_admin: UserPublic = Depends(require_admin)) -> dict:
    items = _load_benchmarks()
    return {"items": items, "total": len(items)}


@router.post("/quality/benchmarks", status_code=201)
def create_benchmark(
    request: BenchmarkCreate,
    admin: UserPublic = Depends(require_admin),
) -> dict:
    source_url = request.source_url.strip()
    if source_url:
        parsed = urlparse(source_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise HTTPException(status_code=400, detail="source_url 必须是有效的 http(s) URL")
    terms: list[str] = []
    seen: set[str] = set()
    for raw in request.match_terms:
        term = " ".join(raw.split()).strip()
        key = term.casefold()
        if len(term) < 2 or len(term) > 80 or key in seen:
            continue
        terms.append(term)
        seen.add(key)
    event_key = request.event_key.strip()
    if not source_url and not event_key and not terms:
        raise HTTPException(status_code=400, detail="至少提供来源链接、event_key 或一个匹配词")
    title = " ".join(request.title.split())
    if len(title) < 3:
        raise HTTPException(status_code=400, detail="标题至少需要 3 个可见字符")
    occurred = request.occurred_at
    if occurred.tzinfo is None:
        occurred = occurred.replace(tzinfo=timezone.utc)
    occurred = occurred.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    if occurred > now + timedelta(minutes=5):
        raise HTTPException(status_code=400, detail="事件时间不能晚于当前时间")
    item = {
        "id": f"b_{secrets.token_hex(6)}",
        "title": title,
        "occurred_at": occurred.isoformat(),
        "source_url": source_url,
        "event_key": event_key,
        "match_terms": terms,
        "deadline_hours": request.deadline_hours,
        "created_at": now.isoformat(),
        "created_by": admin.id,
    }

    def add(items: list[dict]) -> list[dict]:
        existing = items if isinstance(items, list) else []
        return [item, *existing][:500]

    update_json_atomic(BENCHMARKS_FILE, [], add)
    return item


@router.delete("/quality/benchmarks/{benchmark_id}")
def delete_benchmark(
    benchmark_id: str,
    _admin: UserPublic = Depends(require_admin),
) -> dict:
    removed = False

    def delete(items: list[dict]) -> list[dict]:
        nonlocal removed
        existing = items if isinstance(items, list) else []
        kept = [item for item in existing if item.get("id") != benchmark_id]
        removed = len(kept) != len(existing)
        return kept

    update_json_atomic(BENCHMARKS_FILE, [], delete)
    if not removed:
        raise HTTPException(status_code=404, detail="基准事件不存在")
    return {"ok": True}
