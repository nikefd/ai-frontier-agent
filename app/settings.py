"""Configuration via env / .env. All vars prefixed AIF_ (ai-frontier).

Differences from the original multi-agent project's settings.py:
- DeepSeek is the default LLM (self-contained; no hermes / Copilot token theft)
- finance / climbing settings dropped
- env prefix ZYB_ → AIF_
"""
from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AIF_",
        env_file=str(Path(__file__).parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 9702

    # Data root — articles.json / tracks.json / ui.db / reader-cache all live here.
    data_dir: Path = Field(default_factory=lambda: Path.home() / "agent-data")

    # Self-hosted RSSHub base. Feed specs are written with the public
    # `https://rsshub.app` host; at load time every such URL is rewritten to
    # this base. Point it at a private instance (e.g. http://rsshub:1200 inside
    # the compose network) to escape the public instance's rate limits / 403s.
    rsshub_base: str = "https://rsshub.app"

    # LLM — DeepSeek (OpenAI-compatible). Same key serves chat agent + workers.
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"
    llm_api_key: str | None = None

    scheduler_enabled: bool = True
    # Fetch every N hours, anchored at 05:00 (Asia/Shanghai).
    ai_news_cron_hour: int = 5
    ai_news_cron_minute: int = 0
    ai_news_interval_hours: int = 4
    # Refresh the briefing one hour after each fetch. An unchanged cohort is a
    # no-op, so this cadence does not create redundant LLM calls.
    summary_cron_hour: int = 6
    summary_cron_minute: int = 0
    summary_interval_hours: int = 4

    log_level: str = "INFO"

    # ── Auth / multi-user ──────────────────────────────────────────────
    # Secret used to sign session cookies (itsdangerous). When empty a random
    # key is generated and persisted to <data_dir>/auth/secret.key so restarts
    # keep sessions valid; set explicitly in production to survive container
    # rebuilds (otherwise everyone gets logged out on redeploy).
    secret_key: str | None = None
    # Session cookie lifetime in days.
    session_max_age_days: int = 30
    # Mark the session cookie Secure (HTTPS only). True in production behind TLS.
    cookie_secure: bool = False
    # The email that inherits the legacy single-user data on registration. When
    # empty the first account to register inherits it.
    admin_email: str | None = None
    # Daily per-user LLM-action quota (anti-abuse, second line after email verify).
    # Counts user-initiated LLM operations; admins are exempt. 0 = unlimited.
    daily_llm_limit: int = 50
    # CORS allowed origins (comma-separated). Cookies require explicit origins +
    # allow_credentials; "*" is invalid with credentials. Empty = same-origin
    # only (no CORS headers needed for the bundled UI).
    cors_origins: str = ""

    # ── Email (SMTP) for verification links ────────────────────────────
    # All optional: when smtp_host/user/password are unset, email sending is a
    # no-op (registration still works, just no verification mail is sent).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""            # From address; defaults to smtp_user when empty
    # Public base URL used to build verification links (e.g. https://ai.example.com).
    # Empty falls back to same-origin handling on the frontend.
    public_base_url: str = ""

    def model_post_init(self, __ctx) -> None:  # pydantic v2 hook
        # Allow the conventional DeepSeek env var as a fallback so the same key
        # configured for finance-agent / workers also lights up the chat agent.
        if not self.llm_api_key:
            self.llm_api_key = os.environ.get("DEEPSEEK_API_KEY")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self.admin_email:
            self.admin_email = self.admin_email.strip().lower()
        if not self.smtp_from:
            self.smtp_from = self.smtp_user

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


# Module-level singleton (cheap; settings construction is sub-ms)
settings = Settings()
