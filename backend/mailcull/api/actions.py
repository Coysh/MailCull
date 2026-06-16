from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import db
from ..action_executor import ActionExecutor
from ..config import get_settings
from ..models import ActionLog, ActionPreview, ActionResult
from ..state import get_gmail

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/actions", tags=["actions"])


class PreviewRequest(BaseModel):
    sender_ids: list[str]


class ExecuteRequest(BaseModel):
    sender_ids: list[str]
    confirm: bool = False
    dry_run: bool | None = None


@router.post("/preview", response_model=list[ActionPreview])
async def preview_actions(body: PreviewRequest):
    """Return the planned action for each sender. Side-effect free."""
    senders = [s for sid in body.sender_ids if (s := await db.get_sender(sid))]
    senders = [s for s in senders if s.decision]
    return ActionExecutor.preview(senders)


@router.post("/execute", response_model=list[ActionResult])
async def execute_actions(body: ExecuteRequest):
    """Execute actions for the given senders. Requires confirm=true."""
    if not body.confirm:
        raise HTTPException(400, "Pass confirm=true to execute actions")

    settings = get_settings()
    gmail = get_gmail()
    if not await gmail.is_connected():
        raise HTTPException(401, "Not authenticated")

    senders = [s for sid in body.sender_ids if (s := await db.get_sender(sid))]
    senders = [s for s in senders if s.decision]

    # Build service once
    service = await gmail._build_service()
    dry_run = body.dry_run if body.dry_run is not None else settings.dry_run
    executor = ActionExecutor(service, dry_run=dry_run)
    results = await executor.execute(senders)
    return results


@router.get("/log", response_model=list[ActionLog])
async def get_action_log():
    return await db.get_action_log()
