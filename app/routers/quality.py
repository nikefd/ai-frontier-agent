"""Operational quality audit and admin-managed must-not-miss benchmarks."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..auth import require_admin
from ..models import UserPublic
from ..quality_report import (
    build_benchmark_candidates,
    build_benchmark_coverage,
    build_quality_report,
)
from ..storage import read_json, update_json_atomic
from .ai_news import (
    AINEWS_DIR,
    FEED_SPEC_BY_URL,
    SUMMARY_FILE,
    _load_articles,
    _load_sources_meta,
    list_sources,
)


router = APIRouter(prefix="/api/ai-news", tags=["ai-news-quality"])
BENCHMARKS_FILE = AINEWS_DIR / "coverage-benchmarks.json"


class BenchmarkCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    occurred_at: datetime
    source_url: str = Field(default="", max_length=500)
    event_key: str = Field(default="", max_length=160)
    match_terms: list[str] = Field(default_factory=list, max_length=8)
    deadline_hours: int = Field(default=24, ge=1, le=168)
    origin: Literal["manual", "independent", "candidate"] = "manual"


class RemediationUpdate(BaseModel):
    action: Literal["start", "close", "reopen"]
    outcome: Literal["fixed", "accepted", "false_positive"] | None = None
    note: str = Field(default="", max_length=500)


class SourceActivation(BaseModel):
    url: str = Field(min_length=8, max_length=500)
    name: str = Field(min_length=2, max_length=80)


class SourceStateUpdate(BaseModel):
    url: str = Field(min_length=8, max_length=500)
    enabled: bool


def _load_benchmarks() -> list[dict]:
    payload = read_json(BENCHMARKS_FILE, [])
    return payload if isinstance(payload, list) else []


def _coverage_item(benchmark_id: str) -> dict | None:
    coverage = build_benchmark_coverage(
        _load_articles(), _load_benchmarks(), now=datetime.now(timezone.utc), sources=list_sources(),
    )
    return next((item for item in coverage["items"] if item.get("id") == benchmark_id), None)


@router.get("/quality/report")
def quality_report() -> dict:
    summary = read_json(SUMMARY_FILE, None)
    sources = list_sources()
    source_meta = _load_sources_meta()
    for source in sources:
        source["quality_samples"] = source_meta.get(source["url"], {}).get(
            "quality_samples", [],
        )
        source["quality_policy"] = (
            "title_keywords"
            if FEED_SPEC_BY_URL.get(source["url"], {}).get("title_keywords")
            else "default"
        )
    return build_quality_report(
        _load_articles(),
        sources,
        summary if isinstance(summary, dict) else None,
        _load_benchmarks(),
    )


@router.get("/quality/benchmarks")
def list_benchmarks(_admin: UserPublic = Depends(require_admin)) -> dict:
    items = _load_benchmarks()
    return {"items": items, "total": len(items)}


@router.get("/quality/benchmark-candidates")
def list_benchmark_candidates(_admin: UserPublic = Depends(require_admin)) -> dict:
    return build_benchmark_candidates(
        _load_articles(),
        _load_benchmarks(),
        now=datetime.now(timezone.utc),
    )


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
    if request.origin == "independent" and not source_url:
        raise HTTPException(status_code=400, detail="独立基准必须提供可核验的官方来源链接")
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
        "origin": request.origin,
    }

    def add(items: list[dict]) -> list[dict]:
        existing = items if isinstance(items, list) else []
        return [item, *existing][:500]

    update_json_atomic(BENCHMARKS_FILE, [], add)
    return item


@router.patch("/quality/benchmarks/{benchmark_id}/remediation")
def update_remediation(
    benchmark_id: str,
    request: RemediationUpdate,
    admin: UserPublic = Depends(require_admin),
) -> dict:
    current = _coverage_item(benchmark_id)
    if not current:
        raise HTTPException(status_code=404, detail="基准事件不存在或不在当前评测窗口")
    if not current.get("diagnosis"):
        raise HTTPException(status_code=409, detail="当前基准没有需要处理的迟到或漏报问题")
    if request.action == "close" and (not request.outcome or len(request.note.strip()) < 3):
        raise HTTPException(status_code=400, detail="关闭问题时请选择结果并填写至少 3 个字符的说明")
    now = datetime.now(timezone.utc).isoformat()
    updated: dict | None = None

    def change(items: list[dict]) -> list[dict]:
        nonlocal updated
        for item in items if isinstance(items, list) else []:
            if item.get("id") != benchmark_id:
                continue
            previous = item.get("remediation") if isinstance(item.get("remediation"), dict) else {}
            status = "closed" if request.action == "close" else (
                "in_progress" if request.action == "start" else "open"
            )
            remediation = {
                **previous,
                "status": status,
                "outcome": request.outcome if status == "closed" else None,
                "note": request.note.strip() if status == "closed" else "",
                "diagnosis_code": (current.get("diagnosis") or {}).get("code"),
                "updated_at": now,
                "updated_by": admin.id,
            }
            if request.action == "start" and not previous.get("started_at"):
                remediation["started_at"] = now
            item["remediation"] = remediation
            updated = remediation
            break
        return items

    update_json_atomic(BENCHMARKS_FILE, [], change)
    if not updated:
        raise HTTPException(status_code=404, detail="基准事件不存在")
    return {"ok": True, "remediation": updated}


@router.post("/quality/benchmarks/{benchmark_id}/recheck")
async def recheck_benchmark(
    benchmark_id: str,
    admin: UserPublic = Depends(require_admin),
) -> dict:
    current = _coverage_item(benchmark_id)
    if not current:
        raise HTTPException(status_code=404, detail="基准事件不存在或不在当前评测窗口")
    source_url = str(((current.get("diagnosis") or {}).get("source") or {}).get("url") or "")
    if not source_url:
        raise HTTPException(status_code=409, detail="当前诊断没有可复测的已配置来源")
    from ..workers.ai_news_fetcher import fetch_once

    added = await fetch_once([source_url])
    now = datetime.now(timezone.utc).isoformat()

    def record(items: list[dict]) -> list[dict]:
        for item in items if isinstance(items, list) else []:
            if item.get("id") != benchmark_id:
                continue
            previous = item.get("remediation") if isinstance(item.get("remediation"), dict) else {}
            item["remediation"] = {
                **previous,
                "status": "in_progress" if previous.get("status") != "closed" else "closed",
                "last_recheck_at": now,
                "last_recheck_added": added,
                "updated_at": now,
                "updated_by": admin.id,
            }
            break
        return items

    update_json_atomic(BENCHMARKS_FILE, [], record)
    return {"ok": True, "added": added, "item": _coverage_item(benchmark_id)}


@router.post("/quality/benchmarks/{benchmark_id}/discover-sources")
async def discover_benchmark_sources(
    benchmark_id: str,
    admin: UserPublic = Depends(require_admin),
) -> dict:
    current = _coverage_item(benchmark_id)
    if not current:
        raise HTTPException(status_code=404, detail="基准事件不存在或不在当前评测窗口")
    if (current.get("diagnosis") or {}).get("code") != "source_not_configured":
        raise HTTPException(status_code=409, detail="仅未接入官方来源的诊断可以自动发现入口")
    from ..source_discovery import discover_official_sources

    candidates = await discover_official_sources(str(current.get("source_url") or ""))
    now = datetime.now(timezone.utc).isoformat()

    def record(items: list[dict]) -> list[dict]:
        for item in items if isinstance(items, list) else []:
            if item.get("id") != benchmark_id:
                continue
            previous = item.get("remediation") if isinstance(item.get("remediation"), dict) else {}
            item["remediation"] = {
                **previous,
                "status": "in_progress" if previous.get("status") != "closed" else "closed",
                "source_discovery_at": now,
                "source_candidates": candidates,
                "updated_at": now,
                "updated_by": admin.id,
            }
            break
        return items

    update_json_atomic(BENCHMARKS_FILE, [], record)
    return {"ok": True, "total": len(candidates), "items": candidates}


@router.post("/quality/benchmarks/{benchmark_id}/activate-source")
async def activate_benchmark_source(
    benchmark_id: str,
    request: SourceActivation,
    admin: UserPublic = Depends(require_admin),
) -> dict:
    current = _coverage_item(benchmark_id)
    if not current:
        raise HTTPException(status_code=404, detail="基准事件不存在或不在当前评测窗口")
    if (current.get("diagnosis") or {}).get("code") != "source_not_configured":
        raise HTTPException(status_code=409, detail="仅未接入官方来源的诊断可以接入候选")
    stored = next((item for item in _load_benchmarks() if item.get("id") == benchmark_id), None)
    candidates = ((stored or {}).get("remediation") or {}).get("source_candidates") or []
    from ..source_activation import SourceActivationError, activate_source_candidate

    try:
        result = await activate_source_candidate(
            benchmark_id=benchmark_id,
            candidate_url=request.url,
            name=request.name,
            source_url=str(current.get("source_url") or ""),
            title=str(current.get("title") or ""),
            candidates=candidates,
            admin_id=admin.id,
            benchmarks_file=BENCHMARKS_FILE,
        )
    except SourceActivationError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"ok": True, **result}


@router.patch("/sources/custom")
def update_custom_source(
    request: SourceStateUpdate,
    admin: UserPublic = Depends(require_admin),
) -> dict:
    from ..source_management import SourceManagementError, update_source_state

    try:
        source = update_source_state(request.url, request.enabled, admin.id, BENCHMARKS_FILE)
    except SourceManagementError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"ok": True, "source": source}


@router.delete("/sources/custom")
def delete_custom_source_config(
    url: str = Query(min_length=8, max_length=500),
    admin: UserPublic = Depends(require_admin),
) -> dict:
    from ..source_management import SourceManagementError, remove_source

    try:
        source = remove_source(url, admin.id, BENCHMARKS_FILE)
    except SourceManagementError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"ok": True, "source": source, "articles_preserved": True}


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
