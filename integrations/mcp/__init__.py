"""MCP (Model Context Protocol) integration — v2.

Exposes chatwire as MCP tools so LLM agents (e.g. Claude Code) can
send iMessages, read conversations, and search message history.

v2 additions:
- Scope enforcement (mcp:read, mcp:send, mcp:contacts, mcp:meta)
- Contact filter (whitelist / all / explicit)
- Per-tool config with master-defaults + override pattern
- Confirmation flow for send tools
- New tools: resolve_contact, send_message_to_group, get_unread_summary,
  get_status, draft_message, confirm_send

Transport: stdio (primary) + HTTP/SSE (via web/mcp_sse.py).

Usage:
    chatwire mcp              # start MCP stdio server (all granted scopes)
    chatwire mcp --read-only  # start with send tools disabled
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any

from integrations.base import BridgeContext, InboundMessage
from web import log_stream as _ls

log = logging.getLogger("chatwire.mcp")


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _load_mcp_config() -> dict:
    """Load the MCP integration config from config.json."""
    import config as _cfg
    cfg = _cfg.load_config()
    return cfg.get("integrations", {}).get("mcp", {})


def _tool_config(tool_name: str) -> dict:
    """Return the per-tool config dict (may be empty = all inherited)."""
    mcp = _load_mcp_config()
    tools = mcp.get("tools", {})
    return tools.get(tool_name, {})


def _effective_contact_filter(tool_name: str) -> str:
    """Resolve the effective contact_filter for a tool (per-tool override or master)."""
    tc = _tool_config(tool_name)
    if "contact_filter" in tc:
        return tc["contact_filter"]
    mcp = _load_mcp_config()
    return mcp.get("contact_filter", "whitelist")


def _effective_confirmation(tool_name: str) -> str:
    """Resolve the effective confirmation mode for a tool."""
    tc = _tool_config(tool_name)
    if "confirmation" in tc:
        return tc["confirmation"]
    mcp = _load_mcp_config()
    return mcp.get("confirmation_mode", "never")


def _is_tool_enabled(tool_name: str) -> bool:
    """Check if a specific tool is enabled."""
    mcp = _load_mcp_config()
    # Legacy: enabled_tools list (flat list of tool names)
    if "enabled_tools" in mcp and "tools" not in mcp:
        return tool_name in mcp["enabled_tools"]
    # v2: per-tool config
    tools = mcp.get("tools", {})
    tc = tools.get(tool_name, {})
    return tc.get("enabled", True)  # default enabled if not specified


def _allowed_contacts(tool_name: str) -> set | None:
    """Return the set of allowed handles for a tool, or None for unrestricted.

    Returns:
        set of lowercase handles — tool should only operate on these
        None — no restriction (contact_filter is "all")
    """
    mode = _effective_contact_filter(tool_name)
    if mode == "all":
        return None
    if mode == "explicit":
        mcp = _load_mcp_config()
        return {h.strip().lower() for h in mcp.get("mcp_contacts", []) if h.strip()}
    # Default: "whitelist"
    from whitelist import all_handles
    import os
    self_handles = {h.strip().lower() for h in os.environ.get("SELF_HANDLES", "").split(",") if h.strip()}
    return all_handles() | self_handles


def _sends_paused() -> bool:
    """Check if all MCP sends are paused (kill switch)."""
    mcp = _load_mcp_config()
    return bool(mcp.get("pause_sends", False))


def _send_allowed_for(handle: str) -> bool:
    """Check if sending to a specific handle is allowed."""
    mcp = _load_mcp_config()
    send_list = mcp.get("send_allowed_contacts", [])
    if not send_list:
        # No explicit send list — fall back to contact filter
        allowed = _allowed_contacts("send_message")
        if allowed is None:
            return True
        return handle.strip().lower() in allowed
    return handle.strip().lower() in {h.strip().lower() for h in send_list}


# ---------------------------------------------------------------------------
# Scope definitions
# ---------------------------------------------------------------------------

SCOPES = {
    "mcp:read": [
        "read_messages", "list_conversations", "search_messages",
        "get_unread_summary",
    ],
    "mcp:send": [
        "send_message", "send_message_to_group", "confirm_send",
    ],
    "mcp:contacts": [
        "resolve_contact",
    ],
    "mcp:meta": [
        "get_status", "draft_message",
    ],
}

# Reverse map: tool_name → required scope
TOOL_SCOPE: dict[str, str] = {}
for _scope, _tools in SCOPES.items():
    for _t in _tools:
        TOOL_SCOPE[_t] = _scope


def _granted_scopes(read_only: bool = False) -> set:
    """Return the set of granted scopes based on config."""
    mcp = _load_mcp_config()
    # Default scopes
    configured = set(mcp.get("scopes", ["mcp:read", "mcp:contacts", "mcp:meta"]))
    if read_only:
        configured.discard("mcp:send")
    return configured


def check_scope(tool_name: str, granted: set) -> str | None:
    """Return an error message if the tool is not in a granted scope, else None."""
    required = TOOL_SCOPE.get(tool_name)
    if required is None:
        return None  # Unknown tool — let dispatch handle it
    if required not in granted:
        return f"Tool '{tool_name}' requires scope '{required}' which is not granted."
    return None


# ---------------------------------------------------------------------------
# Confirmation queue (in-memory, per-process)
# ---------------------------------------------------------------------------

_PENDING_SENDS: dict[str, dict] = {}  # id → {handle, text, created_at, tool}
_PENDING_TTL = 300  # 5 minutes


def _queue_send(handle: str, text: str, tool: str = "send_message") -> dict:
    """Queue a send for confirmation. Returns the pending confirmation response."""
    confirm_id = "cw_" + secrets.token_hex(8)
    _PENDING_SENDS[confirm_id] = {
        "handle": handle,
        "text": text,
        "tool": tool,
        "created_at": time.time(),
    }
    _ls.info("mcp", f"send queued for confirmation: {confirm_id} → {handle}")
    return {
        "status": "pending_confirmation",
        "confirmation_id": confirm_id,
        "preview": {"handle": handle, "text": text},
        "expires_in_seconds": _PENDING_TTL,
    }


def _expire_pending():
    """Remove expired entries from the pending queue."""
    now = time.time()
    expired = [k for k, v in _PENDING_SENDS.items() if now - v["created_at"] > _PENDING_TTL]
    for k in expired:
        del _PENDING_SENDS[k]


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


def _send_text_to_chat_confirm(chat_guid: str, body: str):
    from chat_send import send_text_to_chat_confirm  # noqa: PLC0415
    return send_text_to_chat_confirm(chat_guid, body)


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


def _load_contacts_lookup() -> dict:
    """Return {handle_lc: display_name} from the contacts module."""
    from contacts import load_lookup  # noqa: PLC0415
    return load_lookup()


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def tool_send_message(handle: str, text: str, wait_for_delivery: bool = True) -> dict:
    """Send an iMessage through the anti-spam guardrails.

    Respects confirmation mode: may queue for approval instead of sending.
    With wait_for_delivery=False, returns immediately after osascript (< 2s)
    instead of polling for delivery confirmation (up to 8s).
    """
    from chat_send import BroadcastBlockedError, RateLimitError  # noqa: PLC0415

    if _sends_paused():
        return {"error": "sends_paused", "detail": "MCP sends are paused via kill switch."}

    if not _send_allowed_for(handle):
        return {"error": "contact_not_allowed", "detail": f"Handle '{handle}' is not in the send allow-list."}

    # Check confirmation mode
    confirm_mode = _effective_confirmation("send_message")
    if confirm_mode == "always":
        return _queue_send(handle, text, "send_message")
    elif confirm_mode == "contacts_only":
        mcp = _load_mcp_config()
        send_list = mcp.get("send_allowed_contacts", [])
        if send_list and handle.strip().lower() not in {h.lower() for h in send_list}:
            return _queue_send(handle, text, "send_message")

    _ls.info("mcp", f"tool: send_message to {handle} ({len(text)} chars)")
    try:
        _check_send_guard(handle, text, "mcp")
    except RateLimitError as exc:
        _ls.warn("mcp", f"send_message rate limited: {exc}")
        return {"error": "rate_limited", "detail": str(exc)}
    except BroadcastBlockedError as exc:
        _ls.error("mcp", f"send_message broadcast blocked: {exc}")
        return {
            "error": "broadcast_blocked",
            "detail": str(exc),
            "retry_after": exc.retry_after,
        }

    if not wait_for_delivery:
        from chat_send import send_text  # noqa: PLC0415
        send_text(handle, text)
        _ls.info("mcp", "send_message fired (no delivery wait)")
        return {"status": "queued", "hint": "Sent without waiting for delivery confirmation."}

    result = _send_text_confirm(handle, text)
    _ls.info("mcp", f"send_message result: {result.status}")
    return {"status": result.status, "hint": result.hint, "service": result.service}


def tool_send_message_to_group(chat_guid: str, text: str) -> dict:
    """Send an iMessage to a group chat via its GUID."""
    from chat_send import BroadcastBlockedError, RateLimitError  # noqa: PLC0415

    if _sends_paused():
        return {"error": "sends_paused", "detail": "MCP sends are paused via kill switch."}

    # Check confirmation mode
    confirm_mode = _effective_confirmation("send_message_to_group")
    if confirm_mode == "always":
        return _queue_send(chat_guid, text, "send_message_to_group")

    _ls.info("mcp", f"tool: send_message_to_group to {chat_guid} ({len(text)} chars)")
    try:
        _check_send_guard(chat_guid, text, "mcp")
    except RateLimitError as exc:
        return {"error": "rate_limited", "detail": str(exc)}
    except BroadcastBlockedError as exc:
        return {"error": "broadcast_blocked", "detail": str(exc), "retry_after": exc.retry_after}
    result = _send_text_to_chat_confirm(chat_guid, text)
    return {"status": result.status, "hint": result.hint, "service": result.service}


def tool_confirm_send(confirmation_id: str) -> dict:
    """Confirm a pending send that was queued for approval."""
    from chat_send import BroadcastBlockedError, RateLimitError  # noqa: PLC0415

    _expire_pending()
    entry = _PENDING_SENDS.pop(confirmation_id, None)
    if entry is None:
        return {"error": "not_found", "detail": "Confirmation ID not found or expired."}

    handle = entry["handle"]
    text = entry["text"]
    tool = entry["tool"]

    _ls.info("mcp", f"confirmed send {confirmation_id}: {tool} → {handle}")
    try:
        _check_send_guard(handle, text, "mcp")
    except RateLimitError as exc:
        return {"error": "rate_limited", "detail": str(exc)}
    except BroadcastBlockedError as exc:
        return {"error": "broadcast_blocked", "detail": str(exc), "retry_after": exc.retry_after}

    if tool == "send_message_to_group":
        result = _send_text_to_chat_confirm(handle, text)
    else:
        result = _send_text_confirm(handle, text)
    return {"status": result.status, "hint": result.hint, "service": result.service}


def tool_read_messages(handle: str, since: int = 0, limit: int = 50) -> dict:
    """Return recent messages for a 1:1 conversation."""
    allowed = _allowed_contacts("read_messages")
    if allowed is not None and handle.strip().lower() not in allowed:
        return {"error": "contact_not_allowed", "detail": f"Handle '{handle}' is not accessible."}

    msgs, has_more = _history_for(handle)
    if since:
        msgs = [m for m in msgs if m["rowid"] > since]
    msgs = msgs[-limit:]
    return {"handle": handle, "messages": msgs, "has_more": has_more}


def tool_list_conversations(limit: int = 20) -> dict:
    """List active conversations with last-message preview."""
    convos = _list_conversations_fn()[:limit]
    # list_conversations already respects whitelist internally via relay_handles()
    # For "all" mode, we'd need a different query — but the existing function
    # is whitelist-filtered. This is acceptable for v1.
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
    """Full-text search across messages using FTS5 index.

    Uses a persistent FTS5 sidecar index for fast search (<100ms).
    Falls back to SQL LIKE if FTS5 fails.
    Respects contact_filter: in whitelist/explicit mode, only returns
    messages from allowed handles.
    """
    allowed = _allowed_contacts("search_messages")
    db = _chat_db_path()

    # Try FTS5 first
    try:
        from integrations.mcp.fts_index import search as fts_search  # noqa: PLC0415
        raw_results = fts_search(query, db, handle=handle)
    except Exception as fts_err:
        _ls.warn("mcp", f"FTS5 search failed, falling back to LIKE: {fts_err}")
        raw_results = _search_like_fallback(query, db, handle)

    # Apply contact filter
    results = []
    for row in raw_results:
        if allowed is not None and row["handle"].lower() not in allowed:
            continue
        results.append(row)

    return {"query": query, "results": results}


def _search_like_fallback(query: str, db: Path, handle: str = "") -> list[dict]:
    """Fallback LIKE search when FTS5 is unavailable."""
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
    except Exception:
        pass
    return results


def tool_resolve_contact(name: str) -> dict:
    """Fuzzy-match a display name to a handle.

    Searches the macOS AddressBook contacts for matches.
    Returns up to 5 matches sorted by relevance.
    """
    lookup = _load_contacts_lookup()
    name_lower = name.lower()
    matches = []
    for handle, display_name in lookup.items():
        score = 0
        dn_lower = display_name.lower()
        if name_lower == dn_lower:
            score = 100
        elif name_lower in dn_lower:
            score = 80
        elif dn_lower.startswith(name_lower):
            score = 70
        else:
            # Check individual words
            words = dn_lower.split()
            if any(w.startswith(name_lower) for w in words):
                score = 60
            elif any(name_lower in w for w in words):
                score = 40
        if score > 0:
            matches.append({"handle": handle, "name": display_name, "score": score})

    matches.sort(key=lambda m: m["score"], reverse=True)
    return {"query": name, "matches": matches[:5]}


def tool_get_unread_summary() -> dict:
    """Return conversations with unread messages, sorted by recency."""
    convos = _list_conversations_fn()
    unread = [
        {
            "handle": c.get("handle") or c.get("guid", ""),
            "name": c.get("name", ""),
            "unread_count": c.get("n", 0),
            "last_text": c.get("preview", ""),
            "last_ts": c.get("last_dt", 0),
        }
        for c in convos
        if c.get("unseen")
    ]
    return {"unread_conversations": unread, "total_unread": len(unread)}


def tool_get_status() -> dict:
    """Return bridge health, rate limit state, and fuse state."""
    from chat_send import _rate_bucket, _fuse  # noqa: PLC0415

    mcp = _load_mcp_config()
    return {
        "mcp_enabled": mcp.get("enabled", False),
        "http_enabled": mcp.get("http_enabled", False),
        "pause_sends": mcp.get("pause_sends", False),
        "contact_filter": mcp.get("contact_filter", "whitelist"),
        "confirmation_mode": mcp.get("confirmation_mode", "never"),
        "rate_limit": {
            "tokens_remaining": round(_rate_bucket._tokens, 1),
            "capacity": _rate_bucket._capacity,
        },
        "fuse": {
            "step": _fuse._step,
            "is_active": _fuse.is_active(),
            "cooldown_remaining_s": max(0, round(_fuse.remaining_s(), 1)),
        },
        "pending_confirmations": len(_PENDING_SENDS),
        "granted_scopes": list(_granted_scopes()),
    }


def tool_draft_message(handle: str, text: str) -> dict:
    """Preview what would happen if send_message were called. No side effects."""
    mcp = _load_mcp_config()
    warnings = []

    if _sends_paused():
        warnings.append("Sends are currently paused via kill switch.")

    if not _send_allowed_for(handle):
        warnings.append(f"Handle '{handle}' is not in the send allow-list.")

    confirm_mode = _effective_confirmation("send_message")
    if confirm_mode == "always":
        warnings.append("Confirmation mode is 'always' — send will require approval.")
    elif confirm_mode == "contacts_only":
        send_list = mcp.get("send_allowed_contacts", [])
        if send_list and handle.strip().lower() not in {h.lower() for h in send_list}:
            warnings.append("Handle not in send_allowed_contacts — will require confirmation.")

    # Estimate service
    service_hint = "iMessage (SMS fallback if unregistered)"

    return {
        "would_send_to": handle,
        "text": text,
        "text_length": len(text),
        "estimated_service": service_hint,
        "warnings": warnings,
        "would_require_confirmation": confirm_mode != "never" and len(warnings) > 0,
    }


# ---------------------------------------------------------------------------
# Tool registry — definitions + dispatch table
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "name": "send_message",
        "description": (
            "Send an iMessage to a contact. Goes through chatwire's "
            "anti-spam guardrails (rate limit + broadcast detection). "
            "May require confirmation depending on settings. "
            "Set wait_for_delivery=false for fast fire-and-forget (<2s)."
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
                "wait_for_delivery": {
                    "type": "boolean",
                    "description": "Wait up to 8s for delivery confirmation. Set false for fast fire-and-forget.",
                    "default": True,
                },
            },
            "required": ["handle", "text"],
        },
    },
    {
        "name": "send_message_to_group",
        "description": (
            "Send an iMessage to a group chat by its GUID. "
            "Use list_conversations or resolve_contact to find group GUIDs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "chat_guid": {
                    "type": "string",
                    "description": "Group chat GUID, e.g. iMessage;+;chat123456",
                },
                "text": {
                    "type": "string",
                    "description": "Message text to send",
                },
            },
            "required": ["chat_guid", "text"],
        },
    },
    {
        "name": "confirm_send",
        "description": (
            "Confirm a pending send that was queued for approval. "
            "Call this after send_message returns status='pending_confirmation'."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "confirmation_id": {
                    "type": "string",
                    "description": "The confirmation_id from the pending_confirmation response",
                },
            },
            "required": ["confirmation_id"],
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
        "description": "Full-text search across iMessages. Respects contact filter settings.",
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
    {
        "name": "resolve_contact",
        "description": (
            "Fuzzy-match a display name to a phone number or email handle. "
            "Use this when you have a name like 'Mom' or 'John' but need the actual handle."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Display name to search for",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "get_unread_summary",
        "description": "Get conversations with unread messages, sorted by most recent.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_status",
        "description": (
            "Get MCP server status: rate limit state, fuse state, "
            "pending confirmations, and current settings."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "draft_message",
        "description": (
            "Preview what would happen if you sent a message. "
            "Returns warnings about confirmation requirements, blocked contacts, etc. "
            "No side effects — nothing is sent."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "handle": {
                    "type": "string",
                    "description": "Phone number or email",
                },
                "text": {
                    "type": "string",
                    "description": "Message text to preview",
                },
            },
            "required": ["handle", "text"],
        },
    },
]

TOOL_DISPATCH: dict[str, Any] = {
    "send_message": lambda args: tool_send_message(
        args["handle"], args["text"],
        wait_for_delivery=args.get("wait_for_delivery", True),
    ),
    "send_message_to_group": lambda args: tool_send_message_to_group(
        args["chat_guid"], args["text"]
    ),
    "confirm_send": lambda args: tool_confirm_send(
        args["confirmation_id"]
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
    "resolve_contact": lambda args: tool_resolve_contact(
        args["name"]
    ),
    "get_unread_summary": lambda args: tool_get_unread_summary(),
    "get_status": lambda args: tool_get_status(),
    "draft_message": lambda args: tool_draft_message(
        args["handle"], args["text"]
    ),
}


# ---------------------------------------------------------------------------
# MCP server runner — requires the `mcp` package (Python 3.10+)
# ---------------------------------------------------------------------------

def run_stdio_server(read_only: bool = False) -> None:
    """Start the MCP server reading JSON-RPC from stdin, writing to stdout.

    Args:
        read_only: If True, send tools are removed regardless of config.

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

    granted = _granted_scopes(read_only=read_only)
    app = Server("chatwire")

    @app.list_tools()
    async def _list_tools() -> list:
        tools = []
        for t in TOOL_DEFINITIONS:
            name = t["name"]
            if not _is_tool_enabled(name):
                continue
            scope_err = check_scope(name, granted)
            if scope_err:
                continue
            tools.append(
                mcp_types.Tool(
                    name=name,
                    description=t["description"],
                    inputSchema=t["inputSchema"],
                )
            )
        return tools

    @app.call_tool()
    async def _call_tool(name: str, arguments: dict) -> list:
        # Check tool enabled
        if not _is_tool_enabled(name):
            return [mcp_types.TextContent(type="text", text=f"Tool disabled: {name}")]
        # Check scope
        scope_err = check_scope(name, granted)
        if scope_err:
            return [mcp_types.TextContent(type="text", text=scope_err)]
        # Dispatch
        handler = TOOL_DISPATCH.get(name)
        if handler is None:
            return [
                mcp_types.TextContent(
                    type="text", text=f"Unknown tool: {name}"
                )
            ]
        try:
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
    """Registers the MCP integration with the bridge."""

    NAME = "mcp"
    TIER = "core"
    DISPLAY_NAME = "MCP Server"
    DESCRIPTION = "Expose chatwire as MCP tools for LLM agents (run: chatwire mcp)"
    ICON = "\U0001f916"

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
        _ls.info("mcp", "MCP integration ready — run `chatwire mcp` to start the stdio server")

    async def stop(self) -> None:
        pass

    async def on_inbound(self, msg: InboundMessage) -> None:
        pass
