"""Deterministic coverage and discovery-latency audit for the news pipeline."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from .news_alerts import build_breaking_alerts, classify_alert


def _parse_date(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = round((len(ordered) - 1) * percentile)
    return round(ordered[index], 1)


def _event_key(article: dict) -> str:
    key = str(article.get("event_key") or "").strip()
    if key:
        return key
    title = article.get("title_zh") or article.get("title") or article.get("id") or ""
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", str(title).lower())


def build_quality_report(
    articles: list[dict],
    sources: list[dict],
    summary: dict | None,
    *,
    now: datetime | None = None,
    window_hours: int = 30,
) -> dict:
    """Measure operational coverage without making an LLM call."""
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff = current - timedelta(hours=window_hours)
    recent = [
        article for article in articles
        if (published := _parse_date(article.get("date")))
        and cutoff <= published <= current + timedelta(hours=1)
    ]

    configured = [source for source in sources if not source.get("orphan")]
    healthy = [source for source in configured if source.get("health_status") == "healthy"]
    fast = [source for source in configured if source.get("cadence") == "fast"]
    fast_healthy = [source for source in fast if source.get("health_status") == "healthy"]
    source_rate = round(len(healthy) / len(configured), 3) if configured else None
    fast_rate = round(len(fast_healthy) / len(fast), 3) if fast else None

    summary_ids = {
        str(item.get("id")) for item in ((summary or {}).get("cohort") or []) if item.get("id")
    }
    alert_ids = {
        str(item.get("id")) for item in build_breaking_alerts(recent, now=current)
        if item.get("id")
    }
    high_impact_groups: dict[str, list[dict]] = {}
    for article in recent:
        if int(article.get("importance") or 0) >= 8 or classify_alert(article):
            high_impact_groups.setdefault(_event_key(article), []).append(article)

    covered_events = 0
    missed_items: list[dict] = []
    for group in high_impact_groups.values():
        ids = {str(article.get("id")) for article in group if article.get("id")}
        if ids & (summary_ids | alert_ids):
            covered_events += 1
            continue
        representative = max(group, key=lambda article: int(article.get("importance") or 0))
        missed_items.append({
            "id": representative.get("id"),
            "title": representative.get("title_zh") or representative.get("title") or "（无标题）",
            "source": representative.get("source") or "",
            "importance": representative.get("importance"),
        })
    event_total = len(high_impact_groups)
    visible_rate = round(covered_events / event_total, 3) if event_total else None

    latencies: list[float] = []
    for article in recent:
        published = _parse_date(article.get("date"))
        ingested = _parse_date(article.get("ingested_at"))
        if not published or not ingested:
            continue
        minutes = (ingested - published).total_seconds() / 60
        if 0 <= minutes <= 7 * 24 * 60:
            latencies.append(minutes)

    pending = sum(article.get("translation_status") == "pending" for article in recent)
    categories = sorted({str(article.get("category")) for article in recent if article.get("category")})
    findings: list[dict] = []
    severity = "healthy"

    def add(level: str, title: str, detail: str) -> None:
        nonlocal severity
        findings.append({"level": level, "title": title, "detail": detail})
        if level == "critical" or (level == "watch" and severity == "healthy"):
            severity = level

    if fast_rate is not None and fast_rate < 0.8:
        add("critical", "高时效源覆盖不足", f"仅 {len(fast_healthy)}/{len(fast)} 个 fast 源健康，先修复失败或过期来源。")
    elif fast_rate is not None and fast_rate < 0.95:
        add("watch", "部分高时效源异常", f"当前 {len(fast_healthy)}/{len(fast)} 个 fast 源健康。")
    if not recent:
        add("critical", "近 30 小时没有新内容", "可能是抓取调度停止、来源集体失败或时间字段异常。")
    if visible_rate is not None and visible_rate < 0.75:
        add("critical", "高影响事件存在漏出", f"速报或重大提醒仅覆盖 {covered_events}/{event_total} 个高影响事件。")
    elif visible_rate is not None and visible_rate < 0.9:
        add("watch", "高影响事件覆盖可提升", f"速报或重大提醒覆盖 {covered_events}/{event_total} 个高影响事件。")
    if pending > 8:
        add("watch", "富化队列积压", f"近 {window_hours} 小时仍有 {pending} 篇等待翻译与评分。")
    if not findings:
        findings.append({"level": "healthy", "title": "覆盖链路正常", "detail": "暂未发现明显的来源、漏出或富化积压问题。"})

    return {
        "status": severity,
        "generated_at": current.isoformat(),
        "window_hours": window_hours,
        "source_health": {
            "healthy": len(healthy), "total": len(configured), "rate": source_rate,
            "fast_healthy": len(fast_healthy), "fast_total": len(fast), "fast_rate": fast_rate,
            "error": sum(source.get("health_status") == "error" for source in configured),
            "stale": sum(source.get("health_status") == "stale" for source in configured),
        },
        "content_coverage": {
            "recent_articles": len(recent),
            "official_articles": sum(article.get("category") == "vendor" for article in recent),
            "categories": categories,
            "high_impact_events": event_total,
            "visible_events": covered_events,
            "visible_rate": visible_rate,
            "missed_items": missed_items[:5],
        },
        "pipeline": {
            "pending_enrichment": pending,
            "latency_sample_size": len(latencies),
            "median_discovery_minutes": _percentile(latencies, 0.5),
            "p90_discovery_minutes": _percentile(latencies, 0.9),
        },
        "findings": findings,
    }
