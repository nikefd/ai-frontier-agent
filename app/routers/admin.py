"""Admin user management — list / change role / delete users.

All endpoints require an admin (``require_admin``). Guardrails prevent an admin
from locking everyone out: you can't delete or demote yourself, and the system
always keeps at least one admin.

Split into its own module (not piled into auth.py) per the code-quality rules.
"""
from __future__ import annotations

import logging
import shutil

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import USERS_FILE, load_users, require_admin
from ..models import UserPublic
from ..storage import read_json, update_json_atomic
from .ai_news import deep_dives_dir, pins_file, review_cards_file, user_dir

router = APIRouter(prefix="/api/admin", tags=["admin"])
log = logging.getLogger("aif.admin")


class RoleUpdate(BaseModel):
    role: str  # "admin" | "user"


def _artifact_counts(uid: str) -> dict:
    """Lightweight per-user artifact overview for the admin table."""
    pins = read_json(pins_file(uid), [])
    cards = read_json(review_cards_file(uid), [])
    ddir = deep_dives_dir(uid)
    dives = len(list(ddir.glob("*.json"))) if ddir.exists() else 0
    return {
        "pins": len(pins) if isinstance(pins, list) else 0,
        "deep_dives": dives,
        "cards": len(cards) if isinstance(cards, list) else 0,
    }


def _public(rec: dict) -> dict:
    """User row for admin view — never includes password_hash."""
    return {
        "id": rec["id"],
        "email": rec["email"],
        "role": rec.get("role", "user"),
        "created_at": rec.get("created_at"),
        "last_login_at": rec.get("last_login_at"),
        "artifacts": _artifact_counts(rec["id"]),
    }


@router.get("/users")
def list_users(admin: UserPublic = Depends(require_admin)) -> dict:
    users = load_users()
    rows = [_public(u) for u in users]
    rows.sort(key=lambda r: r.get("created_at") or "")
    return {"total": len(rows), "items": rows, "me": admin.id}


@router.patch("/users/{uid}/role")
def update_role(uid: str, req: RoleUpdate, admin: UserPublic = Depends(require_admin)) -> dict:
    role = (req.role or "").strip()
    if role not in ("admin", "user"):
        raise HTTPException(400, "role must be 'admin' or 'user'")
    if uid == admin.id:
        raise HTTPException(400, "不能修改自己的角色")
    def mutate(data):
        users = data if isinstance(data, list) else []
        target = next((user for user in users if user.get("id") == uid), None)
        if not target:
            raise HTTPException(404, "user not found")
        admins = sum(1 for user in users if user.get("role") == "admin")
        if target.get("role") == "admin" and role == "user" and admins <= 1:
            raise HTTPException(400, "系统至少要保留一个管理员")
        target["role"] = role
        return users

    update_json_atomic(USERS_FILE, [], mutate)
    return {"ok": True, "id": uid, "role": role}


@router.delete("/users/{uid}")
def delete_user(uid: str, admin: UserPublic = Depends(require_admin)) -> dict:
    if uid == admin.id:
        raise HTTPException(400, "不能删除自己")
    def mutate(data):
        users = data if isinstance(data, list) else []
        target = next((user for user in users if user.get("id") == uid), None)
        if not target:
            raise HTTPException(404, "user not found")
        admins = sum(1 for user in users if user.get("role") == "admin")
        if target.get("role") == "admin" and admins <= 1:
            raise HTTPException(400, "系统至少要保留一个管理员")
        return [user for user in users if user.get("id") != uid]

    update_json_atomic(USERS_FILE, [], mutate)

    # Remove the user's per-user artifact directory (pins/deep-dives/cards/ui.db…).
    try:
        d = user_dir(uid)
        if d.exists():
            shutil.rmtree(d)
    except Exception as e:  # noqa: broad-except
        log.warning("deleted user %s but could not remove its dir: %s", uid, e)

    return {"ok": True, "id": uid}
