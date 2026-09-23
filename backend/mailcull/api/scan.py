from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import db
from ..aggregator import aggregate, apply_unsub_info
from ..config import get_settings
from ..mail_source.gmail import UnsubInfo
from ..models import ScanRecord, Sender
from ..state import get_gmail, get_ollama

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scan", tags=["scan"])

_active_scans: dict[int, asyncio.Task] = {}


class ScanStartRequest(BaseModel):
    since_days: int | None = Field(None, ge=1, le=3650)


class ScanStartResponse(BaseModel):
    scan_id: int


@router.post("", response_model=ScanStartResponse)
async def start_scan(body: ScanStartRequest):
    settings = get_settings()
    gmail = get_gmail()
    if not await gmail.is_connected():
        raise HTTPException(401, "Not authenticated with Gmail")
    running = [sid for sid, t in _active_scans.items() if not t.done()]
    if running:
        raise HTTPException(409, f"Scan {running[0]} is already running")

    since_days = body.since_days or settings.scan_since_days
    scan_id = await db.create_scan(since_days)
    task = asyncio.create_task(_run_scan(scan_id, since_days))
    _active_scans[scan_id] = task
    task.add_done_callback(lambda _t: _active_scans.pop(scan_id, None))
    return ScanStartResponse(scan_id=scan_id)


@router.get("/{scan_id}", response_model=ScanRecord)
async def get_scan(scan_id: int):
    record = await db.get_scan(scan_id)
    if record is None:
        raise HTTPException(404, "Scan not found")
    return record


@router.get("/latest/status", response_model=ScanRecord | None)
async def get_latest_scan():
    return await db.get_latest_scan()


async def _find_body_links(scan_id: int, senders: list[Sender]) -> list[Sender]:
    """For senders with no List-Unsubscribe header, look for a link in their newest message body."""
    existing = {s.id: s for s in await db.get_all_senders(capability="body_link")}
    todo: dict[str, str] = {}
    for s in senders:
        if s.capability != "none" or not s.latest_message_id:
            continue
        prev = existing.get(s.id)
        if prev and prev.latest_message_id == s.latest_message_id:
            continue  # already found a link in this exact message; upsert keeps it
        todo[s.id] = s.latest_message_id
    if not todo:
        return senders

    await db.update_scan(
        scan_id, phase="links", progress_pct=46,
        status_detail=f"Looking for unsubscribe links in {len(todo):,} senders without a header…",
    )
    found = await get_gmail().find_body_unsubscribe_links(todo)
    logger.info("Scan %d: body links found for %d/%d senders", scan_id, len(found), len(todo))

    out: list[Sender] = []
    for s in senders:
        links = found.get(s.id)
        if links:
            info = UnsubInfo(
                http_urls=[l for l in links if not l.lower().startswith("mailto:")],
                mailtos=[l for l in links if l.lower().startswith("mailto:")],
            )
            s = apply_unsub_info(s, info, "body").model_copy(update={"capability": "body_link"})
        out.append(s)
    return out


async def _run_scan(scan_id: int, since_days: int) -> None:
    settings = get_settings()
    gmail = get_gmail()
    ollama = get_ollama()

    try:
        await db.update_scan(scan_id, phase="reading", status_detail="Collecting message IDs…")
        all_messages = []
        total_ids = 0

        async def _on_total(n: int) -> None:
            nonlocal total_ids
            total_ids = n
            await db.update_scan(scan_id, status_detail=f"Found {n:,} messages — reading headers…")

        async for batch in gmail.stream_messages(since_days, on_total=_on_total):
            all_messages.extend(batch)
            read = len(all_messages)
            await db.update_scan(
                scan_id,
                total_messages=read,
                phase="reading",
                progress_pct=int(40 * read / total_ids) if total_ids else 0,
                status_detail=f"Read {read:,} of {total_ids:,} messages",
            )

        await db.update_scan(
            scan_id, phase="aggregating", progress_pct=45,
            status_detail=f"Grouping {len(all_messages):,} messages by sender…",
        )
        senders = aggregate(all_messages)
        total_senders = len(senders)
        if settings.body_link_scan:
            try:
                senders = await _find_body_links(scan_id, senders)
            except Exception:
                logger.exception("Scan %d: body-link lookup failed — continuing with headers only", scan_id)
        logger.info("Scan %d: %d messages → %d senders", scan_id, len(all_messages), total_senders)

        await db.update_scan(
            scan_id, phase="classifying", progress_pct=50,
            total_senders=total_senders,
            status_detail=f"Classifying {total_senders} senders in batches of 25…",
        )

        async def _on_batch(done: int, total: int) -> None:
            pct = 50 + int((done / total) * 38)
            await db.update_scan(
                scan_id,
                progress_pct=pct,
                status_detail=f"Classified {done}/{total} senders",
            )

        enriched, degraded = await ollama.classify_senders(senders, on_batch=_on_batch)

        await db.update_scan(
            scan_id, phase="saving", progress_pct=90,
            status_detail=f"Saving {len(enriched)} senders to database…",
        )
        await db.bulk_upsert_senders(enriched, scan_id)
        still_sending = await db.flag_still_sending(settings.unsub_grace_days)
        if still_sending:
            logger.info("Scan %d: %d senders still sending after unsubscribe", scan_id, still_sending)

        detail = f"Complete — {len(enriched)} senders, {'heuristic' if degraded else ollama.model}"
        if still_sending:
            detail += f" · {still_sending} still sending after unsubscribe"
        await db.update_scan(
            scan_id,
            phase="done",
            progress_pct=100,
            total_messages=len(all_messages),
            total_senders=len(enriched),
            status_detail=detail,
            finished_at=db.utcnow_iso(),
        )
        logger.info("Scan %d complete: %d messages, %d senders", scan_id, len(all_messages), len(enriched))
    except Exception as exc:
        logger.exception("Scan %d failed", scan_id)
        await db.update_scan(scan_id, phase="error", error=str(exc))
