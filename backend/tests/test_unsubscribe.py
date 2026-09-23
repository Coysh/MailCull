"""Unsubscribe reliability: header parsing, aggregation, mailto, fallback chain, verification."""
import base64
import email

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from mailcull import db
from mailcull.action_executor import ActionExecutor
from mailcull.aggregator import aggregate
from mailcull.mail_source.base import RawMessage
from mailcull.mail_source.gmail import parse_unsubscribe_info
from mailcull.models import Sender
from mailcull.unsubscribe import (
    SEND_SCOPE,
    UnsubContext,
    get_confirms,
    one_click_post,
    parse_mailto,
    unsubscribe,
)

POST = "List-Unsubscribe=One-Click"

# Real shape from the local DB: Cinch puts a JSON token (with '+'-free base64 but
# quotes and braces) in the mailto body.
CINCH_MAILTO = (
    'mailto:unsubscribe@service.cinch.co.uk?subject=Unsubscribe%20from%20Cinch'
    '&body=CINCHUNSUBSCRIBE{"token":"eyJhbGci.eyJlbWFp+bC.CZgq","deliveryId":"dgTF+gUA=="}CINCHUNSUBSCRIBE'
)


def _msg(addr="a@b.com", ts=0, unsub=None, post=None, mid="m"):
    return RawMessage(
        message_id=mid, from_address=addr, from_name="Sender", subject="s",
        date_str="", list_unsubscribe=unsub, list_unsubscribe_post=post, internal_date_ms=ts,
    )


def _sender(**kw) -> Sender:
    base = dict(
        id="s_1", from_name="Acme", from_address="news@acme.com", domain="acme.com",
        message_count=10, first_seen="2026-01-01", last_seen="2026-06-01",
        decision="unsubscribe",
    )
    base.update(kw)
    return Sender(**base)


# ── Header parsing ───────────────────────────────────────────────────────────

class TestHeaderParsing:
    def test_folded_whitespace_inside_brackets(self):
        info = parse_unsubscribe_info("<https://x.com/u?a=1\r\n\t&b=2>", POST)
        assert info.one_click_url == "https://x.com/u?a=1&b=2"

    def test_html_entities_unescaped(self):
        info = parse_unsubscribe_info("<https://x.com/u?a=1&amp;b=2>", None)
        assert info.http_urls == ["https://x.com/u?a=1&b=2"]

    def test_bare_url_without_brackets(self):
        info = parse_unsubscribe_info("https://x.com/unsub, mailto:u@x.com", None)
        assert info.capability == "mailto"
        assert info.http_urls == ["https://x.com/unsub"]

    def test_mailto_outranks_link(self):
        info = parse_unsubscribe_info("<https://x.com/page>, <mailto:u@x.com>", None)
        assert info.capability == "mailto"

    def test_one_click_needs_post_header_on_same_message(self):
        assert parse_unsubscribe_info("<https://x.com/u>", None).capability == "link"
        assert parse_unsubscribe_info("<https://x.com/u>", POST).capability == "one_click"

    def test_post_header_spacing_tolerated(self):
        info = parse_unsubscribe_info("<https://x.com/u>", "List-Unsubscribe = One-Click")
        assert info.one_click_url == "https://x.com/u"


# ── Aggregation keeps the newest message's methods together ──────────────────

class TestAggregationFreshness:
    def test_newest_message_links_win(self):
        # Norstat case: links from different messages were merged and the
        # wrong/stale one was POSTed.
        msgs = [
            _msg(ts=3000, unsub="<https://new.example/one-click>", post=POST, mid="new"),
            _msg(ts=1000, unsub="<https://old.example/landing>", mid="old"),
        ]
        s = aggregate(msgs)[0]
        assert s.one_click_url == "https://new.example/one-click"
        assert s.http_links == []
        assert s.latest_message_id == "new"

    def test_order_independent(self):
        msgs = [
            _msg(ts=1000, unsub="<https://old.example/u>", post=POST, mid="old"),
            _msg(ts=3000, unsub="<https://new.example/u>", post=POST, mid="new"),
        ]
        assert aggregate(msgs)[0].one_click_url == "https://new.example/u"
        assert aggregate(list(reversed(msgs)))[0].one_click_url == "https://new.example/u"

    def test_newer_message_without_header_keeps_older_methods(self):
        msgs = [
            _msg(ts=1000, unsub="<mailto:u@x.com>", mid="old"),
            _msg(ts=3000, mid="new"),
        ]
        s = aggregate(msgs)[0]
        assert s.capability == "mailto"
        assert s.latest_message_id == "new"

    def test_capability_and_links_consistent(self):
        # Cinch case: capability said one_click but only mailto links were stored
        msgs = [_msg(ts=1000, unsub=f"<{CINCH_MAILTO}>", post=POST)]
        s = aggregate(msgs)[0]
        assert s.capability == "mailto"
        assert s.one_click_url is None
        assert s.mailto_links == [CINCH_MAILTO]


# ── mailto parsing ───────────────────────────────────────────────────────────

class TestMailto:
    def test_plus_and_json_body_preserved(self):
        to, headers = parse_mailto(CINCH_MAILTO)
        assert to == ["unsubscribe@service.cinch.co.uk"]
        assert headers["subject"] == "Unsubscribe from Cinch"
        assert '"deliveryId":"dgTF+gUA=="' in headers["body"]

    def test_to_param_and_multiple_recipients(self):
        to, _ = parse_mailto("mailto:a@x.com,b@x.com?to=c@x.com&subject=hi")
        assert to == ["a@x.com", "b@x.com", "c@x.com"]

    def test_percent_encoded_address(self):
        to, _ = parse_mailto("mailto:unsub%2Babc@x.com")
        assert to == ["unsub+abc@x.com"]


# ── Local HTTP server for the network tests ──────────────────────────────────

@pytest.fixture
async def server():
    hits: list[tuple[str, str, str]] = []
    counters: dict[str, int] = {}

    async def record(request):
        body = await request.text()
        hits.append((request.method, request.path, body))
        return body

    async def ok(request):
        await record(request)
        return web.Response(text="ok")

    async def not_allowed(request):
        await record(request)
        return web.Response(status=405)

    async def redirect_303(request):
        await record(request)
        raise web.HTTPSeeOther("/done")

    async def redirect_307(request):
        await record(request)
        raise web.HTTPTemporaryRedirect("/ok")

    async def done(request):
        await record(request)
        return web.Response(text="<h1>You have been unsubscribed</h1>", content_type="text/html")

    async def flaky(request):
        await record(request)
        counters["flaky"] = counters.get("flaky", 0) + 1
        if counters["flaky"] < 3:
            return web.Response(status=503)
        return web.Response(text="ok")

    async def landing(request):
        await record(request)
        return web.Response(
            text="<p>Sorry to see you go.</p><form method=post action=/done><button>Unsubscribe</button></form>",
            content_type="text/html",
        )

    app = web.Application()
    app.router.add_route("*", "/ok", ok)
    app.router.add_route("*", "/405", not_allowed)
    app.router.add_route("*", "/303", redirect_303)
    app.router.add_route("*", "/307", redirect_307)
    app.router.add_route("*", "/done", done)
    app.router.add_route("*", "/flaky", flaky)
    app.router.add_route("*", "/landing", landing)
    srv = TestServer(app)
    await srv.start_server()
    srv.hits = hits  # type: ignore[attr-defined]
    yield srv
    await srv.close()


def _url(srv, path):
    return str(srv.make_url(path))


class TestOneClick:
    async def test_2xx_success_and_rfc8058_body(self, server):
        ok, note, status = await one_click_post(_url(server, "/ok"))
        assert ok and status == 200
        assert server.hits[0] == ("POST", "/ok", "List-Unsubscribe=One-Click")

    async def test_405_fails(self, server):
        ok, note, status = await one_click_post(_url(server, "/405"))
        assert not ok and status == 405
        assert len(server.hits) == 1  # 4xx isn't retried

    async def test_303_followed_to_confirmation(self, server):
        ok, note, _ = await one_click_post(_url(server, "/303"))
        assert ok
        assert note == "HTTP 303 → 200"

    async def test_307_repeats_post(self, server):
        ok, _, _ = await one_click_post(_url(server, "/307"))
        assert ok
        assert [h[0] for h in server.hits] == ["POST", "POST"]

    async def test_5xx_retried(self, server):
        ok, _, status = await one_click_post(_url(server, "/flaky"))
        assert ok and status == 200
        assert len(server.hits) == 3


class TestGetConfirm:
    async def test_confirmation_page(self, server):
        ok, _ = await get_confirms(_url(server, "/done"))
        assert ok

    async def test_landing_page_is_not_confirmation(self, server):
        ok, note = await get_confirms(_url(server, "/landing"))
        assert not ok and note == "page needs interaction"


# ── Fallback chain ───────────────────────────────────────────────────────────

class _FakeGmail:
    """Just enough of the Gmail client for messages().send()."""

    def __init__(self):
        self.sent: list[dict] = []

    def users(self):
        return self

    def messages(self):
        return self

    def send(self, userId, body):
        self.sent.append(body)
        return self

    def execute(self):
        return {"id": "sent1"}


class TestChain:
    async def test_one_click_failure_falls_back_to_mailto(self, server):
        gmail = _FakeGmail()
        s = _sender(one_click_url=_url(server, "/405"), mailto_links=[CINCH_MAILTO])
        out = await unsubscribe(s, UnsubContext(gmail, dry_run=False, granted_scopes=[SEND_SCOPE]))
        assert out.status == "unsubscribed"
        assert out.method == "mailto"
        assert out.attempts[0] == "one-click: HTTP 405"
        assert out.attempts[1].startswith("mailto: sent to unsubscribe@service.cinch.co.uk")
        raw = base64.urlsafe_b64decode(gmail.sent[0]["raw"])
        body = email.message_from_bytes(raw).get_payload(decode=True).decode()
        assert '"deliveryId":"dgTF+gUA=="' in body

    async def test_missing_send_scope_skips_mailto_then_tries_page(self, server):
        s = _sender(mailto_links=["mailto:u@x.com"], http_links=[_url(server, "/done")])
        out = await unsubscribe(s, UnsubContext(_FakeGmail(), dry_run=False, granted_scopes=[]))
        assert "gmail.send not granted" in out.attempts[0]
        assert out.status == "unsubscribed" and out.method == "link_get"

    async def test_unconfirmed_page_needs_link(self, server):
        page = _url(server, "/landing")
        s = _sender(http_links=[page])
        out = await unsubscribe(s, UnsubContext(None, dry_run=False, granted_scopes=[]))
        assert out.status == "needs_link"
        assert out.link == page

    async def test_no_methods_fails(self):
        out = await unsubscribe(_sender(), UnsubContext(None, dry_run=False, granted_scopes=[]))
        assert out.status == "failed" and out.method == "none"

    async def test_dry_run_makes_no_requests(self, server):
        s = _sender(one_click_url=_url(server, "/ok"), mailto_links=["mailto:u@x.com"])
        out = await unsubscribe(s, UnsubContext(None, dry_run=True, granted_scopes=[SEND_SCOPE]))
        assert out.detail.startswith("DRY RUN: would try one-click POST → mailto")
        assert server.hits == []


# ── Executor idempotency + verification (real SQLite) ────────────────────────

class TestExecutorAndVerification:
    async def test_done_senders_skipped_unless_forced(self, temp_db, server):
        s = _sender(one_click_url=_url(server, "/ok"))
        await db.bulk_upsert_senders([s], 1)
        await db.update_sender_decision(s.id, "unsubscribe")
        ex = ActionExecutor(None, dry_run=False)

        first = await ex.execute([await db.get_sender(s.id)])
        assert first[0].status == "unsubscribed" and not first[0].skipped
        stored = await db.get_sender(s.id)
        assert stored.unsubscribed_at and stored.unsub_method == "one_click"

        second = await ex.execute([stored])
        assert second[0].skipped
        assert len(server.hits) == 1

        forced = await ex.execute([stored], force=True)
        assert not forced[0].skipped
        assert len(server.hits) == 2

    async def test_dry_run_does_not_change_status(self, temp_db):
        s = _sender(one_click_url="https://x.invalid/u")
        await db.bulk_upsert_senders([s], 1)
        await db.update_sender_decision(s.id, "unsubscribe")
        await ActionExecutor(None, dry_run=True).execute([await db.get_sender(s.id)])
        assert (await db.get_sender(s.id)).status == "pending"

    async def test_flag_still_sending(self, temp_db):
        quiet = _sender(id="s_q", from_address="q@x.com", last_seen="2026-06-18")
        noisy = _sender(id="s_n", from_address="n@x.com", last_seen="2026-06-28")
        await db.bulk_upsert_senders([quiet, noisy], 1)
        for sid in ("s_q", "s_n"):
            await db.update_sender_status(sid, "unsubscribed", unsubscribed_at="2026-06-16T09:13:00+00:00")
        assert await db.flag_still_sending(grace_days=7) == 1
        assert (await db.get_sender("s_n")).status == "still_sending"
        assert (await db.get_sender("s_q")).status == "unsubscribed"

    async def test_rescan_keeps_status_and_body_link(self, temp_db):
        s = _sender(capability="body_link", http_links=["https://x.com/u"], unsubscribe_links=["https://x.com/u"],
                    unsubscribe_source="body")
        await db.bulk_upsert_senders([s], 1)
        await db.update_sender_status(s.id, "unsubscribed", unsubscribed_at="2026-06-16T09:00:00+00:00")
        rescanned = _sender(message_count=12, last_seen="2026-06-10")  # capability none this time
        await db.bulk_upsert_senders([rescanned], 2)
        stored = await db.get_sender(s.id)
        assert stored.capability == "body_link" and stored.http_links == ["https://x.com/u"]
        assert stored.status == "unsubscribed" and stored.message_count == 12

    async def test_rescan_replaces_header_links_together(self, temp_db):
        old = _sender(capability="one_click", one_click_url="https://old/u", unsubscribe_links=["https://old/u"],
                      unsubscribe_source="header")
        await db.bulk_upsert_senders([old], 1)
        new = _sender(capability="mailto", mailto_links=["mailto:u@x.com"], unsubscribe_links=["mailto:u@x.com"],
                      unsubscribe_source="header")
        await db.bulk_upsert_senders([new], 2)
        stored = await db.get_sender(old.id)
        assert stored.capability == "mailto" and stored.one_click_url is None


# ── Gmail batch retry (messages were silently dropped on per-item 429s) ─────

class _Resp(dict):
    def __init__(self, status):
        super().__init__(status=str(status))
        self.status = status
        self.reason = "rate"


class _FakeBatchService:
    def __init__(self, fail_first: set[str]):
        self.fail_first = set(fail_first)
        self.calls: list[str] = []

    def new_batch_http_request(self):
        svc = self

        class _Batch:
            def __init__(self):
                self.items = []

            def add(self, req, callback, request_id):
                self.items.append((req, callback, request_id))

            def execute(self):
                from googleapiclient.errors import HttpError
                for req, cb, rid in self.items:
                    svc.calls.append(rid)
                    if rid in svc.fail_first:
                        svc.fail_first.discard(rid)
                        cb(rid, None, HttpError(_Resp(429), b"rateLimitExceeded"))
                    else:
                        cb(rid, {"id": req}, None)
        return _Batch()


def test_batch_items_rate_limited_are_retried(monkeypatch):
    import time
    from mailcull.mail_source import gmail
    monkeypatch.setattr(time, "sleep", lambda s: None)
    svc = _FakeBatchService(fail_first={"b", "c"})
    out = gmail._run_batch(svc, {k: (lambda k=k: k) for k in "abcd"})
    assert set(out) == {"a", "b", "c", "d"}
    assert svc.calls.count("b") == 2 and svc.calls.count("a") == 1


class TestPostFallbackOn405:
    async def test_get_405_retries_as_post(self):
        async def handler(request):
            if request.method == "GET":
                return web.Response(status=405)
            return web.Response(text="done")

        app = web.Application()
        app.router.add_route("*", "/jsp", handler)
        srv = TestServer(app)
        await srv.start_server()
        try:
            s = _sender(http_links=[str(srv.make_url("/jsp"))], capability="link")
            out = await unsubscribe(s, UnsubContext(None, dry_run=False, granted_scopes=[]))
            assert out.status == "unsubscribed" and out.method == "post"
            assert out.attempts == ["GET: HTTP 405", "POST: HTTP 200"]
        finally:
            await srv.close()
