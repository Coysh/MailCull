"""MailSource interface — keep this clean so alternative adapters (IMAP, etc.) can be added."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Awaitable, Callable


@dataclass
class RawMessage:
    """Minimal parsed message record: headers only, no body."""
    message_id: str
    from_address: str
    from_name: str
    subject: str
    date_str: str
    list_unsubscribe: str | None        # raw header value
    list_unsubscribe_post: str | None   # raw header value
    internal_date_ms: int = 0           # server receive time (reliable ordering)


class MailSource(ABC):
    """Adapter interface for reading mail metadata."""

    @abstractmethod
    async def authenticate(self, redirect_uri: str) -> str:
        """Return a consent URL the user must visit."""

    @abstractmethod
    async def handle_callback(self, code: str, state: str, redirect_uri: str) -> None:
        """Exchange the auth code for tokens and persist them."""

    @abstractmethod
    async def is_connected(self) -> bool:
        """Return True if valid (refreshable) credentials exist."""

    @abstractmethod
    async def get_account_email(self) -> str | None:
        """Return the authenticated account email address."""

    @abstractmethod
    async def get_granted_scopes(self) -> list[str]:
        """Return the list of scopes actually granted."""

    @abstractmethod
    async def revoke(self) -> None:
        """Revoke stored credentials."""

    @abstractmethod
    def stream_messages(
        self,
        since_days: int,
        batch_size: int = 100,
        on_total: Callable[[int], Awaitable[None]] | None = None,
    ) -> AsyncIterator[list[RawMessage]]:
        """
        Yield batches of RawMessage covering the given time window.
        on_total(n) is awaited once the message count is known, before the first batch.
        Yields before classification so the UI can stream results.
        """

    @abstractmethod
    async def find_body_unsubscribe_links(self, message_ids: dict[str, str]) -> dict[str, list[str]]:
        """
        For each {key: message_id}, fetch that message's body and return
        {key: [unsubscribe URLs found in it]}. Bodies are parsed in memory
        and never persisted.
        """
