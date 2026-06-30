"""Personalized learning paths — a staged roadmap for a direction.

DISTINCT from `/guides/generate` (which writes one self-contained long-form
article on a single topic). A learning path is the *orchestration layer above*:
given a direction + the user's profile (to set the starting point), it sequences
several stages (foundation → intermediate → advanced), each pointing at what to
learn, which existing deep-dives/articles to read, and an optional exercise.

Hybrid material policy: stages prefer to reference real items from the user's
library (deep-dives + recent articles, fed to the LLM by id), but may also
suggest free-text "go read X-type content" when the library lacks coverage.

Split into its own module per the code-quality rules. Reuses profile signals,
ai_news loaders, and the tolerant-JSON parse pattern from reflection.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..llm_client import LLMUnavailable, chat_complete, llm_configured
from ..models import UserPublic
from ..auth import require_user, require_verified_user, require_llm_quota, current_user_optional
from ..settings import settings
from ..storage import read_json, write_json_atomic
from .ai_news import (
    _articles_for_today,
    _load_articles,
    deep_dives_dir,
    learning_paths_dir,
)
from .profile import _collect_profile_signals

router = APIRouter(prefix="/api/ai-news", tags=["learning"])

LEARNING_SYSTEM = (
    "你是一位 AI 学习路径规划师。给你一个学习方向、用户的兴趣画像，以及一份「可引用素材库」"
    "（用户已生成的深度解读 + 近期文章，带 id）。请编排一条**分阶段**的个性化学习路线。\n\n"
    "输出严格 JSON（不要 markdown 代码块包裹）：\n"
    '{"stages": [\n'
    '  {"title": "阶段名（如 阶段1·打基础）",\n'
    '   "goal": "这一阶段要达到什么（一句话）",\n'
    '   "learn": ["要点1", "要点2", "要点3"],\n'
    '   "read": [{"ref": "<素材库里的 id，没有合适的就省略这条>", "note": "为什么读它"}],\n'
    '   "suggest": "库里没有合适素材时，用一句话建议去读什么类型的内容（可空）",\n'
    '   "practice": "可选的动手练习（可空）"}\n'
    "]}\n\n"
    "硬性要求：\n"
    "- 3-5 个阶段，由浅入深、有明确顺序。\n"
    "- **根据画像调整起点**：用户已熟悉的子领域，跳过或快速带过；没接触过的，从基础讲起。\n"
    "- read 里的 ref **必须**是素材库里真实存在的 id；找不到合适的就不放 read、改用 suggest 文字建议。**绝不编造 id**。\n"
    "- 中文；技术术语保留英文；不写客套话。"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _material_library(uid: str) -> tuple[list[dict], dict]:
    """Build the reference pool the LLM may cite, plus an id→meta lookup.

    Pool = the user's deep-dives + recent global articles. Each entry carries a
    stable ref id so generated stages can link back to real content.
    """
    pool: list[dict] = []
    lookup: dict = {}

    ddir = deep_dives_dir(uid)
    if ddir.exists():
        for p in ddir.glob("*.json"):
            d = read_json(p, None)
            if not isinstance(d, dict):
                continue
            aid = d.get("article_id") or p.stem
            title = d.get("article_title_zh") or d.get("article_title") or ""
            if not title:
                continue
            ref = f"dive:{aid}"
            pool.append({"ref": ref, "kind": "deep-dive", "title": title})
            lookup[ref] = {"type": "deep-dive", "id": aid, "title": title,
                           "url": d.get("article_url")}

    for a in _articles_for_today(limit=30):
        aid = a.get("id")
        title = a.get("title_zh") or a.get("title") or ""
        if not aid or not title:
            continue
        ref = f"article:{aid}"
        pool.append({"ref": ref, "kind": "article", "title": title})
        lookup[ref] = {"type": "article", "id": aid, "title": title, "url": a.get("url")}

    return pool[:50], lookup


def _build_prompt(topic: str, signals: dict, pool: list[dict]) -> str:
    cats = "、".join(f"{k}×{v}" for k, v in sorted(
        (signals.get("categories") or {}).items(), key=lambda kv: kv[1], reverse=True))
    tags = "、".join(signals.get("top_tags") or [])
    pool_lines = "\n".join(f"- [{m['ref']}] ({m['kind']}) {m['title']}" for m in pool) or "（素材库为空）"
    return (
        f"学习方向：{topic}\n\n"
        f"用户画像：高频标签 = {tags or '（无）'}；收藏来源分布 = {cats or '（无）'}\n\n"
        f"可引用素材库（read 的 ref 只能从这里选）：\n{pool_lines}\n\n"
        "请编排分阶段学习路径。"
    )


def _resolve_reads(stages: list, lookup: dict) -> list:
    """Replace each stage's read[].ref with the real item meta; drop fabricated ids."""
    clean = []
    for s in stages:
        if not isinstance(s, dict):
            continue
        reads = []
        for r in (s.get("read") or []):
            ref = r.get("ref") if isinstance(r, dict) else None
            meta = lookup.get(ref)
            if meta:
                reads.append({**meta, "note": (r.get("note") if isinstance(r, dict) else "") or ""})
        clean.append({
            "title": str(s.get("title", "")).strip(),
            "goal": str(s.get("goal", "")).strip(),
            "learn": [str(x).strip() for x in (s.get("learn") or []) if str(x).strip()],
            "read": reads,
            "suggest": str(s.get("suggest", "")).strip(),
            "practice": str(s.get("practice", "")).strip(),
        })
    return clean


def _parse_stages(raw: str) -> list:
    s = (raw or "").strip()
    if s.startswith("```"):
        s = s[s.find("{"):]
    try:
        obj = json.loads(s[s.find("{"): s.rfind("}") + 1])
        stages = obj.get("stages")
        return stages if isinstance(stages, list) else []
    except Exception:
        return []


class PathGenRequest(BaseModel):
    topic: str


@router.get("/learning-paths/suggestions")
def suggest_directions(user: UserPublic | None = Depends(current_user_optional)) -> dict:
    """Suggested learning directions from the user's profile — zero LLM cost.

    Combines subscribed tracks (explicit intent) with top tags (behavioral
    interest), deduped, so the user can pick instead of staring at a blank box.
    """
    if not user:
        return {"items": []}
    signals = _collect_profile_signals(user.id)
    seen, items = set(), []
    # Tracks first (explicit intent), then top tags (behavioral signal).
    for src in (signals.get("tracks") or [], signals.get("top_tags") or []):
        for d in src:
            key = d.strip().lower()
            if d.strip() and key not in seen:
                seen.add(key)
                items.append(d.strip())
    return {"items": items[:8]}


@router.get("/learning-paths")
def list_paths(user: UserPublic | None = Depends(current_user_optional)) -> dict:
    if not user:
        return {"total": 0, "items": []}
    pdir = learning_paths_dir(user.id)
    items = []
    if pdir.exists():
        for p in pdir.glob("*.json"):
            d = read_json(p, None)
            if isinstance(d, dict):
                items.append({"slug": d.get("slug"), "topic": d.get("topic"),
                              "stage_count": len(d.get("stages") or []),
                              "generated_at": d.get("generated_at")})
    items.sort(key=lambda x: x.get("generated_at") or "", reverse=True)
    return {"total": len(items), "items": items}


@router.get("/learning-paths/{slug}")
def get_path(slug: str, user: UserPublic | None = Depends(current_user_optional)) -> dict:
    if not user:
        return {"status": "none"}
    p = learning_paths_dir(user.id) / f"{slug}.json"
    d = read_json(p, None)
    if not isinstance(d, dict):
        raise HTTPException(404, "path not found")
    return {"status": "ok", **d}


@router.delete("/learning-paths/{slug}")
def delete_path(slug: str, user: UserPublic = Depends(require_user)) -> dict:
    p = learning_paths_dir(user.id) / f"{slug}.json"
    if not p.exists():
        raise HTTPException(404, "path not found")
    p.unlink()
    return {"ok": True}


@router.post("/learning-paths/generate")
async def generate_path(req: PathGenRequest, user: UserPublic = Depends(require_llm_quota)) -> dict:
    topic = (req.topic or "").strip()
    if not topic:
        raise HTTPException(400, "topic is required")
    if not llm_configured():
        raise HTTPException(503, "LLM not configured")

    signals = _collect_profile_signals(user.id)
    pool, lookup = _material_library(user.id)

    messages = [
        {"role": "system", "content": LEARNING_SYSTEM},
        {"role": "user", "content": _build_prompt(topic, signals, pool)},
    ]
    try:
        raw = await chat_complete(messages, max_tokens=2000, temperature=0.5)
    except LLMUnavailable as e:
        raise HTTPException(503, str(e))

    stages = _resolve_reads(_parse_stages(raw), lookup)
    if not stages:
        raise HTTPException(502, "生成失败：模型未返回有效路径，请重试")

    slug = "path_" + hashlib.sha1((topic + _now_iso()).encode()).hexdigest()[:10]
    payload = {
        "slug": slug, "topic": topic,
        "generated_at": _now_iso(), "model": settings.llm_model,
        "based_on_profile": bool(signals.get("top_tags") or signals.get("categories")),
        "stages": stages,
    }
    pdir = learning_paths_dir(user.id)
    pdir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(pdir / f"{slug}.json", payload)
    return {"status": "ok", **payload}
