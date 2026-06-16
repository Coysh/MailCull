"""SQLite persistence layer (aiosqlite)."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator

import aiosqlite

from .models import ActionLog, Sender, ScanRecord

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
        ]:
            try:
                await conn.execute(stmt)
                await conn.commit()
            except Exception:
                pass  # column already exists


# ── Scan ─────────────────────────────────────────────────────────────────────

async def create_scan(since_days: int) -> int:
    async with get_conn() as conn:
        cur = await conn.execute(
            "INSERT INTO scans (started_at, since_days, phase) VALUES (?, ?, 'scanning')",
            (datetime.utcnow().isoformat(), since_days),
        )
        await conn.commit()
        return cur.lastrowid  # type: ignore[return-value]


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

async def upsert_sender(sender: Sender, scan_id: int) -> None:
    async with get_conn() as conn:
        await conn.execute(
            """INSERT INTO senders
               (id, scan_id, from_name, from_address, domain, message_count,
                first_seen, last_seen, sample_subjects, capability,
                unsubscribe_links, category, rationale, suggested_action,
                classification_degraded, decision, status, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
               ON CONFLICT(id) DO UPDATE SET
                 from_name=excluded.from_name,
                 message_count=excluded.message_count,
                 last_seen=excluded.last_seen,
                 sample_subjects=excluded.sample_subjects,
                 capability=excluded.capability,
                 unsubscribe_links=excluded.unsubscribe_links,
                 category=COALESCE(excluded.category, category),
                 rationale=COALESCE(excluded.rationale, rationale),
                 suggested_action=COALESCE(excluded.suggested_action, suggested_action),
                 classification_degraded=excluded.classification_degraded,
                 updated_at=datetime('now')""",
            (
                sender.id, scan_id, sender.from_name, sender.from_address,
                sender.domain, sender.message_count, sender.first_seen,
                sender.last_seen, json.dumps(sender.sample_subjects),
                sender.capability, json.dumps(sender.unsubscribe_links),
                sender.category, sender.rationale, sender.suggested_action,
                int(sender.classification_degraded),
                sender.decision, sender.status,
            ),
        )
        await conn.commit()


async def bulk_upsert_senders(senders: list[Sender], scan_id: int) -> None:
    async with get_conn() as conn:
        data = [
            (
                s.id, scan_id, s.from_name, s.from_address, s.domain,
                s.message_count, s.first_seen, s.last_seen,
                json.dumps(s.sample_subjects), s.capability,
                json.dumps(s.unsubscribe_links), s.category, s.rationale,
                s.suggested_action, int(s.classification_degraded),
                s.decision, s.status,
            )
            for s in senders
        ]
        await conn.executemany(
            """INSERT INTO senders
               (id, scan_id, from_name, from_address, domain, message_count,
                first_seen, last_seen, sample_subjects, capability,
                unsubscribe_links, category, rationale, suggested_action,
                classification_degraded, decision, status, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
               ON CONFLICT(id) DO UPDATE SET
                 from_name=excluded.from_name,
                 message_count=excluded.message_count,
                 last_seen=excluded.last_seen,
                 sample_subjects=excluded.sample_subjects,
                 capability=excluded.capability,
                 unsubscribe_links=excluded.unsubscribe_links,
                 category=COALESCE(excluded.category, category),
                 rationale=COALESCE(excluded.rationale, rationale),
                 suggested_action=COALESCE(excluded.suggested_action, suggested_action),
                 classification_degraded=excluded.classification_degraded,
                 updated_at=datetime('now')""",
            data,
        )
        await conn.commit()


async def get_all_senders(
    category: str | None = None,
    capability: str | None = None,
    decision: str | None = None,
    sort: str = "count",
) -> list[Sender]:
    clauses: list[str] = []
    params: list = []
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


async def update_sender_decision(sender_id: str, decision: Decision) -> None:  # type: ignore[name-defined]
    async with get_conn() as conn:
        await conn.execute(
            "UPDATE senders SET decision = ?, updated_at = datetime('now') WHERE id = ?",
            (decision, sender_id),
        )
        await conn.commit()


async def update_sender_status(sender_id: str, status: str) -> None:
    async with get_conn() as conn:
        await conn.execute(
            "UPDATE senders SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (status, sender_id),
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
        category=d["category"],
        rationale=d["rationale"],
        suggested_action=d["suggested_action"],
        classification_degraded=bool(d["classification_degraded"]),
        decision=d["decision"],
        status=d["status"],
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
) -> None:
    async with get_conn() as conn:
        await conn.execute(
            """INSERT INTO action_log
               (scan_id, sender_id, action, method, result, http_status, dry_run)
               VALUES (?,?,?,?,?,?,?)""",
            (scan_id, sender_id, action, method, result, http_status, int(dry_run)),
        )
        await conn.commit()


async def get_action_log(limit: int = 500) -> list[ActionLog]:
    async with get_conn() as conn:
        rows = await conn.execute_fetchall(
            "SELECT * FROM action_log ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return [
            ActionLog(
                id=r["id"],
                scan_id=r["scan_id"],
                sender_id=r["sender_id"],
                action=r["action"],
                method=r["method"],
                result=r["result"],
                http_status=r["http_status"],
                dry_run=bool(r["dry_run"]),
                created_at=datetime.fromisoformat(r["created_at"]),
            )
            for r in rows
        ]
