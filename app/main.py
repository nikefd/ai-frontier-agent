"""FastAPI entrypoint. Run: uvicorn app.main:app --host 0.0.0.0 --port 9702

Trimmed from the original multi-agent project: only the ai_news router is mounted (climbing
and finance dropped). The conversational agent chat router is added in a later
milestone.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import scheduler
from .llm_client import llm_configured
from .routers import ai_news
from .settings import settings


def _configure_logging() -> None:
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    log = logging.getLogger("aif")
    log.info(
        "starting ai-frontier-agent host=%s port=%s data=%s llm=%s",
        settings.host, settings.port, settings.data_dir,
        "yes" if llm_configured() else "no (chat endpoints will 503)",
    )
    from .migrate import migrate_legacy_to_holding
    migrate_legacy_to_holding()
    scheduler.start()
    try:
        yield
    finally:
        scheduler.stop()


app = FastAPI(
    title="AI Frontier Agent",
    description="可组装的个人 AI 前沿研究 agent — RSS 聚合 + 对话式追踪。",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    # Cookie auth needs explicit origins + credentials ("*" is invalid with
    # credentials). Empty list = same-origin only (the bundled UI), no extra
    # origins allowed. Configure AIF_CORS_ORIGINS for cross-origin frontends.
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "connect-src 'self'; "
        "font-src 'self' data:; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'; "
        "form-action 'self'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    return response

app.include_router(ai_news.router)

# Personal profile (intent-signal aggregation → LLM portrait). Split from
# ai_news to keep that module focused; shares its loaders / path helpers.
from .routers import profile as profile_router
app.include_router(profile_router.router)

# Personalized "for you" feed — re-ranks today's cohort by profile signals.
# Zero extra LLM cost (pure scoring); reuses ai_news cohort + profile signals.
from .routers import feed_personal
app.include_router(feed_personal.router)

# Knowledge cards + spaced-repetition review (SM-2). Per-user card store; zero
# LLM cost. Split into its own module per the code-quality rules.
from .routers import review
app.include_router(review.router)

# Admin user management (list / change role / delete). admin-only guard.
from .routers import admin
app.include_router(admin.router)

# AI reflection coach (Socratic weekly review). Reuses recent-activity signals.
from .routers import reflection
app.include_router(reflection.router)

# Personalized learning paths (staged roadmap; orchestration above guides).
from .routers import learning
app.include_router(learning.router)

# Structured, time-boxed practice cards generated on demand from actionable articles.
from .routers import experiments
app.include_router(experiments.router)

# Proactive nudges (rule-based, zero LLM) — agent suggesting the next step.
from .routers import suggestions
app.include_router(suggestions.router)

# Operational source/coverage/latency audit. Pure calculation, zero LLM.
from .routers import quality
app.include_router(quality.router)

# Auth (register / login / logout / me + session dependencies).
from .auth import router as auth_router
app.include_router(auth_router)

# Conversational agent (sparrow-powered ReAct). Imported lazily-safe: if the
# sparrow package is missing the app still serves the news API.
try:
    from .agent_chat import router as agent_router
    app.include_router(agent_router)
except Exception as e:  # noqa: broad-except
    logging.getLogger("aif").warning("agent chat router not loaded: %s", e)


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "version": "0.1.0",
        "llm_configured": llm_configured(),
        "data_dir": str(settings.data_dir),
    }


# ── Static frontend (Vite build output) ─────────────────────────────
# Vite builds frontend/ → static/dist/ with content-hashed asset filenames,
# served at the ROOT path (no /ui/ prefix). The agent chat component
# (sparrow-chat.js) ships via frontend/public/, served at /sparrow-chat.js.
STATIC_DIR = Path(__file__).parent.parent / "static" / "dist"
STATIC_DIR.mkdir(parents=True, exist_ok=True)


def _index_response() -> FileResponse:
    # The HTML entry is tiny and references content-hashed assets, so it must
    # always be revalidated (no-cache) — once it updates, the new hashed asset
    # URLs pull fresh JS/CSS automatically. A deploy is picked up immediately.
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/")
def root() -> FileResponse:
    return _index_response()


# Legacy /ui/ links → root (don't break old bookmarks from before the routing change).
@app.get("/ui")
@app.get("/ui/")
def legacy_ui() -> RedirectResponse:
    return RedirectResponse("/", status_code=301)


class HashedAssetStaticFiles(StaticFiles):
    """Serve Vite's content-hashed assets with a 1-year immutable cache.

    Mounted at /assets, so every file here is a hashed build artifact whose name
    changes when content changes — safe to cache forever (zero revalidation).
    """

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


# Hashed assets get their own mount (long-cache). Mounted before the SPA
# catch-all so /assets/* resolves to real files, not index.html.
app.mount("/assets", HashedAssetStaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")


@app.get("/sparrow-chat.js")
def sparrow_chat() -> FileResponse:
    return FileResponse(STATIC_DIR / "sparrow-chat.js", headers={"Cache-Control": "no-cache"},
                        media_type="application/javascript")


# SPA catch-all: any non-/api, non-asset path (e.g. /feed, /reflection) returns
# the index so the frontend router can take over. Registered LAST so real routes
# win first. /api/* is handled by routers above and won't reach here.
@app.get("/{full_path:path}")
def spa_fallback(full_path: str) -> FileResponse:
    if full_path.startswith("api/"):
        raise HTTPException(404, "not found")
    # Serve real static files at root (favicon etc.) if they exist; else index.
    candidate = STATIC_DIR / full_path
    if full_path and candidate.is_file():
        return FileResponse(candidate, headers={"Cache-Control": "no-cache"})
    return _index_response()
