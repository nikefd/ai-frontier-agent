"""APScheduler-based background tasks.

Two jobs:
- ai_news_fetch:     daily RSS pull (token-thrifty; users hit "立即抓取" for ad-hoc)
- ai_news_translate: every-2-min tick that translates pending articles

AsyncIOScheduler so jobs share the FastAPI event loop. Trimmed from the
original: the finance recap placeholder job is gone (finance lives elsewhere).
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .settings import settings
from .workers.ai_news_fetcher import fetch_once
from .workers.ai_news_translator import translate_once

log = logging.getLogger("aif.scheduler")

_scheduler: AsyncIOScheduler | None = None


async def _ai_news_job():
    try:
        added = await fetch_once()
        log.info("scheduled ai-news fetch: added=%d", added)
    except Exception as e:  # noqa
        log.exception("ai-news fetch failed: %s", e)


async def _ai_news_translate_job():
    try:
        n = await translate_once()
        if n:
            log.info("translation tick: %d articles", n)
    except Exception as e:  # noqa
        log.exception("translation tick failed: %s", e)


async def _ai_news_summary_job():
    """Daily morning briefing — runs after fetch + translation so it summarizes
    the freshest cohort. No-op if the LLM isn't configured or there's nothing new."""
    from .llm_client import llm_configured
    from .routers.ai_news import build_today_summary
    if not llm_configured():
        log.info("summary job skipped: LLM not configured")
        return
    try:
        payload = await build_today_summary()
        log.info("scheduled briefing: %s", "generated" if payload else "no recent articles")
    except Exception as e:  # noqa
        log.exception("briefing generation failed: %s", e)


def start() -> AsyncIOScheduler | None:
    global _scheduler
    if not settings.scheduler_enabled:
        log.info("scheduler disabled by config")
        return None
    if _scheduler is not None:
        return _scheduler
    sched = AsyncIOScheduler(timezone="Asia/Shanghai")
    sched.add_job(
        _ai_news_job,
        CronTrigger(hour=settings.ai_news_cron_hour, minute=settings.ai_news_cron_minute),
        id="ai_news_daily",
        replace_existing=True,
    )
    sched.add_job(
        _ai_news_translate_job,
        IntervalTrigger(minutes=2),
        id="ai_news_translate",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    sched.add_job(
        _ai_news_summary_job,
        CronTrigger(hour=settings.summary_cron_hour, minute=settings.summary_cron_minute),
        id="ai_news_summary",
        replace_existing=True,
    )
    sched.start()
    _scheduler = sched
    log.info("scheduler started: jobs=%s", [j.id for j in sched.get_jobs()])
    return sched


def stop() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        log.info("scheduler stopped")
