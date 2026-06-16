"""OllamaClient — classify/summarise senders using a local Ollama model.

If Ollama is unreachable, falls back to header-based heuristics so the
pipeline never blocks on the LLM.
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp

from .models import Category, Decision, Sender

logger = logging.getLogger(__name__)

_BATCH_SIZE = 25
_TIMEOUT = aiohttp.ClientTimeout(total=120)

_CLASSIFICATION_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "required": ["id", "category", "rationale", "suggested_action"],
        "properties": {
            "id": {"type": "string"},
            "category": {
                "type": "string",
                "enum": ["Marketing", "Newsletter", "Transactional", "Social", "Spam", "Personal"],
            },
            "rationale": {"type": "string"},
            "suggested_action": {
                "type": "string",
                "enum": ["keep", "unsubscribe", "mute", "delete"],
            },
        },
    },
}

_SYSTEM_PROMPT = """You are an email triage assistant. Classify each sender record and suggest an action.

Return ONLY a JSON array (no markdown, no commentary) with one object per sender:
{
  "id": "<sender id>",
  "category": "Marketing|Newsletter|Transactional|Social|Spam|Personal",
  "rationale": "<one concise sentence explaining the classification>",
  "suggested_action": "keep|unsubscribe|mute|delete"
}

Guidelines:
- Marketing: promotional, sales, brand emails
- Newsletter: subscribed content digests
- Transactional: receipts, invoices, alerts, system notifications, security emails
- Social: platform notifications (LinkedIn, Twitter/X, etc.)
- Spam: unsolicited, never opted-in
- Personal: real people, low volume

Action guidelines:
- keep: transactional, personal, low-volume wanted mail
- unsubscribe: bulk/marketing where opt-out is available
- mute: wanted but noisy, or social noise; use when no unsubscribe exists
- delete: spam, high-volume never-opened backlog"""


class OllamaClient:
    def __init__(self, base_url: str, model: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._reachable: bool | None = None

    async def check_reachable(self) -> bool:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as s:
                async with s.get(f"{self._base_url}/api/tags") as r:
                    self._reachable = r.status == 200
        except Exception:
            self._reachable = False
        return self._reachable

    async def classify_senders(
        self,
        senders: list[Sender],
        on_batch: Callable[[int, int], Awaitable[None]] | None = None,
    ) -> tuple[list[Sender], bool]:
        """
        Classify a list of senders.
        on_batch(done, total) is called after each batch completes.
        Returns (enriched_senders, degraded) where degraded=True means heuristics were used.
        """
        reachable = await self.check_reachable()
        if not reachable:
            logger.info("Ollama unreachable — using heuristic classifier")
            result = _heuristic_classify(senders)
            if on_batch:
                await on_batch(len(senders), len(senders))
            return result, True

        enriched: list[Sender] = []
        total = len(senders)
        for i in range(0, total, _BATCH_SIZE):
            batch = senders[i : i + _BATCH_SIZE]
            try:
                results = await self._classify_batch(batch)
                enriched.extend(results)
            except Exception as exc:
                logger.warning("Ollama batch error: %s — falling back to heuristics", exc)
                enriched.extend(_heuristic_classify(batch))
            if on_batch:
                await on_batch(min(i + _BATCH_SIZE, total), total)

        return enriched, False

    async def _classify_batch(self, senders: list[Sender]) -> list[Sender]:
        user_content = json.dumps(
            [
                {
                    "id": s.id,
                    "from_name": s.from_name,
                    "from_address": s.from_address,
                    "domain": s.domain,
                    "message_count": s.message_count,
                    "sample_subjects": s.sample_subjects,
                    "has_unsubscribe": s.capability != "none",
                    "capability": s.capability,
                }
                for s in senders
            ],
            ensure_ascii=False,
        )

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "stream": False,
            "format": _CLASSIFICATION_SCHEMA,
        }

        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.post(
                f"{self._base_url}/api/chat", json=payload
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()

        raw = data.get("message", {}).get("content", "")
        classifications = _parse_json_response(raw)
        return _apply_classifications(senders, classifications)


def _parse_json_response(raw: str) -> list[dict]:
    """Parse and repair a JSON response from the LLM."""
    raw = raw.strip()
    # Strip markdown fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Attempt to extract a JSON array
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    logger.warning("Could not parse Ollama JSON response")
    return []


def _apply_classifications(
    senders: list[Sender], classifications: list[dict]
) -> list[Sender]:
    by_id = {c["id"]: c for c in classifications if isinstance(c, dict) and "id" in c}
    out: list[Sender] = []
    for s in senders:
        c = by_id.get(s.id)
        if c:
            out.append(
                s.model_copy(
                    update={
                        "category": _safe_category(c.get("category")),
                        "rationale": str(c.get("rationale", ""))[:500],
                        "suggested_action": _safe_action(c.get("suggested_action")),
                        "classification_degraded": False,
                    }
                )
            )
        else:
            # Fallback for this single sender
            out.extend(_heuristic_classify([s]))
    return out


def _safe_category(val: Any) -> Category:
    valid = {"Marketing", "Newsletter", "Transactional", "Social", "Spam", "Personal"}
    return val if val in valid else "Marketing"


def _safe_action(val: Any) -> Decision:
    valid = {"keep", "unsubscribe", "mute", "delete"}
    return val if val in valid else "keep"


# ── Heuristic classifier ──────────────────────────────────────────────────────

_TRANSACTIONAL_PATTERNS = [
    r"invoice", r"receipt", r"order", r"billing", r"payment", r"statement",
    r"security", r"alert", r"notification", r"no-reply@.*\.(aws|azure|google)",
    r"noreply@.*\.(github|gitlab|bitbucket)", r"verify", r"confirm",
]

_SPAM_PATTERNS = [
    r"deals@", r"promo@", r"offers@", r"discount", r"sale",
    r"groupon", r"flash.?sale", r"limited.?time",
]


def _heuristic_classify(senders: list[Sender]) -> list[Sender]:
    out: list[Sender] = []
    for s in senders:
        category, rationale, action = _heuristic_one(s)
        out.append(
            s.model_copy(
                update={
                    "category": category,
                    "rationale": rationale,
                    "suggested_action": action,
                    "classification_degraded": True,
                }
            )
        )
    return out


def _heuristic_one(s: Sender) -> tuple[Category, str, str]:
    addr = s.from_address.lower()
    name = s.from_name.lower()
    combined = addr + " " + name + " " + " ".join(s.sample_subjects).lower()

    if s.capability == "none" and s.message_count <= 10:
        return "Personal", "Low-volume, no unsubscribe header — likely personal.", "keep"

    for pat in _TRANSACTIONAL_PATTERNS:
        if re.search(pat, combined):
            return (
                "Transactional",
                "Matches transactional pattern (billing, security, or system notification).",
                "keep",
            )

    for pat in _SPAM_PATTERNS:
        if re.search(pat, combined):
            return (
                "Spam",
                "Matches known spam/deal-blast pattern — high volume, never opted in.",
                "delete" if s.message_count > 100 else "unsubscribe",
            )

    if s.capability in ("one_click", "link", "mailto"):
        if s.message_count > 200:
            return (
                "Marketing",
                "High-volume sender with unsubscribe capability.",
                "unsubscribe",
            )
        return (
            "Newsletter",
            "Has unsubscribe header — likely a subscribed newsletter.",
            "keep",
        )

    if s.capability == "none" and s.message_count > 50:
        return (
            "Marketing",
            "High-volume sender without unsubscribe header — mute recommended.",
            "mute",
        )

    return "Marketing", "Bulk pattern, moderate volume.", "unsubscribe"
