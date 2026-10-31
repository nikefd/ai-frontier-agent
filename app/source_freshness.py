"""Content freshness classification kept separate from transport health."""
from __future__ import annotations

from datetime import datetime, timezone


_QUIET_AFTER_DAYS = {"fast": 45, "standard": 120, "slow": 180}


def classify_content_freshness(
    latest_entry_at: str | None,
    source: dict,
    now: datetime | None = None,
) -> dict:
    """Describe how long a source has been quiet without calling it broken."""
    threshold = max(
        7,
        int(source.get("quiet_after_days") or _QUIET_AFTER_DAYS.get(source.get("cadence"), 120)),
    )
    if not latest_entry_at:
        return {
            "content_status": "unknown",
            "content_age_days": None,
            "quiet_after_days": threshold,
            "content_reason": "尚无可信的源站最新发布时间",
        }
    try:
        parsed = datetime.fromisoformat(str(latest_entry_at).replace("Z", "+00:00"))
    except ValueError:
        return {
            "content_status": "unknown",
            "content_age_days": None,
            "quiet_after_days": threshold,
            "content_reason": "源站最新发布时间无法解析",
        }
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    if (parsed - current).total_seconds() > 6 * 3600:
        return {
            "content_status": "unknown",
            "content_age_days": None,
            "quiet_after_days": threshold,
            "content_reason": "源站最新发布时间明显晚于当前时间",
        }
    age_days = round(max(0.0, (current - parsed).total_seconds()) / 86400, 1)
    dormant_after = max(threshold * 2, 180)
    if age_days > dormant_after:
        status = "dormant"
        reason = f"最新源站条目已超过 {age_days:.0f} 天，疑似停更或入口迁移"
    elif age_days > threshold:
        status = "quiet"
        reason = f"最新源站条目已超过 {age_days:.0f} 天，需留意更新频率"
    else:
        status = "fresh"
        reason = "源站内容仍在预期更新窗口内"
    return {
        "content_status": status,
        "content_age_days": age_days,
        "quiet_after_days": threshold,
        "content_reason": reason,
    }
