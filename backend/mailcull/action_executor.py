"""ActionExecutor — performs unsubscribes, mutes, and deletions.

Every write action:
  1. Requires explicit confirmation (the API gates this).
  2. Respects the global DRY_RUN flag — logs but never touches Gmail.
  3. Is logged to action_log with its outcome.
  4. Is idempotent where possible.
"""
from __future__ import annotations

import asyncio
import logging
import re
from email.utils import parseaddr
from typing import Any
from urllib.parse import parse_qs, urlparse

import aiohttp
from googleapiclient.errors import HttpError

from . import db
from .models import ActionPreview, ActionResult, Decision, Sender

logger = logging.getLogger(__name__)

_ONE_CLICK_TIMEOUT = aiohttp.ClientTimeout(total=15)
_MAX_TRASH_BATCH = 50


class ActionExecutor:
    def __init__(self, gmail_service: Any, dry_run: bool) -> None:
        self._svc = gmail_service
        self._dry_run = dry_run

    # ── Preview ───────────────────────────────────────────────────────────────

    @staticmethod
    def preview(senders: list[Sender]) -> list[ActionPreview]:
        results: list[ActionPreview] = []
        for s in senders:
            method, description, can_automate, needs_manual = _plan_action(s)
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

    async def execute(self, senders: list[Sender]) -> list[ActionResult]:
        results: list[ActionResult] = []
        for s in senders:
            result = await self._execute_one(s)
            results.append(result)
            await db.update_sender_status(s.id, result.status)
            await db.log_action(
                sender_id=s.id,
                action=s.decision or "none",
                method=result.method,
                result=result.detail,
                dry_run=self._dry_run,
            )
        return results

    async def _execute_one(self, sender: Sender) -> ActionResult:
        decision = sender.decision
        if decision == "keep":
            return _ok(sender, "keep", "no-op", "no action", can_undo=False)
        if decision == "transactional":
            return _ok(sender, "label", "tagged", "tagged + kept", can_undo=False)
        if decision == "snooze":
            return _ok(sender, "local", "snoozed", "snoozed", can_undo=False)
        if decision == "unsubscribe":
            return await self._unsubscribe(sender)
        if decision == "mute":
            return await self._mute(sender)
        if decision == "archive":
            return await self._archive(sender)
        if decision == "delete":
            return await self._delete(sender)
        return _err(sender, "unknown", f"Unknown decision: {decision}")

    # ── Unsubscribe ───────────────────────────────────────────────────────────

    async def _unsubscribe(self, sender: Sender) -> ActionResult:
        cap = sender.capability
        links = sender.unsubscribe_links

        if cap == "one_click":
            https_links = [l for l in links if l.startswith("https://")]
            if not https_links:
                return _err(sender, "one_click", "No HTTPS link for one-click")
            target = https_links[0]
            if self._dry_run:
                return _ok(sender, "one_click", "unsubscribed", f"DRY RUN POST {target}", can_undo=True)
            return await self._http_post_unsubscribe(sender, target)

        if cap == "link":
            target = next((l for l in links if l.startswith("http")), links[0] if links else "")
            return ActionResult(
                sender_id=sender.id,
                from_name=sender.from_name,
                from_address=sender.from_address,
                decision="unsubscribe",
                method="link",
                status="needs_link",
                detail=target,
                can_undo=False,
                link=target,
            )

        if cap == "mailto":
            mailto = next((l for l in links if l.startswith("mailto:")), None)
            if not mailto:
                return _err(sender, "mailto", "No mailto link found")
            if self._dry_run:
                return _ok(sender, "mailto", "unsubscribed", f"DRY RUN mailto {mailto}", can_undo=True)
            return await self._send_mailto(sender, mailto)

        # capability == "none" — should have been caught at preview but handle gracefully
        return _err(sender, "none", "No unsubscribe path — use Mute instead")

    async def _http_post_unsubscribe(self, sender: Sender, url: str) -> ActionResult:
        try:
            async with aiohttp.ClientSession(timeout=_ONE_CLICK_TIMEOUT) as session:
                async with session.post(
                    url,
                    data="List-Unsubscribe=One-Click",
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    allow_redirects=True,
                ) as resp:
                    status = resp.status
                    if status < 400:
                        return _ok(
                            sender, "one_click", "unsubscribed",
                            f"POST {status}", can_undo=True,
                        )
                    return _err(sender, "one_click", f"HTTP {status}", http_status=status)
        except asyncio.TimeoutError:
            return _err(sender, "one_click", "Timeout")
        except Exception as exc:
            return _err(sender, "one_click", str(exc))

    async def _send_mailto(self, sender: Sender, mailto: str) -> ActionResult:
        """Send a mailto unsubscribe via Gmail API (requires gmail.send scope)."""
        try:
            parsed = urlparse(mailto)
            to_addr = parsed.path
            params = parse_qs(parsed.query)
            subject = params.get("subject", ["Unsubscribe"])[0]
            body = params.get("body", ["Please unsubscribe me."])[0]

            import base64
            from email.mime.text import MIMEText
            msg = MIMEText(body)
            msg["To"] = to_addr
            msg["Subject"] = subject
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

            await asyncio.to_thread(
                self._svc.users().messages().send(
                    userId="me", body={"raw": raw}
                ).execute
            )
            return _ok(sender, "mailto", "unsubscribed", f"Email sent to {to_addr}", can_undo=False)
        except HttpError as exc:
            if exc.status_code == 403:
                return _err(sender, "mailto", "gmail.send scope not granted")
            return _err(sender, "mailto", str(exc))
        except Exception as exc:
            return _err(sender, "mailto", str(exc))

    # ── Mute ─────────────────────────────────────────────────────────────────

    async def _mute(self, sender: Sender, mute_action: str = "archive") -> ActionResult:
        """Create a Gmail filter that archives or trashes future mail from this sender."""
        if self._dry_run:
            return _ok(
                sender, "filter", "muted",
                f"DRY RUN: filter from:{sender.domain}", can_undo=True,
            )
        try:
            criteria = {"from": sender.from_address}
            action_body: dict = {}
            if mute_action == "trash":
                action_body = {"addLabelIds": ["TRASH"]}
            else:
                action_body = {"removeLabelIds": ["INBOX"]}

            filter_body = {"criteria": criteria, "action": action_body}
            await asyncio.to_thread(
                self._svc.users().settings().filters().create(
                    userId="me", body=filter_body
                ).execute
            )
            return _ok(
                sender, "filter", "muted",
                f"filter: from:{sender.from_address}", can_undo=True,
            )
        except HttpError as exc:
            return _err(sender, "filter", f"Filter create failed: {exc}")
        except Exception as exc:
            return _err(sender, "filter", str(exc))

    # ── Archive ───────────────────────────────────────────────────────────────

    async def _archive(self, sender: Sender) -> ActionResult:
        """Remove INBOX label from all messages — moves to All Mail."""
        if self._dry_run:
            return _ok(
                sender, "archive", "archived",
                f"DRY RUN: archive {sender.message_count} messages", can_undo=True,
            )
        try:
            resp = await asyncio.to_thread(
                self._svc.users().messages().list(
                    userId="me", q=f"from:{sender.from_address} in:inbox", maxResults=500
                ).execute
            )
            ids = [m["id"] for m in resp.get("messages", [])]
            if not ids:
                return _ok(sender, "archive", "archived", "no inbox messages found", can_undo=False)

            for i in range(0, len(ids), _MAX_TRASH_BATCH):
                chunk = ids[i : i + _MAX_TRASH_BATCH]
                await asyncio.to_thread(
                    self._svc.users().messages().batchModify(
                        userId="me", body={"ids": chunk, "removeLabelIds": ["INBOX"]}
                    ).execute
                )

            return _ok(sender, "archive", "archived", f"{len(ids)} → Archive", can_undo=True)
        except HttpError as exc:
            return _err(sender, "archive", f"API error: {exc}")
        except Exception as exc:
            return _err(sender, "archive", str(exc))

    # ── Delete ────────────────────────────────────────────────────────────────

    async def _delete(self, sender: Sender) -> ActionResult:
        """Trash (or permanently delete) all messages from this sender."""
        if self._dry_run:
            return _ok(
                sender, "trash", "deleted",
                f"DRY RUN: trash {sender.message_count} messages", can_undo=True,
            )
        try:
            # Fetch IDs for messages from this sender
            query = f"from:{sender.from_address}"
            resp = await asyncio.to_thread(
                self._svc.users().messages().list(
                    userId="me", q=query, maxResults=500
                ).execute
            )
            ids = [m["id"] for m in resp.get("messages", [])]
            if not ids:
                return _ok(sender, "trash", "deleted", "no messages found", can_undo=False)

            # Batch trash in chunks
            count = 0
            for i in range(0, len(ids), _MAX_TRASH_BATCH):
                chunk = ids[i : i + _MAX_TRASH_BATCH]
                body = {"ids": chunk, "addLabelIds": ["TRASH"]}
                await asyncio.to_thread(
                    self._svc.users().messages().batchModify(
                        userId="me", body=body
                    ).execute
                )
                count += len(chunk)

            return _ok(
                sender, "trash", "deleted",
                f"{count} → Trash", can_undo=True,
            )
        except HttpError as exc:
            return _err(sender, "trash", f"API error: {exc}")
        except Exception as exc:
            return _err(sender, "trash", str(exc))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _plan_action(s: Sender) -> tuple[str, str, bool, bool]:
    """Return (method, description, can_automate, needs_manual)."""
    d = s.decision
    if d == "keep":
        return "no-op", "No action taken", True, False
    if d == "transactional":
        return "label", "Tagged as transactional and kept", True, False
    if d == "snooze":
        return "local", "Snoozed — will re-surface later", True, False
    if d == "mute":
        return "filter", f"Create Gmail filter: from:{s.from_address}", True, False
    if d == "archive":
        return "archive", f"Archive inbox messages from {s.from_address}", True, False
    if d == "delete":
        return "trash", f"Trash {s.message_count} messages from {s.from_address}", True, False
    if d == "unsubscribe":
        cap = s.capability
        if cap == "one_click":
            return "one_click", "POST to List-Unsubscribe-Post endpoint", True, False
        if cap == "link":
            link = s.unsubscribe_links[0] if s.unsubscribe_links else "unknown"
            return "link", f"Open {link} and complete manually", False, True
        if cap == "mailto":
            return "mailto", "Send unsubscribe email via Gmail API", True, False
        return "none", "No unsubscribe path — use Mute", False, False
    return "none", "No action", False, False


def _ok(
    sender: Sender,
    method: str,
    status: str,
    detail: str,
    can_undo: bool,
    http_status: int | None = None,
) -> ActionResult:
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


def _err(
    sender: Sender,
    method: str,
    error: str,
    http_status: int | None = None,
) -> ActionResult:
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
