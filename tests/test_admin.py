"""Integration tests for admin user-management guardrails.

Uses a temp data dir so it never touches real user data. Verifies the safety
rails: non-admins get 403, admins can't delete/demote themselves, and the
system refuses to drop below one admin.

Runnable two ways:
  - `pytest tests/test_admin.py`
  - `python tests/test_admin.py`  (no pytest needed — see __main__ block)
"""
import importlib
import os
import tempfile


def _fresh_client():
    """A TestClient bound to a throwaway data dir with the app freshly reloaded."""
    tmp = tempfile.mkdtemp(prefix="aif-admin-test-")
    os.environ["AIF_DATA_DIR"] = tmp
    os.environ["AIF_SECRET_KEY"] = "test-secret-key"

    import app.settings as settings_mod
    importlib.reload(settings_mod)
    import app.auth as auth_mod
    importlib.reload(auth_mod)
    import app.routers.ai_news as ainews_mod
    importlib.reload(ainews_mod)
    import app.routers.admin as admin_mod
    importlib.reload(admin_mod)
    import app.main as main_mod
    importlib.reload(main_mod)

    from fastapi.testclient import TestClient
    return TestClient(main_mod.app)


def _register(client, email):
    return client.post("/api/auth/register", json={"email": email, "password": "pass1234"})


def test_non_admin_forbidden():
    client = _fresh_client()
    _register(client, "first@t.com")          # first = admin
    client.post("/api/auth/logout")
    _register(client, "bob@t.com")            # second = user, now logged in
    assert client.get("/api/admin/users").status_code == 403


def test_admin_cannot_delete_or_demote_self():
    client = _fresh_client()
    uid = _register(client, "boss@t.com").json()["user"]["id"]   # admin, logged in
    assert client.delete(f"/api/admin/users/{uid}").status_code == 400
    assert client.patch(f"/api/admin/users/{uid}/role", json={"role": "user"}).status_code == 400


def test_admin_can_promote_and_delete_other():
    client = _fresh_client()
    _register(client, "boss@t.com")           # admin
    client.post("/api/auth/logout")
    carol = _register(client, "carol@t.com").json()["user"]["id"]   # user
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "boss@t.com", "password": "pass1234"})

    assert client.patch(f"/api/admin/users/{carol}/role", json={"role": "admin"}).status_code == 200
    assert client.delete(f"/api/admin/users/{carol}").status_code == 200
    assert client.get("/api/admin/users").json()["total"] == 1


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
