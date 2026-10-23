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


def _importance_value(article: dict) -> int:
    """Use a neutral value while enrichment is pending; never punish new data."""
    value = article.get("importance")
    if isinstance(value, bool):
        return 5
    try:
        return max(0, min(10, int(value))) if value is not None else 5
    except (TypeError, ValueError):
        return 5


def _source_value_report(
    articles: list[dict],
    sources: list[dict],
    *,
    now: datetime,
    window_days: int = 30,
) -> dict:
    """Score source contribution from observable, explainable signals.

    This intentionally distinguishes "insufficient data" from low value.  A
    source needs at least three distinct events before receiving a score, and
    only healthy sources with at least five events can become review candidates.
    """
    cutoff = now - timedelta(days=window_days)
    configured = {
        str(source.get("name") or ""): source
        for source in sources
        if source.get("name") and not source.get("orphan")
    }
    observed = [
        article for article in articles
        if str(article.get("source") or "") in configured
        and (published := _parse_date(article.get("date")))
        and cutoff <= published <= now + timedelta(hours=1)
    ]

    event_groups: dict[str, list[dict]] = {}
    per_source: dict[str, dict[str, list[dict]]] = {}
    for article in observed:
        key = _event_key(article)
        source = str(article.get("source") or "")
        if not key or not source:
            continue
        event_groups.setdefault(key, []).append(article)
        per_source.setdefault(source, {}).setdefault(key, []).append(article)

    event_sources: dict[str, set[str]] = {}
    first_sources: dict[str, set[str]] = {}
    high_impact: set[str] = set()
    for key, group in event_groups.items():
        event_sources[key] = {str(article.get("source") or "") for article in group}
        first_seen = [
            (ingested, str(article.get("source") or ""))
            for article in group
            if (ingested := _parse_date(article.get("ingested_at")))
        ]
        if first_seen:
            earliest = min(item[0] for item in first_seen)
            # Sources discovered within the same fetch window share first credit.
            first_sources[key] = {
                source for ingested, source in first_seen
                if ingested <= earliest + timedelta(minutes=15)
            }
        else:
            first_sources[key] = set()
        if any(_importance_value(article) >= 8 or classify_alert(article) for article in group):
            high_impact.add(key)

    results: list[dict] = []
    for name, source in configured.items():
        source_events = per_source.get(name, {})
        event_count = len(source_events)
        exclusive = sum(len(event_sources[key]) == 1 for key in source_events)
        first = sum(name in first_sources[key] for key in source_events)
        impactful = sum(key in high_impact for key in source_events)
        duplicate_rate = round(1 - exclusive / event_count, 3) if event_count else None

        importance_values = [
            max(_importance_value(article) for article in group)
            for group in source_events.values()
        ]
        mean_importance = (
            round(sum(importance_values) / len(importance_values), 1)
            if importance_values else None
        )
        latencies = []
        for article in observed:
            if article.get("source") != name:
                continue
            published = _parse_date(article.get("date"))
            ingested = _parse_date(article.get("ingested_at"))
            if published and ingested:
                minutes = (ingested - published).total_seconds() / 60
                if 0 <= minutes <= 7 * 24 * 60:
                    latencies.append(minutes)
        median_latency = _percentile(latencies, 0.5)

        score: int | None = None
        classification = "insufficient"
        if event_count >= 3:
            volume_points = min(event_count / 8, 1) * 20
            exclusive_points = exclusive / event_count * 25
            first_points = first / event_count * 20
            importance_points = (mean_importance or 0) / 10 * 25
            if median_latency is None:
                latency_points = 0
            elif median_latency <= 120:
                latency_points = 10
            elif median_latency <= 360:
                latency_points = 8
            elif median_latency <= 1440:
                latency_points = 5
            elif median_latency <= 4320:
                latency_points = 2
            else:
                latency_points = 0
            score = round(
                volume_points + exclusive_points + first_points
                + importance_points + latency_points,
            )
            classification = "high_value" if score >= 70 else "useful" if score >= 45 else "low_signal"

        results.append({
            "name": name,
            "category": source.get("category") or "other",
            "cadence": source.get("cadence") or "standard",
            "health_status": source.get("health_status") or "never",
            "article_count": sum(len(group) for group in source_events.values()),
            "event_count": event_count,
            "exclusive_events": exclusive,
            "first_seen_events": first,
            "high_impact_events": impactful,
            "mean_importance": mean_importance,
            "duplicate_rate": duplicate_rate,
            "median_discovery_minutes": median_latency,
            "score": score,
            "classification": classification,
        })

    evaluated = [item for item in results if item["score"] is not None]
    evaluated.sort(key=lambda item: (-int(item["score"]), -item["event_count"], item["name"]))
    review = [
        item for item in evaluated
        if item["health_status"] == "healthy"
        and item["event_count"] >= 5
        and int(item["score"]) < 40
    ]
    review.sort(key=lambda item: (int(item["score"]), -item["event_count"], item["name"]))
    publication_dates = [
        parsed for article in observed
        if (parsed := _parse_date(article.get("date")))
    ]
    observed_span_days = (
        round((max(publication_dates) - min(publication_dates)).total_seconds() / 86400, 1)
        if len(publication_dates) >= 2 else 0.0
    )
    return {
        "window_days": window_days,
        "sample_articles": len(observed),
        "observed_span_days": observed_span_days,
        "evaluated_sources": len(evaluated),
        "high_value_sources": sum(item["classification"] == "high_value" for item in evaluated),
        "useful_sources": sum(item["classification"] == "useful" for item in evaluated),
        "low_signal_sources": sum(item["classification"] == "low_signal" for item in evaluated),
        "insufficient_sources": len(results) - len(evaluated),
        "top_sources": evaluated[:8],
        "review_candidates": review[:8],
    }


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
        "source_value": _source_value_report(articles, sources, now=current),
        "findings": findings,
    }
