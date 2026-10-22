"""Persistent public archive for generated AI briefings."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .settings import settings
from .storage import read_json, update_json_atomic

AINEWS_DIR = settings.data_dir / "ai-news"
SUMMARY_FILE = AINEWS_DIR / "summary_today.json"
SUMMARY_HISTORY_FILE = AINEWS_DIR / "summary_history.json"
_HISTORY_DAYS = 30
_HISTORY_LIMIT = 180  # up to six changed cohorts per day


def summary_identity(summary: dict) -> str:
    fingerprint = str(summary.get("cohort_fingerprint") or "").strip()
    if fingerprint:
        return fingerprint
    raw = json.dumps(
        {
            "generated_at": summary.get("generated_at"),
            "date": summary.get("date"),
            "body": summary.get("body"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _generated_timestamp(summary: dict) -> float:
    raw = str(summary.get("generated_at") or "")
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return 0.0


def _valid_summary(value: object) -> bool:
    return (
        isinstance(value, dict)
        and bool(value.get("generated_at"))
        and bool(value.get("body"))
    )


def archive_summary(summary: dict) -> list[dict]:
    """Keep one public archive entry per materially different cohort."""
    item = dict(summary)
    identity = summary_identity(item)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=_HISTORY_DAYS)).timestamp()

    def mutate(data: list[dict]) -> list[dict]:
        history = [entry for entry in data if _valid_summary(entry)] if isinstance(data, list) else []
        history = [
            entry for entry in history
            if summary_identity(entry) != identity and _generated_timestamp(entry) >= cutoff
        ]
        history.append(item)
        history.sort(key=_generated_timestamp, reverse=True)
        return history[:_HISTORY_LIMIT]

    return update_json_atomic(SUMMARY_HISTORY_FILE, [], mutate)


def load_public_summaries() -> list[dict]:
    """Merge the current cache into history so RSS works before the next run."""
    history = read_json(SUMMARY_HISTORY_FILE, [])
    candidates = list(history) if isinstance(history, list) else []
    current = read_json(SUMMARY_FILE, None)
    if _valid_summary(current):
        candidates.append(current)

    by_identity: dict[str, dict] = {}
    for summary in candidates:
        if not _valid_summary(summary):
            continue
        identity = summary_identity(summary)
        previous = by_identity.get(identity)
        if previous is None or _generated_timestamp(summary) > _generated_timestamp(previous):
            by_identity[identity] = summary
    return sorted(by_identity.values(), key=_generated_timestamp, reverse=True)
