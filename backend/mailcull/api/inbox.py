"""Inbox view: browse recent mail and act on the sender of a specific message.

Acting from a message uses *that message's* List-Unsubscribe headers — the
freshest token available — rather than whatever the last scan stored.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import db
from ..action_executor import ActionExecutor
from ..aggregator import aggregate, apply_unsub_info
from ..browser_unsub import browser_installed, open_browser
from ..config import get_settings
from ..mail_source.gmail import UnsubInfo
from ..models import ActionResult, Capability, Status
from ..state import get_gmail

router = APIRouter(prefix="/api/inbox", tags=["inbox"])


class InboxMessage(BaseModel):
    message_id: str
    received_at: str  # ISO datetime (UTC)
    unread: bool
    from_name: str
    from_address: str
    subject: str
    capability: Capability  # from this message's headers
    sender_id: str
    sender_status: Status | None = None  # None = sender not seen by a scan yet
    sender_decision: str | None = None
    message_count: int | None = None


class InboxPage(BaseModel):
    messages: list[InboxMessage]
    next_page_token: str | None = None


class MessageActionRequest(BaseModel):
    action: Literal["unsubscribe", "mute"]
    confirm: bool = False
    mute_action: Literal["archive", "trash"] = "archive"


@router.get("", response_model=InboxPage)
async def list_inbox(page_token: str | None = None, limit: int = 50):
    gmail = get_gmail()
    if not await gmail.is_connected():
        raise HTTPException(401, "Not authenticated")
    raw, next_token = await gmail.list_inbox(page_token, min(max(limit, 1), 100))
    per_message = {m.message_id: aggregate([m])[0] for m in raw}
    known = await db.get_senders_by_ids(list({s.id for s in per_message.values()}))
    out: list[InboxMessage] = []
    for m in raw:
        s = per_message[m.message_id]
        k = known.get(s.id)
        out.append(InboxMessage(
            message_id=m.message_id,
            received_at=datetime.fromtimestamp(m.internal_date_ms / 1000, tz=timezone.utc).isoformat(timespec="seconds"),
            unread=m.unread,
            from_name=m.from_name,
            from_address=m.from_address,
            subject=m.subject,
            # No header on this message, but a scan found a body link for the sender
            capability=s.capability if s.capability != "none" or not k else (
                "body_link" if k.capability == "body_link" else "none"),
            sender_id=s.id,
            sender_status=k.status if k else None,
            sender_decision=k.decision if k else None,
            message_count=k.message_count if k else None,
        ))
    return InboxPage(messages=out, next_page_token=next_token)


@router.post("/{message_id}/action", response_model=ActionResult)
async def act_on_message(message_id: str, body: MessageActionRequest):
    """Unsubscribe from / mute the sender of one message. Requires confirm=true."""
    if not body.confirm:
        raise HTTPException(400, "Pass confirm=true to execute")
    settings = get_settings()
    gmail = get_gmail()
    if not await gmail.is_connected():
        raise HTTPException(401, "Not authenticated")

    raw = await gmail.get_message(message_id)
    if raw is None:
        raise HTTPException(404, "Message not found")
    fresh = aggregate([raw])[0]  # methods from this exact message

    if body.action == "unsubscribe" and fresh.capability == "none":
        links = (await gmail.find_body_unsubscribe_links({fresh.id: message_id})).get(fresh.id)
        if links:
            fresh = apply_unsub_info(fresh, UnsubInfo(
                http_urls=[l for l in links if not l.lower().startswith("mailto:")],
                mailtos=[l for l in links if l.lower().startswith("mailto:")],
            ), "body").model_copy(update={"capability": "body_link"})

    existing = await db.get_sender(fresh.id)
    if existing is None:
        await db.save_message_unsub_methods(fresh)  # track the sender so the action is logged
    elif body.action == "unsubscribe" and fresh.capability != "none":
        # This message's methods are the freshest; if it has none, keep what scans found
        await db.save_message_unsub_methods(fresh)
    await db.update_sender_decision(fresh.id, body.action)
    sender = await db.get_sender(fresh.id)
    assert sender is not None

    needs_browser = (
        body.action == "unsubscribe" and not settings.dry_run and settings.browser_unsubscribe
        and bool(sender.http_links or sender.one_click_url)
    )
    async with open_browser(enabled=needs_browser) as browser:
        executor = ActionExecutor(
            await gmail.build_service(),
            dry_run=settings.dry_run,
            granted_scopes=await gmail.get_granted_scopes(),
            account_email=await gmail.get_account_email(),
            browser=browser,
            browser_available=settings.browser_unsubscribe and browser_installed(),
            mute_action=body.mute_action,
        )
        # The user asked explicitly for this message, so re-run even if handled before
        [result] = await executor.execute([sender], force=True)
    return result
