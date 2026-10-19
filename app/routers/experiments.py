"""Per-user, on-demand experiment cards for actionable news articles.

Cards turn an editorial ``hands_on`` hint into a small, verifiable practice:
time box, prerequisites, steps, success criteria, cost/risk, trusted links and
a persistent progress note. Generation is intentionally opt-in so routine feed
refreshes do not spend LLM quota.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import current_user_optional, require_user, require_verified_user
from ..llm_client import LLMUnavailable, chat_complete, llm_configured
from ..models import UserPublic
from ..settings import settings
from ..storage import read_json, update_json_atomic, write_json_atomic
from .ai_news import _load_articles, experiments_dir

router = APIRouter(prefix="/api/ai-news", tags=["experiments"])

EXPERIMENT_SYSTEM = """你是严谨的 AI 实验设计师。把给定文章转为一个短小、可验证、可真正动手的实验卡。
只使用输入中明确给出的事实和链接；不得编造命令、API 名、模型能力、仓库地址或费用。材料没有精确命令时，写“按原文 Quickstart 操作”。
输出严格 JSON，不要 markdown 代码块：
{
  "title": "实验标题",
  "goal": "本次要验证什么",
  "duration_minutes": 15,
  "difficulty": "入门",
  "prerequisites": ["前置条件"],
  "official_links": [{"label": "原文或官方资料", "url": "输入中出现的完整 URL"}],
  "steps": [{"title": "步骤名", "action": "具体动作", "expected": "预期观察"}],
  "success_criteria": ["可判断的成功标准"],
  "cost": "时间、算力或付费说明；未知就明确写未知",
  "risks": ["隐私、费用、兼容性或误用风险"]
}
要求：15/30/60 分钟；3-5 步；中文；每步都能执行并观察结果；范围要小，默认先做最小可行实验。"""

_URL_RE = re.compile(r"https?://[^\s<>\]\[\"']+")
_DURATIONS = (15, 30, 60)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _article(aid: str) -> dict:
    article = next((a for a in _load_articles() if a.get("id") == aid), None)
    if not article:
        raise HTTPException(404, "article not found")
    return article


def _allowed_links(article: dict) -> list[str]:
    links: list[str] = []
    for value in (article.get("url"), article.get("summary"), article.get("summary_zh"), article.get("hands_on")):
        if not value:
            continue
        candidates = [str(value)] if str(value).startswith(("http://", "https://")) else _URL_RE.findall(str(value))
        for url in candidates:
            clean = url.rstrip(".,;:!?)，。；：！？）")
            parsed = urlsplit(clean)
            if parsed.scheme in {"http", "https"} and parsed.netloc and clean not in links:
                links.append(clean)
    return links


def _parse_payload(raw: str) -> dict:
    text = (raw or "").strip()
    try:
        return json.loads(text[text.find("{"): text.rfind("}") + 1])
    except (json.JSONDecodeError, ValueError):
        return {}


def _text(value, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _text_list(value, *, count: int, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item, limit) for item in value[:count] if _text(item, limit)]


def _sanitize_card(raw: dict, article: dict) -> dict:
    """Bound model output and discard every link absent from source material."""
    allowed = _allowed_links(article)
    links, seen = [], set()
    for item in raw.get("official_links") or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip().rstrip("/")
        match = next((candidate for candidate in allowed if candidate.rstrip("/") == url), None)
        if match and match not in seen:
            seen.add(match)
            links.append({"label": _text(item.get("label"), 40) or "官方资料", "url": match})
    source_url = str(article.get("url") or "").strip()
    if source_url in allowed and source_url not in seen:
        links.insert(0, {"label": "原文", "url": source_url})

    steps = []
    for item in (raw.get("steps") or [])[:5]:
        if not isinstance(item, dict):
            continue
        action = _text(item.get("action"), 280)
        if action:
            steps.append({
                "title": _text(item.get("title"), 60) or f"步骤 {len(steps) + 1}",
                "action": action,
                "expected": _text(item.get("expected"), 220),
            })

    try:
        requested_duration = int(raw.get("duration_minutes") or 15)
    except (TypeError, ValueError):
        requested_duration = 15
    duration = min(_DURATIONS, key=lambda x: abs(x - requested_duration))
    difficulty = _text(raw.get("difficulty"), 10)
    if difficulty not in {"入门", "进阶"}:
        difficulty = "入门"
    return {
        "title": _text(raw.get("title"), 100),
        "goal": _text(raw.get("goal"), 300),
        "duration_minutes": duration,
        "difficulty": difficulty,
        "prerequisites": _text_list(raw.get("prerequisites"), count=5, limit=120),
        "official_links": links[:4],
        "steps": steps,
        "success_criteria": _text_list(raw.get("success_criteria"), count=4, limit=180),
        "cost": _text(raw.get("cost"), 240),
        "risks": _text_list(raw.get("risks"), count=4, limit=180),
    }


def _prompt(article: dict, allowed: list[str]) -> str:
    return (
        f"标题：{article.get('title_zh') or article.get('title') or ''}\n"
        f"摘要：{article.get('summary_zh') or article.get('summary') or ''}\n"
        f"编辑实践建议：{article.get('hands_on') or ''}\n"
        f"标签：{'、'.join(article.get('tags') or [])}\n"
        f"允许引用的 URL（只能原样选用）：{json.dumps(allowed, ensure_ascii=False)}\n"
        "请生成结构化实验卡。"
    )


class GenerateRequest(BaseModel):
    force: bool = False


class ExperimentUpdate(BaseModel):
    status: Literal["planned", "in_progress", "completed"] | None = None
    note: str | None = Field(default=None, max_length=4000)


@router.get("/experiments")
def list_experiments(user: UserPublic | None = Depends(current_user_optional)) -> dict:
    if not user:
        return {"total": 0, "items": []}
    items = []
    edir = experiments_dir(user.id)
    if edir.exists():
        for path in edir.glob("*.json"):
            data = read_json(path, None)
            if isinstance(data, dict):
                items.append(data)
    items.sort(key=lambda x: x.get("updated_at") or x.get("generated_at") or "", reverse=True)
    return {"total": len(items), "items": items}


@router.get("/articles/{aid}/experiment")
def get_experiment(aid: str, user: UserPublic | None = Depends(current_user_optional)) -> dict:
    if not user:
        return {"status": "none"}
    data = read_json(experiments_dir(user.id) / f"{aid}.json", None)
    return {"status": "none"} if not isinstance(data, dict) else {"status": "ok", **data}


@router.post("/articles/{aid}/experiment")
async def generate_experiment(
    aid: str,
    req: GenerateRequest,
    user: UserPublic = Depends(require_verified_user),
) -> dict:
    path = experiments_dir(user.id) / f"{aid}.json"
    existing = read_json(path, None)
    if isinstance(existing, dict) and not req.force:
        return {"status": "ok", **existing}
    article = _article(aid)
    if not str(article.get("hands_on") or "").strip():
        raise HTTPException(400, "这篇文章暂不适合生成实验卡")
    if not llm_configured():
        raise HTTPException(503, "LLM not configured")
    # Existing cards are returned for free above. Count quota only when this
    # request is actually about to call the model (admins remain exempt).
    if user.role != "admin":
        from ..usage import consume_quota
        if not consume_quota(user.id):
            raise HTTPException(429, "今日 AI 使用额度已用完，请明天再试")
    try:
        raw = await chat_complete(
            [{"role": "system", "content": EXPERIMENT_SYSTEM},
             {"role": "user", "content": _prompt(article, _allowed_links(article))}],
            max_tokens=1800,
            temperature=0.3,
        )
    except LLMUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    card = _sanitize_card(_parse_payload(raw), article)
    if not card["title"] or not card["goal"] or len(card["steps"]) < 3 or not card["success_criteria"]:
        raise HTTPException(502, "生成失败：模型未返回完整实验卡，请重试")
    now = _now_iso()
    payload = {
        "article_id": aid,
        "article_title": article.get("title_zh") or article.get("title") or "",
        "article_url": article.get("url") or "",
        "source": article.get("source") or "",
        "generated_at": existing.get("generated_at", now) if isinstance(existing, dict) else now,
        "updated_at": now,
        "model": settings.llm_model,
        "status": existing.get("status", "planned") if isinstance(existing, dict) else "planned",
        "note": existing.get("note", "") if isinstance(existing, dict) else "",
        **card,
    }
    write_json_atomic(path, payload)
    return {"status": "ok", **payload}


@router.patch("/articles/{aid}/experiment")
def update_experiment(
    aid: str,
    req: ExperimentUpdate,
    user: UserPublic = Depends(require_user),
) -> dict:
    path = experiments_dir(user.id) / f"{aid}.json"
    if not path.exists():
        raise HTTPException(404, "experiment not found")

    def mutate(data):
        if not isinstance(data, dict):
            raise HTTPException(404, "experiment not found")
        if req.status is not None:
            data["status"] = req.status
        if req.note is not None:
            data["note"] = req.note.strip()
        data["updated_at"] = _now_iso()
        return data

    payload = update_json_atomic(path, {}, mutate)
    return {"status": "ok", **payload}
