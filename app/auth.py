"""Authentication: user store, password hashing, signed-cookie sessions, and
the FastAPI dependencies the rest of the app uses to gate writes / LLM calls.

Design (see docs/requirements/multi-user-auth-design.md):
- Users live in <data_dir>/auth/users.json (global), written atomically.
- Sessions are stateless: a signed, timestamped cookie (itsdangerous) carrying
  the uid. Logout just clears the cookie. The signing secret comes from
  settings.secret_key, falling back to a generated <data_dir>/auth/secret.key.
- Passwords are bcrypt-hashed (salted). Login uses a uniform error and always
  runs a hash compare to blunt user-enumeration / timing signals.
- Two dependencies: current_user_optional (None when anon) for user-scoped
  reads, and require_user (401 when anon) for every write / LLM endpoint.
"""
from __future__ import annotations

import logging
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .models import LoginRequest, RegisterRequest, UserPublic, UserRecord
from .settings import settings
from .storage import read_json, write_json_atomic

log = logging.getLogger("aif.auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])

AUTH_DIR = settings.data_dir / "auth"
USERS_FILE = AUTH_DIR / "users.json"
SECRET_FILE = AUTH_DIR / "secret.key"

# In-memory sliding-window rate limiter for auth endpoints. Single process, so a
# dict of recent attempt timestamps per key is enough (no Redis). Bounds brute
# force on /login and /register.
_RATE_MAX = 8           # attempts...
_RATE_WINDOW = 60.0     # ...per this many seconds, per key
_rate_hits: dict[str, deque] = defaultdict(deque)
_rate_lock = threading.Lock()


def _rate_limit(key: str) -> None:
    """Raise 429 if `key` exceeded _RATE_MAX attempts within _RATE_WINDOW."""
    now = time.monotonic()
    with _rate_lock:
        dq = _rate_hits[key]
        while dq and now - dq[0] > _RATE_WINDOW:
            dq.popleft()
        if len(dq) >= _RATE_MAX:
            raise HTTPException(429, "尝试过于频繁，请稍后再试")
        dq.append(now)


def _client_ip(request: Request) -> str:
    # Behind Traefik/Coolify the real IP is in X-Forwarded-For; fall back to the
    # socket peer. Only the first hop is trusted enough for rate-limit keying.
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "?"

COOKIE_NAME = "aif_session"
_SESSION_SALT = "aif-session"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# A precomputed hash to compare against when the email is unknown, so a missing
# user costs the same as a wrong password (anti-enumeration / timing).
_DUMMY_HASH = bcrypt.hashpw(b"aif-dummy-password", bcrypt.gensalt()).decode()


# ── secret / serializer ──────────────────────────────────────────────
def _get_secret() -> str:
    if settings.secret_key:
        return settings.secret_key
    if SECRET_FILE.exists():
        return SECRET_FILE.read_text(encoding="utf-8").strip()
    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    key = secrets.token_urlsafe(48)
    SECRET_FILE.write_text(key, encoding="utf-8")
    log.warning("AIF_SECRET_KEY not set — generated one at %s "
                "(set it in env to survive container rebuilds)", SECRET_FILE)
    return key


_serializer = URLSafeTimedSerializer(_get_secret(), salt=_SESSION_SALT)


# ── password hashing ─────────────────────────────────────────────────
def hash_password(password: str) -> str:
    # bcrypt caps at 72 bytes; truncate to stay within it deterministically.
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ── user store ───────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_users() -> list[dict]:
    data = read_json(USERS_FILE, [])
    return data if isinstance(data, list) else []


def _save_users(users: list[dict]) -> None:
    write_json_atomic(USERS_FILE, users)


def find_by_email(email: str) -> dict | None:
    email = email.strip().lower()
    return next((u for u in load_users() if u.get("email") == email), None)


def find_by_id(uid: str) -> dict | None:
    return next((u for u in load_users() if u.get("id") == uid), None)


def create_user(email: str, password: str) -> UserRecord:
    """Create + persist a user. First account becomes admin."""
    email = email.strip().lower()
    users = load_users()
    role = "admin" if not users else "user"
    rec = UserRecord(
        id="u_" + secrets.token_hex(8),
        email=email,
        password_hash=hash_password(password),
        role=role,
        created_at=_now_iso(),
        last_login_at=_now_iso(),
    )
    users.append(rec.model_dump())
    _save_users(users)
    return rec


def _touch_login(uid: str) -> None:
    users = load_users()
    for u in users:
        if u.get("id") == uid:
            u["last_login_at"] = _now_iso()
            break
    _save_users(users)


# ── session token ────────────────────────────────────────────────────
def issue_token(uid: str) -> str:
    return _serializer.dumps({"uid": uid})


def read_token(token: str) -> str | None:
    max_age = settings.session_max_age_days * 86400
    try:
        data = _serializer.loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    uid = data.get("uid") if isinstance(data, dict) else None
    return uid


def _set_session_cookie(response: Response, uid: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        issue_token(uid),
        max_age=settings.session_max_age_days * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def _to_public(rec: dict) -> UserPublic:
    return UserPublic(id=rec["id"], email=rec["email"], role=rec.get("role", "user"))


# ── FastAPI dependencies ─────────────────────────────────────────────
def current_user_optional(request: Request) -> UserPublic | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    uid = read_token(token)
    if not uid:
        return None
    rec = find_by_id(uid)
    return _to_public(rec) if rec else None


def require_user(request: Request) -> UserPublic:
    user = current_user_optional(request)
    if user is None:
        raise HTTPException(401, "login required")
    return user


# ── endpoints ────────────────────────────────────────────────────────
def _validate_credentials(email: str, password: str) -> tuple[str, str]:
    email = (email or "").strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(400, "邮箱格式不正确")
    if len(password or "") < 8:
        raise HTTPException(400, "密码至少 8 位")
    if len(password) > 128:
        raise HTTPException(400, "密码过长")
    return email, password


@router.post("/register")
def register(req: RegisterRequest, request: Request, response: Response) -> dict:
    _rate_limit(f"register:{_client_ip(request)}")
    email, password = _validate_credentials(req.email, req.password)
    if find_by_email(email):
        raise HTTPException(409, "该邮箱已注册")
    rec = create_user(email, password)
    # Hook for P1: inherit legacy single-user data on the inheriting account.
    try:
        from .migrate import inherit_legacy_if_eligible
        inherit_legacy_if_eligible(rec)
    except Exception as e:  # noqa: broad-except
        log.warning("legacy inheritance skipped: %s", e)
    _set_session_cookie(response, rec.id)
    return {"ok": True, "user": _to_public(rec.model_dump()).model_dump()}


@router.post("/login")
def login(req: LoginRequest, request: Request, response: Response) -> dict:
    email = (req.email or "").strip().lower()
    # Rate-limit per IP and per target email to blunt brute force / spraying.
    _rate_limit(f"login-ip:{_client_ip(request)}")
    _rate_limit(f"login-email:{email}")
    rec = find_by_email(email)
    # Always run a hash compare (dummy when unknown) → uniform timing + message.
    ok = verify_password(req.password or "", rec["password_hash"] if rec else _DUMMY_HASH)
    if not rec or not ok:
        raise HTTPException(401, "邮箱或密码错误")
    _touch_login(rec["id"])
    _set_session_cookie(response, rec["id"])
    return {"ok": True, "user": _to_public(rec).model_dump()}


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: UserPublic | None = Depends(current_user_optional)) -> dict:
    return {"user": user.model_dump() if user else None}
