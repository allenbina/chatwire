"""Tests for web/api_v1.py — REST API v1 endpoints.

Uses a minimal FastAPI test app built from the api_v1 router so that
web/main.py's many side-effectful imports (chat.db, contacts, subprocess)
are never triggered.  All heavy dependencies (check_send_guard, history_for,
list_conversations, etc.) are patched at the module level.
"""
from __future__ import annotations

import hashlib
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import web.api_v1 as _mod
from web.api_v1 import router as api_router

# ---------------------------------------------------------------------------
# Test app & client
# ---------------------------------------------------------------------------

_test_app = FastAPI()
_test_app.include_router(api_router)
client = TestClient(_test_app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PLAIN_KEY = "test-api-key-abcdef0123456789"
_KEY_HASH = hashlib.sha256(_PLAIN_KEY.encode()).hexdigest()
_AUTH_HEADER = {"X-API-Key": _PLAIN_KEY}


def _mock_send_result(status: str = "delivered", service: str = "iMessage", hint: str = "") -> MagicMock:
    r = MagicMock()
    r.status = status
    r.hint = hint
    r.service = service
    return r


def _mock_conversations() -> list[dict]:
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


def _mock_messages() -> tuple[list[dict], bool]:
    msgs = [
        {"rowid": 10, "date": 700_000_000_000_000_000, "from_me": False,
         "ts": "12:00 PM", "text": "Hello", "attachments": [], "link_preview": None},
        {"rowid": 11, "date": 700_000_000_100_000_000, "from_me": True,
         "ts": "12:01 PM", "text": "Hi back", "attachments": [], "link_preview": None},
    ]
    return msgs, False


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------

class TestApiAuth:
    def test_missing_key_returns_401(self):
        with patch.object(_mod, "_api_key_hash", return_value=_KEY_HASH):
            r = client.get("/conversations")
        assert r.status_code == 401

    def test_wrong_key_returns_401(self):
        with patch.object(_mod, "_api_key_hash", return_value=_KEY_HASH):
            r = client.get("/conversations", headers={"X-API-Key": "wrong-key"})
        assert r.status_code == 401

    def test_valid_key_returns_200_for_conversations(self):
        with patch.object(_mod, "_api_key_hash", return_value=_KEY_HASH), \
             patch.object(_mod, "_list_conversations", return_value=_mock_conversations()):
            r = client.get("/conversations", headers=_AUTH_HEADER)
        assert r.status_code == 200

    def test_no_key_configured_returns_401(self):
        """When no key is stored, every request is rejected."""
        with patch.object(_mod, "_api_key_hash", return_value=None):
            r = client.get("/conversations", headers=_AUTH_HEADER)
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Send endpoint
# ---------------------------------------------------------------------------

class TestApiSend:
    def _post(self, payload: dict, key: str = _PLAIN_KEY) -> object:
        return client.post(
            "/send",
            json=payload,
            headers={"X-API-Key": key},
        )

    def test_calls_check_send_guard(self):
        """Send endpoint must invoke check_send_guard with source='api'."""
        with patch.object(_mod, "_api_key_hash", return_value=_KEY_HASH), \
             patch.object(_mod, "_relay_handles", return_value={"+15551234567"}), \
             patch.object(_mod, "check_send_guard") as mock_guard, \
             patch.object(_mod, "send_text_confirm", return_value=_mock_send_result()):
            r = self._post({"handle": "+15551234567", "text": "hello"})
        assert r.status_code == 200
        mock_guard.assert_called_once_with("+15551234567", "hello", "api")

    def test_valid_send_returns_status_hint_service(self):
        result = _mock_send_result(status="delivered", service="iMessage", hint="")
        with patch.object(_mod, "_api_key_hash", return_value=_KEY_HASH), \
             patch.object(_mod, "_relay_handles", return_value={"+15551234567"}), \
             patch.object(_mod, "check_send_guard"), \
             patch.object(_mod, "send_text_confirm", return_value=result):
            r = self._post({"handle": "+15551234567", "text": "hello"})
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "delivered"
        assert body["service"] == "iMessage"
        assert "hint" in body

    def test_rate_limit_returns_429(self):
        from chat_send import RateLimitError
        with patch.object(_mod, "_api_key_hash", return_value=_KEY_HASH), \
             patch.object(_mod, "_relay_handles", return_value={"+15551234567"}), \
             patch.object(_mod, "check_send_guard",
                          side_effect=RateLimitError("rate limit exceeded")):
            r = self._post({"handle": "+15551234567", "text": "hello"})
        assert r.status_code == 429

    def test_broadcast_blocked_returns_429(self):
        from chat_send import BroadcastBlockedError
        with patch.object(_mod, "_api_key_hash", return_value=_KEY_HASH), \
             patch.object(_mod, "_relay_handles", return_value={"+15551234567"}), \
             patch.object(_mod, "check_send_guard",
                          side_effect=BroadcastBlockedError("timeout", 300)):
            r = self._post({"handle": "+15551234567", "text": "hello"})
        assert r.status_code == 429

    def test_handle_not_in_scope_returns_403(self):
        with patch.object(_mod, "_api_key_hash", return_value=_KEY_HASH), \
             patch.object(_mod, "_relay_handles", return_value=set()):
            r = self._post({"handle": "+15551234567", "text": "hello"})
        assert r.status_code == 403

    def test_missing_api_key_returns_401(self):
        with patch.object(_mod, "_api_key_hash", return_value=_KEY_HASH):
            r = client.post("/send", json={"handle": "+1555", "text": "hi"})
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Messages endpoint
# ---------------------------------------------------------------------------

class TestApiMessages:
    def test_returns_correct_shape(self):
        msgs, has_more = _mock_messages()
        with patch.object(_mod, "_api_key_hash", return_value=_KEY_HASH), \
             patch.object(_mod, "_relay_handles", return_value={"+15551234567"}), \
             patch.object(_mod, "_history_for", return_value=(msgs, has_more)):
            r = client.get(
                "/messages",
                params={"handle": "+15551234567"},
                headers=_AUTH_HEADER,
            )
        assert r.status_code == 200
        body = r.json()
        assert body["handle"] == "+15551234567"
        assert isinstance(body["messages"], list)
        assert len(body["messages"]) == 2
        assert "has_more" in body

    def test_message_fields_present(self):
        msgs, _ = _mock_messages()
        with patch.object(_mod, "_api_key_hash", return_value=_KEY_HASH), \
             patch.object(_mod, "_relay_handles", return_value={"+15551234567"}), \
             patch.object(_mod, "_history_for", return_value=(msgs, False)):
            r = client.get(
                "/messages",
                params={"handle": "+15551234567"},
                headers=_AUTH_HEADER,
            )
        m = r.json()["messages"][0]
        assert "rowid" in m
        assert "text" in m
        assert "from_me" in m
        assert "ts" in m

    def test_since_filters_messages(self):
        msgs, _ = _mock_messages()
        with patch.object(_mod, "_api_key_hash", return_value=_KEY_HASH), \
             patch.object(_mod, "_relay_handles", return_value={"+15551234567"}), \
             patch.object(_mod, "_history_for", return_value=(msgs, False)):
            r = client.get(
                "/messages",
                params={"handle": "+15551234567", "since": 10},
                headers=_AUTH_HEADER,
            )
        # rowid 10 is excluded (since=10 means >10), only rowid 11 remains
        body = r.json()
        assert len(body["messages"]) == 1
        assert body["messages"][0]["rowid"] == 11

    def test_handle_not_in_scope_returns_403(self):
        with patch.object(_mod, "_api_key_hash", return_value=_KEY_HASH), \
             patch.object(_mod, "_relay_handles", return_value=set()):
            r = client.get(
                "/messages",
                params={"handle": "+15551234567"},
                headers=_AUTH_HEADER,
            )
        assert r.status_code == 403

    def test_missing_api_key_returns_401(self):
        with patch.object(_mod, "_api_key_hash", return_value=_KEY_HASH):
            r = client.get("/messages", params={"handle": "+15551234567"})
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Conversations endpoint
# ---------------------------------------------------------------------------

class TestApiConversations:
    def test_returns_list(self):
        with patch.object(_mod, "_api_key_hash", return_value=_KEY_HASH), \
             patch.object(_mod, "_list_conversations", return_value=_mock_conversations()):
            r = client.get("/conversations", headers=_AUTH_HEADER)
        assert r.status_code == 200
        body = r.json()
        assert "conversations" in body
        assert isinstance(body["conversations"], list)
        assert len(body["conversations"]) == 2

    def test_entry_shape(self):
        with patch.object(_mod, "_api_key_hash", return_value=_KEY_HASH), \
             patch.object(_mod, "_list_conversations", return_value=_mock_conversations()):
            r = client.get("/conversations", headers=_AUTH_HEADER)
        entry = r.json()["conversations"][0]
        assert "handle" in entry
        assert "name" in entry
        assert "last_text" in entry
        assert "last_ts" in entry
        assert "unread_count" in entry

    def test_entry_values_correct(self):
        with patch.object(_mod, "_api_key_hash", return_value=_KEY_HASH), \
             patch.object(_mod, "_list_conversations", return_value=_mock_conversations()):
            r = client.get("/conversations", headers=_AUTH_HEADER)
        entry = r.json()["conversations"][0]
        assert entry["handle"] == "+15551234567"
        assert entry["name"] == "Alice"
        assert entry["last_text"] == "Hey there"
        assert entry["unread_count"] == 2

    def test_missing_api_key_returns_401(self):
        with patch.object(_mod, "_api_key_hash", return_value=_KEY_HASH):
            r = client.get("/conversations")
        assert r.status_code == 401
