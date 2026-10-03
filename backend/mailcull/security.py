"""Request guards for a localhost-only API that holds a Gmail token.

* Host check — rejects DNS-rebinding requests (a hostile page resolving its own
  domain to 127.0.0.1 still sends its own Host header).
* Origin check — state-changing requests from a browser must come from MailCull's
  own pages (the Vite dev server counts), never from another site.

Requests with no Origin header (curl, scripts) are allowed: they aren't a
cross-site browser request.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_LOOPBACK = {"localhost", "127.0.0.1", "::1"}
_DEV_PORT = 5173  # Vite dev server


def _hostname(netloc: str) -> str:
    return (urlsplit(f"//{netloc}").hostname or "").lower()


class LocalOnlyMiddleware:
    def __init__(self, app: ASGIApp, port: int, extra_hosts: set[str] | None = None) -> None:
        self.app = app
        self.hosts = _LOOPBACK | {h.lower() for h in (extra_hosts or set())}
        self.origins = {
            f"http://{host}:{p}" for host in self.hosts for p in (port, _DEV_PORT)
        } | {f"http://[::1]:{p}" for p in (port, _DEV_PORT)}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        if _hostname(headers.get("host", "")) not in self.hosts:
            await PlainTextResponse("Invalid host header", status_code=400)(scope, receive, send)
            return

        origin = headers.get("origin")
        if origin and scope["method"] not in _SAFE_METHODS and origin.rstrip("/").lower() not in self.origins:
            await PlainTextResponse("Cross-origin request blocked", status_code=403)(scope, receive, send)
            return

        await self.app(scope, receive, send)
