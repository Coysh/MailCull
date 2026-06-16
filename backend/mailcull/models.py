"""Shared data models (Pydantic)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


Capability = Literal["one_click", "link", "mailto", "none"]
Category = Literal["Marketing", "Newsletter", "Transactional", "Social", "Spam", "Personal"]
Decision = Literal["keep", "unsubscribe", "mute", "delete", "archive", "transactional", "snooze"] | None
Status = Literal[
    "pending", "kept", "unsubscribed", "needs_link", "muted", "deleted", "archived",
    "snoozed", "failed", "transactional",
]


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
    unsubscribe_links: list[str] = Field(default_factory=list)

    # LLM / heuristic classification
    category: Category | None = None
    rationale: str | None = None
    suggested_action: Decision = None
    classification_degraded: bool = False

    # User decision
    decision: Decision = None
    status: Status = "pending"


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
