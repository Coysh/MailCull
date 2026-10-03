from __future__ import annotations

import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException
from googleapiclient.errors import HttpError
from pydantic import BaseModel, Field

from .. import db
from ..action_executor import ActionExecutor, estimate_messages
from ..browser_unsub import browser_installed, open_browser
from ..config import get_settings
from ..models import ActionLog, ActionLogEntry, ActionPreview, ActionResult, Sender
from ..state import get_gmail
from ..unsubscribe import SEND_SCOPE

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/actions", tags=["actions"])


class PreviewRequest(BaseModel):
    sender_ids: list[str]


class ExecuteRequest(BaseModel):
    sender_ids: list[str]
    confirm: bool = False
    force: bool = False  # re-run senders that were already handled (Retry)
    mute_action: Literal["archive", "trash"] = "archive"
    snooze_days: int = Field(30, ge=1, le=365)


async def _load(ids: list[str]) -> list[Sender]:
    senders = [s for sid in ids if (s := await db.get_sender(sid))]
    return [s for s in senders if s.decision]


@router.post("/preview", response_model=list[ActionPreview])
async def preview_actions(body: PreviewRequest):
    """Return the planned action for each sender. Side-effect free."""
    gmail = get_gmail()
    scopes = await gmail.get_granted_scopes()
    settings = get_settings()
    senders = await _load(body.sender_ids)
    previews = ActionExecutor.preview(
        senders,
        can_send=SEND_SCOPE in scopes,
        browser_available=settings.browser_unsubscribe and browser_installed(),
    )

    # Delete/archive act on all of a sender's mail, not just the scanned window,
    # so ask Gmail how many messages they will really touch.
    bulk = [(s, p) for s, p in zip(senders, previews) if s.decision in ("delete", "archive")]
    if bulk and await gmail.is_connected():
        service = await gmail.build_service()
        gate = asyncio.Semaphore(5)

        async def _estimate(s: Sender, p: ActionPreview) -> None:
            async with gate:
                p.estimated_messages = await estimate_messages(service, s)

        await asyncio.gather(*(_estimate(s, p) for s, p in bulk))
    return previews


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
    # DRY_RUN is .env-only: a request can never switch it off
    dry_run = settings.dry_run

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


@router.get("/activity", response_model=list[ActionLogEntry])
async def get_activity(limit: int = 300):
    """History for the Activity view, including which entries can still be undone."""
    return await db.get_activity(min(max(limit, 1), 1000))
