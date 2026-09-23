"""Shared data models (Pydantic)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


Capability = Literal["one_click", "mailto", "link", "body_link", "none"]
Category = Literal["Marketing", "Newsletter", "Transactional", "Social", "Spam", "Personal"]
Decision = Literal["keep", "unsubscribe", "mute", "delete", "archive", "transactional", "snooze"] | None
Status = Literal[
    "pending", "kept", "unsubscribed", "unsub_pending", "still_sending", "needs_link",
    "muted", "deleted", "archived", "snoozed", "failed", "transactional",
]

# Statuses that mean "already handled" — execute skips these unless forced
DONE_STATUSES = {"kept", "unsubscribed", "unsub_pending", "muted", "deleted", "archived", "transactional"}


class Sender(BaseModel):
    id: str
    from_name: str
    from_address: str
    domain: str
    message_count: int
    first_seen: str  # ISO date
    last_seen: str   # ISO date
    sample_subjects: list[str] = Field(default_factory=list)

    capability: Capability = "none"
    # All known methods, preferred first (derived from the fields below)
    unsubscribe_links: list[str] = Field(default_factory=list)
    # Methods from the newest message that advertised any — tokens are per-message
    one_click_url: str | None = None
    mailto_links: list[str] = Field(default_factory=list)
    http_links: list[str] = Field(default_factory=list)
    unsubscribe_source: Literal["header", "body"] | None = None
    latest_message_id: str | None = None
    latest_ts: int = 0  # internalDate (ms) of the newest message seen

    # LLM / heuristic classification
    category: Category | None = None
    rationale: str | None = None
    suggested_action: Decision = None
    classification_degraded: bool = False

    # User decision
    decision: Decision = None
    status: Status = "pending"
    unsubscribed_at: str | None = None  # ISO datetime (UTC)
    unsub_method: str | None = None
    snooze_until: str | None = None     # ISO date

    @model_validator(mode="after")
    def _derive_methods(self) -> "Sender":
        """Rows saved before the per-method fields existed only have the flat list."""
        if self.one_click_url or self.mailto_links or self.http_links or not self.unsubscribe_links:
            return self
        links = self.unsubscribe_links
        self.mailto_links = [l for l in links if l.lower().startswith("mailto:")]
        web = [l for l in links if l.lower().startswith(("http://", "https://"))]
        if self.capability == "one_click":
            https = [l for l in web if l.lower().startswith("https://")]
            self.one_click_url = https[0] if https else None
            web = [l for l in web if l != self.one_click_url]
        self.http_links = web
        return self


class ScanRecord(BaseModel):
    id: int
    started_at: datetime
    finished_at: datetime | None = None
    since_days: int
    total_messages: int = 0
    total_senders: int = 0
    phase: str = "idle"
    progress_pct: int = 0
    status_detail: str | None = None
    error: str | None = None


class ActionLog(BaseModel):
    id: int
    scan_id: int | None
    sender_id: str
    action: str
    method: str
    result: str
    http_status: int | None = None
    dry_run: bool
    undo_data: dict | None = None
    undone: bool = False
    created_at: datetime


class ActionPreview(BaseModel):
    sender_id: str
    from_name: str
    from_address: str
    decision: Decision
    method: str
    description: str
    can_automate: bool
    needs_manual: bool


class ActionResult(BaseModel):
    sender_id: str
    from_name: str
    from_address: str
    decision: Decision
    method: str
    status: Status
    detail: str
    can_undo: bool
    link: str | None = None  # populated for needs_link results
    error: str | None = None
    http_status: int | None = None
    attempts: list[str] = Field(default_factory=list)  # e.g. ["one-click: HTTP 405", "mailto: sent"]
    action_id: int | None = None  # action_log row, used for undo
    skipped: bool = False  # already handled; nothing ran
