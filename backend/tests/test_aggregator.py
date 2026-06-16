"""Unit tests: sender aggregation and normalisation."""
import pytest

from mailcull.aggregator import aggregate, _sender_id, _extract_domain
from mailcull.mail_source.base import RawMessage


def _msg(
    from_address: str,
    from_name: str = "Sender",
    subject: str = "Hello",
    date_str: str = "Mon, 10 Jun 2026 09:00:00 +0000",
    unsub: str | None = None,
    unsub_post: str | None = None,
) -> RawMessage:
    return RawMessage(
        message_id="x",
        from_address=from_address,
        from_name=from_name,
        subject=subject,
        date_str=date_str,
        list_unsubscribe=unsub,
        list_unsubscribe_post=unsub_post,
    )


class TestAggregation:
    def test_groups_by_address(self):
        msgs = [
            _msg("promo@acme.com", "Acme"),
            _msg("promo@acme.com", "Acme", subject="Sale 2"),
            _msg("billing@aws.amazon.com", "AWS"),
        ]
        senders = aggregate(msgs)
        assert len(senders) == 2
        acme = next(s for s in senders if "acme.com" in s.from_address)
        assert acme.message_count == 2

    def test_lowercase_normalises_addresses(self):
        msgs = [_msg("PROMO@ACME.COM"), _msg("promo@acme.com")]
        senders = aggregate(msgs)
        assert len(senders) == 1
        assert senders[0].from_address == "promo@acme.com"

    def test_domain_extraction(self):
        msgs = [_msg("user@example.co.uk")]
        senders = aggregate(msgs)
        assert senders[0].domain == "example.co.uk"

    def test_sample_subjects_capped_at_3(self):
        msgs = [_msg("a@b.com", subject=f"Subject {i}") for i in range(5)]
        senders = aggregate(msgs)
        assert len(senders[0].sample_subjects) <= 3

    def test_capability_one_click_detected(self):
        msgs = [
            _msg(
                "promo@acme.com",
                unsub="<https://acme.com/unsub>",
                unsub_post="List-Unsubscribe=One-Click",
            )
        ]
        senders = aggregate(msgs)
        assert senders[0].capability == "one_click"

    def test_capability_highest_priority_wins(self):
        # one_click should win over link
        msgs = [
            _msg("a@b.com", unsub="<https://b.com/unsub>"),
            _msg(
                "a@b.com",
                unsub="<https://b.com/unsub2>",
                unsub_post="List-Unsubscribe=One-Click",
            ),
        ]
        senders = aggregate(msgs)
        assert senders[0].capability == "one_click"

    def test_no_messages_returns_empty(self):
        assert aggregate([]) == []

    def test_date_range(self):
        msgs = [
            _msg("a@b.com", date_str="Mon, 01 Jan 2024 09:00:00 +0000"),
            _msg("a@b.com", date_str="Mon, 10 Jun 2026 09:00:00 +0000"),
        ]
        senders = aggregate(msgs)
        s = senders[0]
        assert s.first_seen == "2024-01-01"
        assert s.last_seen == "2026-06-10"

    def test_sender_id_stable(self):
        id1 = _sender_id("promo@acme.com")
        id2 = _sender_id("promo@acme.com")
        assert id1 == id2
        assert id1 != _sender_id("other@acme.com")

    def test_sender_id_format(self):
        sid = _sender_id("user@example.com")
        assert sid.startswith("s_")
        assert len(sid) == 14  # "s_" + 12 hex chars
