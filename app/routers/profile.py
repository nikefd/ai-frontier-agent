"""Personal profile: aggregate a user's intent signals into an LLM portrait.

Split out of ``ai_news.py`` to keep that module focused. Reuses ai_news' shared
loaders / path helpers (the same way workers and agent_tools do) so the storage
logic stays single-sourced. Endpoints live under the ``/api/ai-news`` prefix to
keep the public URL stable.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..auth import current_user_optional, require_user
from ..llm_client import LLMUnavailable, chat_complete, llm_configured
from ..models import UserPublic
from ..settings import settings
from ..storage import read_json, sqlite_ro, write_json_atomic
from .ai_news import (
    _load_articles,
    _load_pins,
    _load_tracks,
    _now_iso,
    deep_dives_dir,
    profile_path,
    user_dir,
)

router = APIRouter(prefix="/api/ai-news", tags=["profile"])

PROFILE_SYSTEM = (
    "你是一名 AI 信息策展助手。我会给你某个用户在一个 AI 前沿资讯站上的行为信号"
    "（收藏的文章、生成过深度解读的主题、订阅的追踪主题、和助手聊过的话题）。"
    "请据此推断这位用户的关注画像，用中文输出一段 Markdown。\n\n"
    "硬性结构（按顺序，用下列标题层级）：\n"
    "## 一句话画像\n"
    "  用一句话概括这位用户是谁、关注什么。\n"
    "## 关注领域\n"
    "  - 列出 3-6 个具体子领域（如 推理优化 / Agent 编排 / 多模态），每条后跟一句依据。\n"
    "## 技术栈倾向\n"
    "  从信号里推断偏工程落地还是偏研究/论文，偏厂商动态还是偏社区实践。\n"
    "## 活跃度\n"
    "  根据各信号数量给一句客观描述（不夸大）。\n"
    "## 推荐关注\n"
    "  - 基于已有兴趣，建议 3 条值得新增追踪的主题或方向。\n\n"
    "风格要求：\n"
    "- 结论先行，关键词加粗；句子短，不写客套话\n"
    "- 只根据给到的信号推断，信号稀少时如实说明、不要编造\n"
    "- 技术术语保留英文（LLM, RAG, Agent, ...）\n"
    "- 全文 400-800 字"
)


def _conversation_titles(uid: str, limit: int = 30) -> list[str]:
    """Read the user's recent conversation titles from their ui.db (read-only).

    Avoids importing agent_chat (which would create a circular import via
    agent_tools → ai_news). Missing/empty db yields an empty list.
    """
    db = user_dir(uid) / "ui.db"
    titles: list[str] = []
    try:
        with sqlite_ro(db) as conn:
            rows = conn.execute(
                "SELECT title FROM conversations ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            titles = [r["title"] for r in rows if r["title"] and r["title"] != "New chat"]
    except Exception:
        # Table may not exist yet for a user who never chatted.
        return []
    return titles


def _collect_profile_signals(uid: str) -> dict:
    """Aggregate the user's intent signals for portrait generation."""
    articles_by_id = {a.get("id"): a for a in _load_articles()}

    pinned_ids = _load_pins(uid)
    pinned: list[dict] = []
    tag_counts: dict[str, int] = {}
    cat_counts: dict[str, int] = {}
    for aid in pinned_ids:
        a = articles_by_id.get(aid)
        if not a:
            continue
        pinned.append({
            "title": a.get("title_zh") or a.get("title"),
            "category": a.get("category"),
            "tags": a.get("tags") or [],
        })
        for t in (a.get("tags") or []):
            tag_counts[t] = tag_counts.get(t, 0) + 1
        cat = a.get("category")
        if cat:
            cat_counts[cat] = cat_counts.get(cat, 0) + 1

    dives: list[str] = []
    ddir = deep_dives_dir(uid)
    if ddir.exists():
        for p in ddir.glob("*.json"):
            data = read_json(p, None)
            if isinstance(data, dict):
                dives.append(data.get("article_title_zh") or data.get("article_title") or "")
    dives = [d for d in dives if d]

    tracks = [t.get("title") or t.get("name") or "" for t in _load_tracks(uid)]
    tracks = [t for t in tracks if t]

    conversations = _conversation_titles(uid)

    top_tags = sorted(tag_counts.items(), key=lambda kv: kv[1], reverse=True)[:12]
    return {
        "counts": {
            "pins": len(pinned),
            "deep_dives": len(dives),
            "tracks": len(tracks),
            "conversations": len(conversations),
        },
        "pinned": pinned[:40],
        "top_tags": [t for t, _ in top_tags],
        "categories": cat_counts,
        "deep_dive_topics": dives[:40],
        "tracks": tracks,
        "conversation_topics": conversations,
    }


def _build_profile_prompt(signals: dict) -> str:
    c = signals["counts"]
    cats_str = "、".join(f"{k}×{v}" for k, v in sorted(
        signals["categories"].items(), key=lambda kv: kv[1], reverse=True))
    return (
        f"信号统计：收藏 {c['pins']} 篇 / 深度解读 {c['deep_dives']} 篇 / "
        f"追踪主题 {c['tracks']} 个 / 对话 {c['conversations']} 段\n\n"
        f"收藏文章标题：\n" + "\n".join(f"- {p['title']}" for p in signals["pinned"]) + "\n\n"
        f"高频标签：{('、'.join(signals['top_tags'])) or '（无）'}\n"
        f"收藏来源分布：{cats_str or '（无）'}\n\n"
        f"生成过深度解读的主题：\n" + "\n".join(f"- {t}" for t in signals["deep_dive_topics"]) + "\n\n"
        f"订阅的追踪主题：{('、'.join(signals['tracks'])) or '（无）'}\n\n"
        f"和助手聊过的话题：\n" + "\n".join(f"- {t}" for t in signals["conversation_topics"]) + "\n\n"
        "请基于以上信号生成关注画像。"
    )


@router.get("/profile")
def get_profile(user: UserPublic | None = Depends(current_user_optional)) -> dict:
    """Return the current user's cached portrait, or {status:"none"}."""
    if not user:
        return {"status": "none"}
    data = read_json(profile_path(user.id), None)
    if not isinstance(data, dict) or not data.get("body"):
        return {"status": "none"}
    return {"status": "ok", **data}


@router.post("/profile")
async def generate_profile(user: UserPublic = Depends(require_user)) -> dict:
    """Generate (or regenerate) the current user's interest portrait via LLM.

    Aggregates pins / deep-dives / tracks / conversation titles, asks the LLM for
    a structured Markdown portrait, and caches it to ``users/<uid>/profile.json``.
    """
    if not llm_configured():
        raise HTTPException(503, "LLM not configured")

    signals = _collect_profile_signals(user.id)
    c = signals["counts"]
    if c["pins"] + c["deep_dives"] + c["conversations"] == 0:
        raise HTTPException(400, "数据不足：先 pin 几篇文章、生成深度解读或和助手聊几句，再生成画像")

    messages = [
        {"role": "system", "content": PROFILE_SYSTEM},
        {"role": "user", "content": _build_profile_prompt(signals)},
    ]
    try:
        body = await chat_complete(messages, max_tokens=1500, temperature=0.5)
    except LLMUnavailable as e:
        raise HTTPException(503, str(e))

    payload = {
        "generated_at": _now_iso(),
        "model": settings.llm_model,
        "signals": c,
        "body": body,
    }
    write_json_atomic(profile_path(user.id), payload)
    return {"status": "ok", **payload}
