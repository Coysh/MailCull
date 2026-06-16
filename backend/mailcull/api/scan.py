from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from .. import db
from ..aggregator import aggregate, merge_into
from ..config import get_settings
from ..models import ScanRecord
from ..ollama_client import OllamaClient
from ..state import get_gmail, get_ollama

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scan", tags=["scan"])

_active_scans: dict[int, asyncio.Task] = {}


class ScanStartRequest(BaseModel):
    since_days: int | None = None


class ScanStartResponse(BaseModel):
    scan_id: int


@router.post("", response_model=ScanStartResponse)
async def start_scan(body: ScanStartRequest, background_tasks: BackgroundTasks):
    settings = get_settings()
    gmail = get_gmail()
    if not await gmail.is_connected():
        raise HTTPException(401, "Not authenticated with Gmail")

    since_days = body.since_days or settings.scan_since_days
    scan_id = await db.create_scan(since_days)
    background_tasks.add_task(_run_scan, scan_id, since_days)
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


async def _run_scan(scan_id: int, since_days: int) -> None:
    from datetime import datetime
    gmail = get_gmail()
    ollama = get_ollama()

    try:
        await db.update_scan(scan_id, phase="reading", status_detail="Collecting message IDs…")
        all_messages = []
        page = 0

        async for batch in gmail.stream_messages(since_days):
            all_messages.extend(batch)
            page += 1
            await db.update_scan(
                scan_id,
                total_messages=len(all_messages),
                phase="reading",
                progress_pct=min(40, page * 4),
                status_detail=f"Page {page} — {len(all_messages):,} messages fetched",
            )

        await db.update_scan(
            scan_id, phase="aggregating", progress_pct=45,
            status_detail=f"Grouping {len(all_messages):,} messages by sender…",
        )
        senders = aggregate(all_messages)
        total_senders = len(senders)
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

        await db.update_scan(
            scan_id,
            phase="done",
            progress_pct=100,
            total_messages=len(all_messages),
            total_senders=len(enriched),
            status_detail=f"Complete — {len(enriched)} senders, {'heuristic' if degraded else ollama._model}",
            finished_at=datetime.utcnow().isoformat(),
        )
        logger.info("Scan %d complete: %d messages, %d senders", scan_id, len(all_messages), len(enriched))
    except Exception as exc:
        logger.exception("Scan %d failed", scan_id)
        await db.update_scan(scan_id, phase="error", error=str(exc))
