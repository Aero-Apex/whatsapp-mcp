"""Serve the WhatsApp MCP tools over streamable HTTP at the root path, behind a bearer token.

Reuses the tools defined in main.py. Run with MCP_TOKEN set (see http.env).
"""

import hmac
import os

import uvicorn
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import PlainTextResponse

from main import mcp

MCP_TOKEN = os.environ.get("MCP_TOKEN", "")
PUBLIC_HOST = os.environ.get("PUBLIC_HOST", "localhost")
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8795"))

mcp.settings.streamable_http_path = "/"
mcp.settings.transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=[PUBLIC_HOST, "127.0.0.1:*", "localhost:*"],
)


class BearerAuth:
    """Pure ASGI middleware: every HTTP request must send 'Authorization: Bearer <MCP_TOKEN>'."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            auth = dict(scope["headers"]).get(b"authorization", b"").decode("latin-1")
            allowed = bool(MCP_TOKEN) and hmac.compare_digest(auth.encode(), f"Bearer {MCP_TOKEN}".encode())
            if not allowed:
                await PlainTextResponse("Unauthorized", status_code=401)(scope, receive, send)
                return
        await self.app(scope, receive, send)


app = BearerAuth(mcp.streamable_http_app())

if __name__ == "__main__":
    if not MCP_TOKEN:
        raise SystemExit("MCP_TOKEN is not set")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
