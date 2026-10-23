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
    assert client.get("/api/ai-news/quality/benchmarks").json()["total"] == 1
    assert client.get("/api/ai-news/quality/report").json()["benchmark_coverage"]["total"] == 1

    client.post("/api/auth/logout")
    _register(client, "reader@example.test")
    assert client.get("/api/ai-news/quality/benchmarks").status_code == 403
    assert client.post("/api/ai-news/quality/benchmarks", json=payload).status_code == 403
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
