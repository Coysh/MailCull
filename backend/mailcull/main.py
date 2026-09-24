"""MailCull FastAPI application entry point."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import db
from .config import get_settings
from .state import init_state

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    db.init_db_path(settings.db_path)
    await db.migrate()
    await db.fail_interrupted_scans()
    init_state()
    if settings.app_host != "127.0.0.1":
        logger.warning(
            "APP_HOST is %s — MailCull is designed for localhost only. "
            "Exposing it on a network interface may leak OAuth tokens.",
            settings.app_host,
        )
    if not settings.dry_run:
        logger.warning("DRY_RUN is OFF — actions will affect the live Gmail mailbox")
    yield


app = FastAPI(
    title="MailCull",
    version="0.1.0",
    description="Self-hosted Gmail triage tool",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8420"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from .api.auth import router as auth_router
from .api.scan import router as scan_router
from .api.senders import router as senders_router
from .api.actions import router as actions_router
from .api.settings import router as settings_router
from .api.inbox import router as inbox_router

app.include_router(auth_router)
app.include_router(scan_router)
app.include_router(senders_router)
app.include_router(actions_router)
app.include_router(settings_router)
app.include_router(inbox_router)

@app.get("/api/health")
async def health():
    settings = get_settings()
    return {
        "status": "ok",
        "dry_run": settings.dry_run,
        "version": "0.1.0",
    }


# Serve React frontend from dist if built — must come last (catch-all mount).
# Repo checkout: <repo>/frontend/dist. Docker: /app/frontend/dist.
_here = Path(__file__).resolve()
_frontend_candidates = [
    Path(os.environ["FRONTEND_DIST"]) if os.environ.get("FRONTEND_DIST") else None,
    _here.parents[2] / "frontend" / "dist",
    _here.parents[1] / "frontend" / "dist",
]
_frontend_dist = next((p for p in _frontend_candidates if p and p.is_dir()), None)
if _frontend_dist:
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
