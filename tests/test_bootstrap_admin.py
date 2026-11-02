"""Public signup cannot claim admin; local initialization preserves existing users."""
from concurrent.futures import ThreadPoolExecutor

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from app.storage import read_json


@pytest.fixture
def isolated_auth(tmp_path, monkeypatch):
    import app.auth as auth
    monkeypatch.setattr(auth, "USERS_FILE", tmp_path / "auth/users.json")
    return auth


def test_empty_site_rejects_http_signup_and_role_injection(isolated_auth):
    import app.main as main
    client = TestClient(main.app)
    response = client.post("/api/auth/register", json={
        "email": "attacker@example.test", "password": "valid-pass-123", "role": "admin", "initial_admin": True,
    })
    assert response.status_code == 503
    assert read_json(isolated_auth.USERS_FILE, []) == []
    isolated_auth.create_initial_admin("owner@example.test", "owner-pass-123")
    response = client.post("/api/auth/register", json={
        "email": "reader@example.test", "password": "reader-pass-123", "role": "admin", "initial_admin": True,
    })
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "user"
    assert response.json()["user"]["email_verified"] is False


def test_local_bootstrap_is_once_only_and_existing_admin_password_unchanged(isolated_auth):
    admin = isolated_auth.create_initial_admin(" OWNER@example.test ", "owner-pass-123")
    assert admin.role == "admin" and admin.email_verified is True
    before = isolated_auth.USERS_FILE.read_bytes()
    with pytest.raises(HTTPException) as error:
        isolated_auth.create_initial_admin("another@example.test", "other-pass-123")
    assert error.value.status_code == 409
    assert isolated_auth.USERS_FILE.read_bytes() == before
    assert isolated_auth.verify_password("owner-pass-123", isolated_auth.load_users()[0]["password_hash"])


def test_concurrent_initialization_creates_exactly_one_admin(isolated_auth):
    def initialize(index):
        try:
            return isolated_auth.create_initial_admin(f"owner{index}@example.test", "owner-pass-123").role
        except HTTPException as error:
            return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(initialize, range(2)))
    assert sorted(map(str, results)) == ["409", "admin"]
    assert len(isolated_auth.load_users()) == 1


def test_cli_checks_confirmation_and_never_prints_password(isolated_auth, tmp_path, monkeypatch, capsys):
    import app.bootstrap_admin as cli
    import app.migrate as migrate
    monkeypatch.setattr(cli, "AUTH_DIR", tmp_path / "auth")
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(migrate, "inherit_legacy_if_eligible", lambda _: None)
    monkeypatch.setattr(migrate, "migrate_legacy_to_holding", lambda: None)
    passwords = iter(["owner-pass-123", "different"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: next(passwords))
    with pytest.raises(SystemExit):
        cli.main(["--email", "owner@example.test"])
    assert not isolated_auth.load_users()
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: "owner-pass-123")
    assert cli.main(["--email", "owner@example.test"]) == 0
    output = capsys.readouterr()
    assert "owner-pass-123" not in output.out + output.err
    assert len(isolated_auth.load_users()) == 1


def test_cli_requires_tty_and_rejects_password_argument(isolated_auth, monkeypatch):
    import app.bootstrap_admin as cli
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    with pytest.raises(SystemExit):
        cli.main(["--email", "owner@example.test"])
    with pytest.raises(SystemExit):
        cli.main(["--email", "owner@example.test", "--password", "not-supported"])
    assert not isolated_auth.load_users()


def test_designated_legacy_email_does_not_grant_unverified_signup_access(monkeypatch):
    import app.migrate as migrate
    from app.models import UserRecord
    monkeypatch.setattr(migrate.settings, "admin_email", "owner@example.test")
    user = UserRecord(id="reader", email="owner@example.test", password_hash="unused", role="user")
    assert not migrate._is_eligible(user)
    user.role = "admin"
    assert migrate._is_eligible(user)
