"""Source health classification and observability regressions."""

from datetime import datetime, timezone

from app.routers.ai_news import _source_health


NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)


def test_source_health_distinguishes_never_and_healthy() -> None:
    assert _source_health({}, now=NOW, interval_hours=4)["health_status"] == "never"
    health = _source_health(
        {"last_fetch": "2026-10-16T09:00:00+00:00", "last_ok": "2026-10-16T09:00:00+00:00"},
        now=NOW,
        interval_hours=4,
    )
    assert health["health_status"] == "healthy"
    assert health["fetch_age_hours"] == 3.0


def test_source_health_flags_stopped_scheduler() -> None:
    health = _source_health(
        {"last_fetch": "2026-10-15T20:00:00+00:00", "last_ok": "2026-10-15T20:00:00+00:00"},
        now=NOW,
        interval_hours=4,
    )
    assert health["health_status"] == "stale"
    assert health["stale_after_hours"] == 12


def test_source_health_prioritizes_current_error_and_failure_streak() -> None:
    health = _source_health(
        {
            "last_fetch": "2026-10-15T20:00:00+00:00",
            "last_error": "HTTP 503",
            "consecutive_failures": 3,
        },
        now=NOW,
        interval_hours=4,
    )
    assert health["health_status"] == "error"
    assert "连续 3 次" in health["health_reason"]
