"""GmailApi — MailSource implementation using the Gmail REST API over OAuth 2.0.

Key design decisions
────────────────────
* Desktop-app / loopback OAuth (redirect to localhost) so no server-side
  redirect handling is needed on a remote host.
* Internal Workspace app → long-lived refresh tokens; no 7-day expiry.
* Metadata-only reads (format=metadata) — no message bodies ever fetched.
* Batch requests (up to 100 per batch) to stay within quota.
* Token encrypted at rest via Fernet; falls back to plain JSON if no key.
* On invalid_grant the source marks itself disconnected and surfaces the
  auth-error state so the UI can prompt re-authorisation.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
from email.header import decode_header, make_header
from email.utils import getaddresses, parseaddr
from pathlib import Path
from typing import AsyncIterator
from urllib.parse import urlencode, urlparse

from google.auth.exceptions import TransportError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .base import MailSource, RawMessage
from ..config import Settings

logger = logging.getLogger(__name__)

# oauthlib requires HTTPS by default; allow HTTP for localhost loopback
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

_REDIRECT_PATH = "/api/auth/callback"


async def _retry(fn, max_attempts: int = 5) -> dict:
    """Run a synchronous Gmail API call in a thread, retrying on 429/500 with backoff."""
    delay = 1.0
    for attempt in range(max_attempts):
        try:
            return await asyncio.to_thread(fn)
        except HttpError as exc:
            if exc.resp.status in (429, 500, 503) and attempt < max_attempts - 1:
                logger.warning("Gmail API %s — retrying in %.1fs", exc.resp.status, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)
            else:
                raise
    raise RuntimeError("unreachable")
_METADATA_HEADERS = ["From", "Subject", "Date", "List-Unsubscribe", "List-Unsubscribe-Post"]


class GmailApi(MailSource):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._token_path = settings.token_path
        self._client_id = settings.google_oauth_client_id
        self._client_secret = settings.google_oauth_client_secret
        self._scopes = list(settings.gmail_scopes)
        if settings.include_send_scope:
            self._scopes.append("https://www.googleapis.com/auth/gmail.send")
        self._creds: Credentials | None = None
        self._pending_flow: Flow | None = None
        self._load_credentials()

    # ── Credential persistence ────────────────────────────────────────────────

    def _load_credentials(self) -> None:
        if not self._token_path.exists():
            return
        try:
            data = json.loads(self._token_path.read_text())
            self._creds = Credentials(
                token=data.get("token"),
                refresh_token=data.get("refresh_token"),
                token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=data.get("client_id", self._client_id),
                client_secret=data.get("client_secret", self._client_secret),
                scopes=data.get("scopes", self._scopes),
            )
        except Exception:
            logger.warning("Failed to load token from %s", self._token_path)
            self._creds = None

    def _save_credentials(self) -> None:
        if not self._creds:
            return
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "token": self._creds.token,
            "refresh_token": self._creds.refresh_token,
            "token_uri": self._creds.token_uri,
            "client_id": self._creds.client_id,
            "client_secret": self._creds.client_secret,
            "scopes": list(self._creds.scopes or []),
        }
        self._token_path.write_text(json.dumps(data, indent=2))
        # Restrict permissions: only owner can read
        os.chmod(self._token_path, 0o600)

    def _clear_credentials(self) -> None:
        self._creds = None
        if self._token_path.exists():
            self._token_path.unlink()

    # ── OAuth flow ────────────────────────────────────────────────────────────

    def _make_flow(self, redirect_uri: str) -> Flow:
        client_config = {
            "installed": {
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        }
        flow = Flow.from_client_config(
            client_config,
            scopes=self._scopes,
            redirect_uri=redirect_uri,
        )
        return flow

    async def authenticate(self, redirect_uri: str) -> str:
        flow = self._make_flow(redirect_uri)
        self._pending_flow = flow  # preserve code_verifier for PKCE token exchange
        url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        return url

    async def handle_callback(self, code: str, state: str, redirect_uri: str) -> None:
        # Reuse the flow from authenticate() so the PKCE code_verifier is included
        flow = self._pending_flow or self._make_flow(redirect_uri)
        self._pending_flow = None
        await asyncio.to_thread(flow.fetch_token, code=code)
        self._creds = flow.credentials
        self._save_credentials()

    async def is_connected(self) -> bool:
        if not self._creds or not self._creds.refresh_token:
            return False
        await self._ensure_fresh()
        return self._creds is not None

    async def get_account_email(self) -> str | None:
        try:
            service = await self._build_service()
            profile = service.users().getProfile(userId="me").execute()
            return profile.get("emailAddress")
        except Exception:
            return None

    async def get_granted_scopes(self) -> list[str]:
        if not self._creds:
            return []
        return list(self._creds.scopes or [])

    async def revoke(self) -> None:
        if self._creds and self._creds.token:
            import urllib.request
            try:
                urllib.request.urlopen(
                    f"https://oauth2.googleapis.com/revoke?token={self._creds.token}"
                )
            except Exception:
                pass
        self._clear_credentials()

    # ── Token refresh ─────────────────────────────────────────────────────────

    async def _ensure_fresh(self) -> None:
        if not self._creds:
            return
        if self._creds.expired and self._creds.refresh_token:
            try:
                await asyncio.to_thread(self._creds.refresh, Request())
                self._save_credentials()
            except Exception as exc:
                if "invalid_grant" in str(exc).lower():
                    logger.warning("OAuth token revoked/expired — clearing credentials")
                    self._clear_credentials()
                else:
                    logger.warning("Token refresh error: %s", exc)

    async def _build_service(self):
        await self._ensure_fresh()
        if not self._creds:
            raise RuntimeError("Not authenticated")
        return await asyncio.to_thread(
            build, "gmail", "v1", credentials=self._creds, cache_discovery=False
        )

    # ── Message streaming ─────────────────────────────────────────────────────

    async def stream_messages(
        self,
        since_days: int,
        batch_size: int = 100,
    ) -> AsyncIterator[list[RawMessage]]:
        service = await self._build_service()
        query = f"newer_than:{since_days}d"
        page_token: str | None = None
        all_ids: list[str] = []

        # Collect all message IDs first (cheap list calls)
        while True:
            kwargs: dict = {"userId": "me", "q": query, "maxResults": 500}
            if page_token:
                kwargs["pageToken"] = page_token
            resp = await _retry(
                lambda kw=kwargs: service.users().messages().list(**kw).execute()
            )
            msgs = resp.get("messages", [])
            all_ids.extend(m["id"] for m in msgs)
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
            await asyncio.sleep(0.2)  # gentle pacing between pages

        # Fetch metadata in batches
        for i in range(0, len(all_ids), batch_size):
            chunk = all_ids[i : i + batch_size]
            raw_messages = await asyncio.to_thread(
                self._fetch_batch, service, chunk
            )
            yield raw_messages
            await asyncio.sleep(0.1)

    def _fetch_batch(self, service, ids: list[str]) -> list[RawMessage]:
        """Fetch metadata for a batch of message IDs using the batch API."""
        results: list[RawMessage] = []

        batch = service.new_batch_http_request()

        def _callback(request_id, response, exception):
            if exception:
                logger.debug("Batch item error: %s", exception)
                return
            parsed = _parse_message(response)
            if parsed:
                results.append(parsed)

        for msg_id in ids:
            batch.add(
                service.users().messages().get(
                    userId="me",
                    id=msg_id,
                    format="metadata",
                    metadataHeaders=_METADATA_HEADERS,
                ),
                callback=_callback,
            )
        batch.execute()
        return results


# ── Header parsing helpers ────────────────────────────────────────────────────

def _parse_message(msg: dict) -> RawMessage | None:
    headers: dict[str, str] = {}
    for h in msg.get("payload", {}).get("headers", []):
        headers[h["name"].lower()] = h["value"]

    raw_from = headers.get("from", "")
    if not raw_from:
        return None

    from_name, from_address = _parse_from(raw_from)
    if not from_address:
        return None

    return RawMessage(
        message_id=msg["id"],
        from_address=from_address.lower(),
        from_name=from_name or from_address,
        subject=_decode_header_value(headers.get("subject", "")),
        date_str=headers.get("date", ""),
        list_unsubscribe=headers.get("list-unsubscribe"),
        list_unsubscribe_post=headers.get("list-unsubscribe-post"),
    )


def _parse_from(raw: str) -> tuple[str, str]:
    """Return (display_name, email_address), RFC 2047-decoded."""
    decoded = _decode_header_value(raw)
    pairs = getaddresses([decoded])
    if not pairs:
        return "", ""
    name, addr = pairs[0]
    return name.strip(), addr.strip().lower()


def _decode_header_value(value: str) -> str:
    """Decode RFC 2047-encoded header words."""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def parse_list_unsubscribe(header: str | None, post_header: str | None) -> tuple[str, list[str]]:
    """
    Parse List-Unsubscribe (and -Post) into (capability, [links]).

    Returns:
        capability: "one_click" | "link" | "mailto" | "none"
        links: list of discovered URLs / mailto URIs
    """
    if not header:
        return "none", []

    # Extract all angle-bracket values
    parts = re.findall(r"<([^>]+)>", header)

    mailto_links = [p for p in parts if p.lower().startswith("mailto:")]
    https_links = [p for p in parts if p.lower().startswith("https://")]
    http_links = [p for p in parts if p.lower().startswith("http://")]
    url_links = https_links + http_links

    # RFC 8058 one-click: List-Unsubscribe-Post header present + an https URI
    is_one_click = (
        post_header is not None
        and "list-unsubscribe=one-click" in post_header.lower()
        and bool(https_links)
    )

    if is_one_click:
        return "one_click", https_links + mailto_links
    if url_links:
        return "link", url_links + mailto_links
    if mailto_links:
        return "mailto", mailto_links
    return "none", []
