"""Aggregator — raw messages → per-sender records."""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from .mail_source.base import RawMessage
from .mail_source.gmail import UnsubInfo, parse_unsubscribe_info
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


def apply_unsub_info(sender: Sender, info: UnsubInfo, source: str = "header") -> Sender:
    """Return a copy of sender whose capability and links all come from `info`."""
    return sender.model_copy(update={
        "capability": info.capability,
        "one_click_url": info.one_click_url,
        "http_links": info.http_urls,
        "mailto_links": info.mailtos,
        "unsubscribe_links": info.links[:5],
        "unsubscribe_source": source if info.capability != "none" else None,
    })


class _Bucket:
    def __init__(self, name: str, address: str) -> None:
        self.name = name
        self.address = address
        self.domain = _extract_domain(address)
        self.count = 0
        self.subjects: list[tuple[int, str]] = []
        self.dates: list[str] = []
        self.latest_ts = -1
        self.latest_id: str | None = None
        # Unsubscribe info from the newest message that advertised any.
        # Tokens in these URLs are per-message and expire, so older ones are
        # only a fallback when nothing newer exists.
        self._unsub: UnsubInfo | None = None
        self._unsub_key: tuple[int, int] = (-1, -1)

    def add(self, msg: RawMessage) -> None:
        self.count += 1
        ts = msg.internal_date_ms or _date_to_ms(msg.date_str)
        if msg.subject:
            self.subjects.append((ts, msg.subject))
        day = _ms_to_iso(msg.internal_date_ms) if msg.internal_date_ms else _parse_date(msg.date_str)
        if day:
            self.dates.append(day)
        if ts > self.latest_ts:
            self.latest_ts = ts
            self.latest_id = msg.message_id
            if msg.from_name and msg.from_name != msg.from_address:
                self.name = msg.from_name

        info = parse_unsubscribe_info(msg.list_unsubscribe, msg.list_unsubscribe_post)
        if info.capability == "none":
            return
        # Newest wins; on equal timestamps prefer the more automatable method
        key = (ts, _CAP_RANK[info.capability])
        if key > self._unsub_key:
            self._unsub_key = key
            self._unsub = info

    def to_sender(self) -> Sender:
        first = min(self.dates) if self.dates else _today_iso()
        last = max(self.dates) if self.dates else _today_iso()
        newest_subjects = [s for _, s in sorted(self.subjects, key=lambda x: -x[0])]
        sender = Sender(
            id=_sender_id(self.address),
            from_name=self.name,
            from_address=self.address,
            domain=self.domain,
            message_count=self.count,
            first_seen=first,
            last_seen=last,
            sample_subjects=_dedup(newest_subjects)[:_MAX_SUBJECTS],
            latest_message_id=self.latest_id,
            latest_ts=max(self.latest_ts, 0),
        )
        if self._unsub:
            sender = apply_unsub_info(sender, self._unsub, "header")
        return sender


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


def _ms_to_iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat()


def _date_to_ms(date_str: str) -> int:
    try:
        return int(parsedate_to_datetime(date_str).timestamp() * 1000)
    except Exception:
        return 0


def _today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


_CAP_RANK = {"one_click": 4, "mailto": 3, "link": 2, "body_link": 1, "none": 0}


def _dedup(lst: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in lst:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
