"""ActionExecutor — performs unsubscribes, mutes, archives, deletions.

Every write action:
  1. Requires explicit confirmation (the API gates this).
  2. Respects DRY_RUN — logs the plan but never touches Gmail or the sender's status.
  3. Is logged to action_log with its outcome (and undo data where possible).
  4. Is idempotent: senders already handled are skipped unless forced.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any

from googleapiclient.errors import HttpError

from . import db
from .models import DONE_STATUSES, ActionPreview, ActionResult, Sender
from .unsubscribe import UnsubContext, plan_chain, unsubscribe

logger = logging.getLogger(__name__)

_MODIFY_CHUNK = 1000  # batchModify limit
_TRANSACTIONAL_LABEL = "MailCull/Transactional"


class ActionExecutor:
    def __init__(
        self,
        gmail_service: Any,
        dry_run: bool,
        granted_scopes: list[str] | None = None,
        account_email: str | None = None,
        browser: Any = None,
        browser_available: bool = False,
        mute_action: str = "archive",
        snooze_days: int = 30,
    ) -> None:
        self._svc = gmail_service
        self._dry_run = dry_run
        self._unsub_ctx = UnsubContext(
            gmail_service=gmail_service,
            dry_run=dry_run,
            granted_scopes=granted_scopes or [],
            account_email=account_email,
            browser=browser,
            browser_available=browser_available,
        )
        self._mute_action = mute_action
        self._snooze_days = snooze_days

    # ── Preview ───────────────────────────────────────────────────────────────

    @staticmethod
    def preview(
        senders: list[Sender], can_send: bool = True, browser_available: bool = True,
    ) -> list[ActionPreview]:
        results: list[ActionPreview] = []
        for s in senders:
            method, description, can_automate, needs_manual = _plan_action(s, can_send, browser_available)
            results.append(
                ActionPreview(
                    sender_id=s.id,
                    from_name=s.from_name,
                    from_address=s.from_address,
                    decision=s.decision,
                    method=method,
                    description=description,
                    can_automate=can_automate,
                    needs_manual=needs_manual,
                )
            )
        return results

    # ── Execute ───────────────────────────────────────────────────────────────

    async def execute(self, senders: list[Sender], force: bool = False) -> list[ActionResult]:
        results: list[ActionResult] = []
        for s in senders:
            if not force and s.status in DONE_STATUSES:
                results.append(_skipped(s))
                continue
            try:
                result, extra, undo = await self._execute_one(s)
            except Exception as exc:  # never let one sender abort the batch
                logger.exception("Action failed for %s", s.from_address)
                result, extra, undo = _err(s, s.decision or "unknown", str(exc)[:200]), {}, None

            action_id = await db.log_action(
                sender_id=s.id,
                action=s.decision or "none",
                method=result.method,
                result=result.detail,
                dry_run=self._dry_run,
                http_status=result.http_status,
                undo_data=undo,
            )
            result.action_id = action_id
            result.can_undo = result.can_undo and undo is not None and not self._dry_run
            if not self._dry_run:
                await db.update_sender_status(s.id, result.status, **extra)
            results.append(result)
        return results

    async def _execute_one(self, sender: Sender) -> tuple[ActionResult, dict, dict | None]:
        d = sender.decision
        if d == "keep":
            return _ok(sender, "no-op", "kept", "no action"), {}, None
        if d == "transactional":
            return await self._label_transactional(sender)
        if d == "snooze":
            until = (date.today() + timedelta(days=self._snooze_days)).isoformat()
            return _ok(sender, "local", "snoozed", f"hidden until {until}"), {"snooze_until": until}, None
        if d == "unsubscribe":
            return await self._unsubscribe(sender)
        if d == "mute":
            return await self._mute(sender)
        if d == "archive":
            return await self._archive(sender)
        if d == "delete":
            return await self._delete(sender)
        return _err(sender, "unknown", f"Unknown decision: {d}"), {}, None

    # ── Unsubscribe ───────────────────────────────────────────────────────────

    async def _unsubscribe(self, sender: Sender) -> tuple[ActionResult, dict, dict | None]:
        out = await unsubscribe(sender, self._unsub_ctx)
        result = ActionResult(
            sender_id=sender.id,
            from_name=sender.from_name,
            from_address=sender.from_address,
            decision="unsubscribe",
            method=out.method,
            status=out.status,
            detail=out.detail,
            can_undo=False,
            link=out.link if out.status in ("needs_link", "unsub_pending") else None,
            error=out.detail if out.status == "failed" else None,
            http_status=out.http_status,
            attempts=out.attempts,
        )
        extra: dict = {}
        if out.status in ("unsubscribed", "unsub_pending"):
            extra = {"unsubscribed_at": db.utcnow_iso(), "unsub_method": out.method}
        return result, extra, None

    # ── Mute ─────────────────────────────────────────────────────────────────

    async def _mute(self, sender: Sender) -> tuple[ActionResult, dict, dict | None]:
        """Create a Gmail filter that archives (or trashes) future mail from this sender."""
        verb = "trash" if self._mute_action == "trash" else "skip inbox"
        if self._dry_run:
            return _ok(sender, "filter", "muted", f"DRY RUN: filter from:{sender.from_address} → {verb}"), {}, None
        action_body = (
            {"addLabelIds": ["TRASH"]} if self._mute_action == "trash"
            else {"removeLabelIds": ["INBOX"]}
        )
        filter_body = {"criteria": {"from": sender.from_address}, "action": action_body}
        try:
            created = await asyncio.to_thread(
                self._svc.users().settings().filters().create(userId="me", body=filter_body).execute
            )
        except HttpError as exc:
            if exc.status_code == 400 and "exists" in str(exc).lower():
                return _ok(sender, "filter", "muted", f"filter already exists: from:{sender.from_address}"), {}, None
            return _err(sender, "filter", f"Filter create failed: {_api_msg(exc)}"), {}, None
        result = _ok(sender, "filter", "muted", f"filter: from:{sender.from_address} → {verb}", can_undo=True)
        return result, {}, {"filter_id": created.get("id")}

    # ── Archive ───────────────────────────────────────────────────────────────

    async def _archive(self, sender: Sender) -> tuple[ActionResult, dict, dict | None]:
        """Remove INBOX label from every message — moves to All Mail."""
        if self._dry_run:
            return _ok(sender, "archive", "archived", f"DRY RUN: archive inbox mail from {sender.from_address}"), {}, None
        try:
            ids = await self._list_ids(f"from:{sender.from_address} in:inbox")
            if not ids:
                return _ok(sender, "archive", "archived", "no inbox messages found"), {}, None
            await self._batch_modify(ids, remove=["INBOX"])
        except HttpError as exc:
            return _err(sender, "archive", f"API error: {_api_msg(exc)}"), {}, None
        return (
            _ok(sender, "archive", "archived", f"{len(ids):,} → Archive", can_undo=True),
            {},
            {"message_ids": ids},
        )

    # ── Delete ────────────────────────────────────────────────────────────────

    async def _delete(self, sender: Sender) -> tuple[ActionResult, dict, dict | None]:
        """Move every message from this sender to Trash (recoverable for 30 days)."""
        if self._dry_run:
            return _ok(sender, "trash", "deleted", f"DRY RUN: trash ~{sender.message_count:,} messages"), {}, None
        try:
            ids = await self._list_ids(f"from:{sender.from_address}")
            if not ids:
                return _ok(sender, "trash", "deleted", "no messages found"), {}, None
            await self._batch_modify(ids, add=["TRASH"])
        except HttpError as exc:
            return _err(sender, "trash", f"API error: {_api_msg(exc)}"), {}, None
        return (
            _ok(sender, "trash", "deleted", f"{len(ids):,} → Trash", can_undo=True),
            {},
            {"message_ids": ids},
        )

    # ── Transactional label ───────────────────────────────────────────────────

    async def _label_transactional(self, sender: Sender) -> tuple[ActionResult, dict, dict | None]:
        if self._dry_run:
            return _ok(sender, "label", "transactional", f"DRY RUN: label {_TRANSACTIONAL_LABEL}"), {}, None
        try:
            label_id = await self._ensure_label(_TRANSACTIONAL_LABEL)
            ids = await self._list_ids(f"from:{sender.from_address}")
            if ids:
                await self._batch_modify(ids, add=[label_id])
        except HttpError as exc:
            return _err(sender, "label", f"API error: {_api_msg(exc)}"), {}, None
        return (
            _ok(sender, "label", "transactional", f"{len(ids):,} labelled {_TRANSACTIONAL_LABEL}", can_undo=bool(ids)),
            {},
            {"message_ids": ids, "label_id": label_id} if ids else None,
        )

    # ── Undo ──────────────────────────────────────────────────────────────────

    async def undo(self, action_id: int) -> str:
        entry = await db.get_action(action_id)
        if entry is None:
            raise ValueError("Action not found")
        if entry.undone:
            raise ValueError("Already undone")
        if entry.dry_run or not entry.undo_data:
            raise ValueError("This action can't be undone")
        data = entry.undo_data
        if entry.action == "mute":
            await asyncio.to_thread(
                self._svc.users().settings().filters().delete(userId="me", id=data["filter_id"]).execute
            )
            detail = "filter removed"
        elif entry.action == "archive":
            await self._batch_modify(data["message_ids"], add=["INBOX"])
            detail = f"{len(data['message_ids']):,} moved back to Inbox"
        elif entry.action == "delete":
            await self._batch_untrash(data["message_ids"])
            detail = f"{len(data['message_ids']):,} restored from Trash"
        elif entry.action == "transactional":
            await self._batch_modify(data["message_ids"], remove=[data["label_id"]])
            detail = "label removed"
        else:
            raise ValueError("This action can't be undone")
        await db.mark_action_undone(action_id)
        await db.update_sender_status(entry.sender_id, "pending")
        await db.update_sender_decision(entry.sender_id, None)
        return detail

    # ── Gmail helpers ─────────────────────────────────────────────────────────

    async def _list_ids(self, query: str) -> list[str]:
        ids: list[str] = []
        page_token: str | None = None
        while True:
            kwargs: dict = {"userId": "me", "q": query, "maxResults": 500, "includeSpamTrash": False}
            if page_token:
                kwargs["pageToken"] = page_token
            resp = await asyncio.to_thread(self._svc.users().messages().list(**kwargs).execute)
            ids.extend(m["id"] for m in resp.get("messages", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                return ids

    async def _batch_modify(self, ids: list[str], add: list[str] | None = None, remove: list[str] | None = None) -> None:
        for i in range(0, len(ids), _MODIFY_CHUNK):
            body: dict = {"ids": ids[i : i + _MODIFY_CHUNK]}
            if add:
                body["addLabelIds"] = add
            if remove:
                body["removeLabelIds"] = remove
            await asyncio.to_thread(self._svc.users().messages().batchModify(userId="me", body=body).execute)

    async def _batch_untrash(self, ids: list[str]) -> None:
        # messages.untrash restores each message's previous labels
        for i in range(0, len(ids), 100):
            batch = self._svc.new_batch_http_request()
            for mid in ids[i : i + 100]:
                batch.add(self._svc.users().messages().untrash(userId="me", id=mid))
            await asyncio.to_thread(batch.execute)

    async def _ensure_label(self, name: str) -> str:
        resp = await asyncio.to_thread(self._svc.users().labels().list(userId="me").execute)
        for label in resp.get("labels", []):
            if label.get("name") == name:
                return label["id"]
        created = await asyncio.to_thread(
            self._svc.users().labels().create(
                userId="me",
                body={"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"},
            ).execute
        )
        return created["id"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _plan_action(s: Sender, can_send: bool = True, browser_available: bool = True) -> tuple[str, str, bool, bool]:
    """Return (method, description, can_automate, needs_manual)."""
    d = s.decision
    if d == "keep":
        return "no-op", "No action taken", True, False
    if d == "transactional":
        return "label", f"Label existing mail {_TRANSACTIONAL_LABEL} and keep", True, False
    if d == "snooze":
        return "local", "Snoozed — will re-surface later", True, False
    if d == "mute":
        return "filter", f"Create Gmail filter: from:{s.from_address}", True, False
    if d == "archive":
        return "archive", f"Archive inbox messages from {s.from_address}", True, False
    if d == "delete":
        return "trash", f"Trash all messages from {s.from_address}", True, False
    if d == "unsubscribe":
        steps = plan_chain(s, can_send, browser_available)
        if not steps:
            return "none", "No unsubscribe method found — use Mute", False, False
        # A plain GET ("check …") only occasionally completes an opt-out, so it doesn't count
        automated = [
            x for x in steps
            if x != "manual link" and "needs gmail.send" not in x and not x.startswith("check ")
        ]
        method = (
            "one_click" if s.one_click_url
            else "mailto" if s.mailto_links and can_send
            else "browser" if browser_available and automated
            else "link"
        )
        return method, " → ".join(steps), bool(automated), not automated
    return "none", "No action", False, False


def _ok(sender: Sender, method: str, status: str, detail: str, can_undo: bool = False) -> ActionResult:
    return ActionResult(
        sender_id=sender.id,
        from_name=sender.from_name,
        from_address=sender.from_address,
        decision=sender.decision,
        method=method,
        status=status,  # type: ignore[arg-type]
        detail=detail,
        can_undo=can_undo,
    )


def _err(sender: Sender, method: str, error: str) -> ActionResult:
    return ActionResult(
        sender_id=sender.id,
        from_name=sender.from_name,
        from_address=sender.from_address,
        decision=sender.decision,
        method=method,
        status="failed",
        detail=error,
        can_undo=False,
        error=error,
    )


def _skipped(sender: Sender) -> ActionResult:
    return ActionResult(
        sender_id=sender.id,
        from_name=sender.from_name,
        from_address=sender.from_address,
        decision=sender.decision,
        method="skip",
        status=sender.status,
        detail=f"already {sender.status.replace('_', ' ')} — skipped",
        can_undo=False,
        skipped=True,
    )


def _api_msg(exc: HttpError) -> str:
    try:
        return exc.reason or str(exc)
    except Exception:
        return str(exc)
