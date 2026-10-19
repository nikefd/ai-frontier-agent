"""Pydantic schemas for the AI-frontier agent.

Trimmed from the original multi-agent project's models.py: only the AI-news
shapes are kept (climbing / finance models dropped with their routers).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    ts: str | None = None


class ChatRequest(BaseModel):
    message: str
    stream: bool = False
    conversation_id: str | None = None  # ← new: ties chat to a stored conversation


# ── AI News ──────────────────────────────────────────────────────────
class Article(BaseModel):
    id: str | None = None
    title: str
    url: str
    source: str
    date: str | None = None
    ingested_at: str | None = None  # first persisted by this service; enables latency audits
    summary: str | None = None
    hands_on: str | None = None  # "动手试试" hint
    event_key: str | None = None  # normalized same-event cluster key from enrichment
    tags: list[str] = Field(default_factory=list)
    pinned: bool = False
    # tier + relevance + translation (all optional / backwards-compat)
    tier: str | None = None  # high | med | low (origin feed tier)
    category: str | None = None  # vendor | media | expert | x-ai | community | paper | trending
    ai_relevance: str | None = None  # keyword | curated | unknown | rejected
    title_zh: str | None = None
    summary_zh: str | None = None
    translation_status: str | None = None  # pending | ok | failed | skipped
    importance: int | None = None  # 0-10 LLM-scored importance (set during enrich)
    deep_dive_status: str | None = None  # none | generating | ok | failed
    deep_dive_id: str | None = None  # file stem under deep-dives/
    experiment_status: str | None = None  # planned | in_progress | completed (per-user overlay)


class Track(BaseModel):
    id: str | None = None
    name: str
    keywords: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class Guide(BaseModel):
    id: str | None = None
    title: str
    body: str = ""
    tags: list[str] = Field(default_factory=list)
    updated_at: str | None = None


# ── Auth / users ─────────────────────────────────────────────────────
class UserRecord(BaseModel):
    """Stored shape in <data_dir>/auth/users.json (includes the hash)."""
    id: str
    email: str
    password_hash: str
    role: Literal["admin", "user"] = "user"
    email_verified: bool = False
    created_at: str | None = None
    last_login_at: str | None = None


class UserPublic(BaseModel):
    """Safe shape returned to clients — never carries the password hash."""
    id: str
    email: str
    role: Literal["admin", "user"] = "user"
    email_verified: bool = False


class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
