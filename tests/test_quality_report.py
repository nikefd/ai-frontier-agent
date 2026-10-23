"""Coverage, latency and blind-spot audit regressions."""
from datetime import datetime, timezone

from app.quality_report import build_quality_report
from app.models import Article
from app.storage import read_json


NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)


def _source(
    name: str,
    *,
    cadence: str = "fast",
    status: str = "healthy",
    category: str = "vendor",
) -> dict:
    return {
        "name": name, "cadence": cadence, "health_status": status,
        "category": category,
    }


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


def test_source_value_rewards_exclusive_and_first_seen_events() -> None:
    articles = []
    for index in range(5):
        event_key = f"lab-release-model-{index}"
        articles.append(_article(
            f"lab-{index}", source="Lab", event_key=event_key,
            importance=9, ingested_at=f"2026-10-18T10:{index:02d}:00+00:00",
        ))
        if index >= 2:
            articles.append(_article(
                f"media-{index}", source="Media", event_key=event_key,
                importance=5, category="media",
                ingested_at=f"2026-10-18T11:{index:02d}:00+00:00",
            ))

    report = build_quality_report(
        articles,
        [_source("Lab"), _source("Media", category="media")],
        {"cohort": [{"id": "lab-0"}]},
        now=NOW,
    )
    value = report["source_value"]
    by_name = {item["name"]: item for item in value["top_sources"]}

    assert value["evaluated_sources"] == 2
    assert by_name["Lab"]["exclusive_events"] == 2
    assert by_name["Lab"]["first_seen_events"] == 5
    assert by_name["Lab"]["score"] > by_name["Media"]["score"]
    assert by_name["Lab"]["classification"] == "high_value"


def test_source_value_keeps_small_samples_out_of_low_signal_reviews() -> None:
    report = build_quality_report(
        [_article("only-one", source="New Lab")],
        [_source("New Lab")],
        None,
        now=NOW,
    )

    value = report["source_value"]
    assert value["evaluated_sources"] == 0
    assert value["insufficient_sources"] == 1
    assert value["review_candidates"] == []


def test_source_value_flags_only_sampled_healthy_low_signal_sources() -> None:
    articles = []
    for index in range(5):
        event_key = f"lab-update-{index}"
        articles.extend([
            _article(
                f"primary-{index}", source="Primary", event_key=event_key,
                importance=8, ingested_at=f"2026-10-18T10:{index:02d}:00+00:00",
            ),
            _article(
                f"repeat-{index}", source="Repeater", event_key=event_key,
                importance=1, category="community",
                ingested_at=f"2026-10-18T11:{index:02d}:00+00:00",
            ),
        ])

    report = build_quality_report(
        articles,
        [_source("Primary"), _source("Repeater", category="community")],
        None,
        now=NOW,
    )

    assert [item["name"] for item in report["source_value"]["review_candidates"]] == [
        "Repeater",
    ]


def test_new_articles_record_ingestion_time(tmp_path, monkeypatch) -> None:
    import app.routers.ai_news as news

    articles_file = tmp_path / "articles.json"
    monkeypatch.setattr(news, "ARTICLES_FILE", articles_file)
    news.add_article(Article(title="New", url="https://example.test/new", source="Lab"))

    stored = read_json(articles_file, [])
    assert stored[0]["ingested_at"]
    assert stored[0]["date"] is None
