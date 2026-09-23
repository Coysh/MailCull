from __future__ import annotations

from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import db
from ..browser_unsub import browser_installed
from ..config import get_settings
from ..state import get_ollama

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsResponse(BaseModel):
    ollama_base_url: str
    ollama_model: str
    dry_run: bool
    scan_since_days: int
    body_link_scan: bool
    browser_unsubscribe: bool
    browser_installed: bool
    unsub_grace_days: int


class SettingsPatch(BaseModel):
    ollama_base_url: str | None = None
    ollama_model: str | None = None


def _response() -> SettingsResponse:
    s = get_settings()
    ollama = get_ollama()
    return SettingsResponse(
        ollama_base_url=ollama.base_url,
        ollama_model=ollama.model,
        dry_run=s.dry_run,
        scan_since_days=s.scan_since_days,
        body_link_scan=s.body_link_scan,
        browser_unsubscribe=s.browser_unsubscribe,
        browser_installed=browser_installed(),
        unsub_grace_days=s.unsub_grace_days,
    )


@router.get("", response_model=SettingsResponse)
async def get_settings_endpoint():
    return _response()


@router.patch("", response_model=SettingsResponse)
async def patch_settings(body: SettingsPatch):
    if body.ollama_base_url is not None:
        parsed = urlparse(body.ollama_base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise HTTPException(400, "Ollama URL must be http(s)://host[:port]")
    get_ollama().configure(body.ollama_base_url, body.ollama_model)
    return _response()


@router.get("/ollama-status")
async def ollama_status():
    """Reachability checked server-side — the browser can't reach a LAN Ollama (CORS)."""
    ollama = get_ollama()
    return {"reachable": await ollama.check_reachable(), "base_url": ollama.base_url, "model": ollama.model}


@router.post("/wipe")
async def wipe_data(confirm: bool = False):
    """Delete the local database contents. Gmail is untouched."""
    if not confirm:
        raise HTTPException(400, "Pass confirm=true to wipe local data")
    from .scan import _active_scans
    if any(not t.done() for t in _active_scans.values()):
        raise HTTPException(409, "A scan is running")
    await db.wipe_local_data()
    return {"status": "wiped"}
