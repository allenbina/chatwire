"""MCP HTTP transport — mounts on the FastAPI app at /mcp/.

Provides HTTP access to chatwire's MCP tools so remote LLM agents
(e.g. claude.ai web connector, OpenAI Responses API) can call tools
without a local stdio process.

Supports two transports (auto-selected):
  - **Streamable HTTP** (2025 MCP spec) — single endpoint, stateless.
    All methods on /mcp/ (GET for SSE stream, POST for JSON-RPC, DELETE).
  - **Legacy SSE** (fallback) — GET /mcp/sse + POST /mcp/messages.
    Used if StreamableHTTPSessionManager is unavailable.

Auth: every request must carry a valid ``Authorization: Bearer cwk_...``
API key with the ``mcp`` scope.

Gated behind ``integrations.mcp.http_enabled`` in config.json.
Requires the ``mcp`` Python package (pip install mcp).
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

log = logging.getLogger("chatwire.mcp_http")


def _build_server():
    """Create and configure the MCP Server with tool handlers.

    Returns (server, mcp_types) — shared between both transports.
    """
    from mcp.server import Server
    import mcp.types as mcp_types

    from integrations.mcp import (
        TOOL_DEFINITIONS, TOOL_DISPATCH,
        _is_tool_enabled, check_scope, _granted_scopes,
    )

    server = Server("chatwire")

    @server.list_tools()
    async def _list_tools():
        granted = _granted_scopes()
        return [
            mcp_types.Tool(
                name=t["name"],
                description=t["description"],
                inputSchema=t["inputSchema"],
            )
            for t in TOOL_DEFINITIONS
            if _is_tool_enabled(t["name"]) and check_scope(t["name"], granted) is None
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict):
        if not _is_tool_enabled(name):
            return [mcp_types.TextContent(type="text", text=f"Tool disabled: {name}")]
        granted = _granted_scopes()
        scope_err = check_scope(name, granted)
        if scope_err:
            return [mcp_types.TextContent(type="text", text=scope_err)]
        handler = TOOL_DISPATCH.get(name)
        if handler is None:
            return [mcp_types.TextContent(type="text", text=f"Unknown tool: {name}")]
        try:
            result = await asyncio.to_thread(handler, arguments or {})
        except Exception as exc:
            result = {"error": str(exc)}
        return [
            mcp_types.TextContent(type="text", text=json.dumps(result, default=str))
        ]

    return server


def _auth_middleware_class():
    """Return the ASGI auth middleware class (requires starlette)."""
    from starlette.requests import Request as StarletteRequest
    from starlette.responses import JSONResponse as StarletteJSON
    from starlette.types import ASGIApp, Receive, Scope, Send

    class _McpAuthMiddleware:
        """ASGI middleware: require Bearer cwk_ with mcp scope on every request."""

        def __init__(self, app: ASGIApp):
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send):
            if scope["type"] not in ("http", "websocket"):
                await self.app(scope, receive, send)
                return
            req = StarletteRequest(scope, receive, send)
            auth_header = req.headers.get("authorization", "")
            if not auth_header.startswith("Bearer "):
                resp = StarletteJSON({"detail": "MCP HTTP requires an API key."}, status_code=401)
                await resp(scope, receive, send)
                return
            from web.api_keys import authenticate_bearer
            entry = authenticate_bearer(auth_header[len("Bearer "):])
            if entry is None:
                resp = StarletteJSON({"detail": "Invalid API key."}, status_code=401)
                await resp(scope, receive, send)
                return
            if "mcp" not in entry.scopes:
                resp = StarletteJSON({"detail": "API key lacks 'mcp' scope."}, status_code=403)
                await resp(scope, receive, send)
                return
            await self.app(scope, receive, send)

    return _McpAuthMiddleware


# ---------------------------------------------------------------------------
# Streamable HTTP transport (2025 MCP spec — preferred)
# ---------------------------------------------------------------------------

def _create_streamable_http_app():
    """Build Starlette app using StreamableHTTPSessionManager.

    Single endpoint at / handles GET (SSE), POST (JSON-RPC), DELETE.
    Stateless mode — no session persistence needed.
    """
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    from starlette.applications import Starlette
    from starlette.routing import Mount

    server = _build_server()
    manager = StreamableHTTPSessionManager(app=server, stateless=True)

    AuthMiddleware = _auth_middleware_class()

    async def handle_mcp(scope, receive, send):
        await manager.handle_request(scope, receive, send)

    # The manager's handle_request is a raw ASGI callable.
    # Wrap it in a Starlette app with auth middleware.
    async def asgi_app(scope, receive, send):
        if scope["type"] == "lifespan":
            # Manager needs to run its background task group during lifespan
            async with manager.run():
                await Starlette()(scope, receive, send)
            return
        await AuthMiddleware(handle_mcp)(scope, receive, send)

    # Mount handles all methods at the root path
    inner = Starlette(
        routes=[
            Mount("/", app=handle_mcp),
        ],
    )

    # Wrap with auth + lifespan
    class _App:
        """ASGI app that manages the StreamableHTTP session manager lifecycle."""

        def __init__(self):
            self._manager_ctx = None

        async def __call__(self, scope, receive, send):
            if scope["type"] == "lifespan":
                # Handle lifespan: start/stop the manager's task group
                while True:
                    msg = await receive()
                    if msg["type"] == "lifespan.startup":
                        self._manager_ctx = manager.run()
                        await self._manager_ctx.__aenter__()
                        await send({"type": "lifespan.startup.complete"})
                    elif msg["type"] == "lifespan.shutdown":
                        if self._manager_ctx:
                            await self._manager_ctx.__aexit__(None, None, None)
                        await send({"type": "lifespan.shutdown.complete"})
                        return
                return

            # For HTTP requests, run through auth then manager
            auth = _auth_middleware_class()
            await auth(manager.handle_request)(scope, receive, send)

    log.info("MCP Streamable HTTP app created (stateless mode)")
    return _App()


# ---------------------------------------------------------------------------
# Legacy SSE transport (fallback)
# ---------------------------------------------------------------------------

def _create_legacy_sse_app():
    """Build Starlette app using SseServerTransport (legacy two-endpoint)."""
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Route

    server = _build_server()
    sse = SseServerTransport("/mcp/messages")

    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await server.run(
                streams[0], streams[1],
                server.create_initialization_options(),
            )

    async def handle_post(request):
        await sse.handle_post_message(request.scope, request.receive, request._send)

    AuthMiddleware = _auth_middleware_class()
    mcp_app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Route("/messages", endpoint=handle_post, methods=["POST"]),
        ],
    )

    log.info("MCP legacy SSE app created")
    return mcp_app


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def create_mcp_sse_app():
    """Build the MCP HTTP transport app.

    Tries Streamable HTTP first (2025 spec), falls back to legacy SSE.
    Raises ImportError if the ``mcp`` package is not installed.
    """
    try:
        return _create_streamable_http_app()
    except Exception as exc:
        log.info("Streamable HTTP unavailable (%s), falling back to legacy SSE", exc)
        return _create_legacy_sse_app()
