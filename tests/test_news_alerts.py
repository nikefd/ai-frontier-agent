"""Regression tests for deterministic major-event alerts."""
from datetime import datetime, timezone

from app.news_alerts import build_breaking_alerts, classify_alert


NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)


def _article(**changes) -> dict:
    item = {
        "id": "a1", "title": "Introducing GPT-6", "source": "OpenAI News",
        "url": "https://example.test/a1", "date": "2026-10-18T10:00:00+00:00",
        "category": "vendor", "tier": "high", "importance": 9,
    }
    item.update(changes)
    return item


def test_alert_classifier_covers_release_deprecation_security_and_open_source() -> None:
    assert classify_alert(_article()) == "model_release"
    assert classify_alert(_article(title="API model endpoint deprecated; migration required")) == "api_change"
    assert classify_alert(_article(title="Security incident: CVE-2026-12345 vulnerability")) == "security"
    assert classify_alert(_article(title="We open source model weights", importance=8)) == "open_source"


def test_alert_classifier_rejects_social_hype_and_low_signal_open_source() -> None:
    assert classify_alert(_article(category="x-ai", tier="low")) is None
    assert classify_alert(_article(title="We open source model weights", importance=5)) is None


def test_alerts_are_recent_deduplicated_and_urgency_first() -> None:
    release = _article(event_key="openai-release-gpt-6")
    duplicate = _article(id="a2", title="GPT-6 is now available", event_key="openai-release-gpt-6")
    deprecation = _article(
        id="a3", title="API endpoint deprecated; migration required",
        event_key="openai-deprecate-endpoint", importance=7,
    )
    old = _article(id="old", date="2026-10-15T10:00:00+00:00")

    alerts = build_breaking_alerts([release, duplicate, deprecation, old], now=NOW)

    assert [item["id"] for item in alerts] == ["a3", "a1"]
    assert alerts[0]["severity"] == "critical"
