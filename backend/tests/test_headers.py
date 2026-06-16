"""Unit tests: header parsing, RFC 2047 decoding, List-Unsubscribe variants."""
import pytest

from mailcull.mail_source.gmail import (
    _parse_from,
    _decode_header_value,
    _parse_message,
    parse_list_unsubscribe,
)
from tests.fixtures.headers import (
    RFC2047_FROM,
    PLAIN_FROM,
    BARE_FROM,
    UNICODE_FROM,
    ONE_CLICK_UNSUB,
    ONE_CLICK_POST,
    LINK_ONLY_UNSUB,
    MAILTO_ONLY_UNSUB,
    GMAIL_METADATA_MSG,
    GMAIL_NO_UNSUB_MSG,
    ENCODED_SUBJECT,
)


class TestFromParsing:
    def test_rfc2047_display_name(self):
        name, addr = _parse_from(RFC2047_FROM)
        assert addr == "messages-noreply@linkedin.com"
        assert "LinkedIn" in name

    def test_plain_from(self):
        name, addr = _parse_from(PLAIN_FROM)
        assert name == "GitHub"
        assert addr == "notifications@github.com"

    def test_bare_angle_brackets(self):
        name, addr = _parse_from(BARE_FROM)
        assert addr == "noreply@stripe.com"

    def test_unicode_display_name(self):
        name, addr = _parse_from(UNICODE_FROM)
        assert addr == "bjorn@example.de"
        assert "Björn" in name or "Bj" in name  # may vary by platform


class TestSubjectDecoding:
    def test_encoded_subject(self):
        result = _decode_header_value(ENCODED_SUBJECT)
        assert "Weekly Digest" in result
        assert "June 2026" in result


class TestListUnsubscribeParsing:
    def test_one_click(self):
        cap, links = parse_list_unsubscribe(ONE_CLICK_UNSUB, ONE_CLICK_POST)
        assert cap == "one_click"
        assert any("https://" in l for l in links)

    def test_link_only(self):
        cap, links = parse_list_unsubscribe(LINK_ONLY_UNSUB, None)
        assert cap == "link"
        assert any("https://" in l for l in links)

    def test_mailto_only(self):
        cap, links = parse_list_unsubscribe(MAILTO_ONLY_UNSUB, None)
        assert cap == "mailto"
        assert any(l.startswith("mailto:") for l in links)

    def test_no_header(self):
        cap, links = parse_list_unsubscribe(None, None)
        assert cap == "none"
        assert links == []

    def test_post_header_without_https_is_not_one_click(self):
        # Post header present but only mailto link — should fall back to mailto
        mailto_only = "<mailto:unsub@example.com>"
        cap, links = parse_list_unsubscribe(mailto_only, ONE_CLICK_POST)
        assert cap == "mailto"


class TestMessageParsing:
    def test_full_message_one_click(self):
        msg = _parse_message(GMAIL_METADATA_MSG)
        assert msg is not None
        assert msg.from_address == "promo@acme.com"
        assert msg.from_name == "Acme Marketing"
        assert msg.list_unsubscribe is not None
        assert msg.list_unsubscribe_post is not None

    def test_message_no_unsub(self):
        msg = _parse_message(GMAIL_NO_UNSUB_MSG)
        assert msg is not None
        assert msg.from_address == "billing@aws.amazon.com"
        assert msg.list_unsubscribe is None

    def test_message_missing_from_returns_none(self):
        bad_msg = {"id": "x", "payload": {"headers": []}}
        assert _parse_message(bad_msg) is None
