from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.safe_fetch import UnsafeUrl, sanitize_reader_html, validate_public_http_url
from app.storage import read_json, update_json_atomic


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/file",
        "http://localhost/admin",
        "http://127.0.0.1:8000/private",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "https://user:password@example.com/",
    ],
)
async def test_reader_rejects_non_public_urls(url):
    with pytest.raises(UnsafeUrl):
        await validate_public_http_url(url)


@pytest.mark.asyncio
async def test_reader_accepts_public_literal_ip():
    assert await validate_public_http_url("https://93.184.216.34/article") == (
        "https://93.184.216.34/article"
    )


def test_reader_html_is_inert_and_links_are_safe():
    raw = """
      <html><head><title>Unsafe</title><script>alert(1)</script></head>
      <body onload="alert(2)">
        <form action="/steal"><input name="secret"></form>
        <img src=x onerror="alert(3)">
        <a href="javascript:alert(4)" onclick="alert(5)">bad</a>
        <a href="/story" style="color:red">good</a>
        <p id="x" class="y">Text</p>
      </body></html>
    """
    safe = sanitize_reader_html(raw, "https://example.com/news/item")
    lowered = safe.lower()
    assert "aif-safe-reader-v2" in safe
    assert "<script" not in lowered
    assert "<form" not in lowered
    assert "<input" not in lowered
    assert "<img" not in lowered
    assert "javascript:" not in lowered
    assert "onclick" not in lowered
    assert "onload" not in lowered
    assert "style=\"color:red\"" not in lowered
    assert 'href="https://example.com/story"' in safe
    assert 'rel="noopener noreferrer"' in safe

    unsafe_origin = sanitize_reader_html("<p>Text</p>", "javascript:alert(1)")
    assert "javascript:" not in unsafe_origin.lower()
    assert "原站地址不可用" in unsafe_origin


def test_json_read_modify_write_is_atomic(tmp_path):
    path = tmp_path / "counter.json"

    def increment(_):
        def mutate(data):
            return {"count": int(data.get("count", 0)) + 1}

        update_json_atomic(path, {"count": 0}, mutate)

    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(increment, range(100)))

    assert read_json(path, {}) == {"count": 100}


def test_global_mutations_require_admin(tmp_path, monkeypatch):
    import app.auth as auth
    import app.routers.ai_news as news

    users_file = tmp_path / "users.json"
    articles_file = tmp_path / "articles.json"
    monkeypatch.setattr(auth, "USERS_FILE", users_file)
    monkeypatch.setattr(news, "ARTICLES_FILE", articles_file)

    admin = TestClient(__import__("app.main", fromlist=["app"]).app)
    assert admin.post(
        "/api/auth/register", json={"email": "admin@example.com", "password": "password123"}
    ).status_code == 200
    assert admin.post("/api/auth/logout").status_code == 200
    assert admin.post(
        "/api/auth/register", json={"email": "user@example.com", "password": "password123"}
    ).status_code == 200

    checks = [
        ("post", "/api/ai-news/fetch", None),
        ("post", "/api/ai-news/summary/today", None),
        ("post", "/api/ai-news/translate/run", None),
        (
            "post",
            "/api/ai-news/articles",
            {"title": "x", "url": "https://example.com/x", "source": "test"},
        ),
        ("delete", "/api/ai-news/articles/missing", None),
        ("post", "/api/ai-news/articles/missing/retranslate", None),
    ]
    for method, path, body in checks:
        response = getattr(admin, method)(path, json=body) if body is not None else getattr(admin, method)(path)
        assert response.status_code == 403, (method, path, response.text)


def test_security_headers_present():
    from app.main import app

    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
