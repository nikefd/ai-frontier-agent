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


def _nonnegative_int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


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
    "corroborated": ("多源佐证", "多个独立可信来源共同报道，建议检查官方源是否漏抓", 24, 2),
}


def build_benchmark_candidates(
    articles: list[dict],
    benchmarks: list[dict],
    *,
    now: datetime,
    lookback_days: int = 7,
    limit: int = 12,
) -> dict:
    """Suggest official or independently corroborated events for human review."""
    cutoff = now - timedelta(days=lookback_days)
    registered_urls = {
        url for item in benchmarks if (url := _normalized_url(item.get("source_url")))
    }
    registered_keys = {
        str(item.get("event_key") or "").strip() for item in benchmarks
        if str(item.get("event_key") or "").strip()
    }
    grouped: dict[str, list[tuple[dict, datetime, str, str | None]]] = {}
    for article in articles:
        published = _parse_date(article.get("date"))
        url = _normalized_url(article.get("url"))
        event_key = str(article.get("event_key") or "").strip()
        official = article.get("category") == "vendor" and article.get("tier") == "high"
        trusted_secondary = (
            article.get("category") in {"media", "expert", "blog"}
            and article.get("tier") in {"high", "med"}
        )
        importance = _importance_value(article)
        kind = classify_alert(article)
        if (
            not published or published < cutoff or published > now + timedelta(hours=1)
            or not url or not (official or trusted_secondary)
            or url in registered_urls or (event_key and event_key in registered_keys)
            or (official and not (kind or importance >= 8))
            or (trusted_secondary and importance < 8)
        ):
            continue
        title = article.get("title_zh") or article.get("title") or ""
        group_key = event_key or (_normalized_match_text(title) if official else "")
        if not group_key:
            continue
        grouped.setdefault(group_key, []).append((article, published, url, kind))

    ranked: list[tuple[int, int, float, str, dict]] = []
    for group_key, group in grouped.items():
        official_rows = [
            row for row in group
            if row[0].get("category") == "vendor" and row[0].get("tier") == "high"
        ]
        source_names = {
            str(article.get("source") or urlsplit(url).netloc).strip()
            for article, _, url, _ in group
        }
        if not official_rows and len(source_names) < 2:
            continue
        detected_kinds = [row[3] for row in group if row[3]]
        kind = (
            min(detected_kinds, key=lambda value: _CANDIDATE_META[value][3])
            if detected_kinds else ("high_impact" if official_rows else "corroborated")
        )
        representative_pool = official_rows or [row for row in group if row[3] == kind] or group
        representative = max(
            representative_pool,
            key=lambda row: (_importance_value(row[0]), -row[1].timestamp()),
        )
        article, _, _, _ = representative
        importance = max(_importance_value(row[0]) for row in group)
        label, reason, deadline_hours, priority = _CANDIDATE_META[kind]
        if not official_rows:
            reason = "多个独立可信来源共同报道，建议检查官方源是否漏抓"
        title = " ".join(str(
            article.get("title_zh") or article.get("title") or "（无标题）"
        ).split())[:200]
        if len(title) < 3:
            continue
        occurred = min(row[1] for row in group)
        discovered = min(_parse_date(row[0].get("ingested_at")) or row[1] for row in group)
        item = {
            "article_id": article.get("id"),
            "title": title,
            "occurred_at": occurred.isoformat(),
            "source_url": article.get("url") or "",
            "event_key": str(article.get("event_key") or "").strip(),
            "match_terms": [],
            "deadline_hours": deadline_hours,
            "source": article.get("source") or "",
            "kind": kind,
            "label": label,
            "reason": reason,
            "importance": importance,
            "discovery_mode": "official" if official_rows else "corroborated",
            "corroborating_sources": sorted(source_names, key=str.casefold),
            "discovery_minutes": round(max(0, (discovered - occurred).total_seconds() / 60), 1),
        }
        ranked.append((priority, -importance, -occurred.timestamp(), group_key, item))

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


def _benchmark_source(
    source_url: str,
    matched_article: dict | None,
    sources: list[dict],
) -> dict | None:
    article_source = str((matched_article or {}).get("source") or "")
    if article_source:
        exact = next((
            item for item in sources
            if item.get("name") == article_source and item.get("enabled") is not False
        ), None)
        if exact:
            return exact
    target_host = urlsplit(
        source_url or str((matched_article or {}).get("url") or "")
    ).hostname
    if not target_host:
        return None
    for source in sources:
        if source.get("enabled") is False:
            continue
        source_host = urlsplit(str(source.get("url") or "")).hostname
        if source_host and (
            source_host == target_host
            or source_host.endswith(f".{target_host}")
            or target_host.endswith(f".{source_host}")
        ):
            return source
    return None


def _has_partial_term_match(articles: list[dict], context: dict) -> bool:
    terms = context["terms"]
    if not terms:
        return False
    lower_bound = context["occurred"] - timedelta(hours=24)
    upper_bound = context["now"] + timedelta(hours=1)
    return any(
        lower_bound <= published <= upper_bound
        and any(term in _normalized_match_text(" ".join(
            str(article.get(field) or "")
            for field in ("title", "title_zh", "summary", "summary_zh")
        )) for term in terms)
        for article in articles
        if (published := _parse_date(article.get("date")))
    )


def _benchmark_diagnosis(
    context: dict,
    articles: list[dict],
    sources: list[dict],
) -> dict | None:
    status = context["status"]
    if status not in {"late", "missed"}:
        return None
    matched_article = context.get("matched_article")
    matched_at = context.get("matched_at")
    deadline = context["deadline"]
    source_url = context["source_url"]
    source = _benchmark_source(source_url, matched_article, sources)
    source_info = ({
        "name": source.get("name") or "",
        "url": source.get("url") or "",
        "health_status": source.get("health_status") or "never",
        "health_reason": source.get("health_reason") or "",
        "cadence": source.get("cadence") or "standard",
    } if source else None)
    if status == "late":
        published = _parse_date((matched_article or {}).get("date"))
        if published and published > deadline:
            code, label = "source_published_late", "源站晚于期限发布"
            detail = "匹配文章的发布时间已晚于基准期限，本站在发布后才可能发现。"
            action = "核对事件发生时间；若时间无误，增加更早的官方或可信旁路来源。"
        elif source and source.get("health_status") != "healthy":
            code, label = "source_unhealthy", "来源抓取异常"
            detail = f"匹配来源当前状态为 {source.get('health_status') or 'never'}：{source.get('health_reason') or '无详细原因'}。"
            action = "先修复该来源的抓取错误或调度过期，再复测发现延迟。"
        elif source and source.get("cadence") != "fast":
            code, label = "cadence_too_slow", "来源刷新层级偏慢"
            detail = f"文章在期限前已发布，但来源当前按 {source.get('cadence') or 'standard'} 层刷新。"
            action = "将该来源提升为 fast，或补充一个高时效官方入口。"
        else:
            code, label = "fetch_delay", "抓取或解析延迟"
            delay = round(max(0, ((matched_at or deadline) - deadline).total_seconds() / 60), 1)
            detail = f"文章在期限前已发布，但入库晚了约 {delay} 分钟。"
            action = "检查抓取日志、限流、解析器与单轮配额，确认延迟发生在哪一层。"
    elif source and source.get("health_status") != "healthy":
        code, label = "source_unhealthy", "来源抓取异常"
        detail = f"已配置来源当前状态为 {source.get('health_status') or 'never'}：{source.get('health_reason') or '无详细原因'}。"
        action = "修复来源连通性、解析器或调度后，重新抓取并复核该基准。"
    elif source:
        code, label = "parser_or_filter_gap", "解析或过滤漏掉事件"
        detail = "对应来源已配置且健康，但滚动文章库中没有命中记录。"
        action = "检查来源原始响应、路径选择器、发布日期识别、关键词过滤和抓取配额。"
    elif source_url:
        code, label = "source_not_configured", "官方来源尚未接入"
        detail = f"基准指向 {urlsplit(source_url).hostname or '未知域名'}，当前来源清单没有对应入口。"
        action = "验证该站点的 RSS、sitemap、changelog 或 API，并接入高时效来源。"
    else:
        if _has_partial_term_match(articles, context):
            code, label = "match_rule_gap", "匹配规则过严或已漂移"
            detail = "文章库存在部分关键词命中，但没有记录满足全部匹配条件。"
            action = "缩减或更新匹配词，优先补充稳定的官方 URL 或 event_key。"
        else:
            code, label = "coverage_gap", "当前来源集没有匹配记录"
            detail = "滚动文章库中没有发现可匹配该事件的文章。"
            action = "核对基准信号，并补充能持续覆盖该类事件的一手或交叉验证来源。"
    return {"code": code, "label": label, "detail": detail, "action": action, "source": source_info}


def build_benchmark_coverage(
    articles: list[dict],
    benchmarks: list[dict],
    *,
    now: datetime,
    sources: list[dict] | None = None,
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
        diagnosis = _benchmark_diagnosis(
            {
                "status": status,
                "matched_article": matched_article,
                "matched_at": matched_at,
                "occurred": occurred,
                "deadline": deadline,
                "now": now,
                "source_url": source_url,
                "terms": terms,
            },
            articles,
            sources or [],
        )
        remediation = benchmark.get("remediation")
        if not isinstance(remediation, dict):
            remediation = {}
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
            "diagnosis": diagnosis,
            "remediation": ({
                "status": str(remediation.get("status") or "open"),
                "outcome": remediation.get("outcome"),
                "updated_at": remediation.get("updated_at"),
                "last_recheck_at": remediation.get("last_recheck_at"),
                "last_recheck_added": remediation.get("last_recheck_added"),
            } if diagnosis else None),
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
    diagnosis_counts: dict[str, int] = {}
    for item in settled:
        code = str((item.get("diagnosis") or {}).get("code") or "")
        if code:
            diagnosis_counts[code] = diagnosis_counts.get(code, 0) + 1
    diagnosed = [item for item in settled if item.get("diagnosis")]
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
        "diagnosis_counts": diagnosis_counts,
        "open_issue_count": sum(
            (item.get("remediation") or {}).get("status") != "closed" for item in diagnosed
        ),
        "closed_issue_count": sum(
            (item.get("remediation") or {}).get("status") == "closed" for item in diagnosed
        ),
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
        if source.get("name") and not source.get("orphan") and source.get("enabled") is not False
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


def _source_noise_report(
    sources: list[dict],
    *,
    now: datetime,
    window_days: int = 7,
) -> dict:
    """Aggregate rolling fetch decisions without treating filtering as failure."""
    cutoff = now - timedelta(days=window_days)
    items: list[dict] = []
    for source in sources:
        if source.get("orphan") or source.get("enabled") is False:
            continue
        samples = []
        for sample in source.get("quality_samples") or []:
            if not isinstance(sample, dict):
                continue
            captured = _parse_date(sample.get("at"))
            if captured and cutoff <= captured <= now + timedelta(hours=1):
                samples.append(sample)
        if not samples:
            continue
        accepted = sum(_nonnegative_int(sample.get("accepted")) for sample in samples)
        filtered = sum(_nonnegative_int(sample.get("filtered")) for sample in samples)
        invalid = sum(_nonnegative_int(sample.get("invalid_date")) for sample in samples)
        judged = accepted + filtered
        parsed = accepted + filtered + invalid
        items.append({
            "name": source.get("name") or source.get("url") or "（未命名）",
            "category": source.get("category") or "other",
            "cadence": source.get("cadence") or "standard",
            "policy": source.get("quality_policy") or "default",
            "samples": len(samples),
            "parsed": parsed,
            "accepted": accepted,
            "filtered": filtered,
            "invalid_date": invalid,
            "noise_rate": round(filtered / judged, 3) if judged else None,
            "invalid_rate": round(invalid / parsed, 3) if parsed else None,
        })
    items.sort(key=lambda item: (
        -(item["noise_rate"] if item["noise_rate"] is not None else -1),
        -item["filtered"],
        item["name"],
    ))
    total_accepted = sum(item["accepted"] for item in items)
    total_filtered = sum(item["filtered"] for item in items)
    total_invalid = sum(item["invalid_date"] for item in items)
    total_judged = total_accepted + total_filtered
    total_parsed = total_judged + total_invalid
    possible_overfilter = [
        item for item in items
        if item["samples"] >= 2
        and item["accepted"] == 0
        and item["filtered"] >= 10
        and item["noise_rate"] == 1.0
    ]
    return {
        "window_days": window_days,
        "sampled_sources": len(items),
        "sample_count": sum(item["samples"] for item in items),
        "parsed": total_parsed,
        "accepted": total_accepted,
        "filtered": total_filtered,
        "invalid_date": total_invalid,
        "noise_rate": round(total_filtered / total_judged, 3) if total_judged else None,
        "invalid_rate": round(total_invalid / total_parsed, 3) if total_parsed else None,
        "noisiest_sources": [item for item in items if item["filtered"] > 0][:8],
        "possible_overfilter": possible_overfilter[:8],
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

    configured = [
        source for source in sources
        if not source.get("orphan") and source.get("enabled") is not False
    ]
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
        articles, benchmarks or [], now=current, sources=sources,
    )
    source_noise = _source_noise_report(sources, now=current)
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
    if source_noise["possible_overfilter"]:
        names = "、".join(
            item["name"] for item in source_noise["possible_overfilter"][:3]
        )
        add("watch", "来源门禁可能过严", f"{names} 在近 7 天有足够样本但全部被过滤，请复核关键词。")
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
        "source_noise": source_noise,
        "benchmark_coverage": benchmark_coverage,
        "findings": findings,
    }
