from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException
from googleapiclient.errors import HttpError
from pydantic import BaseModel, Field

from .. import db
from ..action_executor import ActionExecutor
from ..browser_unsub import browser_installed, open_browser
from ..config import get_settings
from ..models import ActionLog, ActionPreview, ActionResult, Sender
from ..state import get_gmail
from ..unsubscribe import SEND_SCOPE

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/actions", tags=["actions"])


class PreviewRequest(BaseModel):
    sender_ids: list[str]


class ExecuteRequest(BaseModel):
    sender_ids: list[str]
    confirm: bool = False
    dry_run: bool | None = None
    force: bool = False  # re-run senders that were already handled (Retry)
    mute_action: Literal["archive", "trash"] = "archive"
    snooze_days: int = Field(30, ge=1, le=365)


async def _load(ids: list[str]) -> list[Sender]:
    senders = [s for sid in ids if (s := await db.get_sender(sid))]
    return [s for s in senders if s.decision]


@router.post("/preview", response_model=list[ActionPreview])
async def preview_actions(body: PreviewRequest):
    """Return the planned action for each sender. Side-effect free."""
    scopes = await get_gmail().get_granted_scopes()
    settings = get_settings()
    return ActionExecutor.preview(
        await _load(body.sender_ids),
        can_send=SEND_SCOPE in scopes,
        browser_available=settings.browser_unsubscribe and browser_installed(),
    )


@router.post("/execute", response_model=list[ActionResult])
async def execute_actions(body: ExecuteRequest):
    """Execute actions for the given senders. Requires confirm=true."""
    if not body.confirm:
        raise HTTPException(400, "Pass confirm=true to execute actions")

    settings = get_settings()
    gmail = get_gmail()
    if not await gmail.is_connected():
        raise HTTPException(401, "Not authenticated")

    senders = await _load(body.sender_ids)
    service = await gmail.build_service()
    dry_run = body.dry_run if body.dry_run is not None else settings.dry_run

    # Only start Chromium when an unsubscribe might need a page
    needs_browser = not dry_run and settings.browser_unsubscribe and any(
        s.decision == "unsubscribe" and (s.http_links or s.one_click_url) for s in senders
    )
    async with open_browser(enabled=needs_browser) as browser:
        executor = ActionExecutor(
            service,
            dry_run=dry_run,
            granted_scopes=await gmail.get_granted_scopes(),
            account_email=await gmail.get_account_email(),
            browser=browser,
            browser_available=settings.browser_unsubscribe and browser_installed(),
            mute_action=body.mute_action,
            snooze_days=body.snooze_days,
        )
        return await executor.execute(senders, force=body.force)


@router.post("/{action_id}/undo")
async def undo_action(action_id: int):
    gmail = get_gmail()
    if not await gmail.is_connected():
        raise HTTPException(401, "Not authenticated")
    executor = ActionExecutor(await gmail.build_service(), dry_run=False)
    try:
        detail = await executor.undo(action_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except HttpError as exc:
        raise HTTPException(502, f"Gmail API error: {exc.reason}")
    return {"status": "undone", "detail": detail}


@router.get("/log", response_model=list[ActionLog])
async def get_action_log():
    return await db.get_action_log()
