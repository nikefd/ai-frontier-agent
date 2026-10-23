"""Deterministic coverage and discovery-latency audit for the news pipeline."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit

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


def _normalized_match_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", text)


def _normalized_url(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return ""
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return ""
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", ""))


_CANDIDATE_META = {
    "api_change": ("API 变更", "需要及时处理兼容性或迁移", 6, 0),
    "security": ("安全事件", "可能影响现有系统与数据安全", 6, 0),
    "model_release": ("模型发布", "官方高影响模型或版本发布", 12, 1),
    "open_source": ("重要开源", "官方开放可实践模型或权重", 24, 1),
    "high_impact": ("高影响官方事件", "重要性评分达到高影响阈值", 24, 2),
}


def build_benchmark_candidates(
    articles: list[dict],
    benchmarks: list[dict],
    *,
    now: datetime,
    lookback_days: int = 7,
    limit: int = 12,
) -> dict:
    """Suggest observed official events for human-confirmed benchmark registration."""
    cutoff = now - timedelta(days=lookback_days)
    registered_urls = {
        url for item in benchmarks if (url := _normalized_url(item.get("source_url")))
    }
    registered_keys = {
        str(item.get("event_key") or "").strip() for item in benchmarks
        if str(item.get("event_key") or "").strip()
    }
    ranked: list[tuple[int, int, float, str, dict]] = []
    for article in articles:
        published = _parse_date(article.get("date"))
        url = _normalized_url(article.get("url"))
        event_key = str(article.get("event_key") or "").strip()
        if (
            not published or published < cutoff or published > now + timedelta(hours=1)
            or not url or article.get("category") != "vendor" or article.get("tier") != "high"
            or url in registered_urls or (event_key and event_key in registered_keys)
        ):
            continue
        importance = _importance_value(article)
        kind = classify_alert(article) or ("high_impact" if importance >= 8 else None)
        if not kind:
            continue
        label, reason, deadline_hours, priority = _CANDIDATE_META[kind]
        title = " ".join(str(
            article.get("title_zh") or article.get("title") or "（无标题）"
        ).split())[:200]
        if len(title) < 3:
            continue
        discovered = _parse_date(article.get("ingested_at")) or published
        dedupe_key = event_key or _normalized_match_text(title)
        item = {
            "article_id": article.get("id"),
            "title": title,
            "occurred_at": published.isoformat(),
            "source_url": article.get("url") or "",
            "event_key": event_key,
            "match_terms": [],
            "deadline_hours": deadline_hours,
            "source": article.get("source") or "",
            "kind": kind,
            "label": label,
            "reason": reason,
            "importance": importance,
            "discovery_minutes": round(max(0, (discovered - published).total_seconds() / 60), 1),
        }
        ranked.append((priority, -importance, -published.timestamp(), dedupe_key, item))

    seen: set[str] = set()
    items: list[dict] = []
    for _, _, _, key, item in sorted(ranked, key=lambda row: row[:3]):
        if key in seen:
            continue
        seen.add(key)
        items.append(item)
        if len(items) >= limit:
            break
    return {"window_days": lookback_days, "total": len(items), "items": items}


def build_benchmark_coverage(
    articles: list[dict],
    benchmarks: list[dict],
    *,
    now: datetime,
    window_days: int = 30,
) -> dict:
    """Evaluate must-not-miss events against the current article library."""
    cutoff = now - timedelta(days=window_days)
    results: list[dict] = []
    for benchmark in benchmarks:
        occurred = _parse_date(benchmark.get("occurred_at"))
        if not occurred or occurred < cutoff or occurred > now + timedelta(hours=1):
            continue
        try:
            deadline_hours = int(benchmark.get("deadline_hours") or 24)
        except (TypeError, ValueError):
            deadline_hours = 24
        deadline_hours = max(1, min(168, deadline_hours))
        deadline = occurred + timedelta(hours=deadline_hours)
        source_url = _normalized_url(benchmark.get("source_url"))
        event_key = str(benchmark.get("event_key") or "").strip()
        terms = [
            normalized for term in (benchmark.get("match_terms") or [])
            if (normalized := _normalized_match_text(term))
        ]
        candidates: list[tuple[datetime, dict, str]] = []
        for article in articles:
            published = _parse_date(article.get("date"))
            if not published or not (occurred - timedelta(hours=24) <= published <= now + timedelta(hours=1)):
                continue
            method = ""
            if source_url and _normalized_url(article.get("url")) == source_url:
                method = "source_url"
            elif event_key and str(article.get("event_key") or "").strip() == event_key:
                method = "event_key"
            elif terms:
                haystack = _normalized_match_text(" ".join(str(article.get(field) or "") for field in (
                    "title", "title_zh", "summary", "summary_zh",
                )))
                if all(term in haystack for term in terms):
                    method = "match_terms"
            if not method:
                continue
            discovered = _parse_date(article.get("ingested_at")) or published
            candidates.append((discovered, article, method))

        matched_at: datetime | None = None
        matched_article: dict | None = None
        match_method = ""
        if candidates:
            matched_at, matched_article, match_method = min(candidates, key=lambda item: item[0])
            status = "on_time" if matched_at <= deadline else "late"
        else:
            status = "pending" if now <= deadline else "missed"
        latency = (
            round(max(0.0, (matched_at - occurred).total_seconds() / 60), 1)
            if matched_at else None
        )
        results.append({
            "id": benchmark.get("id"),
            "title": benchmark.get("title") or "（无标题）",
            "occurred_at": occurred.isoformat(),
            "deadline_at": deadline.isoformat(),
            "deadline_hours": deadline_hours,
            "source_url": str(benchmark.get("source_url") or ""),
            "match_terms": benchmark.get("match_terms") or [],
            "status": status,
            "matched_article": ({
                "id": matched_article.get("id"),
                "title": matched_article.get("title_zh") or matched_article.get("title") or "（无标题）",
                "url": matched_article.get("url") or "",
                "source": matched_article.get("source") or "",
            } if matched_article else None),
            "match_method": match_method or None,
            "discovery_minutes": latency,
        })

    results.sort(key=lambda item: _parse_date(item["occurred_at"]) or cutoff, reverse=True)
    settled = [item for item in results if item["status"] != "pending"]
    covered = [item for item in settled if item["status"] in {"on_time", "late"}]
    on_time = [item for item in settled if item["status"] == "on_time"]
    latencies = [
        float(item["discovery_minutes"]) for item in covered
        if item.get("discovery_minutes") is not None
    ]
    denominator = len(settled)
    return {
        "window_days": window_days,
        "total": len(results),
        "settled": denominator,
        "on_time": len(on_time),
        "late": sum(item["status"] == "late" for item in settled),
        "missed": sum(item["status"] == "missed" for item in settled),
        "pending": sum(item["status"] == "pending" for item in results),
        "on_time_recall_rate": round(len(on_time) / denominator, 3) if denominator else None,
        "coverage_rate": round(len(covered) / denominator, 3) if denominator else None,
        "median_discovery_minutes": _percentile(latencies, 0.5),
        "items": results,
        "missed_items": [item for item in results if item["status"] == "missed"][:8],
    }


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
    benchmarks: list[dict] | None = None,
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
    benchmark_coverage = build_benchmark_coverage(
        articles, benchmarks or [], now=current,
    )
    if benchmark_coverage["missed"]:
        add(
            "critical", "基准事件存在漏报",
            f"近 {benchmark_coverage['window_days']} 天有 {benchmark_coverage['missed']} 个必达事件超过期限仍未命中。",
        )
    elif benchmark_coverage["late"]:
        add(
            "watch", "基准事件发现偏慢",
            f"有 {benchmark_coverage['late']} 个必达事件在期限后才被发现。",
        )
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
        "benchmark_coverage": benchmark_coverage,
        "findings": findings,
    }
