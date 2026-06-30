"""Per-user daily LLM-action quota (anti-abuse).

Second line of defense after email verification: a verified user still shouldn't
be able to drain an unmetered LLM key. We count user-initiated LLM operations
per day and refuse past the limit (429). Admins are exempt; limit is configurable
via AIF_DAILY_LLM_LIMIT (0 = unlimited).

State lives in users/<uid>/usage.json as {date, count}; it resets when the date
rolls over (checked lazily on read, no cron needed).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .settings import settings
from .storage import read_json, write_json_atomic

USERS_DIR = settings.data_dir / "users"


def _usage_file(uid: str) -> Path:
    return USERS_DIR / uid / "usage.json"


def _today() -> str:
    # Local date — quota resets at local midnight.
    return datetime.now().astimezone().date().isoformat()


def usage_today(uid: str) -> int:
    """How many LLM actions this user has spent today (0 if a new day)."""
    data = read_json(_usage_file(uid), None)
    if isinstance(data, dict) and data.get("date") == _today():
        return int(data.get("count", 0))
    return 0


def remaining(uid: str) -> int | None:
    """Remaining quota today; None = unlimited (limit disabled)."""
    limit = settings.daily_llm_limit
    if limit <= 0:
        return None
    return max(0, limit - usage_today(uid))


def has_quota(uid: str) -> bool:
    rem = remaining(uid)
    return rem is None or rem > 0


def record_use(uid: str, n: int = 1) -> None:
    """Increment today's count (called after a successful LLM action)."""
    today = _today()
    cur = usage_today(uid)  # already date-aware (0 if stale)
    p = _usage_file(uid)
    p.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(p, {"date": today, "count": cur + n})
