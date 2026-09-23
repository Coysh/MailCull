"""Unsubscribe fallback chain.

For one sender, try every advertised method in order of reliability until
one succeeds, recording each attempt so the UI can show what happened:

  1. RFC 8058 one-click POST
  2. mailto, sent from the user's own Gmail account
  3. headless browser on the unsubscribe page (header link, then body link)
  4. plain GET, when the page itself confirms the opt-out
  5. otherwise → needs_link (the user finishes it by hand)
"""
from __future__ import annotations

import asyncio
import base64
import logging
import re
from dataclasses import dataclass, field
from email.mime.text import MIMEText
from typing import Any, Literal
from urllib.parse import unquote, urljoin

import aiohttp
from googleapiclient.errors import HttpError

from .models import Sender

logger = logging.getLogger(__name__)

SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
_TIMEOUT = aiohttp.ClientTimeout(total=20)
_MAX_PAGE_BYTES = 512_000
_RETRY_BASE_DELAY = 1.0

# Text that shows the opt-out has been processed. Landing pages that merely
# *ask* ("Are you sure?", "Sorry to see you go") must not match.
CONFIRM_RE = re.compile(
    r"you(?:'ve| have| are| were)?\s+(?:now\s+|been\s+|successfully\s+|now been\s+)*"
    r"(?:unsubscribed|removed|opted[\s-]out)"
    r"|successfully\s+(?:unsubscribed|removed|opted[\s-]out)"
    r"|unsubscri(?:be|ption)d?\s+(?:was\s+|is\s+)?(?:successful|complete|confirmed)"
    r"|(?:has|have)\s+been\s+(?:unsubscribed|removed|opted[\s-]out)"
    r"|removed\s+from\s+(?:our|the|this|all)\s+(?:\w+\s+)?(?:mailing\s+|email\s+)?lists?"
    r"|(?:will\s+)?no\s+longer\s+(?:receive|get|be\s+sent)"
    r"|(?:won't|will\s+not)\s+(?:receive|get)\s+(?:any\s+)?(?:more|further)"
    r"|subscription\s+(?:has\s+been\s+)?cancell?ed"
    r"|opt[\s-]?out\s+(?:was\s+|has\s+been\s+)?(?:successful|confirmed|complete)"
    r"|preferences\s+(?:have\s+been\s+|were\s+)?(?:saved|updated)",
    re.I,
)
ERROR_RE = re.compile(
    r"link\s+(?:has\s+)?expired|invalid\s+(?:link|token|request)|something\s+went\s+wrong"
    r"|page\s+not\s+found|error\s+occurred|could\s+not\s+(?:be\s+)?(?:processed|unsubscribe)",
    re.I,
)

OutcomeStatus = Literal["unsubscribed", "unsub_pending", "needs_link", "failed"]


@dataclass
class UnsubOutcome:
    status: OutcomeStatus
    method: str
    detail: str
    attempts: list[str] = field(default_factory=list)
    http_status: int | None = None
    link: str | None = None


@dataclass
class UnsubContext:
    gmail_service: Any
    dry_run: bool
    granted_scopes: list[str]
    account_email: str | None = None
    browser: Any = None  # BrowserUnsubscriber | None
    browser_available: bool = False  # for dry-run plans, where no browser is started

    @property
    def can_send(self) -> bool:
        return SEND_SCOPE in self.granted_scopes or "https://mail.google.com/" in self.granted_scopes


# ── Planning (shared by preview and dry run) ─────────────────────────────────

def plan_chain(sender: Sender, ctx_can_send: bool, browser_available: bool) -> list[str]:
    """Human-readable ordered list of the steps that would be tried."""
    steps: list[str] = []
    if sender.one_click_url:
        steps.append("one-click POST")
    if sender.mailto_links:
        steps.append("mailto" if ctx_can_send else "mailto (needs gmail.send — re-authorise)")
    if _page_links(sender):
        src = "body link" if sender.unsubscribe_source == "body" else "unsubscribe page"
        steps.append(f"browser: {src}" if browser_available else f"check {src}")
        steps.append("manual link")
    return steps


def _page_links(sender: Sender) -> list[str]:
    """Web pages worth opening, best first. The one-click URL goes last: a GET on it
    usually lands on a confirmation page even when the POST was refused."""
    links = [l for l in sender.http_links if l.lower().startswith(("http://", "https://"))]
    if sender.one_click_url and sender.one_click_url not in links:
        links.append(sender.one_click_url)
    return links


# ── Execution ────────────────────────────────────────────────────────────────

async def unsubscribe(sender: Sender, ctx: UnsubContext) -> UnsubOutcome:
    if ctx.dry_run:
        steps = plan_chain(sender, ctx.can_send, ctx.browser is not None or ctx.browser_available)
        if not steps:
            return UnsubOutcome("failed", "none", "No unsubscribe method found — use Mute instead")
        automated = [x for x in steps if x != "manual link" and "needs gmail.send" not in x]
        status: OutcomeStatus = (
            "unsubscribed" if automated else "needs_link" if _page_links(sender) else "failed"
        )
        return UnsubOutcome(status, _first_method(sender), "DRY RUN: would try " + " → ".join(steps), steps,
                            link=(_page_links(sender) or [None])[0])

    attempts: list[str] = []
    last_status: int | None = None

    # 1. RFC 8058 one-click
    if sender.one_click_url:
        ok, note, status = await one_click_post(sender.one_click_url)
        attempts.append(f"one-click: {note}")
        last_status = status
        if ok:
            return UnsubOutcome("unsubscribed", "one_click", _trail(attempts), attempts, status)

    # 2. mailto
    if sender.mailto_links:
        if not ctx.can_send:
            attempts.append("mailto: skipped — gmail.send not granted (re-authorise)")
        else:
            ok, note = await send_mailto(ctx.gmail_service, sender.mailto_links[0])
            attempts.append(f"mailto: {note}")
            if ok:
                return UnsubOutcome("unsubscribed", "mailto", _trail(attempts), attempts, last_status)

    # 3/4. Unsubscribe web pages
    pages = _page_links(sender)
    for url in pages[:3]:
        if ctx.browser is not None:
            verdict, note = await ctx.browser.run(url, ctx.account_email)
            attempts.append(f"browser: {note}")
            if verdict == "confirmed":
                return UnsubOutcome("unsubscribed", "browser", _trail(attempts), attempts, last_status, link=url)
            if verdict == "submitted":
                # Form submitted but the page never said so — verified by later scans
                return UnsubOutcome("unsub_pending", "browser", _trail(attempts), attempts, last_status, link=url)
        else:
            ok, note = await get_confirms(url)
            attempts.append(f"GET: {note}")
            if ok:
                return UnsubOutcome("unsubscribed", "link_get", _trail(attempts), attempts, last_status, link=url)
        # 405 on GET: the endpoint wants a POST even though the sender didn't
        # advertise one-click (seen with PizzaExpress). Try the RFC 8058 POST.
        if note.startswith("HTTP 405") and url != sender.one_click_url:
            ok, post_note, status = await one_click_post(url)
            attempts.append(f"POST: {post_note}")
            if ok:
                return UnsubOutcome("unsubscribed", "post", _trail(attempts), attempts, status, link=url)

    if pages:
        return UnsubOutcome("needs_link", "link", _trail(attempts) or pages[0], attempts, last_status, link=pages[0])
    if not attempts:
        return UnsubOutcome("failed", "none", "No unsubscribe method found — use Mute instead")
    return UnsubOutcome("failed", _first_method(sender), _trail(attempts), attempts, last_status)


def _first_method(sender: Sender) -> str:
    if sender.one_click_url:
        return "one_click"
    if sender.mailto_links:
        return "mailto"
    if _page_links(sender):
        return "link"
    return "none"


def _trail(attempts: list[str]) -> str:
    return " → ".join(attempts)


# ── One-click POST ───────────────────────────────────────────────────────────

async def one_click_post(url: str, retries: int = 2) -> tuple[bool, str, int | None]:
    """POST per RFC 8058. Returns (success, note, http_status)."""
    delay = _RETRY_BASE_DELAY
    note, status = "not attempted", None
    for attempt in range(retries + 1):
        try:
            ok, note, status = await _one_click_once(url)
        except asyncio.TimeoutError:
            ok, note, status = False, "timeout", None
        except aiohttp.ClientError as exc:
            ok, note, status = False, f"network error ({exc.__class__.__name__})", None
        if ok:
            return True, note, status
        transient = status is None or status == 429 or status >= 500
        if not transient or attempt == retries:
            break
        await asyncio.sleep(delay)
        delay *= 3
    return False, note, status


async def _one_click_once(url: str) -> tuple[bool, str, int | None]:
    headers = {
        "User-Agent": USER_AGENT,
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "*/*",
    }
    # RFC 8058: no cookies or credentials
    async with aiohttp.ClientSession(timeout=_TIMEOUT, cookie_jar=aiohttp.DummyCookieJar()) as session:
        target = url
        for _hop in range(4):
            async with session.post(
                target, data="List-Unsubscribe=One-Click", headers=headers, allow_redirects=False,
            ) as resp:
                status = resp.status
                if 200 <= status < 300:
                    return True, f"HTTP {status}", status
                location = resp.headers.get("Location")
                if status in (307, 308) and location:
                    target = urljoin(target, location)  # method-preserving: re-POST
                    continue
                if status in (301, 302, 303) and location:
                    # Most ESPs process the POST, then redirect to a "you're out" page.
                    # Follow it with GET and make sure it isn't an error page.
                    return await _follow_after_post(session, urljoin(target, location), status)
                return False, f"HTTP {status}", status
        return False, "too many redirects", None


async def _follow_after_post(session: aiohttp.ClientSession, url: str, first: int) -> tuple[bool, str, int | None]:
    try:
        async with session.get(url, headers={"User-Agent": USER_AGENT}, allow_redirects=True) as resp:
            text = _visible_text(await _read_capped(resp))
            if resp.status >= 400:
                return False, f"HTTP {first} → {resp.status}", resp.status
            if ERROR_RE.search(text) and not CONFIRM_RE.search(text):
                return False, f"HTTP {first} → error page", resp.status
            return True, f"HTTP {first} → {resp.status}", first
    except (aiohttp.ClientError, asyncio.TimeoutError):
        # POST was accepted; the landing page just didn't load
        return True, f"HTTP {first}", first


# ── mailto ───────────────────────────────────────────────────────────────────

def parse_mailto(uri: str) -> tuple[list[str], dict[str, str]]:
    """
    Parse a mailto: URI (RFC 6068). Uses unquote (not parse_qs) so '+' and
    JSON/token bodies survive intact. Returns (recipients, headers).
    """
    rest = uri[len("mailto:"):] if uri.lower().startswith("mailto:") else uri
    addr_part, _, query = rest.partition("?")
    recipients = [unquote(a).strip() for a in addr_part.split(",") if a.strip()]
    headers: dict[str, str] = {}
    for pair in query.split("&") if query else []:
        key, _, value = pair.partition("=")
        key = unquote(key).lower()
        value = unquote(value)
        if key == "to":
            recipients += [a.strip() for a in value.split(",") if a.strip()]
        elif key:
            headers[key] = value
    return recipients, headers


async def send_mailto(gmail_service: Any, uri: str) -> tuple[bool, str]:
    recipients, headers = parse_mailto(uri)
    if not recipients:
        return False, "no recipient in mailto"
    msg = MIMEText(headers.get("body") or "unsubscribe", "plain", "utf-8")
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = headers.get("subject") or "unsubscribe"
    if headers.get("cc"):
        msg["Cc"] = headers["cc"]
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    try:
        await asyncio.to_thread(
            gmail_service.users().messages().send(userId="me", body={"raw": raw}).execute
        )
        return True, f"sent to {msg['To']}"
    except HttpError as exc:
        if exc.status_code == 403:
            return False, "gmail.send scope not granted (re-authorise)"
        return False, f"Gmail API {exc.status_code}"
    except Exception as exc:
        return False, str(exc)[:120]


# ── Plain GET (used when no browser is available) ────────────────────────────

async def get_confirms(url: str) -> tuple[bool, str]:
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT, cookie_jar=aiohttp.DummyCookieJar()) as session:
            async with session.get(url, headers={"User-Agent": USER_AGENT}, allow_redirects=True) as resp:
                if resp.status >= 400:
                    return False, f"HTTP {resp.status}"
                text = _visible_text(await _read_capped(resp))
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        return False, f"network error ({exc.__class__.__name__})"
    if CONFIRM_RE.search(text) and not ERROR_RE.search(text):
        return True, "page confirmed unsubscribe"
    return False, "page needs interaction"


async def _read_capped(resp: aiohttp.ClientResponse) -> str:
    raw = await resp.content.read(_MAX_PAGE_BYTES)
    return raw.decode(resp.charset or "utf-8", errors="replace")


def _visible_text(html_text: str) -> str:
    html_text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html_text)
    return " ".join(re.sub(r"<[^>]+>", " ", html_text).split())
