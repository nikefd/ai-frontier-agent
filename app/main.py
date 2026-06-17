"""FastAPI entrypoint. Run: uvicorn app.main:app --host 0.0.0.0 --port 9702

Trimmed from zhangyangbin-agents: only the ai_news router is mounted (climbing
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
    allow_origins=["*"],  # tighten if bound to a public IP without auth in front
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ai_news.router)


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


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse("/ui/")


@app.get("/ui/")
def ui_index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


# Mount /ui after explicit / handler so / still redirects cleanly.
app.mount("/ui", StaticFiles(directory=str(STATIC_DIR), html=True), name="ui")
