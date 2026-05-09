"""MCP (Model Context Protocol) integration.

Exposes chatwire as MCP tools so LLM agents (e.g. Claude Code) can
send iMessages, read conversations, and search message history.

Transport: stdio only in this release (SSE in a later wave).

Usage:
    chatwire mcp          # start MCP stdio server

Tools:
    send_message(handle, text)
    read_messages(handle, since=0, limit=50)
    list_conversations(limit=20)
    search_messages(query, handle="")
"""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from integrations.base import BridgeContext, InboundMessage

log = logging.getLogger("chatwire.mcp")


# ---------------------------------------------------------------------------
# Module-level wrappers — defined at module scope so tests can patch them
# without triggering heavy imports.
# ---------------------------------------------------------------------------

def _check_send_guard(recipient: str, body: str, source: str) -> str:
    from chat_send import check_send_guard  # noqa: PLC0415
    return check_send_guard(recipient, body, source)


def _send_text_confirm(handle: str, body: str):
    from chat_send import send_text_confirm  # noqa: PLC0415
    return send_text_confirm(handle, body)


def _history_for(handle: str):
    from web.main import history_for  # noqa: PLC0415
    return history_for(handle)


def _list_conversations_fn() -> list:
    from web.main import list_conversations  # noqa: PLC0415
    return list_conversations()


def _chat_db_path() -> Path:
    """Return the path to chat.db (module-level so tests can patch)."""
    from chat_db import CHAT_DB  # noqa: PLC0415
    return CHAT_DB


# ---------------------------------------------------------------------------
# Tool implementations — pure synchronous logic, no `mcp` dependency.
# These are called by TOOL_DISPATCH and tested independently.
# ---------------------------------------------------------------------------

def tool_send_message(handle: str, text: str) -> dict:
    """Send an iMessage through the anti-spam guardrails.

    Returns {status, hint, service} on success, or an error dict on failure.
    """
    from chat_send import BroadcastBlockedError, RateLimitError  # noqa: PLC0415
    try:
        _check_send_guard(handle, text, "mcp")
    except RateLimitError as exc:
        return {"error": "rate_limited", "detail": str(exc)}
    except BroadcastBlockedError as exc:
        return {
            "error": "broadcast_blocked",
            "detail": str(exc),
            "retry_after": exc.retry_after,
        }
    result = _send_text_confirm(handle, text)
    return {"status": result.status, "hint": result.hint, "service": result.service}


def tool_read_messages(handle: str, since: int = 0, limit: int = 50) -> dict:
    """Return recent messages for a 1:1 conversation.

    `since` filters to rows with ROWID > since.
    `limit` caps the number of returned messages.
    """
    msgs, has_more = _history_for(handle)
    if since:
        msgs = [m for m in msgs if m["rowid"] > since]
    msgs = msgs[-limit:]
    return {"handle": handle, "messages": msgs, "has_more": has_more}


def tool_list_conversations(limit: int = 20) -> dict:
    """List active conversations with last-message preview."""
    convos = _list_conversations_fn()[:limit]
    return {
        "conversations": [
            {
                "handle": c.get("handle") or c.get("guid", ""),
                "name": c.get("name", ""),
                "last_text": c.get("preview", ""),
                "last_ts": c.get("last_dt", 0),
                "unread_count": c.get("n", 0),
            }
            for c in convos
        ]
    }


def tool_search_messages(query: str, handle: str = "") -> dict:
    """Full-text search across chat.db using SQL LIKE.

    Returns up to 100 matching messages, newest first.
    Filtering by `handle` restricts results to that contact.
    """
    db = _chat_db_path()
    results: list[dict] = []
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            like = f"%{query}%"
            if handle:
                sql = (
                    "SELECT m.ROWID, m.date, m.is_from_me, m.text, "
                    "COALESCE(h.id, '') "
                    "FROM message m "
                    "LEFT JOIN handle h ON m.handle_id = h.ROWID "
                    "WHERE m.text LIKE ? AND lower(COALESCE(h.id, '')) = lower(?) "
                    "ORDER BY m.ROWID DESC LIMIT 100"
                )
                rows = conn.execute(sql, (like, handle)).fetchall()
            else:
                sql = (
                    "SELECT m.ROWID, m.date, m.is_from_me, m.text, "
                    "COALESCE(h.id, '') "
                    "FROM message m "
                    "LEFT JOIN handle h ON m.handle_id = h.ROWID "
                    "WHERE m.text LIKE ? "
                    "ORDER BY m.ROWID DESC LIMIT 100"
                )
                rows = conn.execute(sql, (like,)).fetchall()
            for row in rows:
                results.append({
                    "rowid": row[0],
                    "date": row[1],
                    "from_me": bool(row[2]),
                    "text": row[3] or "",
                    "handle": row[4],
                })
        finally:
            conn.close()
    except Exception as exc:
        return {"error": str(exc), "results": []}
    return {"query": query, "results": results}


# ---------------------------------------------------------------------------
# Tool registry — definitions + dispatch table
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "name": "send_message",
        "description": (
            "Send an iMessage to a contact. Goes through chatwire's "
            "anti-spam guardrails (rate limit + broadcast detection)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "handle": {
                    "type": "string",
                    "description": "Phone number or email, e.g. +15551234567",
                },
                "text": {
                    "type": "string",
                    "description": "Message text to send",
                },
            },
            "required": ["handle", "text"],
        },
    },
    {
        "name": "read_messages",
        "description": "Read recent messages for a 1:1 conversation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "handle": {
                    "type": "string",
                    "description": "Contact handle",
                },
                "since": {
                    "type": "integer",
                    "description": "Return only messages with ROWID > since",
                    "default": 0,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of messages to return",
                    "default": 50,
                },
            },
            "required": ["handle"],
        },
    },
    {
        "name": "list_conversations",
        "description": "List active conversations with last-message preview.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of conversations to return",
                    "default": 20,
                },
            },
        },
    },
    {
        "name": "search_messages",
        "description": "Full-text search across all iMessages using SQL LIKE.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search string",
                },
                "handle": {
                    "type": "string",
                    "description": "Restrict to this contact handle (optional)",
                    "default": "",
                },
            },
            "required": ["query"],
        },
    },
]

TOOL_DISPATCH: dict[str, Any] = {
    "send_message": lambda args: tool_send_message(
        args["handle"], args["text"]
    ),
    "read_messages": lambda args: tool_read_messages(
        args["handle"],
        int(args.get("since", 0)),
        int(args.get("limit", 50)),
    ),
    "list_conversations": lambda args: tool_list_conversations(
        int(args.get("limit", 20))
    ),
    "search_messages": lambda args: tool_search_messages(
        args["query"], args.get("handle", "")
    ),
}


# ---------------------------------------------------------------------------
# MCP server runner — requires the `mcp` package (Python 3.10+)
# ---------------------------------------------------------------------------

def run_stdio_server() -> None:
    """Start the MCP server reading JSON-RPC from stdin, writing to stdout.

    Raises ImportError if the `mcp` package is not installed.
    Install with: pip install mcp
    """
    try:
        from mcp.server import Server  # noqa: PLC0415
        from mcp.server.stdio import stdio_server  # noqa: PLC0415
        import mcp.types as mcp_types  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "The `mcp` package is required to run the MCP server.\n"
            "Install it with: pip install mcp"
        ) from exc

    app = Server("chatwire")

    @app.list_tools()
    async def _list_tools() -> list:
        return [
            mcp_types.Tool(
                name=t["name"],
                description=t["description"],
                inputSchema=t["inputSchema"],
            )
            for t in TOOL_DEFINITIONS
        ]

    @app.call_tool()
    async def _call_tool(name: str, arguments: dict) -> list:
        handler = TOOL_DISPATCH.get(name)
        if handler is None:
            return [
                mcp_types.TextContent(
                    type="text", text=f"Unknown tool: {name}"
                )
            ]
        try:
            # Tool functions are synchronous and may block (send waits up to
            # 8 s for delivery confirmation), so run them in a thread.
            result = await asyncio.to_thread(handler, arguments or {})
        except Exception as exc:
            result = {"error": str(exc)}
        return [
            mcp_types.TextContent(
                type="text", text=json.dumps(result, default=str)
            )
        ]

    async def _amain() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options(),
            )

    asyncio.run(_amain())


# ---------------------------------------------------------------------------
# Integration class — satisfies the Integration Protocol
# ---------------------------------------------------------------------------

class McpIntegration:
    """Registers the MCP integration with the bridge.

    The bridge loads this when ``integrations.mcp.enabled = true`` in
    config.json. It does not start the stdio server by itself — the server
    is started via ``chatwire mcp`` and communicates with callers over stdio.

    The integration class exists so that:
    - The enabled flag appears in the settings UI.
    - Users can see it is available in the integrations list.
    """

    NAME = "mcp"
    DISPLAY_NAME = "MCP Server"
    DESCRIPTION = "Expose chatwire as MCP tools for LLM agents (run: chatwire mcp)"
    ICON = "🤖"

    SETTINGS_SCHEMA = {
        "type": "object",
        "properties": {
            "enabled": {
                "type": "boolean",
                "default": False,
                "title": "Enable MCP integration",
                "description": (
                    "When enabled, run `chatwire mcp` to start the MCP "
                    "stdio server. Connect Claude Code or any MCP client "
                    "to send/read messages and search history."
                ),
            },
        },
    }

    def __init__(self, config: dict[str, Any]):
        self._enabled: bool = bool(config.get("enabled", False))

    async def start(self, ctx: BridgeContext) -> None:
        log.info(
            "mcp integration ready — run `chatwire mcp` to start the stdio server"
        )

    async def stop(self) -> None:
        pass

    async def on_inbound(self, msg: InboundMessage) -> None:
        # MCP clients poll via read_messages / search_messages — no push needed.
        pass
