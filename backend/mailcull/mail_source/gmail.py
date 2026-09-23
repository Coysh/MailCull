"""GmailApi — MailSource implementation using the Gmail REST API over OAuth 2.0.

Key design decisions
────────────────────
* Desktop-app / loopback OAuth (redirect to localhost) so no server-side
  redirect handling is needed on a remote host.
* Internal Workspace app → long-lived refresh tokens; no 7-day expiry.
* Metadata-only reads (format=metadata) — no message bodies ever fetched.
* Batch requests (up to 100 per batch) to stay within quota.
* Token encrypted at rest via Fernet (key from TOKEN_ENCRYPTION_KEY or an
  auto-generated key file next to the token).
* On invalid_grant the source marks itself disconnected and surfaces the
  auth-error state so the UI can prompt re-authorisation.
"""
from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import re
from dataclasses import dataclass, field
from email.header import decode_header, make_header
from email.utils import getaddresses
from typing import AsyncIterator, Awaitable, Callable

import aiohttp
import httplib2
from cryptography.fernet import Fernet, InvalidToken
from google.auth.transport.requests import Request
from google_auth_httplib2 import AuthorizedHttp
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .base import MailSource, RawMessage
from .body_links import body_parts_from_payload, extract_unsubscribe_links
from ..config import Settings

logger = logging.getLogger(__name__)

# oauthlib requires HTTPS by default; allow HTTP for localhost loopback
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

_REDIRECT_PATH = "/api/auth/callback"


# Gmail allows 15,000 quota units per user per minute; messages.get costs 5.
# Stay around 1,500 gets/min (half the limit) so batches are rarely throttled.
_GETS_PER_SECOND = 25
_HTTP_TIMEOUT_S = 60


async def _retry(fn, max_attempts: int = 7) -> dict:
    """Run a synchronous Gmail API call in a thread, retrying rate limits/5xx with backoff."""
    delay = 2.0
    for attempt in range(max_attempts):
        try:
            return await asyncio.to_thread(fn)
        except (HttpError, *_NETWORK_ERRORS) as exc:
            if _is_retriable(exc) and attempt < max_attempts - 1:
                logger.warning("Gmail API %s — retrying in %.1fs",
                               getattr(getattr(exc, "resp", None), "status", exc.__class__.__name__), delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)
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
        self._pending_state: str | None = None
        self._account_email: str | None = None
        self._load_credentials()

    # ── Credential persistence ────────────────────────────────────────────────

    def _fernet(self) -> Fernet | None:
        key = self._settings.token_encryption_key
        if not key:
            key_path = self._token_path.parent / ".token.key"
            try:
                if key_path.exists():
                    key = key_path.read_text().strip()
                else:
                    key_path.parent.mkdir(parents=True, exist_ok=True)
                    key = Fernet.generate_key().decode()
                    key_path.write_text(key)
                    os.chmod(key_path, 0o600)
            except OSError as exc:
                logger.warning("Token key unavailable (%s) — token stored unencrypted", exc)
                return None
        try:
            return Fernet(key.encode() if isinstance(key, str) else key)
        except Exception:
            logger.warning("TOKEN_ENCRYPTION_KEY is not a valid Fernet key — token stored unencrypted")
            return None

    def _load_credentials(self) -> None:
        if not self._token_path.exists():
            return
        try:
            blob = self._token_path.read_bytes()
            fernet = self._fernet()
            migrate_plaintext = False
            try:
                text = fernet.decrypt(blob).decode() if fernet else blob.decode()
            except InvalidToken:
                text = blob.decode()  # legacy plaintext token — re-save encrypted below
                migrate_plaintext = True
            data = json.loads(text)
            self._creds = Credentials(
                token=data.get("token"),
                refresh_token=data.get("refresh_token"),
                token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=data.get("client_id", self._client_id),
                client_secret=data.get("client_secret", self._client_secret),
                scopes=data.get("scopes", self._scopes),
            )
            if migrate_plaintext:
                self._save_credentials()
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
        blob = json.dumps(data, indent=2).encode()
        fernet = self._fernet()
        self._token_path.write_bytes(fernet.encrypt(blob) if fernet else blob)
        # Restrict permissions: only owner can read
        os.chmod(self._token_path, 0o600)

    def _clear_credentials(self) -> None:
        self._creds = None
        self._account_email = None
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
        url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        self._pending_state = state
        return url

    async def handle_callback(self, code: str, state: str, redirect_uri: str) -> None:
        # Reuse the flow from authenticate() so the PKCE code_verifier is included
        flow, expected_state = self._pending_flow, self._pending_state
        if flow is None or not expected_state or state != expected_state:
            raise ValueError("OAuth state mismatch — restart the connection from MailCull")
        self._pending_flow = None
        self._pending_state = None
        await asyncio.to_thread(flow.fetch_token, code=code)
        self._creds = flow.credentials
        self._account_email = None
        self._save_credentials()

    async def is_connected(self) -> bool:
        if not self._creds or not self._creds.refresh_token:
            return False
        await self._ensure_fresh()
        return self._creds is not None

    async def get_account_email(self) -> str | None:
        if self._account_email:
            return self._account_email
        try:
            service = await self._build_service()
            profile = await asyncio.to_thread(service.users().getProfile(userId="me").execute)
            self._account_email = profile.get("emailAddress")
            return self._account_email
        except Exception:
            return None

    @property
    def requested_scopes(self) -> list[str]:
        return list(self._scopes)

    async def get_granted_scopes(self) -> list[str]:
        if not self._creds:
            return []
        return list(self._creds.scopes or [])

    async def revoke(self) -> None:
        token = self._creds and (self._creds.refresh_token or self._creds.token)
        if token:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                    await s.post(
                        "https://oauth2.googleapis.com/revoke",
                        data={"token": token},
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )
            except Exception:
                logger.warning("Token revoke request failed — clearing local credentials anyway")
        self._clear_credentials()

    async def build_service(self):
        """Public accessor for an authenticated Gmail API client."""
        return await self._build_service()

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
        # httplib2 has no socket timeout by default — a stalled connection would hang a scan forever
        http = AuthorizedHttp(self._creds, http=httplib2.Http(timeout=_HTTP_TIMEOUT_S))
        return await asyncio.to_thread(build, "gmail", "v1", http=http, cache_discovery=False)

    # ── Message streaming ─────────────────────────────────────────────────────

    async def stream_messages(
        self,
        since_days: int,
        batch_size: int = 100,
        on_total: Callable[[int], Awaitable[None]] | None = None,
    ) -> AsyncIterator[list[RawMessage]]:
        service = await self._build_service()
        # Only mail you received: your own sent mail, drafts and chats aren't senders to cull
        query = f"newer_than:{since_days}d -from:me -in:drafts -in:chats"
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

        if on_total:
            await on_total(len(all_ids))

        # Fetch metadata in batches, paced under the per-minute quota
        loop = asyncio.get_running_loop()
        for i in range(0, len(all_ids), batch_size):
            chunk = all_ids[i : i + batch_size]
            started = loop.time()
            raw_messages = await asyncio.to_thread(
                self._fetch_batch, service, chunk
            )
            yield raw_messages
            min_duration = len(chunk) / _GETS_PER_SECOND
            await asyncio.sleep(max(0.0, min_duration - (loop.time() - started)))

    def _fetch_batch(self, service, ids: list[str]) -> list[RawMessage]:
        """Fetch metadata for a batch of message IDs using the batch API."""
        responses = _run_batch(service, {
            msg_id: (lambda m=msg_id: service.users().messages().get(
                userId="me", id=m, format="metadata", metadataHeaders=_METADATA_HEADERS,
            ))
            for msg_id in ids
        })
        return [p for p in (_parse_message(r) for r in responses.values()) if p]

    # ── Body-link discovery ───────────────────────────────────────────────────

    async def find_body_unsubscribe_links(
        self, message_ids: dict[str, str], batch_size: int = 50,
    ) -> dict[str, list[str]]:
        service = await self._build_service()
        items = list(message_ids.items())
        found: dict[str, list[str]] = {}
        for i in range(0, len(items), batch_size):
            chunk = items[i : i + batch_size]
            found.update(await asyncio.to_thread(self._fetch_body_batch, service, chunk))
            await asyncio.sleep(len(chunk) / _GETS_PER_SECOND)
        return found

    def _fetch_body_batch(self, service, chunk: list[tuple[str, str]]) -> dict[str, list[str]]:
        responses = _run_batch(service, {
            key: (lambda m=msg_id: service.users().messages().get(userId="me", id=m, format="full"))
            for key, msg_id in chunk
        })
        out: dict[str, list[str]] = {}
        for key, response in responses.items():
            html_body, text_body = body_parts_from_payload(response.get("payload", {}))
            links = extract_unsubscribe_links(html_body, text_body)
            if links:
                out[key] = links
        return out


_BATCH_MAX = 50  # Gmail rate-limits larger batches per user ("too many concurrent requests")


_NETWORK_ERRORS = (ConnectionError, TimeoutError, OSError, httplib2.HttpLib2Error)


def _is_retriable(exc: Exception) -> bool:
    """Rate limits (429, or 403 rateLimitExceeded / per-minute quota), 5xx and dropped connections are transient."""
    if isinstance(exc, _NETWORK_ERRORS) and not isinstance(exc, HttpError):
        return True
    if isinstance(exc, HttpError):
        if exc.resp.status in (429, 500, 502, 503, 504):
            return True
        if exc.resp.status == 403:
            text = str(exc).lower()
            return "ratelimitexceeded" in text.replace(" ", "") or (
                "quota exceeded" in text and "per minute" in text
            )
    return False


def _run_batch(service, requests: dict, max_rounds: int = 8) -> dict[str, dict]:
    """
    Execute {key: request_factory} as Gmail batch requests and return {key: response}.
    Items that fail with a rate-limit/5xx error are retried with backoff — a
    batch "succeeds" as a whole even when individual items were throttled, so
    without this messages silently go missing.
    """
    import time

    results: dict[str, dict] = {}
    pending = dict(requests)
    delay = 1.0
    for round_no in range(max_rounds):
        failed: dict = {}
        keys = list(pending)
        for i in range(0, len(keys), _BATCH_MAX):
            batch = service.new_batch_http_request()

            def _callback(request_id, response, exception):
                if exception is None:
                    results[request_id] = response
                elif _is_retriable(exception):
                    failed[request_id] = pending[request_id]
                else:
                    logger.debug("Batch item %s failed: %s", request_id, exception)

            for key in keys[i : i + _BATCH_MAX]:
                batch.add(pending[key](), callback=_callback, request_id=key)
            try:
                batch.execute()
            except (HttpError, *_NETWORK_ERRORS) as exc:
                if not _is_retriable(exc):
                    raise
                logger.info("Gmail batch request failed (%s) — will retry", exc.__class__.__name__)
                for key in keys[i : i + _BATCH_MAX]:
                    if key not in results:
                        failed[key] = pending[key]
        if not failed:
            break
        if round_no == max_rounds - 1:
            logger.warning("Gmail batch: %d items still rate-limited after %d rounds", len(failed), max_rounds)
            break
        logger.info("Gmail batch: %d/%d items throttled — retrying in %.0fs", len(failed), len(requests), delay)
        time.sleep(delay)
        delay = min(delay * 2, 32)  # per-minute quota can need a ~60s cool-down in total
        pending = failed
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
        internal_date_ms=int(msg.get("internalDate") or 0),
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


@dataclass
class UnsubInfo:
    """Unsubscribe methods advertised by a single message."""
    one_click_url: str | None = None
    http_urls: list[str] = field(default_factory=list)
    mailtos: list[str] = field(default_factory=list)

    @property
    def capability(self) -> str:
        if self.one_click_url:
            return "one_click"
        if self.mailtos:
            return "mailto"  # automatable, so it outranks a manual link
        if self.http_urls:
            return "link"
        return "none"

    @property
    def links(self) -> list[str]:
        ordered = ([self.one_click_url] if self.one_click_url else []) + self.http_urls + self.mailtos
        out: list[str] = []
        for l in ordered:
            if l not in out:
                out.append(l)
        return out


def parse_unsubscribe_info(header: str | None, post_header: str | None) -> UnsubInfo:
    """Parse List-Unsubscribe (and -Post) from one message (RFC 2369 / RFC 8058)."""
    info = UnsubInfo()
    if not header:
        return info

    parts = re.findall(r"<([^>]+)>", header)
    if not parts:
        # Non-compliant senders sometimes omit the angle brackets
        parts = [p for p in re.split(r"[,\s]+", header) if p]
    uris = []
    for p in parts:
        uri = html.unescape(re.sub(r"\s+", "", p))  # drop header folding inside <…>
        if uri and uri not in uris:
            uris.append(uri)

    info.mailtos = [u for u in uris if u.lower().startswith("mailto:")]
    https = [u for u in uris if u.lower().startswith("https://")]
    http = [u for u in uris if u.lower().startswith("http://")]

    is_one_click = (
        post_header is not None
        and "list-unsubscribe=one-click" in post_header.lower().replace(" ", "")
        and bool(https)
    )
    if is_one_click:
        info.one_click_url = https[0]
        info.http_urls = https[1:] + http
    else:
        info.http_urls = https + http
    return info


def parse_list_unsubscribe(header: str | None, post_header: str | None) -> tuple[str, list[str]]:
    """
    Parse List-Unsubscribe (and -Post) into (capability, [links]).

    Returns:
        capability: "one_click" | "mailto" | "link" | "none"
        links: discovered URLs / mailto URIs, preferred first
    """
    info = parse_unsubscribe_info(header, post_header)
    return info.capability, info.links
