from __future__ import annotations

from pydantic import BaseModel

from fastapi import APIRouter

from ..config import get_settings
from ..state import get_ollama

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsResponse(BaseModel):
    ollama_base_url: str
    ollama_model: str
    dry_run: bool
    scan_since_days: int


class SettingsPatch(BaseModel):
    ollama_base_url: str | None = None
    ollama_model: str | None = None


@router.get("", response_model=SettingsResponse)
async def get_settings_endpoint():
    s = get_settings()
    ollama = get_ollama()
    return SettingsResponse(
        ollama_base_url=ollama._base_url,
        ollama_model=ollama._model,
        dry_run=s.dry_run,
        scan_since_days=s.scan_since_days,
    )


@router.patch("", response_model=SettingsResponse)
async def patch_settings(body: SettingsPatch):
    s = get_settings()
    ollama = get_ollama()
    if body.ollama_base_url is not None:
        ollama._base_url = body.ollama_base_url.rstrip("/")
        ollama._reachable = None
    if body.ollama_model is not None:
        ollama._model = body.ollama_model
    return SettingsResponse(
        ollama_base_url=ollama._base_url,
        ollama_model=ollama._model,
        dry_run=s.dry_run,
        scan_since_days=s.scan_since_days,
    )
