"""Unit tests: action-method selection from ActionExecutor.preview."""
import pytest

from mailcull.action_executor import ActionExecutor
from mailcull.models import Sender


def _sender(
    capability: str = "none",
    decision: str = "keep",
    message_count: int = 10,
    unsubscribe_links: list[str] | None = None,
) -> Sender:
    return Sender(
        id="s_test123",
        from_name="Test Sender",
        from_address="promo@test.com",
        domain="test.com",
        message_count=message_count,
        first_seen="2025-01-01",
        last_seen="2026-06-10",
        capability=capability,
        unsubscribe_links=unsubscribe_links or [],
        decision=decision,
    )


class TestActionMethodSelection:
    def test_keep_is_no_op(self):
        previews = ActionExecutor.preview([_sender(decision="keep")])
        assert previews[0].method == "no-op"
        assert previews[0].can_automate is True

    def test_one_click_unsubscribe(self):
        s = _sender(
            capability="one_click",
            decision="unsubscribe",
            unsubscribe_links=["https://example.com/unsub"],
        )
        previews = ActionExecutor.preview([s])
        assert previews[0].method == "one_click"
        assert previews[0].can_automate is True
        assert previews[0].needs_manual is False

    def test_link_unsubscribe_needs_manual_without_browser(self):
        s = _sender(
            capability="link",
            decision="unsubscribe",
            unsubscribe_links=["https://example.com/unsub-page"],
        )
        previews = ActionExecutor.preview([s], browser_available=False)
        assert previews[0].method == "link"
        assert previews[0].needs_manual is True
        assert previews[0].can_automate is False

    def test_link_unsubscribe_automated_with_browser(self):
        s = _sender(
            capability="link",
            decision="unsubscribe",
            unsubscribe_links=["https://example.com/unsub-page"],
        )
        previews = ActionExecutor.preview([s], browser_available=True)
        assert previews[0].method == "browser"
        assert previews[0].can_automate is True
        assert "manual link" in previews[0].description

    def test_one_click_preview_lists_fallbacks(self):
        s = _sender(
            capability="one_click",
            decision="unsubscribe",
            unsubscribe_links=["https://example.com/u", "mailto:u@example.com"],
        )
        desc = ActionExecutor.preview([s])[0].description
        assert desc.startswith("one-click POST → mailto")

    def test_mailto_without_send_scope_flags_reauth(self):
        s = _sender(
            capability="mailto",
            decision="unsubscribe",
            unsubscribe_links=["mailto:unsub@example.com"],
        )
        p = ActionExecutor.preview([s], can_send=False)[0]
        assert "re-authorise" in p.description
        assert p.can_automate is False

    def test_mailto_unsubscribe(self):
        s = _sender(
            capability="mailto",
            decision="unsubscribe",
            unsubscribe_links=["mailto:unsub@example.com"],
        )
        previews = ActionExecutor.preview([s])
        assert previews[0].method == "mailto"
        assert previews[0].can_automate is True

    def test_none_capability_unsubscribe_has_no_method(self):
        s = _sender(capability="none", decision="unsubscribe")
        previews = ActionExecutor.preview([s])
        assert previews[0].method == "none"
        assert previews[0].can_automate is False

    def test_mute_creates_filter(self):
        s = _sender(decision="mute")
        previews = ActionExecutor.preview([s])
        assert previews[0].method == "filter"

    def test_delete_creates_trash(self):
        s = _sender(decision="delete")
        previews = ActionExecutor.preview([s])
        assert previews[0].method == "trash"

    def test_transactional_is_label(self):
        s = _sender(decision="transactional")
        previews = ActionExecutor.preview([s])
        assert previews[0].method == "label"

    def test_empty_sender_list(self):
        assert ActionExecutor.preview([]) == []

    def test_all_sender_ids_present(self):
        senders = [
            _sender(decision="keep"),
            _sender(decision="mute"),
        ]
        previews = ActionExecutor.preview(senders)
        assert all(p.sender_id == "s_test123" for p in previews)
        assert len(previews) == 2
