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
):
    return await db.get_all_senders(
        category=category,
        capability=capability,
        decision=decision,
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

    scan = await db.get_latest_scan()
    scan_id = scan.id if scan else 0
    await db.bulk_upsert_senders(enriched, scan_id)
    return {"classified": len(enriched), "degraded": degraded}


class DecisionItem(BaseModel):
    sender_id: str
    decision: Decision


@router.post("/decisions")
async def set_decisions(items: list[DecisionItem]):
    for item in items:
        await db.update_sender_decision(item.sender_id, item.decision)
    return {"updated": len(items)}
