"""AI front-line news / track / guide agent.

Storage (compat with openclaw-deploy `~/agent-data/ai-news/`):
  <data_dir>/ai-news/articles.json   list of Article dicts (cap 500)
  <data_dir>/ai-news/tracks.json     list of Track dicts (user-defined)
  <data_dir>/ai-news/guides.json     list of Guide dicts (notes / "动手试试")
  <data_dir>/ai-news/reader-cache/*.html (best-effort readability cache)

The fetcher worker (app.scheduler.fetch_ai_news) appends new articles via
the same atomic JSON helpers we use here, so concurrency is safe.
"""
from __future__ import annotations

import hashlib
import logging
import re
import secrets
import unicodedata
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel, Field

from ..auth import current_user_optional, require_admin, require_user, require_verified_user, require_llm_quota
from ..llm_client import LLMUnavailable, chat_complete, chat_stream, llm_configured
from ..models import Article, ChatRequest, Guide, Track, UserPublic
from ..settings import settings
from ..safe_fetch import UnsafeUrl, fetch_public_html, sanitize_reader_html
from ..storage import read_json, update_json_atomic, write_json_atomic, write_text_atomic

log = logging.getLogger("aif.ai_news")

router = APIRouter(prefix="/api/ai-news", tags=["ai-news"])

AINEWS_DIR = settings.data_dir / "ai-news"
# ── Global, shared by everyone ──────────────────────────────────────
ARTICLES_FILE = AINEWS_DIR / "articles.json"
SOURCES_FILE = AINEWS_DIR / "sources.json"  # per-feed fetch metadata
SUMMARY_FILE = AINEWS_DIR / "summary_today.json"  # cached "today" summary
READER_CACHE = AINEWS_DIR / "reader-cache"

# ── Per-user artifacts: <data_dir>/users/<uid>/… ────────────────────
# These used to be module-level constants under ai-news/; they are now keyed by
# the logged-in user. Callers (routers / agent_tools) resolve them with a uid.
USERS_DIR = settings.data_dir / "users"


def user_dir(uid: str) -> Path:
    return USERS_DIR / uid


def tracks_file(uid: str) -> Path:
    return user_dir(uid) / "tracks.json"


def pins_file(uid: str) -> Path:
    return user_dir(uid) / "pins.json"


def guides_file(uid: str) -> Path:
    return user_dir(uid) / "guides.json"


def guides_dir(uid: str) -> Path:
    return user_dir(uid) / "guides"


def deep_dives_dir(uid: str) -> Path:
    return user_dir(uid) / "deep-dives"

def profile_path(uid: str) -> Path:
    return user_dir(uid) / "profile.json"

def review_cards_file(uid: str) -> Path:
    return user_dir(uid) / "review-cards.json"

def reflection_file(uid: str) -> Path:
    return user_dir(uid) / "reflection.json"

def learning_paths_dir(uid: str) -> Path:
    return user_dir(uid) / "learning-paths"

_ARTICLE_LIMIT = 400    # rolling history cap (pinned articles are protected)
_DAILY_FETCH_CAP = 150  # hard per-fetch global ceiling
_PER_FEED_CAP = 4       # first-pass max per feed (ensures source diversity)

# Hard ceilings keep discovery channels from overwhelming first-party news and
# substantive analysis.  The values intentionally add up to the global cap.
_CATEGORY_FETCH_CAPS: dict[str, int] = {
    "vendor": 38,
    "media": 20,
    "blog": 16,
    "paper": 22,
    "community": 18,
    "expert": 18,
    "x-ai": 12,
    "trending": 6,
}

_DEFAULT_TIER_BY_CATEGORY = {
    "vendor": "high",
    "blog": "high",
    "expert": "high",
    "media": "med",
    "paper": "med",
    "community": "med",
    "x-ai": "low",
    "trending": "low",
}


# ── Defaults seed ───────────────────────────────────────────────────
DEFAULT_TRACKS: list[dict] = [
    {
        "id": "t_llm",
        "name": "大模型 & 训练",
        "keywords": ["LLM", "训练", "推理", "RLHF", "MoE"],
        "sources": [],
    },
    {
        "id": "t_agent",
        "name": "Agent / 工具调用",
        "keywords": ["Agent", "tool use", "MCP", "function calling"],
        "sources": [],
    },
    {
        "id": "t_infra",
        "name": "AI Infra",
        "keywords": ["推理优化", "vLLM", "GPU", "Triton"],
        "sources": [],
    },
]

# ── RSS feed registry ─────────────────────────────────────────────
# Source categories drive both UI grouping and ingestion quotas. Tiers are
# normalized by category below: first-party/editorial sources rank ahead of
# discovery sources, while X and Trending must also pass keyword relevance.
#   vendor / media / blog / paper / community / expert / x-ai / trending
DEFAULT_FEED_SPECS: list[dict] = [
    # ── vendor: 官方实验室/厂商
    {"url": "https://www.anthropic.com/sitemap.xml", "name": "Anthropic News & Research", "tier": "high", "category": "vendor", "format": "sitemap", "include_paths": ["/news/", "/research/"], "description": "Anthropic 官方新闻与研究 · 模型、产品、研究与安全发布"},
    {"url": "https://rsshub.app/github/file/anthropics/claude-code/main/CHANGELOG.md", "name": "Claude Code CHANGELOG", "tier": "high", "category": "vendor", "description": "AI 官方源 · 实验室/厂商第一手发布"},
    {"url": "https://api.xgo.ing/rss/user/01f60d63a61b44d692cc35c7feb0b4a4", "name": "Claude(@claudeai)", "tier": "high", "category": "vendor", "description": "AI 官方源 · 实验室/厂商第一手发布"},
    {"url": "https://rsshub.app/deepseek/news", "name": "DeepSeek 新闻", "tier": "high", "category": "vendor", "description": "AI 官方源 · 实验室/厂商第一手发布"},
    {"url": "https://github.blog/changelog/feed/", "name": "GitHub Changelog", "tier": "high", "category": "vendor", "description": "GitHub 产品 changelog · Copilot/Actions 新功能上线公告"},
    {"url": "https://deepmind.google/blog/rss.xml", "name": "Google DeepMind", "tier": "high", "category": "vendor", "description": "DeepMind 博客 · AlphaFold、Gemini、强化学习、AI 安全等前沿研究"},
    {"url": "https://blog.research.google/feeds/posts/default?alt=rss", "name": "Google Research", "tier": "high", "category": "vendor", "description": "Google Research 博客 · Gemini 之外的基础研究和长文"},
    {"url": "https://huggingface.co/blog/feed.xml", "name": "Hugging Face Blog", "tier": "high", "category": "vendor", "description": "HF 官方博客 · 开源模型、Transformers/Diffusers 库、社区工程实践"},
    {"url": "https://www.microsoft.com/en-us/research/feed/", "name": "Microsoft Research", "tier": "high", "category": "vendor", "description": "微软研究院 · Phi 系列、Azure AI、系统级研究"},
    {"url": "https://blogs.nvidia.com/feed/", "name": "NVIDIA Blog", "tier": "high", "category": "vendor", "description": "英伟达企业博客 · GPU、CUDA、AI 行业动态"},
    {"url": "https://developer.nvidia.com/blog/feed", "name": "NVIDIA Developer", "tier": "high", "category": "vendor", "description": "NVIDIA 开发者博客 · 推理优化、TensorRT、CUDA kernel 等工程实战"},
    {"url": "https://api.xgo.ing/rss/user/971dc1fc90da449bac23e5fad8a33d55", "name": "OpenAI Developers(@OpenAIDevs)", "tier": "high", "category": "vendor", "description": "AI 官方源 · 实验室/厂商第一手发布"},
    {"url": "https://openai.com/news/rss.xml", "name": "OpenAI News", "tier": "high", "category": "vendor", "description": "AI 官方源 · 实验室/厂商第一手发布"},
    {"url": "https://machinelearning.apple.com/rss.xml", "name": "Apple Machine Learning Research", "tier": "high", "category": "vendor", "description": "Apple 机器学习研究 · Foundation Models、端侧 AI 与隐私研究"},
    {"url": "https://aws.amazon.com/blogs/machine-learning/feed/", "name": "AWS Machine Learning Blog", "tier": "high", "category": "vendor", "description": "AWS 官方机器学习博客 · 模型、Agent、云端推理与工程实践"},
    {"url": "https://cohere.com/sitemap.xml", "name": "Cohere Blog", "tier": "high", "category": "vendor", "format": "sitemap", "include_paths": ["/blog/"], "description": "Cohere 官方博客 · 企业模型、检索、Agent 与研究发布"},
    {"url": "https://mistral.ai/sitemap.xml", "name": "Mistral News", "tier": "high", "category": "vendor", "format": "sitemap", "include_paths": ["/news/"], "description": "Mistral 官方新闻 · 开源模型、Le Chat、Agent 与工程发布"},
    {"url": "https://x.ai/sitemap.xml", "name": "xAI News", "tier": "high", "category": "vendor", "format": "sitemap", "include_paths": ["/news/"], "description": "xAI 官方新闻 · Grok 模型、API、研究与安全发布"},
    {"url": "https://qwen.ai/api/v2/article/retrieval?type=qwen_ai&language=en-US", "name": "Qwen Blog", "tier": "high", "category": "vendor", "format": "qwen_api", "description": "Qwen 官方博客 · 通义千问模型、开源权重与多模态发布"},
    {"url": "https://allenai.org/rss.xml", "name": "Ai2 Research", "tier": "high", "category": "vendor", "description": "Ai2 官方研究 · OLMo、开放模型、科学智能与可信评测"},
    # ── media: AI 媒体
    {"url": "https://arstechnica.com/ai/feed/", "name": "Ars Technica AI", "tier": "high", "category": "media", "description": "Ars Technica AI · 技术深度评测，重视一手数据和复盘"},
    {"url": "https://www.technologyreview.com/topic/artificial-intelligence/feed", "name": "MIT Tech Review AI", "tier": "high", "category": "media", "description": "MIT Tech Review · 长篇深度报道与影响分析"},
    {"url": "https://techcrunch.com/category/artificial-intelligence/feed/", "name": "TechCrunch AI", "tier": "high", "category": "media", "description": "TechCrunch AI · 创业公司、投资、产品发布快讯"},
    {"url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "name": "The Verge AI", "tier": "high", "category": "media", "description": "Verge AI 栏目 · 科技媒体视角，重点关注产品发布和行业大事"},
    {"url": "https://venturebeat.com/category/ai/feed/", "name": "VentureBeat AI", "tier": "high", "category": "media", "description": "VentureBeat AI · 企业级 AI、融资、商业落地新闻"},
    # ── blog: AI 博客(原)
    {"url": "https://karpathy.github.io/feed.xml", "name": "Andrej Karpathy", "tier": "high", "category": "blog", "description": "Karpathy 个人博客 · 从零写 LLM、micrograd、教学性内容"},
    {"url": "https://www.latent.space/feed", "name": "Latent Space", "tier": "high", "category": "blog", "description": "Latent Space 播客博客 · swyx 与 Alessio 的 AI 工程师播客与短文"},
    {"url": "https://lilianweng.github.io/index.xml", "name": "Lilian Weng", "tier": "high", "category": "blog", "description": "OpenAI Lilian Weng 个人博客 · agent / hallucination / safety 级综述长文"},
    {"url": "https://magazine.sebastianraschka.com/feed", "name": "Sebastian Raschka", "tier": "high", "category": "blog", "description": "Raschka 通讯 · LLM 内部机制、训练 trick、技术综述"},
    {"url": "https://simonwillison.net/atom/everything/", "name": "Simon Willison", "tier": "high", "category": "blog", "description": "Simon Willison 博客 · LLM 工具评测、prompt 技巧、每日观察"},
    {"url": "https://bair.berkeley.edu/blog/feed.xml", "name": "Berkeley AI Research", "tier": "high", "category": "blog", "description": "Berkeley AI Research 官方博客 · 学术前沿、系统与机器人研究"},
    # ── paper: arXiv 论文
    {"url": "http://export.arxiv.org/rss/cs.AI", "name": "arXiv cs.AI", "tier": "high", "category": "paper", "description": "arXiv 人工智能类目（规划、知识表示、智能体）"},
    {"url": "http://export.arxiv.org/rss/cs.CL", "name": "arXiv cs.CL", "tier": "high", "category": "paper", "description": "arXiv 计算语言学（NLP/LLM 论文主战场）"},
    {"url": "http://export.arxiv.org/rss/cs.CV", "name": "arXiv cs.CV", "tier": "high", "category": "paper", "description": "arXiv 计算机视觉类目（多模态 / 图像生成相关论文）"},
    {"url": "http://export.arxiv.org/rss/cs.LG", "name": "arXiv cs.LG", "tier": "high", "category": "paper", "description": "arXiv 机器学习类目（覆盖训练、优化、新架构论文）"},
    # ── community: 社区/周刊
    {"url": "https://quaily.com/op7418/feed/atom", "name": "AIGC Weekly", "tier": "high", "category": "community", "description": "AI 社区/周刊 · 聚合精选与中文资讯"},
    {"url": "https://justlovemaki.github.io/CloudFlare-AI-Insight-Daily/rss.xml", "name": "AI资讯日报 RSS Feed", "tier": "high", "category": "community", "description": "AI 社区/周刊 · 聚合精选与中文资讯"},
    {"url": "https://aigc-weekly.agi.li/rss.xml", "name": "Agili 的 AIGC 周刊", "tier": "high", "category": "community", "description": "AI 社区/周刊 · 聚合精选与中文资讯"},
    {"url": "https://www.bestblogs.dev/en/feeds/rss?category=ai&minScore=90", "name": "BestBlogs.dev - Artificial Intelligence ", "tier": "high", "category": "community", "description": "AI 社区/周刊 · 聚合精选与中文资讯"},
    {"url": "https://hnrss.org/newest?q=AI+OR+LLM+OR+GPT+OR+Claude+OR+Gemini", "name": "HN: AI keyword", "tier": "high", "category": "community", "description": "Hacker News AI 关键词搜索流 · 杂噪较高但覆盖广，靠相关性过滤"},
    {"url": "https://www.reddit.com/r/LocalLLaMA/.rss", "name": "r/LocalLLaMA", "tier": "high", "category": "community", "description": "Reddit 本地大模型社区 · 开源权重、量化、推理硬件经验"},
    {"url": "https://www.reddit.com/r/MachineLearning/.rss", "name": "r/MachineLearning", "tier": "high", "category": "community", "description": "Reddit ML 社区 · 论文讨论、招聘、求建议帖"},
    {"url": "https://sanhua.himrr.com/daily-news/feed", "name": "三花 AI 快讯", "tier": "high", "category": "community", "description": "AI 社区/周刊 · 聚合精选与中文资讯"},
    {"url": "https://wechat2rss.bestblogs.dev/feed/484d4199ae6c0b72ea01e7e0597a1f74933dfb62.xml", "name": "刘小排r", "tier": "high", "category": "community", "description": "AI 社区/周刊 · 聚合精选与中文资讯"},
    {"url": "https://rsshub.app/yuque/wikidesign/vngzgk", "name": "大厂AI实践", "tier": "high", "category": "community", "description": "AI 社区/周刊 · 聚合精选与中文资讯"},
    {"url": "https://rss.zslren.com/mp/feed/c849b842170d59c6820e070ae18ba18152041c38.xml", "name": "数字生命卡兹克", "tier": "high", "category": "community", "description": "AI 社区/周刊 · 聚合精选与中文资讯"},
    {"url": "https://quaily.com/ameow/feed/atom", "name": "猫鱼周刊", "tier": "high", "category": "community", "description": "AI 社区/周刊 · 聚合精选与中文资讯"},
    # ── expert: AI 专家博客
    {"url": "https://gwern.substack.com/feed", "name": "Gwern.net Newsletter", "tier": "high", "category": "expert", "description": "AI 专家博客 · 个人深度文章与综述"},
    {"url": "https://sunocean.life/blog/feed.xml", "name": "NoteAI", "tier": "high", "category": "expert", "description": "AI 专家博客 · 个人深度文章与综述"},
    {"url": "https://www.dwarkesh.com/feed", "name": "dwarkesh.com", "tier": "high", "category": "expert", "description": "AI 专家博客 · 个人深度文章与综述"},
    {"url": "https://garymarcus.substack.com/feed", "name": "garymarcus.substack.com", "tier": "high", "category": "expert", "description": "AI 专家博客 · 个人深度文章与综述"},
    {"url": "https://geohot.github.io/blog/feed.xml", "name": "geohot.github.io", "tier": "high", "category": "expert", "description": "AI 专家博客 · 个人深度文章与综述"},
    {"url": "https://minimaxir.com/index.xml", "name": "minimaxir.com", "tier": "high", "category": "expert", "description": "AI 专家博客 · 个人深度文章与综述"},
    {"url": "https://www.wheresyoured.at/rss/", "name": "wheresyoured.at", "tier": "high", "category": "expert", "description": "AI 专家博客 · 个人深度文章与综述"},
    {"url": "https://worksonmymachine.ai/feed", "name": "worksonmymachine.substack.com", "tier": "high", "category": "expert", "description": "AI 专家博客 · 个人深度文章与综述"},
    {"url": "https://s.baoyu.io/feed.xml", "name": "宝玉的分享", "tier": "high", "category": "expert", "description": "AI 专家博客 · 个人深度文章与综述"},
    # ── x-ai: X 上的 AI 大V
    {"url": "https://api.xgo.ing/rss/user/341f7b9f8d9b477e8bb200caa7f32c6e", "name": "AK(@_akhaliq)", "tier": "high", "category": "x-ai", "description": "X(Twitter) AI 大V · 一线从业者短观点"},
    {"url": "https://rsshub.app/twitter/user/aaditsh", "name": "Aadit Sheth", "tier": "high", "category": "x-ai", "description": "X(Twitter) AI 大V · 一线从业者短观点"},
    {"url": "https://rsshub.app/twitter/user/alexalbert__", "name": "Alex Albert", "tier": "high", "category": "x-ai", "description": "X(Twitter) AI 大V · 一线从业者短观点"},
    {"url": "https://rsshub.app/twitter/user/karpathy", "name": "Andrej Karpathy", "tier": "high", "category": "x-ai", "description": "X(Twitter) AI 大V · 一线从业者短观点"},
    {"url": "https://api.xgo.ing/rss/user/08b5488b20bc437c8bfc317a52e5c26d", "name": "Andrew Ng(@AndrewYNg)", "tier": "high", "category": "x-ai", "description": "X(Twitter) AI 大V · 一线从业者短观点"},
    {"url": "https://rsshub.app/twitter/user/heybarsee", "name": "Barsee 🐶", "tier": "high", "category": "x-ai", "description": "X(Twitter) AI 大V · 一线从业者短观点"},
    {"url": "https://rss.app/feeds/83CQGxSgKZmSqKb5.xml", "name": "Ethan Mollick (@emollick)", "tier": "high", "category": "x-ai", "description": "X(Twitter) AI 大V · 一线从业者短观点"},
    {"url": "https://rsshub.app/twitter/user/gregisenberg", "name": "GREG ISENBERG", "tier": "high", "category": "x-ai", "description": "X(Twitter) AI 大V · 一线从业者短观点"},
    {"url": "https://rsshub.app/twitter/user/hamelhusain", "name": "Hamel Husain", "tier": "high", "category": "x-ai", "description": "X(Twitter) AI 大V · 一线从业者短观点"},
    {"url": "https://api.xgo.ing/rss/user/f299207df53745bca04a03db8d11c5aa", "name": "Harrison Chase(@hwchase17)", "tier": "high", "category": "x-ai", "description": "X(Twitter) AI 大V · 一线从业者短观点"},
    {"url": "https://rsshub.app/twitter/user/DrJimFan", "name": "Jim Fan", "tier": "high", "category": "x-ai", "description": "X(Twitter) AI 大V · 一线从业者短观点"},
    {"url": "https://rsshub.app/twitter/user/mckaywrigley", "name": "Mckay Wrigley", "tier": "high", "category": "x-ai", "description": "X(Twitter) AI 大V · 一线从业者短观点"},
    {"url": "https://rsshub.app/twitter/user/itspaulai", "name": "Paul Couvert", "tier": "high", "category": "x-ai", "description": "X(Twitter) AI 大V · 一线从业者短观点"},
    {"url": "https://rsshub.app/twitter/user/steipete", "name": "Peter Steinberger 🦞", "tier": "high", "category": "x-ai", "description": "X(Twitter) AI 大V · 一线从业者短观点"},
    {"url": "https://rsshub.app/twitter/user/petergyang", "name": "Peter Yang", "tier": "high", "category": "x-ai", "description": "X(Twitter) AI 大V · 一线从业者短观点"},
    {"url": "https://rsshub.app/twitter/user/rileybrown_ai", "name": "Riley Brown", "tier": "high", "category": "x-ai", "description": "X(Twitter) AI 大V · 一线从业者短观点"},
    {"url": "https://rsshub.app/twitter/user/goodside", "name": "Riley Goodside", "tier": "high", "category": "x-ai", "description": "X(Twitter) AI 大V · 一线从业者短观点"},
    {"url": "https://rsshub.app/twitter/user/rowancheung", "name": "Rowan Cheung", "tier": "high", "category": "x-ai", "description": "X(Twitter) AI 大V · 一线从业者短观点"},
    {"url": "https://api.xgo.ing/rss/user/e30d4cd223f44bed9d404807105c8927", "name": "Sam Altman(@sama)", "tier": "high", "category": "x-ai", "description": "X(Twitter) AI 大V · 一线从业者短观点"},
    {"url": "https://api.xgo.ing/rss/user/30ad80be93c84e44acc37d5ddf31db57", "name": "Simon Willison(@simonw)", "tier": "high", "category": "x-ai", "description": "X(Twitter) AI 大V · 一线从业者短观点"},
    {"url": "https://rsshub.app/twitter/user/jackfriks", "name": "jack friks", "tier": "high", "category": "x-ai", "description": "X(Twitter) AI 大V · 一线从业者短观点"},
    {"url": "https://rsshub.app/twitter/user/vasumanmoza", "name": "vas", "tier": "high", "category": "x-ai", "description": "X(Twitter) AI 大V · 一线从业者短观点"},
    {"url": "https://rsshub.app/twitter/user/hesamation", "name": "ℏεsam", "tier": "high", "category": "x-ai", "description": "X(Twitter) AI 大V · 一线从业者短观点"},
    {"url": "https://rsshub.app/twitter/user/lxfater", "name": "铁锤人", "tier": "high", "category": "x-ai", "description": "X(Twitter) AI 大V · 一线从业者短观点"},
    # ── trending: GitHub 风向
    {"url": "https://mshibanami.github.io/GitHubTrendingRSS/daily/all.xml", "name": "GH Trending · All", "tier": "high", "category": "trending", "description": "GitHub 每日热门仓库 · 全语言榜，社区在用什么的风向标"},
]

# Keep the registry readable while ensuring category policy cannot silently
# drift because a newly added entry copied an old tier value.
for _spec in DEFAULT_FEED_SPECS:
    _spec["tier"] = _DEFAULT_TIER_BY_CATEGORY.get(_spec.get("category"), "med")

# Rewrite the public rsshub.app host to the configured (possibly self-hosted)
# instance. Done once here so DEFAULT_FEEDS, FEED_SPEC_BY_URL and everything
# downstream consistently use the resolved host.
if settings.rsshub_base and settings.rsshub_base.rstrip("/") != "https://rsshub.app":
    _rsshub = settings.rsshub_base.rstrip("/")
    for _spec in DEFAULT_FEED_SPECS:
        if _spec["url"].startswith("https://rsshub.app"):
            _spec["url"] = _spec["url"].replace("https://rsshub.app", _rsshub, 1)

DEFAULT_FEEDS: list[str] = [f["url"] for f in DEFAULT_FEED_SPECS]
# Quick lookup by url
FEED_SPEC_BY_URL: dict[str, dict] = {f["url"]: f for f in DEFAULT_FEED_SPECS}


# ── AI relevance keyword allowlist ─────────────────────────────────
# Articles that match any of these (case-insensitive, in title or summary)
# pass the relevance filter without LLM consultation.
AI_KEYWORDS: tuple[str, ...] = (
    # core terms
    "llm", "gpt", "claude", "gemini", "mistral", "llama", "deepseek", "qwen",
    "anthropic", "openai", "huggingface", "hugging face", "cohere", "perplexity",
    # techniques
    "agent", "agentic", "rag", "fine-tun", "finetun", "lora", "qlora", "dpo", "rlhf", "ppo",
    "prompt engineer", "tool use", "function call", "mcp", "model context protocol",
    "transformer", "attention", "embedding", "vector db", "retrieval",
    "diffusion", "stable diffusion", "image generation", "text-to-image", "text-to-video",
    "speech recognition", "tts", "asr", " whisper",
    # infra / training
    "vllm", "sglang", "triton", "cuda", "rocm", "tensorrt", "onnx", "ggml", "gguf",
    "quantiz", "distillation", "speculative decoding", "kv cache",
    "pretrain", "post-train", "instruct tun", "reinforcement learning",
    # ecosystem
    "langchain", "llamaindex", "dspy", "autogen", "crewai",
    "copilot", "codex", "cursor",
    # general AI/ML
    "machine learning", "deep learning", "neural net", "foundation model", "multimodal",
    "ai safety", "ai policy", "alignment", "interpretability",
    # cn
    "大模型", "人工智能", "推理优化", "微调", "智能体",
)


def _is_ai_relevant_keywords(title: str, summary: str) -> bool:
    """Cheap keyword pre-filter. Returns True if any AI keyword hits."""
    hay = (title + " " + summary).lower()
    return any(kw in hay for kw in AI_KEYWORDS)


# ── Helpers ────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _article_id(url: str) -> str:
    return "a_" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def _load_articles() -> list[dict]:
    data = read_json(ARTICLES_FILE, [])
    return data if isinstance(data, list) else []


def _load_tracks(uid: str) -> list[dict]:
    data = read_json(tracks_file(uid), None)
    if data is None or not isinstance(data, list):
        # New users get the default tracking topics seeded once.
        def seed(current):
            return current if isinstance(current, list) else list(DEFAULT_TRACKS)

        return update_json_atomic(tracks_file(uid), list(DEFAULT_TRACKS), seed)
    return data


def _load_guides(uid: str) -> list[dict]:
    data = read_json(guides_file(uid), [])
    return data if isinstance(data, list) else []


# ── Per-user pins (article ids) ─────────────────────────────────────
def _load_pins(uid: str) -> set[str]:
    data = read_json(pins_file(uid), [])
    return set(data) if isinstance(data, list) else set()


def _all_pinned_ids() -> set[str]:
    """Union of every user's pinned article ids — used to protect pinned
    articles from the global rolling-history eviction."""
    ids: set[str] = set()
    if not USERS_DIR.exists():
        return ids
    for d in USERS_DIR.iterdir():
        if not d.is_dir():
            continue
        data = read_json(d / "pins.json", [])
        if isinstance(data, list):
            ids.update(data)
    return ids


def _overlay_user_state(articles: list[dict], uid: str | None) -> None:
    """Stamp per-user `pinned` + `deep_dive_status` onto article dicts for the
    response. These are NOT persisted to the global articles.json (pins live in
    the user's pins.json; deep-dives in the user's deep-dives/)."""
    pins = _load_pins(uid) if uid else set()
    ddir = deep_dives_dir(uid) if uid else None
    for a in articles:
        aid = a.get("id")
        a["pinned"] = aid in pins
        if ddir is not None and aid and (ddir / f"{aid}.json").exists():
            a["deep_dive_status"] = "ok"
            a["deep_dive_id"] = aid
        else:
            a["deep_dive_status"] = None
            a["deep_dive_id"] = None


# ── Articles ───────────────────────────────────────────────────────
@router.get("/articles")
def list_articles(
    q: str | None = None,
    pinned_only: bool = False,
    tier: str | None = None,
    category: str | None = None,
    tag: str | None = None,
    sort: str = "newest",
    offset: int = 0,
    limit: int = 20,
    user: UserPublic | None = Depends(current_user_optional),
) -> dict:
    """Paginated article listing.

    Returns ``{total, offset, limit, items}``. The article store is global, but
    each item is stamped with the current user's `pinned` / `deep_dive_status`
    (anonymous users see everything unpinned). The legacy flat-list response was
    retired in favor of explicit pagination metadata so the always-on feed can
    render page controls.
    """
    uid = user.id if user else None
    articles = _load_articles()
    _overlay_user_state(articles, uid)
    if pinned_only:
        articles = [a for a in articles if a.get("pinned")]
    if q:
        ql = q.lower()
        articles = [
            a for a in articles
            if ql in (a.get("title", "").lower() + a.get("summary", "").lower())
            or ql in (a.get("title_zh") or "").lower()
            or ql in (a.get("summary_zh") or "").lower()
        ]
    if tier:
        wanted = {t.strip() for t in tier.split(",") if t.strip()}
        articles = [a for a in articles if (a.get("tier") or "med") in wanted]
    if category:
        wanted_c = {c.strip() for c in category.split(",") if c.strip()}
        # Resolve each article's category: prefer the field stored on the
        # article; fall back to the feed spec keyed by source name.
        cat_by_name = {s.get("name"): s.get("category") for s in DEFAULT_FEED_SPECS}
        articles = [
            a for a in articles
            if (a.get("category") or cat_by_name.get(a.get("source")) or "") in wanted_c
        ]
    if tag:
        wanted_t = {t.strip() for t in tag.split(",") if t.strip()}
        articles = [a for a in articles if wanted_t & set(a.get("tags") or [])]
    # Sort. Pinned articles are NOT bubbled to the top in the feed — collections
    # have their own "收藏" tab (pinned_only). Keeping them pinned-to-top here
    # would let a growing collection crowd out new content. They keep a ★ marker
    # but otherwise sort like everything else.
    if sort == "important":
        # Highest importance first; unscored (None) sink to the bottom; date breaks ties.
        articles.sort(key=lambda a: (
            -(a.get("importance") if a.get("importance") is not None else -1),
            -(_parse_ts(a.get("date") or "")),
        ))
    else:
        articles.sort(key=lambda a: -(_parse_ts(a.get("date") or "")))
    total = len(articles)
    offset = max(0, offset)
    limit = max(1, min(limit, 100))
    items = articles[offset : offset + limit]
    return {"total": total, "offset": offset, "limit": limit, "items": items}


def _parse_ts(ts: str) -> float:
    if not ts:
        return 0.0
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        try:
            parsed = parsedate_to_datetime(ts)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()
        except (TypeError, ValueError, OverflowError):
            return 0.0


@router.post("/articles", dependencies=[Depends(require_admin)])
def add_article(article: Article) -> dict:
    """Manual add — for openclaw-compat write API and for the fetcher worker."""
    aid = article.id or _article_id(article.url)
    result = {"ok": True, "id": aid}

    def mutate(data):
        articles = data if isinstance(data, list) else []
        if any(a.get("id") == aid or a.get("url") == article.url for a in articles):
            result["duplicate"] = True
            return articles
        payload = article.model_dump()
        payload["id"] = aid
        payload["date"] = payload.get("date") or _now_iso()
        for k in ("pinned", "deep_dive_status", "deep_dive_id"):
            payload.pop(k, None)
        articles.insert(0, payload)
        if len(articles) > _ARTICLE_LIMIT:
            protected = _all_pinned_ids()
            kept_pinned = [a for a in articles if a.get("id") in protected]
            rest = [a for a in articles if a.get("id") not in protected][:_ARTICLE_LIMIT - len(kept_pinned)]
            return kept_pinned + rest
        return articles

    update_json_atomic(ARTICLES_FILE, [], mutate)
    return result


@router.delete("/articles/{aid}", dependencies=[Depends(require_admin)])
def delete_article(aid: str) -> dict:
    def mutate(data):
        articles = data if isinstance(data, list) else []
        kept = [a for a in articles if a.get("id") != aid]
        if len(kept) == len(articles):
            raise HTTPException(404, "article not found")
        return kept

    update_json_atomic(ARTICLES_FILE, [], mutate)
    return {"ok": True}


@router.post("/articles/{aid}/pin")
def toggle_pin(aid: str, user: UserPublic = Depends(require_user)) -> dict:
    """Toggle the current user's pin on an article (stored in their pins.json,
    not on the global article record)."""
    if not any(a.get("id") == aid for a in _load_articles()):
        raise HTTPException(404, "article not found")
    result = {"pinned": False}

    def mutate(data):
        pins = set(data) if isinstance(data, list) else set()
        if aid in pins:
            pins.discard(aid)
        else:
            pins.add(aid)
            result["pinned"] = True
        return sorted(pins)

    update_json_atomic(pins_file(user.id), [], mutate)
    return {"ok": True, **result}


@router.get("/reader/{aid}", response_class=HTMLResponse)
async def reader(aid: str) -> HTMLResponse:
    """Best-effort article reader: try cache, else proxy fetch."""
    article = next((a for a in _load_articles() if a.get("id") == aid), None)
    if not article:
        raise HTTPException(404, "article not found")
    READER_CACHE.mkdir(parents=True, exist_ok=True)
    cache_file = READER_CACHE / f"{aid}.html"
    if cache_file.exists():
        cached_html = cache_file.read_text(encoding="utf-8")
        if "<!-- aif-safe-reader-v2 -->" in cached_html[:100]:
            safe_html = cached_html
        else:
            safe_html = sanitize_reader_html(cached_html, article["url"])
            write_text_atomic(cache_file, safe_html)
        return HTMLResponse(safe_html)
    try:
        raw_html, final_url = await fetch_public_html(article["url"])
        safe_html = sanitize_reader_html(raw_html, final_url)
    except UnsafeUrl as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: broad-except
        log.warning("reader fetch failed for article %s: %s", aid, e)
        return HTMLResponse("<h1>无法抓取</h1><p>原站暂时不可用。</p>", status_code=502)
    write_text_atomic(cache_file, safe_html)
    return HTMLResponse(safe_html)


# ── Tracks ─────────────────────────────────────────────────────────
@router.get("/tracks")
def list_tracks(user: UserPublic | None = Depends(current_user_optional)) -> list[dict]:
    if not user:
        return []
    return _load_tracks(user.id)


@router.put("/tracks")
def put_tracks(tracks: list[Track], user: UserPublic = Depends(require_user)) -> dict:
    payload = [t.model_dump() for t in tracks]
    for t in payload:
        if not t.get("id"):
            t["id"] = "t_" + secrets.token_hex(4)
    write_json_atomic(tracks_file(user.id), payload)
    return {"ok": True, "count": len(payload)}


# ── Guides ─────────────────────────────────────────────────────────
@router.get("/guides")
def list_guides(user: UserPublic | None = Depends(current_user_optional)) -> list[dict]:
    if not user:
        return []
    return _load_guides(user.id)


@router.post("/guides")
def add_guide(guide: Guide, user: UserPublic = Depends(require_user)) -> dict:
    payload = guide.model_dump()
    payload["id"] = payload.get("id") or "g_" + secrets.token_hex(4)
    payload["updated_at"] = _now_iso()
    def upsert(data):
        guides = data if isinstance(data, list) else []
        for i, saved in enumerate(guides):
            if saved.get("id") == payload["id"]:
                guides[i] = payload
                break
        else:
            guides.insert(0, payload)
        return guides

    update_json_atomic(guides_file(user.id), [], upsert)
    return {"ok": True, "id": payload["id"]}


@router.delete("/guides/{gid}")
def delete_guide(gid: str, user: UserPublic = Depends(require_user)) -> dict:
    def remove(data):
        guides = data if isinstance(data, list) else []
        new = [g for g in guides if g.get("id") != gid]
        if len(new) == len(guides):
            raise HTTPException(404, "guide not found")
        return new

    update_json_atomic(guides_file(user.id), [], remove)
    return {"ok": True}


# ── Fetcher trigger ────────────────────────────────────────────────
@router.post("/fetch", dependencies=[Depends(require_admin)])
async def trigger_fetch() -> dict:
    from ..workers.ai_news_fetcher import fetch_once  # local import to avoid cycle
    added = await fetch_once()
    return {"ok": True, "added": added}


# ── AI chat about a track / article ────────────────────────────────
SYSTEM_PROMPT = (
    "你是一个紧跟 AI 前沿的资深研究员，帮用户消化最近的 AI 资讯与论文。\n"
    "回答要求：\n"
    "1. 直奔重点，避免营销词；用「这是什么 / 为什么重要 / 怎么动手」三段式\n"
    "2. 如果用户问到具体项目，给出可执行的体验路径（pip install / colab / demo URL）\n"
    "3. 中文回复，技术词汇保留英文。"
)


@router.post("/chat", dependencies=[Depends(require_llm_quota)])
async def chat(req: ChatRequest):
    if not llm_configured():
        raise HTTPException(503, "LLM not configured")
    arts = _load_articles()[:10]
    ctx_lines = [
        f"- [{a.get('source')}] {a.get('title')} ({a.get('url')})"
        for a in arts if not a.get("pinned")
    ][:8]
    pinned = [a for a in arts if a.get("pinned")][:5]
    if pinned:
        ctx_lines.append("\n固定关注:")
        for a in pinned:
            ctx_lines.append(f"- ⭐ [{a.get('source')}] {a.get('title')} ({a.get('url')})")
    context = "\n".join(ctx_lines) or "(尚无文章数据)"
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"近期文章:\n{context}"},
        {"role": "user", "content": req.message},
    ]
    if req.stream:
        async def gen():
            try:
                async for delta in chat_stream(messages):
                    yield delta
            except LLMUnavailable as e:
                yield f"\n[error: {e}]"
        return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")
    try:
        reply = await chat_complete(messages)
    except LLMUnavailable as e:
        raise HTTPException(503, str(e))
    return {"reply": reply}


# ── Sources (data feeds) ───────────────────────────────────────────
def _load_sources_meta() -> dict[str, dict]:
    """Per-feed metadata (last_fetch / last_ok / counts).  Worker updates this."""
    data = read_json(SOURCES_FILE, {})
    return data if isinstance(data, dict) else {}


def _save_sources_meta(meta: dict[str, dict]) -> None:
    write_json_atomic(SOURCES_FILE, meta)


@router.get("/sources")
def list_sources() -> list[dict]:
    """List configured RSS feeds with their last-fetch state.

    Returned shape (also used by the UI 'sources' tab):
        [
          {url, enabled, name, last_fetch, last_ok, last_error,
           article_count, last_added}
        ]
    """
    meta = _load_sources_meta()
    articles = _load_articles()
    # count articles per source (group by canonical source title from articles)
    counts: dict[str, int] = {}
    for a in articles:
        counts[a.get("source", "?")] = counts.get(a.get("source", "?"), 0) + 1

    out = []
    for spec in DEFAULT_FEED_SPECS:
        url = spec["url"]
        m = meta.get(url, {})
        name = m.get("name") or spec.get("name") or url
        out.append({
            "url": url,
            "name": name,
            "tier": spec.get("tier") or m.get("tier"),
            "category": spec.get("category") or m.get("category"),
            "description": spec.get("description") or "",
            "enabled": True,
            "last_fetch": m.get("last_fetch"),
            "last_ok": m.get("last_ok"),
            "last_error": m.get("last_error"),
            "last_added": m.get("last_added", 0),
            "last_filtered": m.get("last_filtered", 0),
            "article_count": counts.get(name, 0),
        })
    # Also surface "orphan" sources — articles present without a tracked URL
    tracked_names = {s["name"] for s in out}
    for name, c in counts.items():
        if name not in tracked_names:
            out.append({
                "url": "", "name": name, "enabled": False,
                "tier": None, "category": None,
                "last_fetch": None, "last_ok": None, "last_error": None,
                "last_added": 0, "last_filtered": 0, "article_count": c,
                "orphan": True,
            })
    return out


# ── Today's summary (LLM) ──────────────────────────────────────────
def _today_iso_date() -> str:
    return datetime.now(timezone.utc).astimezone().date().isoformat()


_SUMMARY_CATEGORY_CAPS: dict[str, int] = {
    "vendor": 8,
    "media": 5,
    "blog": 4,
    "paper": 5,
    "community": 4,
    "expert": 4,
    "x-ai": 3,
    "trending": 2,
}


def _article_category(article: dict) -> str:
    if article.get("category"):
        return str(article["category"])
    by_name = {s.get("name"): s.get("category") for s in DEFAULT_FEED_SPECS}
    return str(by_name.get(article.get("source")) or "community")


def _summary_rank(article: dict) -> tuple[int, int, int, float]:
    """Editorial rank: model importance, source class, tier, then freshness."""
    importance = article.get("importance")
    if not isinstance(importance, int):
        importance = 5
    category_quality = {
        "vendor": 4, "blog": 3, "expert": 3, "paper": 2,
        "media": 2, "community": 1, "x-ai": 0, "trending": 0,
    }
    tier_quality = {"high": 2, "med": 1, "low": 0}
    return (
        importance,
        category_quality.get(_article_category(article), 1),
        tier_quality.get(article.get("tier") or "med", 1),
        _parse_ts(article.get("date") or ""),
    )


def _headline_key(article: dict) -> str:
    """Conservative exact-title key across case, spacing, and punctuation."""
    title = str(article.get("title_zh") or article.get("title") or "")
    normalized = unicodedata.normalize("NFKC", title).casefold()
    return re.sub(r"[^\w]+", "", normalized, flags=re.UNICODE)


def _dedupe_summary_articles(articles: list[dict]) -> list[dict]:
    """Collapse exact syndicated headlines, preferring the primary source."""
    category_quality = {
        "vendor": 4, "blog": 3, "expert": 3, "paper": 2,
        "media": 2, "community": 1, "x-ai": 0, "trending": 0,
    }
    by_headline: dict[str, dict] = {}
    without_title: list[dict] = []
    for article in articles:
        key = _headline_key(article)
        if not key:
            without_title.append(article)
            continue
        current = by_headline.get(key)
        authority = (
            category_quality.get(_article_category(article), 1),
            _summary_rank(article),
        )
        if current is None:
            by_headline[key] = article
            continue
        current_authority = (
            category_quality.get(_article_category(current), 1),
            _summary_rank(current),
        )
        if authority > current_authority:
            by_headline[key] = article
    return list(by_headline.values()) + without_title


def _select_summary_cohort(articles: list[dict], limit: int) -> list[dict]:
    """Build a quality-ranked, source-diverse briefing cohort."""
    ranked = sorted(_dedupe_summary_articles(articles), key=_summary_rank, reverse=True)
    selected: list[dict] = []
    selected_ids: set[str] = set()
    category_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}

    def take(article: dict, *, enforce_source_cap: bool, allow_discovery_overflow: bool) -> bool:
        identity = str(article.get("id") or article.get("url") or id(article))
        if identity in selected_ids:
            return False
        category = _article_category(article)
        source = str(article.get("source") or "")
        cap = _SUMMARY_CATEGORY_CAPS.get(category, limit)
        if category_counts.get(category, 0) >= cap:
            if not allow_discovery_overflow or category in {"x-ai", "trending"}:
                return False
        if enforce_source_cap and source_counts.get(source, 0) >= 2:
            return False
        selected.append(article)
        selected_ids.add(identity)
        category_counts[category] = category_counts.get(category, 0) + 1
        source_counts[source] = source_counts.get(source, 0) + 1
        return True

    # First pass maximizes source diversity. A second pass can use more items
    # from trusted/editorial sources, but never relaxes X/Trending ceilings.
    for article in ranked:
        take(article, enforce_source_cap=True, allow_discovery_overflow=False)
        if len(selected) >= limit:
            return selected
    for article in ranked:
        take(article, enforce_source_cap=False, allow_discovery_overflow=True)
        if len(selected) >= limit:
            break
    return selected


def _articles_for_today(limit: int = 25) -> list[dict]:
    """Quality-ranked, balanced articles from the last 30 hours."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=30)).timestamp()
    arts = _load_articles()
    fresh = [a for a in arts if _parse_ts(a.get("date") or "") >= cutoff]
    # Fall back to the latest N if nothing dated recently
    if len(fresh) < 5:
        fresh = sorted(arts, key=lambda a: _parse_ts(a.get("date") or ""), reverse=True)
        fresh = fresh[: max(8, limit * 3)]
    return _select_summary_cohort(fresh, limit)


@router.get("/summary/today")
def get_today_summary() -> dict:
    """Return cached summary (if any) and cohort metadata.

    The UI calls this on load.  If it's missing/stale, the user hits the
    'regenerate' button which POSTs to /summary/today.
    """
    cached = read_json(SUMMARY_FILE, None)
    cohort = _articles_for_today()
    return {
        "summary": cached if isinstance(cached, dict) else None,
        "cohort_size": len(cohort),
        "cohort_preview": [
            {"id": a.get("id"), "title": a.get("title"), "source": a.get("source"), "date": a.get("date")}
            for a in cohort[:10]
        ],
        "today": _today_iso_date(),
    }


async def build_today_summary() -> dict | None:
    """Generate today's briefing from the recent cohort and persist it.

    Returns the payload, or None if there's nothing recent to summarize. Shared
    by the manual endpoint and the daily scheduler job (single source of truth).
    Raises LLMUnavailable if the LLM call fails (caller decides how to surface it).
    """
    cohort = _articles_for_today(limit=25)
    if not cohort:
        return None

    lines = []
    for i, a in enumerate(cohort, 1):
        snippet = (a.get("summary") or "")[:240]
        lines.append(
            f"[{i}] {a.get('title')}\n"
            f"    source={a.get('source')} category={_article_category(a)} "
            f"importance={a.get('importance')}\n"
            f"    url={a.get('url')}\n    excerpt={snippet}"
        )
    article_block = "\n\n".join(lines)

    messages = [
        {
            "role": "system",
            "content": (
                "你是 AI 行业的早报编辑。我会给你最近 24-30 小时的 RSS/资讯片段，"
                "请你筛选并整理一个高密度的中文每日速报：\n"
                "- 标题层级：## 一句话总结 / ## 今日重点 (3-5 条) / ## 值得动手 / ## 接下来关注 / ## 更多动态\n"
                "- 今日重点每条 1-2 句，先说发生了什么，再说为什么重要或影响谁；必须包含来源名 + 用 [n] 标注引用片段编号\n"
                "- 接下来关注列 2-3 个未来几天值得验证的具体信号（如权重/API/评测/开源时间），不得无依据预测\n"
                "- 不要复述营销词；过滤掉与 AI/ML/Agent/Infra 无关的项\n"
                "- 官方发布、关键研究、重大产品/政策事件优先；GitHub Trending 和社交观点只能作为补充信号\n"
                "- 不要因为多个热门仓库讨论同一趋势就挤掉更重要的一手消息\n"
                "- 如果同一主题有多源，合并为一条并列出 [n][m] 引用"
            ),
        },
        {
            "role": "user",
            "content": f"今日候选（已按质量、来源可信度和多样性预筛，共 {len(cohort)} 条）：\n\n{article_block}",
        },
    ]
    body = await chat_complete(messages, max_tokens=1400)

    payload = {
        "generated_at": _now_iso(),
        "date": _today_iso_date(),
        "model": settings.llm_model,
        "cohort_size": len(cohort),
        "body": body,
        "cohort": [
            {"id": a.get("id"), "title": a.get("title"), "source": a.get("source"), "url": a.get("url")}
            for a in cohort
        ],
    }
    write_json_atomic(SUMMARY_FILE, payload)
    return payload


@router.post("/summary/today", dependencies=[Depends(require_admin)])
async def regenerate_today_summary() -> dict:
    if not llm_configured():
        raise HTTPException(503, "LLM not configured")
    try:
        payload = await build_today_summary()
    except LLMUnavailable as e:
        raise HTTPException(503, str(e))
    if payload is None:
        raise HTTPException(400, "no recent articles to summarize")
    return {"ok": True, "summary": payload}


# ── Long-form guides (deep-dive learning notes) ────────────────────
@router.get("/guides/long")
def list_long_guides(user: UserPublic | None = Depends(current_user_optional)) -> list[dict]:
    """List the current user's on-disk deep-dive guides (users/<uid>/guides/*.json)."""
    if not user:
        return []
    gdir = guides_dir(user.id)
    gdir.mkdir(parents=True, exist_ok=True)
    items: list[dict] = []
    for p in sorted(gdir.glob("guide_*.json")):
        data = read_json(p, None)
        if not isinstance(data, dict):
            continue
        items.append({
            "id": data.get("id") or p.stem,
            "slug": p.stem,
            "title": data.get("title") or p.stem,
            "topic": data.get("topic"),
            "tags": data.get("tags", []),
            "updated_at": data.get("updated_at") or data.get("generated_at"),
            "size": p.stat().st_size,
            "preview": (data.get("body") or "")[:240],
        })
    items.sort(key=lambda g: -(_parse_ts(g.get("updated_at") or "")))
    return items


@router.get("/guides/long/{slug}")
def get_long_guide(slug: str, user: UserPublic | None = Depends(current_user_optional)) -> dict:
    if not user:
        raise HTTPException(404, "guide not found")
    p = guides_dir(user.id) / f"{slug}.json"
    if not p.exists():
        raise HTTPException(404, "guide not found")
    data = read_json(p, None)
    if not isinstance(data, dict):
        raise HTTPException(500, "guide payload corrupt")
    return data


@router.delete("/guides/long/{slug}")
def delete_long_guide(slug: str, user: UserPublic = Depends(require_user)) -> dict:
    p = guides_dir(user.id) / f"{slug}.json"
    if not p.exists():
        raise HTTPException(404, "guide not found")
    p.unlink()
    return {"ok": True}


class GuideGenRequest(BaseModel):
    topic: str
    article_ids: list[str] = Field(default_factory=list)  # optional anchor articles
    depth: Literal["brief", "deep"] = "deep"
    tags: list[str] = Field(default_factory=list)


@router.post("/guides/generate")
async def generate_long_guide(req: GuideGenRequest, user: UserPublic = Depends(require_llm_quota)) -> dict:
    """LLM-generated long-form learning guide on `topic`.

    If `article_ids` is given, those articles are used as anchor context;
    otherwise the latest matching articles (by keyword overlap with the topic)
    are auto-picked.
    """
    if not llm_configured():
        raise HTTPException(503, "LLM not configured")
    topic = (req.topic or "").strip()
    if not topic:
        raise HTTPException(400, "topic is required")

    articles = _load_articles()
    if req.article_ids:
        anchors = [a for a in articles if a.get("id") in set(req.article_ids)]
    else:
        kw = topic.lower().split()
        anchors = [
            a for a in articles
            if any(k in (a.get("title", "") + " " + (a.get("summary") or "")).lower() for k in kw)
        ][:8]
        if not anchors:
            anchors = articles[:6]

    anchor_block = "\n".join(
        f"- [{a.get('source')}] {a.get('title')} :: {a.get('url')}\n  摘要: {(a.get('summary') or '')[:300]}"
        for a in anchors
    ) or "(无锚定文章，按公开知识展开)"

    depth_hint = (
        "请写一篇 1500-2500 字的深度学习指南" if req.depth == "deep"
        else "请写一篇 600-900 字的快速入门简报"
    )

    messages = [
        {
            "role": "system",
            "content": (
                "你是一位 AI 工程师导师，擅长把前沿研究/工具用工程师能上手的方式讲清楚。\n"
                f"{depth_hint}，使用 Markdown 输出，结构必须包含：\n"
                "1. ## 这是什么 — 一段话定义与定位\n"
                "2. ## 为什么重要 — 1-3 个核心 insight\n"
                "3. ## 关键概念 — 列要点\n"
                "4. ## 怎么动手 — 5-10 步具体命令/代码片段（pip install / git clone / colab 都可以）\n"
                "5. ## 陷阱与对比 — 易踩坑 + 与同类对比\n"
                "6. ## 延伸阅读 — 引用我给你的 RSS 锚定文章 + 1-2 个权威源 URL\n"
                "中文表述，技术词保留英文；不要写「让我们一起来…」之类客套话。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"主题：{topic}\n\n"
                f"可参考的近期资讯锚定 (n={len(anchors)})：\n{anchor_block}\n\n"
                "请开始撰写。"
            ),
        },
    ]
    try:
        body = await chat_complete(messages, max_tokens=2400 if req.depth == "deep" else 1200)
    except LLMUnavailable as e:
        raise HTTPException(503, str(e))

    slug = "guide_" + hashlib.sha1((topic + _now_iso()).encode()).hexdigest()[:10]
    payload = {
        "id": slug,
        "slug": slug,
        "title": topic,
        "topic": topic,
        "depth": req.depth,
        "tags": req.tags,
        "model": settings.llm_model,
        "generated_at": _now_iso(),
        "updated_at": _now_iso(),
        "anchors": [
            {"id": a.get("id"), "title": a.get("title"), "source": a.get("source"), "url": a.get("url")}
            for a in anchors
        ],
        "body": body,
    }
    gdir = guides_dir(user.id)
    gdir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(gdir / f"{slug}.json", payload)
    return {"ok": True, "guide": payload}


# ── Translation control ───────────────────────────────────────────
@router.post("/translate/run", dependencies=[Depends(require_admin)])
async def translate_run() -> dict:
    """Manually trigger one translation batch (admin-style)."""
    from ..workers.ai_news_translator import translate_once
    n = await translate_once()
    return {"ok": True, "translated": n}


@router.post("/articles/{aid}/retranslate", dependencies=[Depends(require_admin)])
def retranslate_article(aid: str) -> dict:
    """Reset translation status so the worker picks the article up again."""
    def mutate(data):
        articles = data if isinstance(data, list) else []
        for article in articles:
            if article.get("id") == aid:
                article["title_zh"] = None
                article["summary_zh"] = None
                article["translation_status"] = "pending"
                return articles
        raise HTTPException(404, "article not found")

    update_json_atomic(ARTICLES_FILE, [], mutate)
    return {"ok": True}


# ── Deep dive (per-article on-demand long-read with mermaid diagram) ──
DEEP_DIVE_SYSTEM = (
    "你是一名顶尖的 AI 工程师 + 资深技术撰稿人。我会给你一篇 AI 相关文章，"
    "请基于文章内容 + 你的公开知识，写一篇高密度、可执行的中文深度解读。\n\n"
    "硬性结构（用 Markdown，标题层级如下，按顺序）：\n"
    "# 一句话定位\n"
    "## 背景 & 问题\n"
    "## 核心方案\n"
    "## 系统/架构图\n"
    "  在这里务必输出 ```mermaid 代码块（推荐 flowchart TD 或 sequenceDiagram），\n"
    "  把核心组件、数据流、决策点画清楚。节点名简短，禁止特殊字符。\n"
    "  如果文章主题不适合架构图，给一张关系图（concept map）。\n"
    "## 关键技术细节\n"
    "## 怎么动手 / 复现路径\n"
    "  - 至少 5 条可执行步骤：pip install / git clone / curl / 配置项 / 验证命令\n"
    "## 与同类对比\n"
    "## 易踩坑\n"
    "## 延伸阅读\n\n"
    "风格要求：\n"
    "- 中文为主，技术术语保留英文（LLM, RAG, vLLM, ...）\n"
    "- 不写客套话；不堆形容词；句子短\n"
    "- 全文 1500-2500 字\n"
    "- 只允许出现一段 mermaid 代码块，且必须语法合法"
)


@router.get("/deep-dives")
def list_deep_dives(user: UserPublic | None = Depends(current_user_optional)) -> list[dict]:
    """List the current user's stored deep-dives as an independent library.

    Reads the user's ``deep-dives/*.json`` directly (NOT filtered through the
    global articles.json), so a deep-dive survives even after its origin article
    rolls out of the feed. ``has_origin_article`` tells the UI whether the global
    feed still has a card that can link here. Anonymous users get an empty list.
    """
    if not user:
        return []
    ddir = deep_dives_dir(user.id)
    if not ddir.exists():
        return []
    live_ids = {a.get("id") for a in _load_articles()}
    items: list[dict] = []
    for p in ddir.glob("*.json"):
        data = read_json(p, None)
        if not isinstance(data, dict):
            continue
        aid = data.get("article_id") or p.stem
        items.append({
            "article_id": aid,
            "title": data.get("article_title"),
            "title_zh": data.get("article_title_zh"),
            "source": data.get("article_source"),
            "url": data.get("article_url"),
            "generated_at": data.get("generated_at"),
            "model": data.get("model"),
            "is_manual": data.get("article_source") == "手动输入",
            "has_origin_article": aid in live_ids,
        })
    items.sort(key=lambda x: x.get("generated_at") or "", reverse=True)
    return items


@router.get("/articles/{aid}/deep-dive")
def get_deep_dive(aid: str, user: UserPublic | None = Depends(current_user_optional)) -> dict:
    """Return the current user's stored deep-dive for an article, if any."""
    if not user:
        return {"status": "none", "article_id": aid}
    p = deep_dives_dir(user.id) / f"{aid}.json"
    if not p.exists():
        # Distinguish: article exists but this user has no deep-dive yet
        article = next((a for a in _load_articles() if a.get("id") == aid), None)
        if not article:
            raise HTTPException(404, "article not found")
        return {"status": "none", "article_id": aid}
    data = read_json(p, None)
    if not isinstance(data, dict):
        raise HTTPException(500, "deep-dive payload corrupt")
    return {"status": "ok", **data}


@router.post("/articles/{aid}/deep-dive")
async def generate_deep_dive(aid: str, user: UserPublic = Depends(require_llm_quota)) -> dict:
    """Generate (or regenerate) the current user's per-article deep dive with a
    mermaid diagram. Stored under users/<uid>/deep-dives/{aid}.json."""
    if not llm_configured():
        raise HTTPException(503, "LLM not configured")
    articles = _load_articles()
    article = next((a for a in articles if a.get("id") == aid), None)

    ddir = deep_dives_dir(user.id)
    ddir.mkdir(parents=True, exist_ok=True)
    p = ddir / f"{aid}.json"

    # The deep-dive library is independent of the feed: if the origin article has
    # rolled out, fall back to the existing deep-dive payload's metadata so the
    # user can still regenerate. Only 404 when we have neither.
    existing = read_json(p, None) if p.exists() else None
    if not article and not isinstance(existing, dict):
        raise HTTPException(404, "article not found")

    def _meta(key_article: str, key_dive: str):
        if article:
            return article.get(key_article)
        return (existing or {}).get(key_dive)

    title = _meta("title", "article_title")
    title_zh = _meta("title_zh", "article_title_zh")
    url = _meta("url", "article_url")
    source = _meta("source", "article_source")

    user_block = (
        f"文章标题：{title}\n"
        f"来源：{source}\n"
        f"链接：{url}\n"
        + (f"原文摘要：{(article.get('summary') or '')[:1200]}\n" if article else "")
        + (f"中文标题：{title_zh}\n" if title_zh else "")
        + (f"中文摘要：{article.get('summary_zh')}\n" if article and article.get('summary_zh') else "")
        + "\n请基于以上信息 + 你的公开知识开始撰写深度解读。"
    )
    messages = [
        {"role": "system", "content": DEEP_DIVE_SYSTEM},
        {"role": "user", "content": user_block},
    ]
    try:
        body = await chat_complete(messages, max_tokens=2800, temperature=0.4)
    except LLMUnavailable as e:
        raise HTTPException(503, str(e))

    payload = {
        "article_id": aid,
        "article_title": title,
        "article_title_zh": title_zh,
        "article_url": url,
        "article_source": source,
        "generated_at": _now_iso(),
        "model": settings.llm_model,
        "body": body,
    }
    write_json_atomic(p, payload)
    return {"ok": True, **payload}


@router.delete("/articles/{aid}/deep-dive")
def delete_deep_dive(aid: str, user: UserPublic = Depends(require_user)) -> dict:
    p = deep_dives_dir(user.id) / f"{aid}.json"
    if p.exists():
        p.unlink()
    return {"ok": True}


# ── Manual deep-dive: user-supplied topic → standalone explainer ───
class ManualDeepDiveRequest(BaseModel):
    topic: str                       # the headline / question / paper title
    context: str | None = None       # optional pasted abstract / notes / link

@router.post("/manual-dive")
async def manual_deep_dive(req: ManualDeepDiveRequest, user: UserPublic = Depends(require_llm_quota)) -> dict:
    """Generate a deep-dive from a user-supplied topic (no RSS source).

    Persists only as a deep-dive under the user's library (``source='手动输入'``).
    It is NOT inserted into the global article feed — it shows up solely in the
    user's "深度解读" view (the feed stays purely RSS / global).
    """
    topic = (req.topic or "").strip()
    if not topic:
        raise HTTPException(400, "topic required")
    if not llm_configured():
        raise HTTPException(503, "LLM not configured")

    # Synthetic article ID — same scheme as RSS so the frontend treats it uniformly
    seed = f"manual::{topic}::{_now_iso()}"
    aid = "a_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]

    user_block = (
        f"主题 / 标题：{topic}\n"
        + (f"用户提供的背景资料：\n{req.context.strip()[:3000]}\n" if req.context else "")
        + "\n请基于以上信息 + 你的公开知识开始撰写深度解读。"
    )
    messages = [
        {"role": "system", "content": DEEP_DIVE_SYSTEM},
        {"role": "user", "content": user_block},
    ]
    try:
        body = await chat_complete(messages, max_tokens=2800, temperature=0.4)
    except LLMUnavailable as e:
        raise HTTPException(503, str(e))

    now = _now_iso()
    ddir = deep_dives_dir(user.id)
    ddir.mkdir(parents=True, exist_ok=True)
    payload = {
        "article_id": aid,
        "article_title": topic,
        "article_title_zh": topic,
        "article_url": None,
        "article_source": "手动输入",
        "generated_at": now,
        "model": settings.llm_model,
        "body": body,
    }
    write_json_atomic(ddir / f"{aid}.json", payload)
    return {"ok": True, **payload}

