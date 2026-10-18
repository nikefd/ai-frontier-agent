"""Coverage, latency and blind-spot audit regressions."""
from datetime import datetime, timezone

from app.quality_report import build_quality_report
from app.models import Article
from app.storage import read_json


NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)


def _source(name: str, *, cadence: str = "fast", status: str = "healthy") -> dict:
    return {"name": name, "cadence": cadence, "health_status": status}


def _article(aid: str, **changes) -> dict:
    article = {
        "id": aid, "title": f"Important event {aid}", "source": "Lab",
        "date": "2026-10-18T10:00:00+00:00",
        "ingested_at": "2026-10-18T10:30:00+00:00",
        "category": "vendor", "tier": "high", "importance": 9,
        "translation_status": "ok", "event_key": f"lab-release-{aid}",
    }
    article.update(changes)
    return article


def test_quality_report_counts_events_not_duplicate_articles() -> None:
    first = _article("a1", event_key="lab-release-model-x")
    duplicate = _article("a2", event_key="lab-release-model-x", source="Media")
    report = build_quality_report(
        [first, duplicate],
        [_source("Lab")],
        {"cohort": [{"id": "a1"}]},
        now=NOW,
    )

    assert report["status"] == "healthy"
    assert report["content_coverage"]["high_impact_events"] == 1
    assert report["content_coverage"]["visible_rate"] == 1.0
    assert report["pipeline"]["median_discovery_minutes"] == 30.0


def test_quality_report_surfaces_missed_events_and_fast_source_failures() -> None:
    missed = _article("missed", importance=8, title="Important benchmark result")
    sources = [_source("Lab", status="error"), _source("Other", status="stale")]

    report = build_quality_report([missed], sources, {"cohort": []}, now=NOW)

    assert report["status"] == "critical"
    assert report["source_health"]["fast_rate"] == 0.0
    assert report["content_coverage"]["visible_rate"] == 0.0
    assert report["content_coverage"]["missed_items"][0]["id"] == "missed"


def test_major_alert_counts_as_visible_before_briefing_refresh() -> None:
    release = _article("release", title="Introducing GPT-6")
    report = build_quality_report([release], [_source("Lab")], None, now=NOW)
    assert report["content_coverage"]["visible_rate"] == 1.0


def test_new_articles_record_ingestion_time(tmp_path, monkeypatch) -> None:
    import app.routers.ai_news as news

    articles_file = tmp_path / "articles.json"
    monkeypatch.setattr(news, "ARTICLES_FILE", articles_file)
    news.add_article(Article(title="New", url="https://example.test/new", source="Lab"))

    stored = read_json(articles_file, [])
    assert stored[0]["ingested_at"]
    assert stored[0]["date"]
