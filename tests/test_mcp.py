"""Tests for integrations/mcp/__init__.py — MCP tool implementations.

Covers:
- tool_send_message calls _check_send_guard with source="mcp"
- tool_search_messages returns matching rows
- tool_list_conversations returns correct shape
- TOOL_DEFINITIONS includes all four expected tools
- tool_read_messages filters by since and caps with limit
- Error paths: rate limit, broadcast block
- McpIntegration class shape (SETTINGS_SCHEMA, NAME)

The `mcp` package is NOT required — all tests exercise the pure-Python
tool logic via module-level wrapper functions that are patched.
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import integrations.mcp as _mod
from integrations.mcp import (
    TOOL_DEFINITIONS,
    McpIntegration,
    tool_list_conversations,
    tool_read_messages,
    tool_search_messages,
    tool_send_message,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_send_result(status="delivered", service="iMessage", hint=""):
    r = MagicMock()
    r.status = status
    r.hint = hint
    r.service = service
    return r


def _mock_conversations():
    return [
        {
            "handle": "+15551234567",
            "name": "Alice",
            "preview": "Hey there",
            "last_dt": 700_000_000_000_000_000,
            "n": 2,
        },
        {
            "handle": "+15559876543",
            "name": "Bob",
            "preview": "",
            "last_dt": 699_000_000_000_000_000,
            "n": 0,
        },
    ]


def _mock_messages():
    msgs = [
        {
            "rowid": 10,
            "date": 700_000_000_000_000_000,
            "from_me": False,
            "ts": "12:00 PM",
            "text": "Hello",
            "attachments": [],
            "link_preview": None,
        },
        {
            "rowid": 11,
            "date": 700_000_000_100_000_000,
            "from_me": True,
            "ts": "12:01 PM",
            "text": "Hi back",
            "attachments": [],
            "link_preview": None,
        },
    ]
    return msgs, False


# ---------------------------------------------------------------------------
# Minimal in-memory chat.db fixture for search tests
# ---------------------------------------------------------------------------

@pytest.fixture()
def fake_chat_db(tmp_path):
    """Create an in-memory-style SQLite DB that mimics the chat.db schema
    needed by tool_search_messages."""
    db_file = tmp_path / "chat.db"
    conn = sqlite3.connect(str(db_file))
    conn.executescript("""
        CREATE TABLE handle (
            ROWID INTEGER PRIMARY KEY,
            id TEXT
        );
        CREATE TABLE message (
            ROWID INTEGER PRIMARY KEY,
            date INTEGER,
            is_from_me INTEGER,
            text TEXT,
            handle_id INTEGER
        );
        INSERT INTO handle VALUES (1, '+15551234567');
        INSERT INTO handle VALUES (2, '+15559876543');
        INSERT INTO message VALUES (1, 700000000, 0, 'Hello world', 1);
        INSERT INTO message VALUES (2, 700000001, 1, 'Hi there friend', 1);
        INSERT INTO message VALUES (3, 700000002, 0, 'Good morning', 2);
        INSERT INTO message VALUES (4, 700000003, 1, 'hello again', 1);
    """)
    conn.commit()
    conn.close()
    return db_file


# ---------------------------------------------------------------------------
# tool_send_message
# ---------------------------------------------------------------------------

class TestToolSendMessage:
    def test_calls_check_send_guard_with_mcp_source(self):
        """send_message must call _check_send_guard with source='mcp'."""
        with patch.object(_mod, "_check_send_guard") as mock_guard, \
             patch.object(_mod, "_send_text_confirm",
                          return_value=_mock_send_result()):
            tool_send_message("+15551234567", "hello")
        mock_guard.assert_called_once_with("+15551234567", "hello", "mcp")

    def test_returns_status_hint_service_on_success(self):
        result = _mock_send_result(status="delivered", service="iMessage", hint="")
        with patch.object(_mod, "_check_send_guard"), \
             patch.object(_mod, "_send_text_confirm", return_value=result):
            out = tool_send_message("+15551234567", "hello")
        assert out["status"] == "delivered"
        assert out["service"] == "iMessage"
        assert "hint" in out

    def test_rate_limit_returns_error_dict(self):
        from chat_send import RateLimitError
        with patch.object(_mod, "_check_send_guard",
                          side_effect=RateLimitError("too fast")):
            out = tool_send_message("+15551234567", "hello")
        assert out["error"] == "rate_limited"
        assert "too fast" in out["detail"]

    def test_broadcast_blocked_returns_error_dict_with_retry_after(self):
        from chat_send import BroadcastBlockedError
        with patch.object(_mod, "_check_send_guard",
                          side_effect=BroadcastBlockedError("blocked", 300)):
            out = tool_send_message("+15551234567", "hello")
        assert out["error"] == "broadcast_blocked"
        assert out["retry_after"] == 300

    def test_send_text_confirm_not_called_when_guard_raises(self):
        from chat_send import RateLimitError
        with patch.object(_mod, "_check_send_guard",
                          side_effect=RateLimitError("too fast")), \
             patch.object(_mod, "_send_text_confirm") as mock_send:
            tool_send_message("+15551234567", "hello")
        mock_send.assert_not_called()


# ---------------------------------------------------------------------------
# tool_read_messages
# ---------------------------------------------------------------------------

class TestToolReadMessages:
    def test_returns_correct_shape(self):
        msgs, has_more = _mock_messages()
        with patch.object(_mod, "_history_for", return_value=(msgs, has_more)):
            out = tool_read_messages("+15551234567")
        assert out["handle"] == "+15551234567"
        assert isinstance(out["messages"], list)
        assert "has_more" in out

    def test_since_filters_older_rows(self):
        msgs, _ = _mock_messages()
        with patch.object(_mod, "_history_for", return_value=(msgs, False)):
            out = tool_read_messages("+15551234567", since=10)
        # rowid 10 is excluded (since=10 means ROWID > 10), only rowid 11 remains
        assert len(out["messages"]) == 1
        assert out["messages"][0]["rowid"] == 11

    def test_limit_caps_results(self):
        msgs, _ = _mock_messages()
        with patch.object(_mod, "_history_for", return_value=(msgs, False)):
            out = tool_read_messages("+15551234567", limit=1)
        assert len(out["messages"]) == 1
        # limit takes the last N messages (newest)
        assert out["messages"][0]["rowid"] == 11

    def test_returns_all_messages_when_since_zero(self):
        msgs, _ = _mock_messages()
        with patch.object(_mod, "_history_for", return_value=(msgs, False)):
            out = tool_read_messages("+15551234567", since=0)
        assert len(out["messages"]) == 2


# ---------------------------------------------------------------------------
# tool_list_conversations
# ---------------------------------------------------------------------------

class TestToolListConversations:
    def test_returns_conversations_key(self):
        with patch.object(_mod, "_list_conversations_fn",
                          return_value=_mock_conversations()):
            out = tool_list_conversations()
        assert "conversations" in out
        assert isinstance(out["conversations"], list)

    def test_entry_has_required_fields(self):
        with patch.object(_mod, "_list_conversations_fn",
                          return_value=_mock_conversations()):
            out = tool_list_conversations()
        entry = out["conversations"][0]
        assert "handle" in entry
        assert "name" in entry
        assert "last_text" in entry
        assert "last_ts" in entry
        assert "unread_count" in entry

    def test_entry_values_correct(self):
        with patch.object(_mod, "_list_conversations_fn",
                          return_value=_mock_conversations()):
            out = tool_list_conversations()
        entry = out["conversations"][0]
        assert entry["handle"] == "+15551234567"
        assert entry["name"] == "Alice"
        assert entry["last_text"] == "Hey there"
        assert entry["unread_count"] == 2

    def test_limit_caps_results(self):
        convos = _mock_conversations()  # 2 entries
        with patch.object(_mod, "_list_conversations_fn", return_value=convos):
            out = tool_list_conversations(limit=1)
        assert len(out["conversations"]) == 1

    def test_two_conversations_returned_by_default(self):
        with patch.object(_mod, "_list_conversations_fn",
                          return_value=_mock_conversations()):
            out = tool_list_conversations()
        assert len(out["conversations"]) == 2


# ---------------------------------------------------------------------------
# tool_search_messages
# ---------------------------------------------------------------------------

class TestToolSearchMessages:
    def test_returns_matching_rows(self, fake_chat_db):
        with patch.object(_mod, "_chat_db_path", return_value=fake_chat_db):
            out = tool_search_messages("hello")
        assert "results" in out
        # 'Hello world' and 'hello again' both match
        texts = [r["text"] for r in out["results"]]
        assert any("Hello" in t or "hello" in t for t in texts)
        assert len(out["results"]) >= 2

    def test_result_has_required_fields(self, fake_chat_db):
        with patch.object(_mod, "_chat_db_path", return_value=fake_chat_db):
            out = tool_search_messages("hello")
        row = out["results"][0]
        assert "rowid" in row
        assert "date" in row
        assert "from_me" in row
        assert "text" in row
        assert "handle" in row

    def test_handle_filter_restricts_results(self, fake_chat_db):
        with patch.object(_mod, "_chat_db_path", return_value=fake_chat_db):
            # search for 'morning' — only handle 2 has it
            out = tool_search_messages("morning", handle="+15559876543")
        assert len(out["results"]) == 1
        assert "morning" in out["results"][0]["text"].lower()

    def test_no_match_returns_empty_results(self, fake_chat_db):
        with patch.object(_mod, "_chat_db_path", return_value=fake_chat_db):
            out = tool_search_messages("xyzzy_no_match_xyz")
        assert out["results"] == []

    def test_bad_db_path_returns_error(self, tmp_path):
        nonexistent = tmp_path / "no_such_file.db"
        with patch.object(_mod, "_chat_db_path", return_value=nonexistent):
            out = tool_search_messages("anything")
        assert "error" in out

    def test_query_key_in_result(self, fake_chat_db):
        with patch.object(_mod, "_chat_db_path", return_value=fake_chat_db):
            out = tool_search_messages("world")
        assert out["query"] == "world"


# ---------------------------------------------------------------------------
# TOOL_DEFINITIONS completeness
# ---------------------------------------------------------------------------

class TestToolDefinitions:
    def test_all_four_tools_defined(self):
        names = {t["name"] for t in TOOL_DEFINITIONS}
        assert "send_message" in names
        assert "read_messages" in names
        assert "list_conversations" in names
        assert "search_messages" in names

    def test_each_tool_has_name_description_input_schema(self):
        for t in TOOL_DEFINITIONS:
            assert "name" in t
            assert "description" in t
            assert "inputSchema" in t

    def test_send_message_requires_handle_and_text(self):
        defn = next(t for t in TOOL_DEFINITIONS if t["name"] == "send_message")
        required = defn["inputSchema"].get("required", [])
        assert "handle" in required
        assert "text" in required

    def test_read_messages_requires_handle(self):
        defn = next(t for t in TOOL_DEFINITIONS if t["name"] == "read_messages")
        assert "handle" in defn["inputSchema"].get("required", [])

    def test_search_messages_requires_query(self):
        defn = next(t for t in TOOL_DEFINITIONS if t["name"] == "search_messages")
        assert "query" in defn["inputSchema"].get("required", [])


# ---------------------------------------------------------------------------
# McpIntegration class
# ---------------------------------------------------------------------------

class TestMcpIntegration:
    def test_name(self):
        assert McpIntegration.NAME == "mcp"

    def test_settings_schema_has_enabled_boolean(self):
        schema = McpIntegration.SETTINGS_SCHEMA
        assert schema["type"] == "object"
        enabled = schema["properties"]["enabled"]
        assert enabled["type"] == "boolean"
        assert enabled["default"] is False

    def test_init_reads_enabled_flag(self):
        integ = McpIntegration({"enabled": True})
        assert integ._enabled is True

    def test_init_defaults_to_disabled(self):
        integ = McpIntegration({})
        assert integ._enabled is False

    def test_start_does_not_raise(self):
        import asyncio
        integ = McpIntegration({})
        ctx = MagicMock()
        asyncio.get_event_loop().run_until_complete(integ.start(ctx))

    def test_stop_does_not_raise(self):
        import asyncio
        integ = McpIntegration({})
        asyncio.get_event_loop().run_until_complete(integ.stop())

    def test_on_inbound_does_not_raise(self):
        import asyncio
        integ = McpIntegration({})
        msg = MagicMock()
        asyncio.get_event_loop().run_until_complete(integ.on_inbound(msg))
