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

from ..auth import (
    _save_users,
    count_admins,
    find_by_id,
    load_users,
    require_admin,
)
from ..models import UserPublic
from ..storage import read_json
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
    target = find_by_id(uid)
    if not target:
        raise HTTPException(404, "user not found")
    # Refuse demoting the last admin (defensive — self-demote is already blocked).
    if target.get("role") == "admin" and role == "user" and count_admins() <= 1:
        raise HTTPException(400, "系统至少要保留一个管理员")

    users = load_users()
    for u in users:
        if u["id"] == uid:
            u["role"] = role
            break
    _save_users(users)
    return {"ok": True, "id": uid, "role": role}


@router.delete("/users/{uid}")
def delete_user(uid: str, admin: UserPublic = Depends(require_admin)) -> dict:
    if uid == admin.id:
        raise HTTPException(400, "不能删除自己")
    target = find_by_id(uid)
    if not target:
        raise HTTPException(404, "user not found")
    if target.get("role") == "admin" and count_admins() <= 1:
        raise HTTPException(400, "系统至少要保留一个管理员")

    users = [u for u in load_users() if u["id"] != uid]
    _save_users(users)

    # Remove the user's per-user artifact directory (pins/deep-dives/cards/ui.db…).
    try:
        d = user_dir(uid)
        if d.exists():
            shutil.rmtree(d)
    except Exception as e:  # noqa: broad-except
        log.warning("deleted user %s but could not remove its dir: %s", uid, e)

    return {"ok": True, "id": uid}
