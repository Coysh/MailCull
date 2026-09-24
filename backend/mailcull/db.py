"""SQLite persistence layer (aiosqlite)."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

import aiosqlite

from .models import ActionLog, Decision, Sender, ScanRecord

_db_path: Path | None = None


def init_db_path(path: Path) -> None:
    global _db_path
    _db_path = path
    path.parent.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def get_conn() -> AsyncIterator[aiosqlite.Connection]:
    assert _db_path is not None, "call init_db_path() first"
    async with aiosqlite.connect(_db_path) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        yield conn


async def migrate() -> None:
    async with get_conn() as conn:
        await conn.executescript("""
        CREATE TABLE IF NOT EXISTS scans (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at  TEXT NOT NULL,
            finished_at TEXT,
            since_days  INTEGER NOT NULL,
            total_messages INTEGER NOT NULL DEFAULT 0,
            total_senders  INTEGER NOT NULL DEFAULT 0,
            phase       TEXT NOT NULL DEFAULT 'idle',
            progress_pct INTEGER NOT NULL DEFAULT 0,
            status_detail TEXT,
            error       TEXT
        );

        CREATE TABLE IF NOT EXISTS senders (
            id                    TEXT PRIMARY KEY,
            scan_id               INTEGER REFERENCES scans(id),
            from_name             TEXT NOT NULL,
            from_address          TEXT NOT NULL,
            domain                TEXT NOT NULL,
            message_count         INTEGER NOT NULL DEFAULT 0,
            first_seen            TEXT NOT NULL,
            last_seen             TEXT NOT NULL,
            sample_subjects       TEXT NOT NULL DEFAULT '[]',
            capability            TEXT NOT NULL DEFAULT 'none',
            unsubscribe_links     TEXT NOT NULL DEFAULT '[]',
            category              TEXT,
            rationale             TEXT,
            suggested_action      TEXT,
            classification_degraded INTEGER NOT NULL DEFAULT 0,
            decision              TEXT,
            status                TEXT NOT NULL DEFAULT 'pending',
            updated_at            TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_senders_domain ON senders(domain);
        CREATE INDEX IF NOT EXISTS idx_senders_decision ON senders(decision);

        CREATE TABLE IF NOT EXISTS action_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id     INTEGER REFERENCES scans(id),
            sender_id   TEXT NOT NULL,
            action      TEXT NOT NULL,
            method      TEXT NOT NULL,
            result      TEXT NOT NULL,
            http_status INTEGER,
            dry_run     INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """)
        await conn.commit()
        # Additive migrations — safe to re-run
        for stmt in [
            "ALTER TABLE scans ADD COLUMN status_detail TEXT",
            "ALTER TABLE senders ADD COLUMN one_click_url TEXT",
            "ALTER TABLE senders ADD COLUMN mailto_links TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE senders ADD COLUMN http_links TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE senders ADD COLUMN unsubscribe_source TEXT",
            "ALTER TABLE senders ADD COLUMN latest_message_id TEXT",
            "ALTER TABLE senders ADD COLUMN latest_ts INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE senders ADD COLUMN unsubscribed_at TEXT",
            "ALTER TABLE senders ADD COLUMN unsub_method TEXT",
            "ALTER TABLE senders ADD COLUMN snooze_until TEXT",
            "ALTER TABLE action_log ADD COLUMN undo_data TEXT",
            "ALTER TABLE action_log ADD COLUMN undone INTEGER NOT NULL DEFAULT 0",
        ]:
            try:
                await conn.execute(stmt)
                await conn.commit()
            except Exception:
                pass  # column already exists

        # Backfill unsubscribed_at for senders unsubscribed before it was tracked,
        # so "still sending" verification covers them too.
        await conn.execute(
            """UPDATE senders SET
                 unsubscribed_at = (
                   SELECT replace(MIN(a.created_at), ' ', 'T') || '+00:00' FROM action_log a
                   WHERE a.sender_id = senders.id AND a.action = 'unsubscribe'
                     AND a.dry_run = 0 AND a.result NOT LIKE 'DRY RUN%'),
                 unsub_method = COALESCE(unsub_method, (
                   SELECT a.method FROM action_log a
                   WHERE a.sender_id = senders.id AND a.action = 'unsubscribe' AND a.dry_run = 0
                   ORDER BY a.id LIMIT 1))
               WHERE status = 'unsubscribed' AND unsubscribed_at IS NULL"""
        )
        await conn.commit()


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── Scan ─────────────────────────────────────────────────────────────────────

async def create_scan(since_days: int) -> int:
    async with get_conn() as conn:
        cur = await conn.execute(
            "INSERT INTO scans (started_at, since_days, phase) VALUES (?, ?, 'scanning')",
            (utcnow_iso(), since_days),
        )
        await conn.commit()
        return cur.lastrowid  # type: ignore[return-value]


async def wipe_local_data() -> None:
    """Delete all local state (senders, scans, action log). Gmail is untouched."""
    async with get_conn() as conn:
        await conn.executescript("DELETE FROM action_log; DELETE FROM senders; DELETE FROM scans;")
        await conn.commit()


async def fail_interrupted_scans() -> None:
    """Scans run in-process; any still 'running' at startup died with the last process."""
    async with get_conn() as conn:
        await conn.execute(
            "UPDATE scans SET phase = 'error', error = 'Interrupted — server restarted' "
            "WHERE phase NOT IN ('done', 'error')"
        )
        await conn.commit()


async def update_scan(scan_id: int, **fields) -> None:
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [scan_id]
    async with get_conn() as conn:
        await conn.execute(f"UPDATE scans SET {sets} WHERE id = ?", vals)
        await conn.commit()


async def get_scan(scan_id: int) -> ScanRecord | None:
    async with get_conn() as conn:
        cur = await conn.execute("SELECT * FROM scans WHERE id = ?", (scan_id,))
        row = await cur.fetchone()
        if row is None:
            return None
        return _row_to_scan(row)


async def get_latest_scan() -> ScanRecord | None:
    async with get_conn() as conn:
        cur = await conn.execute("SELECT * FROM scans ORDER BY id DESC LIMIT 1")
        row = await cur.fetchone()
        return _row_to_scan(row) if row else None


async def get_latest_completed_scan() -> ScanRecord | None:
    async with get_conn() as conn:
        cur = await conn.execute("SELECT * FROM scans WHERE phase = 'done' ORDER BY id DESC LIMIT 1")
        row = await cur.fetchone()
        return _row_to_scan(row) if row else None


def _row_to_scan(row: aiosqlite.Row) -> ScanRecord:
    d = dict(row)
    return ScanRecord(
        id=d["id"],
        started_at=datetime.fromisoformat(d["started_at"]),
        finished_at=datetime.fromisoformat(d["finished_at"]) if d["finished_at"] else None,
        since_days=d["since_days"],
        total_messages=d["total_messages"],
        total_senders=d["total_senders"],
        phase=d["phase"],
        progress_pct=d["progress_pct"],
        status_detail=d.get("status_detail"),
        error=d["error"],
    )


# ── Senders ──────────────────────────────────────────────────────────────────

_UPSERT_SQL = """INSERT INTO senders
   (id, scan_id, from_name, from_address, domain, message_count,
    first_seen, last_seen, sample_subjects, capability,
    unsubscribe_links, one_click_url, mailto_links, http_links, unsubscribe_source,
    latest_message_id, latest_ts, category, rationale, suggested_action,
    classification_degraded, decision, status, updated_at)
   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
   ON CONFLICT(id) DO UPDATE SET
     scan_id=excluded.scan_id,
     from_name=excluded.from_name,
     message_count=excluded.message_count,
     first_seen=MIN(first_seen, excluded.first_seen),
     last_seen=MAX(last_seen, excluded.last_seen),
     sample_subjects=excluded.sample_subjects,
     latest_message_id=excluded.latest_message_id,
     latest_ts=MAX(latest_ts, excluded.latest_ts),
     -- Capability and its links always move together. A scan that found
     -- nothing never wipes a body link discovered earlier.
     capability=CASE WHEN excluded.capability = 'none' AND unsubscribe_source = 'body'
                     THEN capability ELSE excluded.capability END,
     unsubscribe_links=CASE WHEN excluded.capability = 'none' AND unsubscribe_source = 'body'
                     THEN unsubscribe_links ELSE excluded.unsubscribe_links END,
     one_click_url=CASE WHEN excluded.capability = 'none' AND unsubscribe_source = 'body'
                     THEN one_click_url ELSE excluded.one_click_url END,
     mailto_links=CASE WHEN excluded.capability = 'none' AND unsubscribe_source = 'body'
                     THEN mailto_links ELSE excluded.mailto_links END,
     http_links=CASE WHEN excluded.capability = 'none' AND unsubscribe_source = 'body'
                     THEN http_links ELSE excluded.http_links END,
     unsubscribe_source=CASE WHEN excluded.capability = 'none' AND unsubscribe_source = 'body'
                     THEN unsubscribe_source ELSE excluded.unsubscribe_source END,
     category=COALESCE(excluded.category, category),
     rationale=COALESCE(excluded.rationale, rationale),
     suggested_action=COALESCE(excluded.suggested_action, suggested_action),
     classification_degraded=excluded.classification_degraded,
     updated_at=datetime('now')"""


def _sender_params(s: Sender, scan_id: int) -> tuple:
    return (
        s.id, scan_id, s.from_name, s.from_address, s.domain,
        s.message_count, s.first_seen, s.last_seen,
        json.dumps(s.sample_subjects), s.capability,
        json.dumps(s.unsubscribe_links), s.one_click_url,
        json.dumps(s.mailto_links), json.dumps(s.http_links), s.unsubscribe_source,
        s.latest_message_id, s.latest_ts,
        s.category, s.rationale, s.suggested_action, int(s.classification_degraded),
        s.decision, s.status,
    )


async def upsert_sender(sender: Sender, scan_id: int) -> None:
    await bulk_upsert_senders([sender], scan_id)


async def bulk_upsert_senders(senders: list[Sender], scan_id: int) -> None:
    async with get_conn() as conn:
        await conn.executemany(_UPSERT_SQL, [_sender_params(s, scan_id) for s in senders])
        await conn.commit()


async def get_senders_by_ids(ids: list[str]) -> dict[str, Sender]:
    if not ids:
        return {}
    async with get_conn() as conn:
        rows = await conn.execute_fetchall(
            f"SELECT * FROM senders WHERE id IN ({','.join('?' * len(ids))})", ids,
        )
        return {r["id"]: _row_to_sender(r) for r in rows}


async def save_message_unsub_methods(sender: Sender) -> None:
    """
    Store unsubscribe methods taken from one specific message (inbox view).
    Existing senders keep their scan stats — only the methods are replaced.
    Unknown senders are inserted so the action is tracked like any other.
    """
    async with get_conn() as conn:
        cur = await conn.execute(
            """UPDATE senders SET capability = ?, unsubscribe_links = ?, one_click_url = ?,
                 mailto_links = ?, http_links = ?, unsubscribe_source = ?, latest_message_id = ?,
                 latest_ts = MAX(latest_ts, ?), updated_at = datetime('now')
               WHERE id = ?""",
            (sender.capability, json.dumps(sender.unsubscribe_links), sender.one_click_url,
             json.dumps(sender.mailto_links), json.dumps(sender.http_links), sender.unsubscribe_source,
             sender.latest_message_id, sender.latest_ts, sender.id),
        )
        if cur.rowcount == 0:
            await conn.execute(_UPSERT_SQL, _sender_params(sender, None))  # type: ignore[arg-type]
        await conn.commit()


async def update_classifications(senders: list[Sender]) -> None:
    """Write only classification fields (used by re-classify, which must not touch scan data)."""
    async with get_conn() as conn:
        await conn.executemany(
            """UPDATE senders SET category = ?, rationale = ?, suggested_action = ?,
                 classification_degraded = ?, updated_at = datetime('now') WHERE id = ?""",
            [(s.category, s.rationale, s.suggested_action, int(s.classification_degraded), s.id)
             for s in senders],
        )
        await conn.commit()


async def get_all_senders(
    category: str | None = None,
    capability: str | None = None,
    decision: str | None = None,
    status: str | None = None,
    sort: str = "count",
) -> list[Sender]:
    await release_expired_snoozes()
    clauses: list[str] = []
    params: list = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if category:
        clauses.append("category = ?")
        params.append(category)
    if capability:
        clauses.append("capability = ?")
        params.append(capability)
    if decision == "undecided":
        clauses.append("decision IS NULL")
    elif decision:
        clauses.append("decision = ?")
        params.append(decision)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    order = {
        "count": "message_count DESC",
        "sender": "from_name ASC",
        "last": "last_seen DESC",
    }.get(sort, "message_count DESC")

    async with get_conn() as conn:
        rows = await conn.execute_fetchall(
            f"SELECT * FROM senders {where} ORDER BY {order}",
            params,
        )
        return [_row_to_sender(r) for r in rows]


async def get_sender(sender_id: str) -> Sender | None:
    async with get_conn() as conn:
        cur = await conn.execute("SELECT * FROM senders WHERE id = ?", (sender_id,))
        row = await cur.fetchone()
        return _row_to_sender(row) if row else None


async def update_sender_decision(sender_id: str, decision: Decision) -> None:
    async with get_conn() as conn:
        await conn.execute(
            "UPDATE senders SET decision = ?, updated_at = datetime('now') WHERE id = ?",
            (decision, sender_id),
        )
        await conn.commit()


async def update_sender_status(sender_id: str, status: str, **extra) -> None:
    """Set status plus any of: unsubscribed_at, unsub_method, snooze_until."""
    allowed = {"unsubscribed_at", "unsub_method", "snooze_until"}
    fields = {"status": status, **{k: v for k, v in extra.items() if k in allowed}}
    sets = ", ".join(f"{k} = ?" for k in fields)
    async with get_conn() as conn:
        await conn.execute(
            f"UPDATE senders SET {sets}, updated_at = datetime('now') WHERE id = ?",
            (*fields.values(), sender_id),
        )
        await conn.commit()


async def flag_still_sending(grace_days: int) -> int:
    """
    After a scan: senders who kept mailing more than `grace_days` after we
    unsubscribed become 'still_sending'. Pending (browser-submitted, unconfirmed)
    unsubscribes that stayed quiet past the grace period are promoted to
    'unsubscribed'. Returns the number newly flagged.
    """
    modifier = f"+{int(grace_days)} day"
    async with get_conn() as conn:
        cur = await conn.execute(
            """UPDATE senders SET status = 'still_sending', updated_at = datetime('now')
               WHERE status IN ('unsubscribed', 'unsub_pending')
                 AND unsubscribed_at IS NOT NULL
                 AND last_seen > date(unsubscribed_at, ?)""",
            (modifier,),
        )
        flagged = cur.rowcount
        await conn.execute(
            """UPDATE senders SET status = 'unsubscribed', updated_at = datetime('now')
               WHERE status = 'unsub_pending' AND unsubscribed_at IS NOT NULL
                 AND date('now') > date(unsubscribed_at, ?)""",
            (modifier,),
        )
        await conn.commit()
        return flagged


async def release_expired_snoozes() -> None:
    async with get_conn() as conn:
        await conn.execute(
            """UPDATE senders SET status = 'pending', decision = NULL, snooze_until = NULL
               WHERE status = 'snoozed' AND snooze_until IS NOT NULL AND snooze_until <= date('now')"""
        )
        await conn.commit()


def _row_to_sender(row: aiosqlite.Row) -> Sender:
    d = dict(row)
    return Sender(
        id=d["id"],
        from_name=d["from_name"],
        from_address=d["from_address"],
        domain=d["domain"],
        message_count=d["message_count"],
        first_seen=d["first_seen"],
        last_seen=d["last_seen"],
        sample_subjects=json.loads(d["sample_subjects"]),
        capability=d["capability"],
        unsubscribe_links=json.loads(d["unsubscribe_links"]),
        one_click_url=d.get("one_click_url"),
        mailto_links=json.loads(d.get("mailto_links") or "[]"),
        http_links=json.loads(d.get("http_links") or "[]"),
        unsubscribe_source=d.get("unsubscribe_source"),
        latest_message_id=d.get("latest_message_id"),
        latest_ts=d.get("latest_ts") or 0,
        category=d["category"],
        rationale=d["rationale"],
        suggested_action=d["suggested_action"],
        classification_degraded=bool(d["classification_degraded"]),
        decision=d["decision"],
        status=d["status"],
        unsubscribed_at=d.get("unsubscribed_at"),
        unsub_method=d.get("unsub_method"),
        snooze_until=d.get("snooze_until"),
    )


# ── Action log ───────────────────────────────────────────────────────────────

async def log_action(
    sender_id: str,
    action: str,
    method: str,
    result: str,
    dry_run: bool,
    scan_id: int | None = None,
    http_status: int | None = None,
    undo_data: dict | None = None,
) -> int:
    async with get_conn() as conn:
        cur = await conn.execute(
            """INSERT INTO action_log
               (scan_id, sender_id, action, method, result, http_status, dry_run, undo_data)
               VALUES (?,?,?,?,?,?,?,?)""",
            (scan_id, sender_id, action, method, result, http_status, int(dry_run),
             json.dumps(undo_data) if undo_data else None),
        )
        await conn.commit()
        return cur.lastrowid  # type: ignore[return-value]


async def get_action(action_id: int) -> ActionLog | None:
    async with get_conn() as conn:
        cur = await conn.execute("SELECT * FROM action_log WHERE id = ?", (action_id,))
        row = await cur.fetchone()
        return _row_to_action(row) if row else None


async def mark_action_undone(action_id: int) -> None:
    async with get_conn() as conn:
        await conn.execute("UPDATE action_log SET undone = 1 WHERE id = ?", (action_id,))
        await conn.commit()


async def get_action_log(limit: int = 500) -> list[ActionLog]:
    async with get_conn() as conn:
        rows = await conn.execute_fetchall(
            "SELECT * FROM action_log ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [_row_to_action(r) for r in rows]


def _row_to_action(r: aiosqlite.Row) -> ActionLog:
    d = dict(r)
    return ActionLog(
        id=d["id"],
        scan_id=d["scan_id"],
        sender_id=d["sender_id"],
        action=d["action"],
        method=d["method"],
        result=d["result"],
        http_status=d["http_status"],
        dry_run=bool(d["dry_run"]),
        undo_data=json.loads(d["undo_data"]) if d.get("undo_data") else None,
        undone=bool(d.get("undone") or 0),
        created_at=datetime.fromisoformat(d["created_at"]),
    )
