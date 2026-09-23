"""Body-link extraction and headless-browser unsubscribe."""
import base64

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from mailcull.browser_unsub import open_browser, rank_control
from mailcull.mail_source.body_links import body_parts_from_payload, extract_unsubscribe_links


def _b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


class TestBodyLinks:
    def test_footer_unsubscribe_anchor(self):
        html = """
        <a href="https://shop.example/sale">Shop the sale</a>
        <a href="https://shop.example/view">View in browser</a>
        <p>Don't want these? <a href="https://esp.example/u?id=1&amp;t=2">Unsubscribe</a></p>
        """
        assert extract_unsubscribe_links(html) == ["https://esp.example/u?id=1&t=2"]

    def test_anchor_text_beats_url_match(self):
        html = """
        <a href="https://x.example/unsubscribe-tracking">here</a>
        <a href="https://x.example/p">Unsubscribe</a>
        """
        assert extract_unsubscribe_links(html)[0] == "https://x.example/p"

    def test_url_only_match_when_text_is_generic(self):
        html = 'To stop, click <a href="https://x.example/unsubscribe?u=9">here</a>.'
        assert extract_unsubscribe_links(html) == ["https://x.example/unsubscribe?u=9"]

    def test_preferences_link_ranked_below_unsubscribe(self):
        html = """
        <a href="https://x.example/prefs">Manage your email preferences</a>
        <a href="https://x.example/out">Opt out</a>
        """
        assert extract_unsubscribe_links(html) == ["https://x.example/out", "https://x.example/prefs"]

    def test_resubscribe_ignored(self):
        html = '<a href="https://x.example/re">Resubscribe</a>'
        assert extract_unsubscribe_links(html) == []

    def test_mailto_only_when_nothing_else(self):
        assert extract_unsubscribe_links('<a href="mailto:u@x.example">unsubscribe</a>') == ["mailto:u@x.example"]
        both = '<a href="mailto:u@x.example">unsubscribe</a><a href="https://x.example/u">unsubscribe</a>'
        assert extract_unsubscribe_links(both) == ["https://x.example/u"]

    def test_plain_text_body(self):
        text = "Hi\nRead more at https://x.example/post\nTo unsubscribe visit https://x.example/u/abc.\n"
        assert extract_unsubscribe_links(None, text) == ["https://x.example/u/abc"]

    def test_multilingual(self):
        html = '<a href="https://x.example/d">Se désabonner</a>'
        assert extract_unsubscribe_links(html) == ["https://x.example/d"]

    def test_payload_walk_decodes_nested_parts(self):
        payload = {
            "mimeType": "multipart/mixed",
            "parts": [{
                "mimeType": "multipart/alternative",
                "parts": [
                    {"mimeType": "text/plain", "body": {"data": _b64("plain body")}},
                    {"mimeType": "text/html", "body": {"data": _b64('<a href="https://x/u">Unsubscribe</a>')}},
                ],
            }],
        }
        html, text = body_parts_from_payload(payload)
        assert "Unsubscribe" in html and text == "plain body"


class TestRankControl:
    @pytest.mark.parametrize("label, rank", [
        ("Unsubscribe from all", 0),
        ("Unsubscribe", 1),
        ("Yes, unsubscribe me", 1),
        ("Opt out", 1),
        ("Confirm", 2),
        ("Save preferences", 3),
    ])
    def test_positive(self, label, rank):
        assert rank_control(label) == rank

    @pytest.mark.parametrize("label", [
        "Subscribe", "Keep me subscribed", "Resubscribe", "Cancel unsubscribe",
        "Sign up for more", "Log in", "No, take me back", "Accept all cookies", "",
    ])
    def test_never_clicked(self, label):
        assert rank_control(label) is None


# ── Browser (skipped when Chromium isn't installed) ──────────────────────────

_PAGES = {
    "/one-step": """<p>Sorry to see you go</p>
        <form method=post action=/confirmed>
          <button type=button>Keep me subscribed</button>
          <button type=submit>Unsubscribe</button>
        </form>""",
    "/two-step": """<button onclick="document.body.innerHTML=
        '<p>Are you sure?</p><form method=post action=/confirmed><button>Yes, confirm</button></form>'">
        Unsubscribe</button>""",
    "/checkbox": """<form method=post action=/confirmed>
          <label><input type=checkbox name=all> Unsubscribe me from all emails</label>
          <input type=email name=email>
          <button>Save preferences</button>
        </form>""",
    "/already": "<h1>You have been unsubscribed.</h1>",
    "/no-button": "<p>Manage your account</p><a href='/login'>Log in</a>",
    "/silent": "<form method=post action=/blank><button>Unsubscribe</button></form>",
}


@pytest.fixture
async def site():
    posts: list[tuple[str, dict]] = []

    async def page(request):
        return web.Response(text=f"<html><body>{_PAGES[request.path]}</body></html>", content_type="text/html")

    async def confirmed(request):
        posts.append((request.path, dict(await request.post())))
        return web.Response(text="<html><body><h1>You've been unsubscribed</h1></body></html>",
                            content_type="text/html")

    async def blank(request):
        posts.append((request.path, dict(await request.post())))
        return web.Response(text="<html><body>Thanks.</body></html>", content_type="text/html")

    app = web.Application()
    for path in _PAGES:
        app.router.add_get(path, page)
    app.router.add_post("/confirmed", confirmed)
    app.router.add_post("/blank", blank)
    srv = TestServer(app)
    await srv.start_server()
    srv.posts = posts  # type: ignore[attr-defined]
    yield srv
    await srv.close()


@pytest.fixture
async def browser():
    async with open_browser() as b:
        if b is None:
            pytest.skip("Playwright/Chromium not installed")
        yield b


class TestBrowser:
    async def test_clicks_unsubscribe_not_keep(self, site, browser):
        verdict, note = await browser.run(str(site.make_url("/one-step")), "me@x.com")
        assert verdict == "confirmed", note
        assert "Unsubscribe" in note

    async def test_multi_step_confirmation(self, site, browser):
        verdict, note = await browser.run(str(site.make_url("/two-step")), None)
        assert verdict == "confirmed", note
        assert "Yes, confirm" in note

    async def test_ticks_unsubscribe_all_and_fills_email(self, site, browser):
        verdict, note = await browser.run(str(site.make_url("/checkbox")), "me@x.com")
        assert verdict == "confirmed", note
        assert site.posts[-1][1] == {"all": "on", "email": "me@x.com"}

    async def test_already_confirmed_on_load(self, site, browser):
        verdict, _ = await browser.run(str(site.make_url("/already")), None)
        assert verdict == "confirmed"

    async def test_no_button_fails_without_clicking(self, site, browser):
        verdict, note = await browser.run(str(site.make_url("/no-button")), None)
        assert verdict == "failed" and note == "no unsubscribe button found"

    async def test_clicked_but_unconfirmed_is_submitted(self, site, browser):
        verdict, _ = await browser.run(str(site.make_url("/silent")), None)
        assert verdict == "submitted"

    async def test_http_error(self, site, browser):
        verdict, note = await browser.run(str(site.make_url("/missing")), None)
        assert verdict == "failed" and note == "HTTP 404"
