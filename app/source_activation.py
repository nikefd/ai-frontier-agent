"""Activate one verified discovery candidate as a persistent fast source."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .custom_sources import add_custom_source
from .source_discovery import validate_discovered_feed
from .storage import update_json_atomic


class SourceActivationError(ValueError):
    pass


async def activate_source_candidate(
    *,
    benchmark_id: str,
    candidate_url: str,
    name: str,
    source_url: str,
    title: str,
    candidates: list[dict],
    admin_id: str,
    benchmarks_file: Path,
) -> dict:
    candidate = next(
        (item for item in candidates if isinstance(item, dict) and item.get("url") == candidate_url),
        None,
    )
    if not candidate or candidate.get("kind") not in {"rss", "atom"} or not candidate.get("ready"):
        raise SourceActivationError("该候选尚未达到可直接接入标准")

    normalized_name = " ".join(name.split())
    if len(normalized_name) < 2:
        raise SourceActivationError("来源名称至少需要 2 个可见字符")
    verified = await validate_discovered_feed(candidate_url, source_url)
    if not verified:
        raise SourceActivationError("候选重新验证失败，请先重新发现入口")

    from .routers.ai_news import (
        CUSTOM_SOURCES_FILE,
        FEED_SPEC_BY_URL,
        list_sources,
        register_custom_feed_spec,
    )

    url = str(verified["url"])
    configured_names = {str(item.get("name") or "").casefold() for item in list_sources()}
    if url in FEED_SPEC_BY_URL or normalized_name.casefold() in configured_names:
        raise SourceActivationError("相同地址或名称的来源已经存在")

    now = datetime.now(timezone.utc).isoformat()
    spec = {
        "url": url,
        "name": normalized_name,
        "kind": str(verified["kind"]),
        "tier": "high",
        "category": "vendor",
        "cadence": "fast",
        "custom": True,
        "description": f"自动发现的官方来源 · 来自必达事件「{title[:80]}」",
        "benchmark_id": benchmark_id,
        "created_at": now,
        "created_by": admin_id,
    }
    if not add_custom_source(CUSTOM_SOURCES_FILE, spec) or not register_custom_feed_spec(spec):
        raise SourceActivationError("该来源已经接入")

    from .workers.ai_news_fetcher import fetch_once

    added = await fetch_once([url])

    def record(items: list[dict]) -> list[dict]:
        for item in items if isinstance(items, list) else []:
            if item.get("id") != benchmark_id:
                continue
            remediation = item.get("remediation") if isinstance(item.get("remediation"), dict) else {}
            updated_candidates = []
            for source_candidate in remediation.get("source_candidates") or []:
                updated = dict(source_candidate)
                if updated.get("url") == candidate_url:
                    updated.update({
                        "activated_at": now,
                        "activated_url": url,
                        "activated_name": normalized_name,
                        "activated_added": added,
                    })
                updated_candidates.append(updated)
            item["remediation"] = {
                **remediation,
                "status": "in_progress" if remediation.get("status") != "closed" else "closed",
                "source_candidates": updated_candidates,
                "source_activated_at": now,
                "source_activated_url": url,
                "updated_at": now,
                "updated_by": admin_id,
            }
            break
        return items

    update_json_atomic(benchmarks_file, [], record)
    return {"added": added, "source": spec}
