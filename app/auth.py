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
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .models import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    UserPublic,
    UserRecord,
)
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
# Separate salt so a session cookie can't be replayed as a verify token (or vice versa).
_verify_serializer = URLSafeTimedSerializer(_get_secret(), salt="aif-email-verify")
_VERIFY_MAX_AGE = 24 * 3600  # verification links valid 24h
# Yet another salt for password-reset tokens — shorter-lived (more sensitive).
_reset_serializer = URLSafeTimedSerializer(_get_secret(), salt="aif-pw-reset")
_RESET_MAX_AGE = 3600  # reset links valid 1h


def make_reset_token(uid: str) -> str:
    return _reset_serializer.dumps({"uid": uid})


def read_reset_token(token: str) -> str | None:
    try:
        data = _reset_serializer.loads(token, max_age=_RESET_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("uid") if isinstance(data, dict) else None


def set_password(uid: str, new_password: str) -> bool:
    """Replace a user's password hash. Returns False if the user is gone."""
    users = load_users()
    for u in users:
        if u.get("id") == uid:
            u["password_hash"] = hash_password(new_password)
            _save_users(users)
            return True
    return False


def make_verification_token(uid: str) -> str:
    return _verify_serializer.dumps({"uid": uid})


def read_verification_token(token: str) -> str | None:
    try:
        data = _verify_serializer.loads(token, max_age=_VERIFY_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("uid") if isinstance(data, dict) else None


def mark_email_verified(uid: str) -> bool:
    users = load_users()
    changed = False
    for u in users:
        if u.get("id") == uid:
            if not u.get("email_verified"):
                u["email_verified"] = True
                changed = True
            break
    if changed:
        _save_users(users)
    return changed


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
        # First account (the bootstrap admin) is trusted as verified, so the
        # operator isn't locked behind a verification mail before SMTP is set up.
        email_verified=(role == "admin"),
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
    return UserPublic(
        id=rec["id"],
        email=rec["email"],
        role=rec.get("role", "user"),
        email_verified=bool(rec.get("email_verified", False)),
    )


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


def require_admin(user: UserPublic = Depends(require_user)) -> UserPublic:
    """Guard for admin-only endpoints (403 for non-admins, 401 for anon)."""
    if user.role != "admin":
        raise HTTPException(403, "admin only")
    return user


def require_verified_user(user: UserPublic = Depends(require_user)) -> UserPublic:
    """Guard for LLM-burning endpoints: requires a verified email.

    Anti-abuse: with an unmetered LLM key, unverified throwaway accounts must not
    be able to spend tokens. Browsing/reads stay open; only LLM actions gate on
    verification. The bootstrap admin is auto-verified, so the operator is fine.
    """
    if not user.email_verified:
        raise HTTPException(403, "请先验证邮箱后再使用 AI 功能（顶栏「📧 未验证」可重发验证邮件）")
    return user


def count_admins() -> int:
    """Number of admin accounts — used to refuse removing the last admin."""
    return sum(1 for u in load_users() if u.get("role") == "admin")


# ── endpoints ────────────────────────────────────────────────────────
def _validate_password(password: str) -> str:
    if len(password or "") < 8:
        raise HTTPException(400, "密码至少 8 位")
    if len(password) > 128:
        raise HTTPException(400, "密码过长")
    return password


def _validate_credentials(email: str, password: str) -> tuple[str, str]:
    email = (email or "").strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(400, "邮箱格式不正确")
    _validate_password(password)
    return email, password


def _send_verification(rec: dict) -> None:
    """Build a verification link and email it. No-op if SMTP/base URL unset."""
    base = settings.public_base_url.rstrip("/")
    if not base:
        log.warning("AIF_PUBLIC_BASE_URL not set — cannot build verification link")
        return
    token = make_verification_token(rec["id"])
    link = f"{base}/api/auth/verify?token={token}"
    try:
        from .email import send_verification_email
        send_verification_email(rec["email"], link)
    except Exception as e:  # noqa: broad-except
        log.warning("verification email failed for %s: %s", rec["email"], e)


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
    # Send a verification email to non-admin signups (admin is auto-verified).
    if not rec.email_verified:
        _send_verification(rec.model_dump())
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


@router.get("/verify")
def verify_email(token: str) -> RedirectResponse:
    """Land here from the email link. Validate token, mark verified, bounce to UI."""
    uid = read_verification_token(token)
    if not uid or not find_by_id(uid):
        return RedirectResponse("/ui/?verify=invalid")
    mark_email_verified(uid)
    return RedirectResponse("/ui/?verify=ok")


@router.post("/resend-verification")
def resend_verification(request: Request, user: UserPublic = Depends(require_user)) -> dict:
    """Re-send the verification email to the logged-in user."""
    _rate_limit(f"resend:{user.id}")
    if user.email_verified:
        return {"ok": True, "already_verified": True}
    rec = find_by_id(user.id)
    if rec:
        _send_verification(rec)
    return {"ok": True}


@router.post("/change-password")
def change_password(req: ChangePasswordRequest, response: Response,
                    user: UserPublic = Depends(require_user)) -> dict:
    """Change the logged-in user's password (requires the current password)."""
    rec = find_by_id(user.id)
    if not rec or not verify_password(req.old_password or "", rec["password_hash"]):
        raise HTTPException(400, "当前密码不正确")
    _validate_password(req.new_password)
    set_password(user.id, req.new_password)
    # Re-issue the session cookie (keeps this session valid after the change).
    _set_session_cookie(response, user.id)
    return {"ok": True}


def _send_password_reset(rec: dict) -> None:
    base = settings.public_base_url.rstrip("/")
    if not base:
        log.warning("AIF_PUBLIC_BASE_URL not set — cannot build reset link")
        return
    token = make_reset_token(rec["id"])
    link = f"{base}/ui/?reset={token}"
    try:
        from .email import send_password_reset_email
        send_password_reset_email(rec["email"], link)
    except Exception as e:  # noqa: broad-except
        log.warning("password reset email failed for %s: %s", rec["email"], e)


@router.post("/forgot-password")
def forgot_password(req: ForgotPasswordRequest, request: Request) -> dict:
    """Email a password-reset link. Always returns ok (no account enumeration)."""
    email = (req.email or "").strip().lower()
    _rate_limit(f"forgot-ip:{_client_ip(request)}")
    _rate_limit(f"forgot-email:{email}")
    rec = find_by_email(email)
    if rec:
        _send_password_reset(rec)
    # Uniform response whether or not the email exists.
    return {"ok": True}


@router.post("/reset-password")
def reset_password(req: ResetPasswordRequest, response: Response) -> dict:
    """Set a new password from a valid reset token, then log the user in."""
    uid = read_reset_token(req.token)
    if not uid or not find_by_id(uid):
        raise HTTPException(400, "重置链接无效或已过期")
    _validate_password(req.new_password)
    set_password(uid, req.new_password)
    _set_session_cookie(response, uid)
    rec = find_by_id(uid)
    return {"ok": True, "user": _to_public(rec).model_dump()}
