"""Tests for email-verification token round-trip (pure-ish, uses temp data dir)."""
import importlib
import os
import tempfile


def _fresh_auth():
    os.environ["AIF_DATA_DIR"] = tempfile.mkdtemp(prefix="aif-verify-test-")
    os.environ["AIF_SECRET_KEY"] = "test-secret-key"
    import app.settings as s
    importlib.reload(s)
    import app.auth as a
    importlib.reload(a)
    return a


def test_token_roundtrip():
    a = _fresh_auth()
    tok = a.make_verification_token("u_abc")
    assert a.read_verification_token(tok) == "u_abc"


def test_tampered_token_rejected():
    a = _fresh_auth()
    tok = a.make_verification_token("u_abc")
    assert a.read_verification_token(tok + "x") is None
    assert a.read_verification_token("garbage") is None


def test_session_token_not_valid_as_verify_token():
    # Different salts → a session cookie must not pass as a verify token.
    a = _fresh_auth()
    session = a.issue_token("u_abc")
    assert a.read_verification_token(session) is None


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
