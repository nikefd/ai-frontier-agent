"""Source health classification and observability regressions."""

from datetime import datetime, timezone

from app.routers.ai_news import _source_health
from app.source_freshness import classify_content_freshness


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


def test_content_freshness_is_separate_from_transport_health() -> None:
    source = {"cadence": "fast"}

    fresh = classify_content_freshness("2026-10-10T12:00:00Z", source, NOW)
    quiet = classify_content_freshness("2026-08-01T12:00:00Z", source, NOW)
    dormant = classify_content_freshness("2026-01-01T12:00:00Z", source, NOW)

    assert fresh["content_status"] == "fresh"
    assert quiet["content_status"] == "quiet"
    assert dormant["content_status"] == "dormant"
    assert _source_health(
        {"last_fetch": "2026-10-16T11:00:00Z"}, now=NOW, interval_hours=1,
    )["health_status"] == "healthy"


def test_content_freshness_allows_explicit_low_frequency_window() -> None:
    result = classify_content_freshness(
        "2026-01-01T12:00:00Z", {"cadence": "standard", "quiet_after_days": 365}, NOW,
    )

    assert result["content_status"] == "fresh"
    assert result["quiet_after_days"] == 365


def test_content_freshness_rejects_unknown_and_future_dates() -> None:
    for date in (None, "invalid", "2027-01-01T00:00:00Z"):
        result = classify_content_freshness(date, {"cadence": "fast"}, NOW)
        assert result["content_status"] == "unknown"
        assert result["content_age_days"] is None
