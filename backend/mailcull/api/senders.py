from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .. import db
from ..models import Decision, Sender
from ..state import get_ollama

router = APIRouter(prefix="/api/senders", tags=["senders"])


@router.get("", response_model=list[Sender])
async def list_senders(
    sort: str = Query("count", pattern="^(count|sender|last)$"),
    category: str | None = None,
    capability: str | None = None,
    decision: str | None = None,
    status: str | None = None,
):
    return await db.get_all_senders(
        category=category,
        capability=capability,
        decision=decision,
        status=status,
        sort=sort,
    )


@router.get("/{sender_id}", response_model=Sender)
async def get_sender(sender_id: str):
    s = await db.get_sender(sender_id)
    if not s:
        raise HTTPException(404, "Sender not found")
    return s


class ClassifyRequest(BaseModel):
    sender_ids: list[str] | None = None


@router.post("/classify")
async def classify_senders(body: ClassifyRequest | None = None):
    """Re-run LLM classification on all (or specified) senders."""
    if body and body.sender_ids:
        senders = [s for sid in body.sender_ids if (s := await db.get_sender(sid))]
    else:
        senders = await db.get_all_senders()

    if not senders:
        return {"classified": 0, "degraded": False}

    ollama = get_ollama()
    enriched, degraded = await ollama.classify_senders(senders)
    await db.update_classifications(enriched)
    return {"classified": len(enriched), "degraded": degraded}


class DecisionItem(BaseModel):
    sender_id: str
    decision: Decision


@router.post("/decisions")
async def set_decisions(items: list[DecisionItem]):
    for item in items:
        await db.update_sender_decision(item.sender_id, item.decision)
    return {"updated": len(items)}


@router.post("/{sender_id}/manual-done", response_model=Sender)
async def mark_manual_unsubscribe(sender_id: str):
    """The user finished a link unsubscribe by hand; track it like any other."""
    s = await db.get_sender(sender_id)
    if not s:
        raise HTTPException(404, "Sender not found")
    await db.update_sender_status(
        sender_id, "unsubscribed", unsubscribed_at=db.utcnow_iso(), unsub_method="manual",
    )
    await db.log_action(sender_id=sender_id, action="unsubscribe", method="manual",
                        result="marked done by user", dry_run=False)
    return await db.get_sender(sender_id)
