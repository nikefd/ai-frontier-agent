"""Manage the lifecycle of persistent admin-approved sources."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .custom_sources import delete_custom_source, set_custom_source_enabled
from .storage import update_json_atomic


class SourceManagementError(ValueError):
    pass


def _record_lifecycle(
    benchmarks_file: Path,
    *,
    url: str,
    enabled: bool | None,
    admin_id: str,
    now: str,
) -> None:
    def record(items: list[dict]) -> list[dict]:
        for item in items if isinstance(items, list) else []:
            remediation = item.get("remediation")
            if not isinstance(remediation, dict):
                continue
            candidates = remediation.get("source_candidates") or []
            changed = False
            updated_candidates = []
            for candidate in candidates:
                updated = dict(candidate)
                if updated.get("activated_url") == url:
                    changed = True
                    if enabled is None:
                        updated["last_deleted_at"] = now
                        updated["last_deleted_by"] = admin_id
                        for key in (
                            "activated_at", "activated_url", "activated_name",
                            "activated_added", "source_enabled",
                        ):
                            updated.pop(key, None)
                    else:
                        updated["source_enabled"] = enabled
                        updated["source_state_changed_at"] = now
                updated_candidates.append(updated)
            if changed:
                item["remediation"] = {
                    **remediation,
                    "source_candidates": updated_candidates,
                    "updated_at": now,
                    "updated_by": admin_id,
                }
        return items

    update_json_atomic(benchmarks_file, [], record)


def update_source_state(
    url: str,
    enabled: bool,
    admin_id: str,
    benchmarks_file: Path,
) -> dict:
    from .routers.ai_news import CUSTOM_SOURCES_FILE, FEED_SPEC_BY_URL, set_custom_feed_enabled

    runtime_source = FEED_SPEC_BY_URL.get(url)
    if not runtime_source or not runtime_source.get("custom"):
        raise SourceManagementError("自定义来源不存在")
    now = datetime.now(timezone.utc).isoformat()
    source = set_custom_source_enabled(
        CUSTOM_SOURCES_FILE,
        url,
        enabled=enabled,
        updated_at=now,
        updated_by=admin_id,
    )
    if not source or not set_custom_feed_enabled(url, enabled):
        raise SourceManagementError("自定义来源不存在")
    _record_lifecycle(
        benchmarks_file, url=url, enabled=enabled, admin_id=admin_id, now=now,
    )
    return source


def remove_source(url: str, admin_id: str, benchmarks_file: Path) -> dict:
    from .routers.ai_news import CUSTOM_SOURCES_FILE, FEED_SPEC_BY_URL, remove_custom_feed_spec

    runtime_source = FEED_SPEC_BY_URL.get(url)
    if not runtime_source or not runtime_source.get("custom"):
        raise SourceManagementError("自定义来源不存在")
    source = delete_custom_source(CUSTOM_SOURCES_FILE, url)
    if not source or not remove_custom_feed_spec(url):
        raise SourceManagementError("自定义来源不存在")
    now = datetime.now(timezone.utc).isoformat()
    _record_lifecycle(
        benchmarks_file, url=url, enabled=None, admin_id=admin_id, now=now,
    )
    return source
