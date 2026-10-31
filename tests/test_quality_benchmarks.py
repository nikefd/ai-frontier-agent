"""Admin CRUD guardrails for must-not-miss coverage benchmarks."""
from __future__ import annotations

import importlib
import os
import tempfile
from datetime import datetime, timedelta, timezone


def _fresh_client():
    tmp = tempfile.mkdtemp(prefix="aif-quality-benchmark-test-")
    os.environ["AIF_DATA_DIR"] = tmp
    os.environ["AIF_SECRET_KEY"] = "test-secret-key"

    import app.settings as settings_mod
    importlib.reload(settings_mod)
    import app.auth as auth_mod
    importlib.reload(auth_mod)
    import app.routers.ai_news as ainews_mod
    importlib.reload(ainews_mod)
    import app.routers.quality as quality_mod
    importlib.reload(quality_mod)
    import app.main as main_mod
    importlib.reload(main_mod)

    from fastapi.testclient import TestClient
    return TestClient(main_mod.app)


def _register(client, email: str):
    return client.post("/api/auth/register", json={"email": email, "password": "pass1234"})


def test_admin_can_create_and_delete_benchmark_but_regular_user_cannot() -> None:
    client = _fresh_client()
    _register(client, "admin@example.test")
    occurred = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    payload = {
        "title": "GPT-6 正式发布",
        "occurred_at": occurred,
        "source_url": "https://openai.com/news/gpt-6",
        "match_terms": ["GPT-6", "OpenAI", "GPT-6"],
        "deadline_hours": 6,
    }

    created = client.post("/api/ai-news/quality/benchmarks", json=payload)
    assert created.status_code == 201
    benchmark = created.json()
    assert benchmark["match_terms"] == ["GPT-6", "OpenAI"]
    assert benchmark["origin"] == "manual"
    assert client.get("/api/ai-news/quality/benchmarks").json()["total"] == 1
    assert client.get("/api/ai-news/quality/benchmark-candidates").status_code == 200
    assert client.get("/api/ai-news/quality/report").json()["benchmark_coverage"]["total"] == 1

    client.post("/api/auth/logout")
    _register(client, "reader@example.test")
    assert client.get("/api/ai-news/quality/benchmarks").status_code == 403
    assert client.get("/api/ai-news/quality/benchmark-candidates").status_code == 403
    assert client.post("/api/ai-news/quality/benchmarks", json=payload).status_code == 403
    assert client.patch(
        f"/api/ai-news/quality/benchmarks/{benchmark['id']}/remediation",
        json={"action": "start"},
    ).status_code == 403
    assert client.post(f"/api/ai-news/quality/benchmarks/{benchmark['id']}/recheck").status_code == 403
    assert client.post(
        f"/api/ai-news/quality/benchmarks/{benchmark['id']}/discover-sources"
    ).status_code == 403
    assert client.post(
        f"/api/ai-news/quality/benchmarks/{benchmark['id']}/activate-source",
        json={"url": "https://openai.com/feed.xml", "name": "OpenAI Feed"},
    ).status_code == 403
    assert client.patch(
        "/api/ai-news/sources/custom",
        json={"url": "https://openai.com/feed.xml", "enabled": False},
    ).status_code == 403
    assert client.delete(
        "/api/ai-news/sources/custom?url=https%3A%2F%2Fopenai.com%2Ffeed.xml"
    ).status_code == 403
    assert client.delete(f"/api/ai-news/quality/benchmarks/{benchmark['id']}").status_code == 403

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "admin@example.test", "password": "pass1234"})
    assert client.delete(f"/api/ai-news/quality/benchmarks/{benchmark['id']}").status_code == 200
    assert client.get("/api/ai-news/quality/benchmarks").json()["total"] == 0


def test_benchmark_requires_a_match_signal() -> None:
    client = _fresh_client()
    _register(client, "admin@example.test")
    response = client.post("/api/ai-news/quality/benchmarks", json={
        "title": "无法匹配的事件",
        "occurred_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
    })
    assert response.status_code == 400


def test_admin_can_track_close_and_recheck_remediation(monkeypatch) -> None:
    client = _fresh_client()
    _register(client, "admin@example.test")
    created = client.post("/api/ai-news/quality/benchmarks", json={
        "title": "OpenAI 关键模型发布",
        "occurred_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        "source_url": "https://openai.com/news/model-release",
        "deadline_hours": 6,
    }).json()
    benchmark_id = created["id"]

    started = client.patch(f"/api/ai-news/quality/benchmarks/{benchmark_id}/remediation", json={
        "action": "start",
    })
    assert started.status_code == 200
    assert started.json()["remediation"]["status"] == "in_progress"

    invalid_close = client.patch(
        f"/api/ai-news/quality/benchmarks/{benchmark_id}/remediation",
        json={"action": "close", "outcome": "fixed", "note": "no"},
    )
    assert invalid_close.status_code == 400
    closed = client.patch(
        f"/api/ai-news/quality/benchmarks/{benchmark_id}/remediation",
        json={"action": "close", "outcome": "accepted", "note": "源站本身延迟发布"},
    )
    assert closed.status_code == 200

    async def fake_fetch(feeds):
        assert len(feeds) == 1
        assert "openai.com" in feeds[0]
        return 2

    import app.workers.ai_news_fetcher as fetcher
    monkeypatch.setattr(fetcher, "fetch_once", fake_fetch)
    rechecked = client.post(f"/api/ai-news/quality/benchmarks/{benchmark_id}/recheck")
    assert rechecked.status_code == 200
    assert rechecked.json()["added"] == 2
    assert rechecked.json()["item"]["remediation"]["status"] == "closed"
    assert rechecked.json()["item"]["remediation"]["last_recheck_added"] == 2

    public_item = client.get("/api/ai-news/quality/report").json()["benchmark_coverage"]["items"][0]
    assert public_item["remediation"]["outcome"] == "accepted"
    assert "note" not in public_item["remediation"]


def test_admin_can_discover_and_persist_unconfigured_source_candidates(monkeypatch) -> None:
    client = _fresh_client()
    _register(client, "admin@example.test")
    created = client.post("/api/ai-news/quality/benchmarks", json={
        "title": "Missing Lab 模型发布",
        "occurred_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        "source_url": "https://missing-lab.test/news/model",
        "deadline_hours": 6,
    }).json()

    candidate = {
        "url": "https://missing-lab.test/feed.xml", "kind": "rss", "ready": True,
        "entry_count": 8, "dated_entries": 8, "latest_at": datetime.now(timezone.utc).isoformat(),
        "evidence": "页面声明的 RSS；可解析 8 条", "next_step": "可按 fast 官方源接入",
    }

    async def fake_discovery(source_url: str):
        assert source_url == "https://missing-lab.test/news/model"
        return [candidate]

    import app.source_discovery as discovery
    monkeypatch.setattr(discovery, "discover_official_sources", fake_discovery)
    response = client.post(f"/api/ai-news/quality/benchmarks/{created['id']}/discover-sources")
    assert response.status_code == 200
    assert response.json()["items"] == [candidate]

    stored = client.get("/api/ai-news/quality/benchmarks").json()["items"][0]
    assert stored["remediation"]["status"] == "in_progress"
    assert stored["remediation"]["source_candidates"] == [candidate]
    public_item = client.get("/api/ai-news/quality/report").json()["benchmark_coverage"]["items"][0]
    assert "source_candidates" not in public_item["remediation"]

    async def fake_validate(url: str, source_url: str, kind: str):
        assert url == candidate["url"]
        assert source_url == "https://missing-lab.test/news/model"
        assert kind == "rss"
        return candidate

    async def fake_fetch(feeds):
        assert feeds == [candidate["url"]]
        return 3

    import app.source_activation as activation
    monkeypatch.setattr(activation, "validate_discovered_source", fake_validate)
    import app.workers.ai_news_fetcher as fetcher
    monkeypatch.setattr(fetcher, "fetch_once", fake_fetch)
    activated = client.post(
        f"/api/ai-news/quality/benchmarks/{created['id']}/activate-source",
        json={"url": candidate["url"], "name": "Missing Lab Official"},
    )
    assert activated.status_code == 200
    assert activated.json()["added"] == 3
    assert activated.json()["source"]["cadence"] == "fast"
    assert activated.json()["source"]["category"] == "vendor"

    sources = client.get("/api/ai-news/sources").json()
    custom = next(item for item in sources if item["url"] == candidate["url"])
    assert custom["custom"] is True
    assert custom["name"] == "Missing Lab Official"

    stored = client.get("/api/ai-news/quality/benchmarks").json()["items"][0]
    activated_candidate = stored["remediation"]["source_candidates"][0]
    assert activated_candidate["activated_name"] == "Missing Lab Official"
    assert activated_candidate["activated_added"] == 3
    assert client.post(
        f"/api/ai-news/quality/benchmarks/{created['id']}/activate-source",
        json={"url": candidate["url"], "name": "Missing Lab Official"},
    ).status_code == 409

    disabled = client.patch("/api/ai-news/sources/custom", json={
        "url": candidate["url"], "enabled": False,
    })
    assert disabled.status_code == 200
    assert disabled.json()["source"]["enabled"] is False
    custom = next(item for item in client.get("/api/ai-news/sources").json() if item["url"] == candidate["url"])
    assert custom["enabled"] is False
    assert custom["health_status"] == "disabled"

    import app.routers.ai_news as ainews
    import app.scheduler as scheduler
    assert candidate["url"] not in ainews.DEFAULT_FEEDS
    assert candidate["url"] not in scheduler._feeds_for_cadence("fast")
    stored = client.get("/api/ai-news/quality/benchmarks").json()["items"][0]
    assert stored["remediation"]["source_candidates"][0]["source_enabled"] is False

    enabled = client.patch("/api/ai-news/sources/custom", json={
        "url": candidate["url"], "enabled": True,
    })
    assert enabled.status_code == 200
    assert candidate["url"] in ainews.DEFAULT_FEEDS

    deleted = client.delete(
        "/api/ai-news/sources/custom?url=https%3A%2F%2Fmissing-lab.test%2Ffeed.xml"
    )
    assert deleted.status_code == 200
    assert deleted.json()["articles_preserved"] is True
    assert not any(
        item["url"] == candidate["url"] for item in client.get("/api/ai-news/sources").json()
    )
    assert candidate["url"] not in ainews.FEED_SPEC_BY_URL
    stored = client.get("/api/ai-news/quality/benchmarks").json()["items"][0]
    lifecycle = stored["remediation"]["source_candidates"][0]
    assert "activated_at" not in lifecycle
    assert lifecycle["last_deleted_at"]
    assert client.delete(
        "/api/ai-news/sources/custom?url=https%3A%2F%2Fmissing-lab.test%2Ffeed.xml"
    ).status_code == 404


def test_admin_can_validate_and_activate_sitemap_adapter(monkeypatch) -> None:
    client = _fresh_client()
    _register(client, "admin@example.test")
    created = client.post("/api/ai-news/quality/benchmarks", json={
        "title": "Adapter Lab 模型发布",
        "occurred_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        "source_url": "https://adapter-lab.test/news/model",
        "deadline_hours": 6,
    }).json()
    candidate = {
        "url": "https://adapter-lab.test/sitemap.xml", "kind": "sitemap",
        "ready": False, "entry_count": 30, "dated_entries": 30,
        "evidence": "有效 sitemap", "next_step": "自动验证",
    }

    async def fake_discovery(_source_url: str):
        return [candidate]

    import app.source_discovery as discovery
    monkeypatch.setattr(discovery, "discover_official_sources", fake_discovery)
    response = client.post(f"/api/ai-news/quality/benchmarks/{created['id']}/discover-sources")
    assert response.status_code == 200

    async def fake_validate(url: str, source_url: str, kind: str):
        assert (url, source_url, kind) == (
            candidate["url"], "https://adapter-lab.test/news/model", "sitemap",
        )
        return {
            **candidate, "ready": True,
            "adapter": {"format": "sitemap", "include_paths": ["/news/"]},
        }

    import app.source_activation as activation
    monkeypatch.setattr(activation, "validate_discovered_source", fake_validate)

    async def fake_fetch(feeds):
        assert feeds == [candidate["url"]]
        return 2

    import app.workers.ai_news_fetcher as fetcher
    monkeypatch.setattr(fetcher, "fetch_once", fake_fetch)
    activated = client.post(
        f"/api/ai-news/quality/benchmarks/{created['id']}/activate-source",
        json={"url": candidate["url"], "name": "Adapter Lab News"},
    )

    assert activated.status_code == 200
    assert activated.json()["source"]["format"] == "sitemap"
    assert activated.json()["source"]["include_paths"] == ["/news/"]
    source = next(
        item for item in client.get("/api/ai-news/sources").json()
        if item["url"] == candidate["url"]
    )
    assert source["custom"] is True


def test_independent_benchmark_requires_evidence_and_reports_origin_separately():
    client = _fresh_client()
    _register(client, "admin@example.test")
    payload = {"title": "Independently found release", "origin": "independent",
        "occurred_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        "match_terms": ["UniqueModel"]}
    assert client.post("/api/ai-news/quality/benchmarks", json=payload).status_code == 400
    payload["source_url"] = "https://official.test/news/model"
    result = client.post("/api/ai-news/quality/benchmarks", json=payload)
    assert result.status_code == 201
    assert result.json()["origin"] == "independent"
    coverage = client.get("/api/ai-news/quality/report").json()["benchmark_coverage"]
    assert coverage["origin_breakdown"]["independent"] == {"total": 1, "settled": 1, "on_time": 0, "missed": 1}
    assert coverage["origin_breakdown"]["candidate"]["total"] == 0
    assert coverage["items"][0]["origin"] == "independent"
    payload["origin"] = "candidate"
    assert client.post("/api/ai-news/quality/benchmarks", json=payload).status_code == 201
    groups = client.get("/api/ai-news/quality/report").json()["benchmark_coverage"]["origin_breakdown"]
    assert groups["candidate"]["total"] == groups["independent"]["total"] == 1
    payload["origin"] = "unverified"
    assert client.post("/api/ai-news/quality/benchmarks", json=payload).status_code == 422
