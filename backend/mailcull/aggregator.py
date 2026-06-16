"""Aggregator — raw messages → per-sender records."""
from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from .mail_source.base import RawMessage
from .mail_source.gmail import parse_list_unsubscribe
from .models import Sender

logger = logging.getLogger(__name__)

_MAX_SUBJECTS = 3


def aggregate(messages: list[RawMessage]) -> list[Sender]:
    """Collapse a flat list of RawMessage into per-sender Sender records."""
    buckets: dict[str, _Bucket] = {}

    for msg in messages:
        addr = msg.from_address.lower().strip()
        if not addr:
            continue
        if addr not in buckets:
            buckets[addr] = _Bucket(msg.from_name, addr)
        buckets[addr].add(msg)

    return [b.to_sender() for b in buckets.values()]


def merge_into(existing: list[Sender], new_batch: list[Sender]) -> list[Sender]:
    """Merge a new batch of senders into an existing list (by from_address)."""
    index = {s.from_address.lower(): s for s in existing}
    for new in new_batch:
        key = new.from_address.lower()
        if key not in index:
            index[key] = new
        else:
            old = index[key]
            merged = Sender(
                id=old.id,
                from_name=old.from_name or new.from_name,
                from_address=old.from_address,
                domain=old.domain,
                message_count=old.message_count + new.message_count,
                first_seen=min(old.first_seen, new.first_seen),
                last_seen=max(old.last_seen, new.last_seen),
                sample_subjects=_dedup_subjects(old.sample_subjects + new.sample_subjects),
                capability=new.capability if new.capability != "none" else old.capability,
                unsubscribe_links=_dedup(old.unsubscribe_links + new.unsubscribe_links),
                category=old.category,
                rationale=old.rationale,
                suggested_action=old.suggested_action,
                classification_degraded=old.classification_degraded,
                decision=old.decision,
                status=old.status,
            )
            index[key] = merged
    return list(index.values())


class _Bucket:
    def __init__(self, name: str, address: str) -> None:
        self.name = name
        self.address = address
        self.domain = _extract_domain(address)
        self.messages: list[RawMessage] = []
        self.subjects: list[str] = []
        self.dates: list[str] = []
        self._cap: str = "none"
        self._links: list[str] = []

    def add(self, msg: RawMessage) -> None:
        self.messages.append(msg)
        if msg.subject and len(self.subjects) < _MAX_SUBJECTS:
            self.subjects.append(msg.subject)
        if msg.date_str:
            self.dates.append(msg.date_str)

        cap, links = parse_list_unsubscribe(msg.list_unsubscribe, msg.list_unsubscribe_post)
        if _cap_priority(cap) > _cap_priority(self._cap):
            self._cap = cap
        for link in links:
            if link not in self._links:
                self._links.append(link)

    def to_sender(self) -> Sender:
        iso_dates = [_parse_date(d) for d in self.dates if _parse_date(d)]
        first = min(iso_dates) if iso_dates else _today_iso()
        last = max(iso_dates) if iso_dates else _today_iso()
        return Sender(
            id=_sender_id(self.address),
            from_name=self.name,
            from_address=self.address,
            domain=self.domain,
            message_count=len(self.messages),
            first_seen=first,
            last_seen=last,
            sample_subjects=self.subjects[:_MAX_SUBJECTS],
            capability=self._cap,
            unsubscribe_links=self._links[:5],
        )


def _sender_id(address: str) -> str:
    return "s_" + hashlib.sha1(address.encode()).hexdigest()[:12]


def _extract_domain(address: str) -> str:
    return address.split("@")[-1] if "@" in address else address


def _parse_date(date_str: str) -> str | None:
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.date().isoformat()
    except Exception:
        return None


def _today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


_CAP_RANK = {"one_click": 3, "mailto": 2, "link": 2, "none": 0}


def _cap_priority(cap: str) -> int:
    return _CAP_RANK.get(cap, 0)


def _dedup(lst: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in lst:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _dedup_subjects(lst: list[str]) -> list[str]:
    return _dedup(lst)[:_MAX_SUBJECTS]
