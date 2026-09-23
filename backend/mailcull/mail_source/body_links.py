"""Extract unsubscribe links from a message body.

Used for senders that don't send a List-Unsubscribe header. The body is
decoded and parsed in memory only; nothing but the chosen URL is kept.
"""
from __future__ import annotations

import base64
import html
import re
from html.parser import HTMLParser

# Strongest signal first — earlier patterns rank higher.
_RANKED_PATTERNS = [
    re.compile(r"unsubscribe|unsubcribe|unsub\b", re.I),
    re.compile(r"opt[\s_-]?out", re.I),
    re.compile(r"d[ée]sabonner|d[ée]sinscri|abmelden|abbestellen|darse de baja|cancelar suscripci|disiscriviti|uitschrijven|afmelden", re.I),
    re.compile(r"(stop|no longer) (receiving|getting) (these |this )?e?-?mails?", re.I),
    re.compile(r"(manage|update|change)\s+(your\s+)?(email\s+|e-mail\s+|subscription\s+|communication\s+)?preferences", re.I),
    re.compile(r"email preferences|subscription (centre|center|settings)|preference (centre|center)", re.I),
]

# Anchors that look like unsubscribe links but aren't.
_NEGATIVE = re.compile(r"resubscribe|re-subscribe|\bsubscribe now\b|sign up|view (this )?(email )?(in|on) (your )?browser|privacy policy", re.I)

_PLAIN_URL = re.compile(r"https?://[^\s<>\"')\]]+", re.I)


class _AnchorCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: list[tuple[str, str]] = []  # (href, visible text + title)
        self._href: str | None = None
        self._title: str = ""
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            a = dict(attrs)
            self._href = (a.get("href") or "").strip()
            self._title = " ".join(filter(None, [a.get("title"), a.get("aria-label")]))
            self._text = []
        elif tag == "img" and self._href is not None:
            alt = dict(attrs).get("alt")
            if alt:
                self._text.append(alt)

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            text = " ".join(" ".join(self._text).split())
            self.anchors.append((self._href, f"{text} {self._title}".strip()))
            self._href = None


def extract_unsubscribe_links(html_body: str | None, text_body: str | None = None) -> list[str]:
    """Return candidate unsubscribe URLs, best first (at most 3)."""
    scored: list[tuple[int, int, str]] = []  # (rank, order, url)

    if html_body:
        parser = _AnchorCollector()
        try:
            parser.feed(html_body)
        except Exception:
            pass
        for order, (href, label) in enumerate(parser.anchors):
            url = html.unescape(href)
            if not url.lower().startswith(("http://", "https://", "mailto:")):
                continue
            if _NEGATIVE.search(label) and not _RANKED_PATTERNS[0].search(label):
                continue
            rank = _rank(label)
            if rank is None:
                # URL path itself often says it, even when the anchor text is "here"
                rank = _rank(url)
                if rank is None:
                    continue
                rank += len(_RANKED_PATTERNS)  # URL match ranks below text match
            scored.append((rank, order, url))

    if not scored and text_body:
        # Plain-text bodies: take URLs on the same line as unsubscribe wording
        for order, line in enumerate(text_body.splitlines()):
            for m in _PLAIN_URL.finditer(line):
                url = m.group(0).rstrip(".,;")
                rank = _rank(line)
                if rank is None:
                    rank = _rank(url)
                    if rank is None:
                        continue
                    rank += len(_RANKED_PATTERNS)
                scored.append((rank, order, url))

    # mailto: from a body is a weak signal; only keep it if nothing else exists
    http = [s for s in scored if not s[2].lower().startswith("mailto:")]
    chosen = http or scored
    # Last occurrence usually lives in the footer, which is the real opt-out
    chosen.sort(key=lambda s: (s[0], -s[1]))
    out: list[str] = []
    for _, _, url in chosen:
        if url not in out:
            out.append(url)
    return out[:3]


def _rank(text: str) -> int | None:
    for i, pat in enumerate(_RANKED_PATTERNS):
        if pat.search(text):
            return i
    return None


def body_parts_from_payload(payload: dict) -> tuple[str | None, str | None]:
    """Walk a Gmail format=full payload and return (html, text) bodies."""
    html_parts: list[str] = []
    text_parts: list[str] = []

    def walk(part: dict) -> None:
        mime = (part.get("mimeType") or "").lower()
        data = (part.get("body") or {}).get("data")
        if data and mime in ("text/html", "text/plain"):
            decoded = _b64url_decode(data)
            (html_parts if mime == "text/html" else text_parts).append(decoded)
        for sub in part.get("parts") or []:
            walk(sub)

    walk(payload or {})
    return ("\n".join(html_parts) or None, "\n".join(text_parts) or None)


def _b64url_decode(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    raw = base64.urlsafe_b64decode(padded)
    return raw.decode("utf-8", errors="replace")
