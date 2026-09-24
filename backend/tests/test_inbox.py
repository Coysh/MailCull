"""Inbox view: listing and acting on the sender of one specific message."""
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from mailcull import db
from mailcull.api import inbox as inbox_api
from mailcull.config import get_settings
from mailcull.mail_source.base import RawMessage
from mailcull.models import Sender

POST = "List-Unsubscribe=One-Click"


def _raw(mid, addr, ts, unsub=None, post=None, unread=False):
    return RawMessage(message_id=mid, from_address=addr, from_name=addr.split("@")[0], subject=f"s-{mid}",
                      date_str="", list_unsubscribe=unsub, list_unsubscribe_post=post,
                      internal_date_ms=ts, unread=unread)


class FakeGmail:
    def __init__(self, messages, body_links=None):
        self.messages = {m.message_id: m for m in messages}
        self.body_links = body_links or {}

    async def is_connected(self):
        return True

    async def list_inbox(self, page_token=None, limit=50):
        return sorted(self.messages.values(), key=lambda m: -m.internal_date_ms), "next-tok"

    async def get_message(self, mid):
        return self.messages.get(mid)

    async def find_body_unsubscribe_links(self, ids):
        return {k: self.body_links[mid] for k, mid in ids.items() if mid in self.body_links}

    async def build_service(self):
        return None

    async def get_granted_scopes(self):
        return []

    async def get_account_email(self):
        return "me@example.com"


@pytest.fixture
def live(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "dry_run", False)
    monkeypatch.setattr(s, "browser_unsubscribe", False)


@pytest.fixture
async def esp():
    hits = []

    async def ok(request):
        hits.append(request.path)
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_post("/{tail:.*}", ok)
    srv = TestServer(app)
    await srv.start_server()
    srv.hits = hits
    yield srv
    await srv.close()


async def test_list_newest_first_with_known_status(temp_db, monkeypatch):
    msgs = [_raw("old", "a@x.com", 1000), _raw("new", "b@x.com", 5000, unsub="<https://x/u>", post=POST, unread=True)]
    monkeypatch.setattr(inbox_api, "get_gmail", lambda: FakeGmail(msgs))
    known = Sender(id=inbox_api.aggregate([msgs[0]])[0].id, from_name="a", from_address="a@x.com",
                   domain="x.com", message_count=40, first_seen="2026-01-01", last_seen="2026-09-01")
    await db.bulk_upsert_senders([known], 1)
    await db.update_sender_status(known.id, "unsubscribed")

    page = await inbox_api.list_inbox()
    assert [m.message_id for m in page.messages] == ["new", "old"]
    assert page.messages[0].capability == "one_click" and page.messages[0].unread
    assert page.messages[0].sender_status is None  # never scanned
    assert page.messages[1].sender_status == "unsubscribed" and page.messages[1].message_count == 40
    assert page.next_page_token == "next-tok"


async def test_unsubscribe_uses_this_messages_fresh_link(temp_db, monkeypatch, live, esp):
    fresh_url = str(esp.make_url("/fresh"))
    msg = _raw("m1", "news@shop.com", 9000, unsub=f"<{fresh_url}>", post=POST)
    monkeypatch.setattr(inbox_api, "get_gmail", lambda: FakeGmail([msg]))
    # A scan stored an older, stale link and real stats for this sender
    stale = Sender(id=inbox_api.aggregate([msg])[0].id, from_name="Shop", from_address="news@shop.com",
                   domain="shop.com", message_count=120, first_seen="2025-01-01", last_seen="2026-09-01",
                   capability="one_click", one_click_url=str(esp.make_url("/stale")),
                   unsubscribe_links=[str(esp.make_url("/stale"))])
    await db.bulk_upsert_senders([stale], 1)

    result = await inbox_api.act_on_message("m1", inbox_api.MessageActionRequest(action="unsubscribe", confirm=True))
    assert result.status == "unsubscribed"
    assert esp.hits == ["/fresh"]
    stored = await db.get_sender(stale.id)
    assert stored.status == "unsubscribed" and stored.message_count == 120
    # Local server is http://, so it's stored as a page link (one-click needs https) — but
    # crucially the stale scan link is gone and only this message's link remains
    assert stored.unsubscribe_links == [fresh_url] and stored.one_click_url is None


async def test_unknown_sender_is_created_and_tracked(temp_db, monkeypatch, live, esp):
    msg = _raw("m2", "new@brand.com", 9000, unsub=f"<{esp.make_url('/u')}>", post=POST)
    monkeypatch.setattr(inbox_api, "get_gmail", lambda: FakeGmail([msg]))
    result = await inbox_api.act_on_message("m2", inbox_api.MessageActionRequest(action="unsubscribe", confirm=True))
    stored = await db.get_sender(result.sender_id)
    assert stored is not None and stored.status == "unsubscribed" and stored.unsubscribed_at


async def test_no_header_falls_back_to_body_link(temp_db, monkeypatch, live):
    msg = _raw("m3", "nohdr@x.com", 9000)
    monkeypatch.setattr(inbox_api, "get_gmail", lambda: FakeGmail([msg], body_links={"m3": ["https://x/body-unsub"]}))
    monkeypatch.setattr(get_settings(), "dry_run", True)  # don't hit the network
    result = await inbox_api.act_on_message("m3", inbox_api.MessageActionRequest(action="unsubscribe", confirm=True))
    assert "body link" in result.detail
    assert (await db.get_sender(result.sender_id)).capability == "body_link"


async def test_requires_confirm(temp_db, monkeypatch):
    monkeypatch.setattr(inbox_api, "get_gmail", lambda: FakeGmail([]))
    with pytest.raises(inbox_api.HTTPException):
        await inbox_api.act_on_message("x", inbox_api.MessageActionRequest(action="mute"))
