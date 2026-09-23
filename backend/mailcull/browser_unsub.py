"""Headless-browser unsubscribe for pages that need a click.

Optional: requires `pip install mailcull[browser]` and `playwright install chromium`.
If Playwright or Chromium is missing, `open_browser()` yields None and the
unsubscribe chain falls back to a plain GET, then a manual link.

Each page runs in a fresh, cookie-less context. Nothing is stored and no
screenshots are taken.
"""
from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager
from typing import AsyncIterator, Literal

from .unsubscribe import CONFIRM_RE, ERROR_RE, USER_AGENT

logger = logging.getLogger(__name__)

Verdict = Literal["confirmed", "submitted", "failed"]

_NAV_TIMEOUT_MS = 20_000
_MAX_STEPS = 3  # e.g. "Unsubscribe" → "Yes, confirm" → done

# Controls worth clicking, strongest first
_CLICK_RANKS = [
    re.compile(r"unsubscribe\s+(me\s+)?from\s+all|opt[\s-]?out\s+of\s+all|unsubscribe\s+all", re.I),
    re.compile(r"\bunsubscribe\b|\bunsub\b|opt[\s-]?out|remove\s+me|d[ée]sabonner|abmelden|darse de baja", re.I),
    re.compile(r"^\s*(yes|confirm|i'?m sure|continue)\b|\bconfirm\b", re.I),
    re.compile(r"^\s*(submit|save|update)(\s+(my\s+)?(preferences|settings|changes))?\s*$", re.I),
]
# Never click these — they'd keep or re-add the subscription, or log in
_NEVER = re.compile(
    r"(^|[^n])subscribe|resubscribe|re-subscribe|sign\s?up|keep|stay|cancel|go\s+back|undo"
    r"|log\s?in|sign\s?in|register|privacy|cookie|accept\s+all|manage\s+cookies|^\s*no\b",
    re.I,
)
_UNSUB_ALL_TOGGLE = re.compile(
    r"unsubscribe\s+(me\s+)?from\s+all|all\s+(emails|communications|mailings|marketing)"
    r"|opt[\s-]?out\s+of\s+all|do\s+not\s+(send|email)",
    re.I,
)

_CANDIDATES_JS = """
els => els.map(e => {
  const t = (e.innerText || e.value || e.getAttribute('aria-label') || e.title || '').trim().slice(0, 140);
  const r = e.getBoundingClientRect();
  const visible = r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== 'hidden';
  return [t, visible, e.tagName.toLowerCase(), !!e.disabled];
})
"""

_TOGGLES_JS = """
els => els.map(e => {
  let label = '';
  if (e.id) { const l = document.querySelector(`label[for="${CSS.escape(e.id)}"]`); if (l) label = l.innerText; }
  if (!label && e.closest('label')) label = e.closest('label').innerText;
  if (!label && e.parentElement) label = e.parentElement.innerText;
  return [(label || e.value || '').trim().slice(0, 160), e.checked];
})
"""


class BrowserUnsubscriber:
    def __init__(self, browser) -> None:
        self._browser = browser

    async def run(self, url: str, email: str | None) -> tuple[Verdict, str]:
        context = await self._browser.new_context(user_agent=USER_AGENT, locale="en-GB")
        await context.route("**/*", _block_heavy_resources)
        page = await context.new_page()
        page.set_default_timeout(_NAV_TIMEOUT_MS)
        clicked: list[str] = []
        try:
            resp = await page.goto(url, wait_until="domcontentloaded")
            await _settle(page)
            if resp is not None and resp.status >= 400:
                return "failed", f"HTTP {resp.status}"
            text = await _page_text(page)
            if _confirms(text):
                return "confirmed", "page confirmed on load"

            for _ in range(_MAX_STEPS):
                await _tick_unsubscribe_all(page)
                await _fill_email(page, email)
                label = await _click_best(page, exclude=clicked)
                if label is None:
                    break
                clicked.append(label)
                await _settle(page)
                text = await _page_text(page)
                if _confirms(text):
                    return "confirmed", f"clicked “{label}”, page confirmed"
                if ERROR_RE.search(text):
                    return "failed", f"clicked “{label}”, page showed an error"

            if clicked:
                return "submitted", f"clicked {' → '.join(f'“{c}”' for c in clicked)}, no confirmation shown"
            return "failed", "no unsubscribe button found"
        except Exception as exc:
            msg = str(exc).splitlines()[0][:120] if str(exc) else exc.__class__.__name__
            if clicked:
                return "submitted", f"clicked “{clicked[-1]}”, then {msg}"
            return "failed", msg
        finally:
            await context.close()


@asynccontextmanager
async def open_browser(enabled: bool = True) -> AsyncIterator[BrowserUnsubscriber | None]:
    """Yield a BrowserUnsubscriber, or None if Playwright/Chromium is unavailable."""
    if not enabled:
        yield None
        return
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.info("Playwright not installed — link unsubscribes fall back to GET/manual")
        yield None
        return
    pw = await async_playwright().start()
    try:
        try:
            browser = await pw.chromium.launch(headless=True)
        except Exception as exc:
            logger.warning("Could not launch Chromium (%s) — run `playwright install chromium`",
                           str(exc).splitlines()[0])
            yield None
            return
        try:
            yield BrowserUnsubscriber(browser)
        finally:
            await browser.close()
    finally:
        await pw.stop()


def browser_installed() -> bool:
    """True if the Playwright package is importable (Chromium is checked at launch)."""
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False
    return True


# ── Page helpers ─────────────────────────────────────────────────────────────

async def _block_heavy_resources(route) -> None:
    if route.request.resource_type in ("image", "media", "font"):
        await route.abort()
    else:
        await route.continue_()


async def _settle(page) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=8_000)
    except Exception:
        pass


async def _page_text(page) -> str:
    parts: list[str] = []
    for frame in page.frames:
        try:
            parts.append(await frame.locator("body").inner_text(timeout=3_000))
        except Exception:
            continue
    return " ".join(" ".join(parts).split())


def _confirms(text: str) -> bool:
    return bool(CONFIRM_RE.search(text)) and not ERROR_RE.search(text)


def rank_control(label: str) -> int | None:
    """Rank a clickable control by its label; None means never click it."""
    if not label:
        return None
    for i, pat in enumerate(_CLICK_RANKS):
        if pat.search(label):
            # "Unsubscribe" beats the never-list ("unsubscribe" contains "subscribe")
            if i >= 2 and _NEVER.search(label):
                return None
            if i < 2 and _NEVER.search(re.sub(r"un-?subscribe", "", label, flags=re.I)):
                return None
            return i
    return None


async def _click_best(page, exclude: list[str]) -> str | None:
    best: tuple[int, int, object, int, str] | None = None  # (rank, is_link, locator, index, label)
    for frame in page.frames:
        loc = frame.locator("button, input[type=submit], input[type=button], [role=button], a")
        try:
            items = await loc.evaluate_all(_CANDIDATES_JS)
        except Exception:
            continue
        for idx, (label, visible, tag, disabled) in enumerate(items):
            if not visible or disabled or label in exclude:
                continue
            rank = rank_control(label)
            if rank is None:
                continue
            key = (rank, 1 if tag == "a" else 0)  # prefer real buttons over links
            if best is None or key < best[:2]:
                best = (rank, key[1], loc, idx, label)
    if best is None:
        return None
    _, _, loc, idx, label = best
    try:
        await loc.nth(idx).click(timeout=5_000)  # type: ignore[attr-defined]
    except Exception:
        return None
    return label


async def _tick_unsubscribe_all(page) -> None:
    for frame in page.frames:
        loc = frame.locator("input[type=checkbox], input[type=radio]")
        try:
            items = await loc.evaluate_all(_TOGGLES_JS)
        except Exception:
            continue
        for idx, (label, checked) in enumerate(items):
            if not checked and _UNSUB_ALL_TOGGLE.search(label):
                try:
                    await loc.nth(idx).check(timeout=3_000)
                except Exception:
                    pass


async def _fill_email(page, email: str | None) -> None:
    if not email:
        return
    for frame in page.frames:
        loc = frame.locator("input[type=email], input[name*=email i], input[id*=email i]")
        try:
            count = await loc.count()
        except Exception:
            continue
        for i in range(count):
            field = loc.nth(i)
            try:
                if await field.is_visible() and not (await field.input_value()):
                    await field.fill(email)
            except Exception:
                continue
