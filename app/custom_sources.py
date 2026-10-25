"""Persistent admin-approved feed specs discovered from coverage gaps."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from .storage import read_json, update_json_atomic

_ALLOWED_KINDS = {"rss", "atom"}


def load_custom_source_specs(path: Path) -> list[dict]:
    payload = read_json(path, [])
    if not isinstance(payload, list):
        return []
    specs: list[dict] = []
    for item in payload:
        if not isinstance(item, dict) or item.get("kind") not in _ALLOWED_KINDS:
            continue
        url = str(item.get("url") or "").strip()
        name = str(item.get("name") or "").strip()
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or not name:
            continue
        specs.append({
            **item,
            "url": url,
            "name": name,
            "tier": "high",
            "category": "vendor",
            "cadence": "fast",
            "custom": True,
            "enabled": item.get("enabled") is not False,
        })
    return specs


def add_custom_source(path: Path, spec: dict) -> bool:
    """Persist one source atomically; return False when URL or name exists."""
    added = False

    def add(items: list[dict]) -> list[dict]:
        nonlocal added
        existing = items if isinstance(items, list) else []
        url = str(spec.get("url") or "")
        name = str(spec.get("name") or "").casefold()
        if any(
            str(item.get("url") or "") == url
            or str(item.get("name") or "").casefold() == name
            for item in existing if isinstance(item, dict)
        ):
            return existing
        added = True
        return [*existing, spec]

    update_json_atomic(path, [], add)
    return added


def set_custom_source_enabled(
    path: Path,
    url: str,
    *,
    enabled: bool,
    updated_at: str,
    updated_by: str,
) -> dict | None:
    """Persist a custom source state change and return the updated item."""
    updated: dict | None = None

    def change(items: list[dict]) -> list[dict]:
        nonlocal updated
        existing = items if isinstance(items, list) else []
        for item in existing:
            if isinstance(item, dict) and item.get("url") == url:
                item["enabled"] = enabled
                item["updated_at"] = updated_at
                item["updated_by"] = updated_by
                updated = dict(item)
                break
        return existing

    update_json_atomic(path, [], change)
    return updated


def delete_custom_source(path: Path, url: str) -> dict | None:
    """Remove one custom source definition without touching fetched articles."""
    removed: dict | None = None

    def delete(items: list[dict]) -> list[dict]:
        nonlocal removed
        existing = items if isinstance(items, list) else []
        kept = []
        for item in existing:
            if isinstance(item, dict) and item.get("url") == url:
                removed = dict(item)
            else:
                kept.append(item)
        return kept

    update_json_atomic(path, [], delete)
    return removed
