from __future__ import annotations

from xml.etree import ElementTree as ET

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.routers.rss as rss_router
from app.routers.rss import build_digest_rss
from app.storage import write_json_atomic
from app.summary_feed import archive_summary, load_public_summaries


def _summary(fingerprint: str, generated_at: str, body: str = "## 今日重点\n- 新模型发布 [1]") -> dict:
    return {
        "generated_at": generated_at,
        "date": generated_at[:10],
        "cohort_fingerprint": fingerprint,
        "body": body,
        "cohort": [{
            "id": "a1",
            "title": "Model X",
            "source": "Example Lab",
            "url": "https://example.com/model-x",
        }],
    }


def test_archive_deduplicates_same_cohort_and_merges_current(tmp_path, monkeypatch) -> None:
    import app.summary_feed as feed

    history_file = tmp_path / "summary_history.json"
    current_file = tmp_path / "summary_today.json"
    monkeypatch.setattr(feed, "SUMMARY_HISTORY_FILE", history_file)
    monkeypatch.setattr(feed, "SUMMARY_FILE", current_file)

    archive_summary(_summary("same", "2026-10-22T01:00:00+00:00", "old"))
    archive_summary(_summary("same", "2026-10-22T02:00:00+00:00", "new"))
    write_json_atomic(current_file, _summary("current", "2026-10-22T03:00:00+00:00"))

    summaries = load_public_summaries()
    assert [item["cohort_fingerprint"] for item in summaries] == ["current", "same"]
    assert summaries[1]["body"] == "new"


def test_digest_rss_has_stable_guid_and_clickable_citations() -> None:
    payload = build_digest_rss(
        [_summary("abc123", "2026-10-22T05:37:43+00:00")],
        "https://ai.example.com/",
    )
    root = ET.fromstring(payload)
    channel = root.find("channel")
    assert channel is not None
    assert channel.findtext("title") == "AI 前沿速报"
    item = channel.find("item")
    assert item is not None
    assert item.findtext("guid") == "urn:ai-frontier:briefing:abc123"
    assert item.findtext("link") == "https://ai.example.com/summary"
    assert 'href="https://example.com/model-x"' in (item.findtext("description") or "")


def test_digest_endpoint_supports_reader_discovery_cache(monkeypatch) -> None:
    monkeypatch.setattr(
        rss_router,
        "load_public_summaries",
        lambda: [_summary("abc123", "2026-10-22T05:37:43+00:00")],
    )
    app = FastAPI()
    app.include_router(rss_router.router)
    client = TestClient(app)

    response = client.get("/rss/digest.xml")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/rss+xml")
    assert response.headers["cache-control"] == "public, max-age=300"
    assert response.headers["etag"]
    head = client.head("/rss/digest.xml")
    assert head.status_code == 200
    assert head.headers["content-type"].startswith("application/rss+xml")
    assert head.headers["etag"] == response.headers["etag"]
    assert not head.content
    cached = client.get(
        "/rss/digest.xml",
        headers={"If-None-Match": response.headers["etag"]},
    )
    assert cached.status_code == 304
