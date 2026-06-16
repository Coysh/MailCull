from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from ..config import get_settings
from ..state import get_gmail

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _redirect_uri(request: Request) -> str:
    settings = get_settings()
    return f"http://{settings.app_host}:{settings.app_port}/api/auth/callback"


class AuthStartResponse(BaseModel):
    consent_url: str


class AuthStatusResponse(BaseModel):
    connected: bool
    account: str | None = None
    scopes: list[str] = []


@router.get("/start", response_model=AuthStartResponse)
async def auth_start(request: Request):
    gmail = get_gmail()
    url = await gmail.authenticate(_redirect_uri(request))
    return AuthStartResponse(consent_url=url)


@router.get("/callback")
async def auth_callback(code: str, state: str = "", request: Request = None):  # type: ignore[assignment]
    gmail = get_gmail()
    try:
        await gmail.handle_callback(code, state, _redirect_uri(request))
    except Exception as exc:
        logger.error("OAuth callback failed: %s", exc, exc_info=True)
        settings = get_settings()
        return RedirectResponse(
            f"http://localhost:{settings.app_port}/?auth_error=1"
        )
    settings = get_settings()
    return RedirectResponse(f"http://localhost:{settings.app_port}/")


@router.get("/status", response_model=AuthStatusResponse)
async def auth_status():
    gmail = get_gmail()
    connected = await gmail.is_connected()
    if not connected:
        return AuthStatusResponse(connected=False)
    account = await gmail.get_account_email()
    scopes = await gmail.get_granted_scopes()
    return AuthStatusResponse(connected=True, account=account, scopes=scopes)


@router.post("/disconnect")
async def auth_disconnect():
    gmail = get_gmail()
    await gmail.revoke()
    return {"status": "disconnected"}
