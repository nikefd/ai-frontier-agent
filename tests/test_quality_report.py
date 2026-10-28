"""Coverage, latency and blind-spot audit regressions."""
from datetime import datetime, timezone

from app.quality_report import (
    build_benchmark_candidates,
    build_benchmark_coverage,
    build_quality_report,
)
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


def test_quality_report_aggregates_recent_source_noise_without_punishing_filtering() -> None:
    noisy = _source("Broad vendor") | {
        "quality_policy": "title_keywords",
        "quality_samples": [
            {"at": "2026-10-18T10:00:00Z", "accepted": 6, "filtered": 4, "invalid_date": 1},
            {"at": "2026-10-17T10:00:00Z", "accepted": 4, "filtered": 6, "invalid_date": 0},
            {"at": "2026-10-01T10:00:00Z", "accepted": 0, "filtered": 99, "invalid_date": 0},
        ],
    }

    report = build_quality_report([], [noisy], None, now=NOW)
    noise = report["source_noise"]

    assert noise["sample_count"] == 2
    assert noise["parsed"] == 21
    assert noise["noise_rate"] == 0.5
    assert noise["invalid_rate"] == 0.048
    assert noise["noisiest_sources"][0]["policy"] == "title_keywords"
    assert noise["possible_overfilter"] == []


def test_quality_report_warns_when_a_sampled_source_rejects_everything() -> None:
    blocked = _source("Overstrict") | {
        "quality_samples": [
            {"at": "2026-10-18T10:00:00Z", "accepted": 0, "filtered": 5},
            {"at": "2026-10-17T10:00:00Z", "accepted": 0, "filtered": 7},
        ],
    }

    report = build_quality_report([], [blocked], None, now=NOW)

    assert report["source_noise"]["possible_overfilter"][0]["name"] == "Overstrict"
    assert any(item["title"] == "来源门禁可能过严" for item in report["findings"])


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


def test_must_not_miss_benchmarks_distinguish_on_time_late_missed_and_pending() -> None:
    articles = [
        _article(
            "on-time", title="OpenAI releases GPT-6", source="OpenAI",
            date="2026-10-18T08:00:00+00:00",
            ingested_at="2026-10-18T09:00:00+00:00",
        ),
        _article(
            "late", title="Anthropic launches Claude 5", source="Anthropic",
            date="2026-10-18T08:00:00+00:00",
            ingested_at="2026-10-18T10:00:00+00:00",
        ),
    ]
    benchmarks = [
        {"id": "b1", "title": "GPT-6 发布", "occurred_at": "2026-10-18T08:00:00Z",
         "match_terms": ["GPT-6", "OpenAI"], "deadline_hours": 2},
        {"id": "b2", "title": "Claude 5 发布", "occurred_at": "2026-10-18T08:00:00Z",
         "match_terms": ["Claude 5", "Anthropic"], "deadline_hours": 1},
        {"id": "b3", "title": "重要安全事故", "occurred_at": "2026-10-18T08:00:00Z",
         "match_terms": ["Safety Incident"], "deadline_hours": 1},
        {"id": "b4", "title": "刚刚发布的模型", "occurred_at": "2026-10-18T11:30:00Z",
         "match_terms": ["Fresh Model"], "deadline_hours": 2},
    ]

    coverage = build_benchmark_coverage(articles, benchmarks, now=NOW)
    statuses = {item["id"]: item["status"] for item in coverage["items"]}

    assert statuses == {"b1": "on_time", "b2": "late", "b3": "missed", "b4": "pending"}
    assert coverage["settled"] == 3
    assert coverage["on_time_recall_rate"] == 0.333
    assert coverage["coverage_rate"] == 0.667
    assert coverage["missed_items"][0]["id"] == "b3"
    by_id = {item["id"]: item for item in coverage["items"]}
    assert by_id["b2"]["diagnosis"]["code"] == "fetch_delay"
    assert coverage["missed_items"][0]["diagnosis"]["code"] == "coverage_gap"


def test_benchmark_diagnosis_separates_source_cadence_health_and_matching_gaps() -> None:
    articles = [
        _article(
            "late-source", title="Official event appeared late", source="Fast Lab",
            date="2026-10-18T10:00:00Z", ingested_at="2026-10-18T10:05:00Z",
        ),
        _article(
            "slow-fetch", title="Cadence event", source="Slow Lab",
            date="2026-10-18T08:20:00Z", ingested_at="2026-10-18T10:00:00Z",
        ),
        _article("partial", title="Partial signal appeared"),
    ]
    benchmarks = [
        {"id": "late-source", "title": "源站晚发", "occurred_at": "2026-10-18T08:00:00Z",
         "match_terms": ["Official event appeared late"], "deadline_hours": 1},
        {"id": "slow", "title": "刷新太慢", "occurred_at": "2026-10-18T08:00:00Z",
         "match_terms": ["Cadence event"], "deadline_hours": 1},
        {"id": "unhealthy", "title": "异常来源", "occurred_at": "2026-10-18T08:00:00Z",
         "source_url": "https://broken.test/news/item", "deadline_hours": 1},
        {"id": "parser", "title": "解析缺口", "occurred_at": "2026-10-18T08:00:00Z",
         "source_url": "https://healthy.test/news/item", "deadline_hours": 1},
        {"id": "missing-source", "title": "未接入", "occurred_at": "2026-10-18T08:00:00Z",
         "source_url": "https://missing.test/news/item", "deadline_hours": 1},
        {"id": "matching", "title": "规则漂移", "occurred_at": "2026-10-18T08:00:00Z",
         "match_terms": ["Partial", "Absent"], "deadline_hours": 1},
    ]
    sources = [
        {"name": "Fast Lab", "url": "https://fast.test/feed", "health_status": "healthy", "cadence": "fast"},
        {"name": "Slow Lab", "url": "https://slow.test/feed", "health_status": "healthy", "cadence": "standard"},
        {"name": "Broken", "url": "https://broken.test/feed", "health_status": "error", "health_reason": "HTTP 500"},
        {"name": "Healthy", "url": "https://healthy.test/feed", "health_status": "healthy"},
    ]

    coverage = build_benchmark_coverage(articles, benchmarks, now=NOW, sources=sources)
    causes = {item["id"]: item["diagnosis"]["code"] for item in coverage["items"]}

    assert causes == {
        "late-source": "source_published_late",
        "slow": "cadence_too_slow",
        "unhealthy": "source_unhealthy",
        "parser": "parser_or_filter_gap",
        "missing-source": "source_not_configured",
        "matching": "match_rule_gap",
    }
    assert coverage["diagnosis_counts"]["source_unhealthy"] == 1


def test_benchmark_candidates_find_official_events_and_exclude_registered() -> None:
    articles = [
        _article(
            "release", title="Introducing GPT-6", source="OpenAI",
            url="https://openai.com/news/gpt-6", importance=9,
        ),
        _article(
            "duplicate", title="GPT-6 is now available", source="OpenAI",
            url="https://openai.com/news/gpt-6-details", importance=9,
            event_key="lab-release-release",
        ),
        _article(
            "important", title="New developer platform", source="Lab",
            url="https://lab.test/platform", importance=8,
        ),
        _article(
            "community", title="Introducing GPT-7", source="Forum",
            url="https://forum.test/gpt-7", category="community", importance=10,
        ),
        _article(
            "registered", title="Claude 5 released", source="Anthropic",
            url="https://anthropic.test/claude-5", event_key="claude-5", importance=9,
        ),
        _article(
            "old", title="Introducing GPT-5", source="OpenAI",
            url="https://openai.com/news/gpt-5", date="2026-10-01T10:00:00Z",
        ),
    ]
    result = build_benchmark_candidates(
        articles,
        [{"source_url": "https://anthropic.test/claude-5", "event_key": "claude-5"}],
        now=NOW,
    )

    assert [item["article_id"] for item in result["items"]] == ["release", "important"]
    assert result["items"][0]["kind"] == "model_release"
    assert result["items"][0]["deadline_hours"] == 12
    assert result["items"][0]["discovery_minutes"] == 30.0
    assert result["items"][1]["kind"] == "high_impact"


def test_benchmark_candidates_require_two_trusted_sources_without_official_item() -> None:
    articles = [
        _article(
            "media-a", title="Agent benchmark reveals major capability jump",
            source="Tech Wire", url="https://wire.test/agent-benchmark",
            category="media", tier="high", event_key="agent-benchmark-jump",
        ),
        _article(
            "expert-a", title="Independent analysis of the new agent benchmark",
            source="AI Researcher", url="https://expert.test/agent-benchmark",
            category="expert", tier="med", event_key="agent-benchmark-jump",
            ingested_at="2026-10-18T10:45:00+00:00",
        ),
        _article(
            "single", title="Unconfirmed model rumor", source="Another Wire",
            url="https://another.test/rumor", category="media", tier="high",
            event_key="unconfirmed-model-rumor",
        ),
        _article(
            "low-a", title="CVE-2026-1000 vulnerability", source="Security Wire",
            url="https://security.test/cve", category="media", tier="high",
            event_key="low-impact-security", importance=7,
        ),
        _article(
            "low-b", title="CVE-2026-1000 security incident", source="Tech Blog",
            url="https://blog.test/cve", category="blog", tier="med",
            event_key="low-impact-security", importance=7,
        ),
    ]

    result = build_benchmark_candidates(articles, [], now=NOW)

    assert result["total"] == 1
    candidate = result["items"][0]
    assert candidate["kind"] == "corroborated"
    assert candidate["discovery_mode"] == "corroborated"
    assert candidate["corroborating_sources"] == ["AI Researcher", "Tech Wire"]
    assert candidate["reason"].startswith("多个独立可信来源")


def test_new_articles_record_ingestion_time(tmp_path, monkeypatch) -> None:
    import app.routers.ai_news as news

    articles_file = tmp_path / "articles.json"
    monkeypatch.setattr(news, "ARTICLES_FILE", articles_file)
    news.add_article(Article(title="New", url="https://example.test/new", source="Lab"))

    stored = read_json(articles_file, [])
    assert stored[0]["ingested_at"]
    assert stored[0]["date"] is None
