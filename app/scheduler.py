"""APScheduler-based background tasks.

Five jobs:
- ai_news_fast:      hourly first-party model/API updates
- ai_news_standard:  broad editorial/news pulls on a configurable cadence
- ai_news_slow:      twice-daily paper/social/discovery pulls
- ai_news_translate: every-2-min tick that translates pending articles
- ai_news_summary:   intraday briefing refresh, skipped when inputs are unchanged

AsyncIOScheduler so jobs share the FastAPI event loop. Trimmed from the
original: the finance recap placeholder job is gone (finance lives elsewhere).
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .settings import settings
from .routers.ai_news import DEFAULT_FEED_SPECS
from .workers.ai_news_fetcher import fetch_once
from .workers.ai_news_translator import translate_once

log = logging.getLogger("aif.scheduler")

_scheduler: AsyncIOScheduler | None = None

_VALID_INTERVAL_HOURS = (1, 2, 3, 4, 6, 8, 12, 24)


def _scheduled_hours(anchor: int, interval: int) -> tuple[int, ...]:
    """Return stable daily cron hours for a divisor-of-24 cadence."""
    anchor = int(anchor) % 24
    interval = int(interval)
    if interval not in _VALID_INTERVAL_HOURS:
        log.warning("invalid scheduler interval %s; falling back to 4 hours", interval)
        interval = 4
    return tuple(sorted({(anchor + offset) % 24 for offset in range(0, 24, interval)}))


def _cron_hours(anchor: int, interval: int) -> str:
    return ",".join(str(hour) for hour in _scheduled_hours(anchor, interval))


def _feeds_for_cadence(cadence: str) -> list[str]:
    return [spec["url"] for spec in DEFAULT_FEED_SPECS if spec.get("cadence") == cadence]


async def _ai_news_job(cadence: str):
    try:
        added = await fetch_once(_feeds_for_cadence(cadence))
        log.info("scheduled ai-news %s fetch: added=%d", cadence, added)
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
    """Refresh the briefing after fetch + translation when its inputs changed."""
    from .llm_client import llm_configured
    from .routers.ai_news import build_today_summary
    if not llm_configured():
        log.info("summary job skipped: LLM not configured")
        return
    try:
        payload = await build_today_summary()
        log.info("scheduled briefing: %s", "generated" if payload else "unchanged or empty")
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
    fast_hours = _cron_hours(settings.ai_news_cron_hour, settings.fast_news_interval_hours)
    standard_hours = _cron_hours(settings.ai_news_cron_hour, settings.ai_news_interval_hours)
    slow_hours = _cron_hours(settings.slow_news_cron_hour, settings.slow_news_interval_hours)
    summary_hours = _cron_hours(settings.summary_cron_hour, settings.summary_interval_hours)
    sched.add_job(
        _ai_news_job,
        CronTrigger(hour=fast_hours, minute=settings.fast_news_cron_minute),
        args=["fast"],
        id="ai_news_fast",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    sched.add_job(
        _ai_news_job,
        CronTrigger(hour=standard_hours, minute=settings.ai_news_cron_minute),
        args=["standard"],
        id="ai_news_standard",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    sched.add_job(
        _ai_news_job,
        CronTrigger(hour=slow_hours, minute=settings.slow_news_cron_minute),
        args=["slow"],
        id="ai_news_slow",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
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
        CronTrigger(hour=summary_hours, minute=settings.summary_cron_minute),
        id="ai_news_summary",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    sched.start()
    _scheduler = sched
    log.info(
        "scheduler started: fast=%s standard=%s slow=%s summary=%s jobs=%s",
        fast_hours,
        standard_hours,
        slow_hours,
        summary_hours,
        [j.id for j in sched.get_jobs()],
    )
    return sched


def stop() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        log.info("scheduler stopped")
