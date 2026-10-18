"""High-precision, zero-LLM alerts for time-sensitive AI events."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone


_MODEL_NAMES = re.compile(
    r"\b(gpt[-\s]?\w*|claude(?:[-\s]\w+)*|gemini(?:[-\s]\w+)*|grok(?:[-\s]\w+)*|"
    r"llama(?:[-\s]\w+)*|mistral(?:[-\s]\w+)*|deepseek(?:[-\s]\w+)*|qwen(?:[-\s]\w+)*)\b",
    re.IGNORECASE,
)
_RELEASE_WORDS = re.compile(
    r"\b(introduc(?:e|ing)|launch(?:ed|es|ing)?|releas(?:e|ed|es|ing)|announc(?:e|ed|es|ing)|"
    r"now available|generally available|ga\b)\b|发布|推出|上线",
    re.IGNORECASE,
)
_API_CHANGE = re.compile(
    r"\b(deprecat(?:e|ed|es|ing|ion)|sunset|retir(?:e|ed|es|ing)|end of support|"
    r"breaking change|migration required|remov(?:e|ed|al))\b|弃用|停止支持|迁移|重大变更",
    re.IGNORECASE,
)
_API_CONTEXT = re.compile(
    r"\b(api|sdk|endpoint|model|platform|developer|tool(?:s|ing)?)\b|接口|模型|平台|开发者",
    re.IGNORECASE,
)
_SECURITY = re.compile(
    r"\b(cve-\d{4}-\d+|zero[- ]day|security incident|data breach|remote code execution|"
    r"vulnerabilit(?:y|ies))\b|安全事件|数据泄露|远程代码执行|漏洞",
    re.IGNORECASE,
)
_OPEN_SOURCE = re.compile(
    r"\b(open[- ]sourc(?:e|ed|ing)|open weights?|weights? available|release[sd]? .*weights?)\b|"
    r"开源|开放权重",
    re.IGNORECASE,
)

_ALERT_META = {
    "api_change": ("API 变更", "critical", "可能需要迁移或调整现有集成"),
    "security": ("安全事件", "critical", "可能影响现有系统或数据安全"),
    "model_release": ("模型发布", "high", "官方发布了新的前沿模型或版本"),
    "open_source": ("重要开源", "high", "官方开放了可直接试用的模型或权重"),
}


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


def classify_alert(article: dict) -> str | None:
    """Classify only high-signal events; false negatives are preferable to noise."""
    text = " ".join(str(article.get(key) or "") for key in (
        "title", "title_zh", "summary", "summary_zh",
    ))
    category = str(article.get("category") or "")
    official = category == "vendor" and article.get("tier") == "high"

    if _API_CHANGE.search(text) and _API_CONTEXT.search(text) and official:
        return "api_change"
    if _SECURITY.search(text) and category in {"vendor", "media"}:
        return "security"
    if official and _MODEL_NAMES.search(text) and _RELEASE_WORDS.search(text):
        return "model_release"
    if official and _OPEN_SOURCE.search(text) and int(article.get("importance") or 0) >= 7:
        return "open_source"
    return None


def build_breaking_alerts(
    articles: list[dict],
    *,
    now: datetime | None = None,
    lookback_hours: int = 36,
    limit: int = 5,
) -> list[dict]:
    """Return recent, deduplicated alerts ordered by urgency and importance."""
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff = current - timedelta(hours=lookback_hours)
    ranked: list[tuple[int, int, float, str, dict]] = []

    for article in articles:
        published = _parse_date(article.get("date"))
        if not published or published < cutoff or published > current + timedelta(hours=1):
            continue
        kind = classify_alert(article)
        if not kind:
            continue
        label, severity, reason = _ALERT_META[kind]
        item = {
            "id": article.get("id"),
            "title": article.get("title_zh") or article.get("title") or "（无标题）",
            "source": article.get("source") or "",
            "url": article.get("url") or "",
            "date": article.get("date"),
            "kind": kind,
            "label": label,
            "severity": severity,
            "reason": reason,
        }
        urgency = 0 if severity == "critical" else 1
        dedupe_key = str(article.get("event_key") or "").strip()
        if not dedupe_key:
            dedupe_key = re.sub(
                r"[^a-z0-9\u4e00-\u9fff]+", "", str(item["title"]).lower()
            )
        ranked.append((
            urgency, -int(article.get("importance") or 0), -published.timestamp(),
            dedupe_key, item,
        ))

    seen: set[str] = set()
    alerts: list[dict] = []
    for _, _, _, key, item in sorted(ranked, key=lambda row: row[:3]):
        if key in seen:
            continue
        seen.add(key)
        alerts.append(item)
        if len(alerts) >= limit:
            break
    return alerts
