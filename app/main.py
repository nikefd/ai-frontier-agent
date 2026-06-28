"""FastAPI entrypoint. Run: uvicorn app.main:app --host 0.0.0.0 --port 9702

Trimmed from the original multi-agent project: only the ai_news router is mounted (climbing
and finance dropped). The conversational agent chat router is added in a later
milestone.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
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

app.include_router(ai_news.router)

# Personal profile (intent-signal aggregation → LLM portrait). Split from
# ai_news to keep that module focused; shares its loaders / path helpers.
from .routers import profile as profile_router
app.include_router(profile_router.router)

# Personalized "for you" feed — re-ranks today's cohort by profile signals.
# Zero extra LLM cost (pure scoring); reuses ai_news cohort + profile signals.
from .routers import feed_personal
app.include_router(feed_personal.router)

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


# ── Static frontend ─────────────────────────────────────────────────
STATIC_DIR = Path(__file__).parent.parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)


def _sync_sparrow_assets() -> None:
    """Copy the bundled sparrow-chat.js into our static dir so the page can
    serve it from /ui/js/. Done at startup so a sparrow upgrade auto-propagates."""
    try:
        import shutil
        from sparrow.web import asset_path
        dst = STATIC_DIR / "js"
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copy(asset_path("sparrow-chat.js"), dst / "sparrow-chat.js")
    except Exception as e:  # noqa: broad-except
        logging.getLogger("aif").warning("could not sync sparrow-chat.js: %s", e)


_sync_sparrow_assets()


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse("/ui/")


@app.get("/ui/")
def ui_index() -> FileResponse:
    # no-store on the HTML entry so a deploy is picked up immediately; the JS
    # modules it pulls are revalidated via ETag by NoCacheStaticFiles below.
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Cache-Control": "no-store"},
    )


class NoCacheStaticFiles(StaticFiles):
    """Serve static assets with ``Cache-Control: no-cache``.

    This is a zero-build ES-module frontend: ``main.js`` pulls ~9 sibling
    modules via bare relative ``import`` (no query string), so we can't bust
    them with a versioned URL without a build step. ``no-cache`` keeps the
    browser cache but forces an ETag revalidation on every load — a cheap 304
    when unchanged, and the fresh file the instant a deploy changes it. Fixes
    users seeing stale JS for hours after a deploy.
    """

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


# Mount /ui after explicit / handler so / still redirects cleanly.
app.mount("/ui", NoCacheStaticFiles(directory=str(STATIC_DIR), html=True), name="ui")
