"""Configuration via env / .env. All vars prefixed AIF_ (ai-frontier).

Differences from the original zhangyangbin-agents/settings.py:
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

    # LLM — DeepSeek (OpenAI-compatible). Same key serves chat agent + workers.
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"
    llm_api_key: str | None = None

    scheduler_enabled: bool = True
    ai_news_cron_hour: int = 7
    ai_news_cron_minute: int = 30

    log_level: str = "INFO"

    def model_post_init(self, __ctx) -> None:  # pydantic v2 hook
        # Allow the conventional DeepSeek env var as a fallback so the same key
        # configured for finance-agent / workers also lights up the chat agent.
        if not self.llm_api_key:
            self.llm_api_key = os.environ.get("DEEPSEEK_API_KEY")
        self.data_dir.mkdir(parents=True, exist_ok=True)


# Module-level singleton (cheap; settings construction is sub-ms)
settings = Settings()
