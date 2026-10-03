"""Safety guards: DRY_RUN can't be overridden per request, Host/Origin checks, real bulk counts."""
import httpx
import pytest
from fastapi import FastAPI

from mailcull import db
from mailcull.action_executor import estimate_messages
from mailcull.api import actions as actions_api
from mailcull.config import get_settings
from mailcull.models import Sender
from mailcull.security import LocalOnlyMiddleware


def _sender(addr="news@shop.com", decision="delete", count=10):
    return Sender(id=addr, from_name="Shop", from_address=addr, domain="shop.com", message_count=count,
                  first_seen="2026-01-01", last_seen="2026-09-01", decision=decision)


# ── DRY_RUN is .env-only ─────────────────────────────────────────────────────

class FakeGmail:
    async def is_connected(self):
        return True

    async def build_service(self):
        return None

    async def get_granted_scopes(self):
        return []

    async def get_account_email(self):
        return "me@example.com"


async def test_request_cannot_disable_dry_run(temp_db, monkeypatch):
    monkeypatch.setattr(get_settings(), "dry_run", True)
    monkeypatch.setattr(actions_api, "get_gmail", lambda: FakeGmail())
    s = _sender(decision="mute")
    await db.bulk_upsert_senders([s], 1)
    await db.update_sender_decision(s.id, "mute")

    # A client smuggling dry_run=false must be ignored: the model has no such field
    body = actions_api.ExecuteRequest.model_validate({"sender_ids": [s.id], "confirm": True, "dry_run": False})
    assert not hasattr(body, "dry_run")
    [result] = await actions_api.execute_actions(body)

    assert result.detail.startswith("DRY RUN")
    assert (await db.get_sender(s.id)).status == "pending"  # nothing recorded as done


# ── Host / Origin guard ──────────────────────────────────────────────────────

@pytest.fixture
def client():
    app = FastAPI()

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    @app.post("/write")
    async def write():
        return {"ok": True}

    app.add_middleware(LocalOnlyMiddleware, port=8420, extra_hosts={"mailcull.lan"})
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app))


@pytest.mark.parametrize("host", ["localhost:8420", "127.0.0.1:8420", "[::1]:8420", "mailcull.lan"])
async def test_loopback_hosts_allowed(client, host):
    r = await client.get("http://x/ping", headers={"Host": host})
    assert r.status_code == 200


async def test_rebound_host_rejected(client):
    r = await client.get("http://x/ping", headers={"Host": "evil.example.com:8420"})
    assert r.status_code == 400


async def test_cross_site_write_rejected(client):
    r = await client.post("http://x/write", headers={"Host": "localhost:8420", "Origin": "https://evil.example.com"})
    assert r.status_code == 403


@pytest.mark.parametrize("origin", ["http://localhost:8420", "http://127.0.0.1:8420", "http://localhost:5173"])
async def test_own_origin_write_allowed(client, origin):
    r = await client.post("http://x/write", headers={"Host": "localhost:8420", "Origin": origin})
    assert r.status_code == 200


async def test_write_without_origin_allowed(client):
    # curl / scripts are not cross-site browser requests
    r = await client.post("http://x/write", headers={"Host": "localhost:8420"})
    assert r.status_code == 200


async def test_cross_site_read_not_blocked_by_origin_rule(client):
    r = await client.get("http://x/ping", headers={"Host": "localhost:8420", "Origin": "https://evil.example.com"})
    assert r.status_code == 200  # CORS keeps the response unreadable; Origin rule is for writes


# ── Bulk action estimates ────────────────────────────────────────────────────

class _Req:
    def __init__(self, svc, q):
        self.svc, self.q = svc, q

    def execute(self):
        self.svc.queries.append(self.q)
        return {"resultSizeEstimate": 1234}


class _Messages:
    def __init__(self, svc):
        self.svc = svc

    def list(self, userId, q, maxResults, includeSpamTrash):
        return _Req(self.svc, q)


class _Svc:
    def __init__(self):
        self.queries = []

    def users(self):
        return self

    def messages(self):
        return _Messages(self)


async def test_estimate_uses_real_action_queries():
    svc = _Svc()
    assert await estimate_messages(svc, _sender(decision="delete")) == 1234
    assert await estimate_messages(svc, _sender(decision="archive")) == 1234
    assert svc.queries == ["from:news@shop.com", "from:news@shop.com in:inbox"]


async def test_estimate_skips_other_decisions_and_survives_errors():
    assert await estimate_messages(_Svc(), _sender(decision="mute")) is None

    class Boom:
        def users(self):
            raise RuntimeError("gmail down")

    assert await estimate_messages(Boom(), _sender(decision="delete")) is None


# ── Activity (persistent history + undo flags) ──────────────────────────────

async def test_activity_joins_sender_and_flags_undoable(temp_db):
    s = _sender(decision="mute")
    await db.bulk_upsert_senders([s], 1)
    live = await db.log_action(s.id, "mute", "filter", "filter: from:x", dry_run=False, undo_data={"filter_id": "F1"})
    await db.log_action(s.id, "delete", "trash", "DRY RUN: trash", dry_run=True, undo_data={"message_ids": ["a"]})
    await db.log_action("gone@x.com", "unsubscribe", "manual", "marked done", dry_run=False)
    await db.mark_action_undone(live)

    entries = await db.get_activity()
    assert [e.action for e in entries] == ["unsubscribe", "delete", "mute"]  # newest first
    unsub, dry, muted = entries
    assert unsub.from_name == "gone@x.com" and not unsub.can_undo      # unknown sender falls back to id
    assert dry.from_name == "Shop" and dry.dry_run and not dry.can_undo  # dry runs never undoable
    assert muted.undone and not muted.can_undo                          # already undone
    assert not hasattr(muted, "undo_data")                              # payload not exposed


# ── Keep is a local mark ─────────────────────────────────────────────────────

async def test_keep_marks_kept_and_reopens_when_changed(temp_db):
    s = _sender(decision=None)
    await db.bulk_upsert_senders([s], 1)

    await db.update_sender_decisions([(s.id, "keep")])
    got = await db.get_sender(s.id)
    assert (got.decision, got.status) == ("keep", "kept")
    assert await db.get_action_log() == []  # nothing to confirm or log

    await db.update_sender_decisions([(s.id, "unsubscribe")])
    got = await db.get_sender(s.id)
    assert (got.decision, got.status) == ("unsubscribe", "pending")

    await db.update_sender_decisions([(s.id, "keep")])
    await db.update_sender_decisions([(s.id, None)])
    got = await db.get_sender(s.id)
    assert (got.decision, got.status) == (None, "pending")


async def test_decision_on_done_sender_keeps_its_status(temp_db):
    s = _sender(decision=None)
    await db.bulk_upsert_senders([s], 1)
    await db.update_sender_status(s.id, "unsubscribed")
    await db.update_sender_decisions([(s.id, "mute")])  # e.g. "Mute all" on a still-sending sender
    assert (await db.get_sender(s.id)).status == "unsubscribed"


# ── Preferences persist ──────────────────────────────────────────────────────

async def test_prefs_roundtrip_through_settings_api(temp_db, monkeypatch):
    from mailcull.api import settings as settings_api
    from mailcull.ollama_client import OllamaClient

    monkeypatch.setattr(settings_api, "get_ollama", lambda: OllamaClient("http://localhost:11434", "m"))
    monkeypatch.setattr(settings_api, "browser_installed", lambda: False)

    first = await settings_api.get_settings_endpoint()
    assert (first.mute_action, first.snooze_days) == ("archive", 30)

    out = await settings_api.patch_settings(settings_api.SettingsPatch(mute_action="trash", snooze_days=90, scan_since_days=180))
    assert (out.mute_action, out.snooze_days, out.scan_since_days) == ("trash", 90, 180)

    again = await settings_api.get_settings_endpoint()  # a fresh page load
    assert (again.mute_action, again.snooze_days, again.scan_since_days) == ("trash", 90, 180)

    # An unrelated patch must not reset the others
    await settings_api.patch_settings(settings_api.SettingsPatch(ollama_model="x"))
    assert (await settings_api.get_settings_endpoint()).mute_action == "trash"
