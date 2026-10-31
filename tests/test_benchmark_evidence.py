"""Historical scores survive eviction, restart, enrichment and concurrent updates."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json

import pytest

from app.benchmark_evidence import record_benchmark_matches, retain_match
from app.benchmark_matching import find_benchmark_match
from app.quality_report import build_benchmark_coverage
from app.storage import read_json, write_json_atomic

NOW = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)


def _benchmark(**changes):
    return {"id": "b1", "title": "Release", "occurred_at": "2026-10-31T08:00:00Z",
            "deadline_hours": 2, "source_url": "https://lab.test/news/model", **changes}


def _article(**changes):
    return {"id": "a1", "title": "Official release", "url": "https://lab.test/news/model",
            "source": "Lab", "date": "2026-10-31T08:00:00Z",
            "ingested_at": "2026-10-31T09:00:00Z", **changes}


@pytest.mark.parametrize("ingested,status", [("2026-10-31T09:00:00Z", "on_time"), ("2026-10-31T11:00:00Z", "late")])
def test_disk_evidence_preserves_status_and_latency_after_eviction(tmp_path, ingested, status):
    path = tmp_path / "coverage.json"
    write_json_atomic(path, [_benchmark()])
    assert record_benchmark_matches(path, [_article(ingested_at=ingested)], NOW) == 1
    loaded = read_json(path, [])
    report = build_benchmark_coverage([], loaded, now=NOW)
    item = report["items"][0]
    assert item["status"] == status
    assert item["match_evidence_retained"] is True
    assert item["matched_article"]["url"] == _article()["url"]
    assert item["discovery_minutes"] == (60 if status == "on_time" else 180)
    assert item["match_time_basis"] == "ingested_at"
    assert "rule_fingerprint" not in json.dumps(report)
    assert loaded[0]["evidence"]["recorded_at"] == NOW.isoformat()


def test_earliest_hit_wins_and_noop_does_not_rewrite_file(tmp_path):
    path = tmp_path / "coverage.json"
    write_json_atomic(path, [_benchmark(remediation={"note": "keep internal note"})])
    assert record_benchmark_matches(path, [_article()], NOW) == 1
    before = path.stat().st_mtime_ns
    assert record_benchmark_matches(path, [_article(ingested_at="2026-10-31T11:00:00Z")], NOW) == 0
    assert path.stat().st_mtime_ns == before
    assert record_benchmark_matches(path, [_article(id="earlier", ingested_at="2026-10-31T08:30:00Z")], NOW) == 1
    stored = read_json(path, [])[0]
    assert stored["remediation"]["note"] == "keep internal note"
    assert stored["evidence"]["article"]["id"] == "earlier"


def test_keyword_evidence_replays_but_rule_changes_and_corruption_invalidate_it():
    benchmark = _benchmark(source_url="", match_terms=["unique", "breakthrough"])
    assert retain_match(benchmark, [_article(summary="A unique breakthrough in reasoning")], NOW)
    assert find_benchmark_match([], benchmark, NOW)[2] == "match_terms"
    changed = {**benchmark, "match_terms": ["unrelated"]}
    assert find_benchmark_match([], changed, NOW) is None
    benchmark["evidence"]["matched_at"] = "not-a-date"
    assert find_benchmark_match([], benchmark, NOW) is None


def test_different_changelog_anchors_do_not_create_wrong_evidence():
    benchmark = _benchmark(source_url="https://lab.test/changelog#model-two")
    assert not retain_match(benchmark, [_article(url="https://lab.test/changelog#model-one")], NOW)
    assert retain_match(benchmark, [_article(url="https://lab.test/changelog?utm_source=rss#model-two")], NOW)


def test_legacy_missing_ingestion_time_stays_labelled_as_publication_fallback():
    benchmark = _benchmark()
    assert retain_match(benchmark, [_article(ingested_at=None)], NOW)
    assert benchmark["evidence"]["time_basis"] == "published_at"
    assert benchmark["evidence"]["article"]["ingested_at"] is None
    assert build_benchmark_coverage([], [benchmark], now=NOW)["items"][0]["match_time_basis"] == "published_at"


def test_parallel_evidence_updates_keep_earliest_observation(tmp_path):
    path = tmp_path / "coverage.json"
    write_json_atomic(path, [_benchmark()])
    articles = [_article(id=str(i), ingested_at=f"2026-10-31T09:{i:02d}:00Z") for i in reversed(range(8))]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda article: record_benchmark_matches(path, [article], NOW), articles))
    assert read_json(path, [])[0]["evidence"]["matched_at"] == "2026-10-31T09:00:00+00:00"


def test_article_eviction_captures_previously_unretained_hit(tmp_path, monkeypatch):
    import app.routers.ai_news as news
    from app.models import Article
    articles_path, benchmarks_path = tmp_path / "articles.json", tmp_path / "benchmarks.json"
    now = datetime.now(timezone.utc)
    existing = _article(date=(now - timedelta(hours=2)).isoformat(), ingested_at=(now - timedelta(hours=1)).isoformat())
    benchmark = _benchmark(occurred_at=(now - timedelta(hours=2)).isoformat())
    write_json_atomic(articles_path, [existing])
    write_json_atomic(benchmarks_path, [benchmark])
    monkeypatch.setattr(news, "ARTICLES_FILE", articles_path)
    monkeypatch.setattr(news, "BENCHMARKS_FILE", benchmarks_path)
    monkeypatch.setattr(news, "_ARTICLE_LIMIT", 1)
    monkeypatch.setattr(news, "_all_pinned_ids", lambda: set())
    news.add_article(Article(title="Unrelated", url="https://other.test/new", source="Other", date=now.isoformat()))
    assert all(article["id"] != "a1" for article in read_json(articles_path, []))
    assert build_benchmark_coverage([], read_json(benchmarks_path, []), now=now)["on_time"] == 1


@pytest.mark.asyncio
async def test_enrichment_captures_event_key_match_with_original_ingestion_time(tmp_path, monkeypatch):
    import app.workers.ai_news_translator as translator
    articles_path, benchmarks_path = tmp_path / "articles.json", tmp_path / "benchmarks.json"
    now = datetime.now(timezone.utc)
    article = _article(date=(now - timedelta(hours=2)).isoformat(), ingested_at=(now - timedelta(hours=1)).isoformat(), translation_status="pending")
    benchmark = _benchmark(source_url="", event_key="lab-release-unique-model", occurred_at=(now - timedelta(hours=2)).isoformat())
    write_json_atomic(articles_path, [article])
    write_json_atomic(benchmarks_path, [benchmark])
    async def response(*args, **kwargs):
        return json.dumps([{"id": "a1", "title_zh": "发布", "event_key": "lab-release-unique-model"}])
    monkeypatch.setattr(translator, "ARTICLES_FILE", articles_path)
    monkeypatch.setattr(translator, "BENCHMARKS_FILE", benchmarks_path)
    monkeypatch.setattr(translator, "_load_articles", lambda: read_json(articles_path, []))
    monkeypatch.setattr(translator, "llm_configured", lambda: True)
    monkeypatch.setattr(translator, "chat_complete", response)
    assert await translator._translate_once() == 1
    stored = read_json(benchmarks_path, [])[0]
    assert stored["evidence"]["article"]["ingested_at"] == article["ingested_at"]
    assert build_benchmark_coverage([], [stored], now=now)["on_time"] == 1


def test_new_article_is_retained_before_any_report_is_read(tmp_path, monkeypatch):
    import app.routers.ai_news as news
    from app.models import Article
    now = datetime.now(timezone.utc)
    path = tmp_path / "benchmarks.json"
    write_json_atomic(path, [_benchmark(occurred_at=(now - timedelta(minutes=30)).isoformat())])
    monkeypatch.setattr(news, "ARTICLES_FILE", tmp_path / "articles.json")
    monkeypatch.setattr(news, "BENCHMARKS_FILE", path)
    result = news.add_article(Article(title="Official release", url=_article()["url"], source="Lab", date=now.isoformat()))
    assert read_json(path, [])[0]["evidence"]["article"]["id"] == result["id"]


@pytest.mark.asyncio
async def test_startup_backfills_legacy_benchmarks_from_available_articles(tmp_path, monkeypatch):
    import app.main as main
    import app.migrate as migrate
    import app.publication_dates as dates
    now = datetime.now(timezone.utc)
    path = tmp_path / "benchmarks.json"
    benchmark = _benchmark(occurred_at=(now - timedelta(hours=2)).isoformat())
    article = _article(date=benchmark["occurred_at"], ingested_at=(now - timedelta(hours=1)).isoformat())
    write_json_atomic(path, [benchmark])
    monkeypatch.setattr(main.ai_news, "BENCHMARKS_FILE", path)
    monkeypatch.setattr(main.ai_news, "_load_articles", lambda: [article])
    monkeypatch.setattr(migrate, "migrate_legacy_to_holding", lambda: None)
    monkeypatch.setattr(dates, "repair_known_publication_dates", lambda: 0)
    monkeypatch.setattr(main.scheduler, "start", lambda: None)
    monkeypatch.setattr(main.scheduler, "stop", lambda: None)
    async with main.lifespan(None):
        assert read_json(path, [])[0]["evidence"]["article"]["id"] == "a1"


def test_rss_publication_dates_are_accepted_and_future_ingestion_is_not_frozen():
    benchmark = _benchmark()
    assert retain_match(benchmark, [_article(date="Sat, 31 Oct 2026 08:00:00 GMT")], NOW)
    assert build_benchmark_coverage([], [benchmark], now=NOW)["on_time"] == 1
    assert not retain_match(_benchmark(), [_article(ingested_at="2027-01-01T00:00:00Z")], NOW)


def test_query_article_identifiers_are_preserved_while_tracking_is_ignored():
    benchmark = _benchmark(source_url="https://qwen.ai/blog?id=model-two")
    assert not retain_match(benchmark, [_article(url="https://qwen.ai/blog?id=model-one")], NOW)
    assert retain_match(benchmark, [_article(url="https://qwen.ai/blog?utm_source=rss&id=model-two")], NOW)
