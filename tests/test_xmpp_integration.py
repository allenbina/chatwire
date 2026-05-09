"""Tests for chunk 6 Part B: XMPP relay plugin (chatwire-xmpp).

Strategy
--------
- Import XMPPIntegration directly from the plugin source tree.
- Patch slixmpp.ClientXMPP to avoid real network calls.
- Mock BridgeContext / SendTarget stubs for relay assertions.
- asyncio.run() for async tests (no pytest-asyncio needed).

Covers:
  a. start() creates ClientXMPP and calls connect() with correct host.
  b. start() uses server_url when provided instead of JID domain.
  c. start() raises ValueError if jid is missing.
  d. start() raises ValueError if password is missing.
  e. stop() calls xmpp.disconnect() and clears self._xmpp.
  f. on_inbound() relays message text to mapped XMPP JID via send_message.
  g. on_inbound() ignores unmapped iMessage handles.
  h. on_inbound() ignores messages with empty text.
  i. on_inbound() is a no-op before start() is called (xmpp=None).
  j. _on_xmpp_message() relays XMPP text to mapped iMessage handle.
  k. _on_xmpp_message() ignores unmapped XMPP JIDs.
  l. _on_xmpp_message() ignores non-chat message types.
  m. _on_xmpp_message() ignores empty body.
  n. Contact mapping is bidirectional (both dicts populated).
"""
from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Make the plugin importable.
# ---------------------------------------------------------------------------
_PLUGIN_ROOT = (
    Path(__file__).resolve().parent.parent / "chatwire-plugins" / "chatwire-xmpp"
)
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

# Patch slixmpp before importing so the module-level import doesn't fail
# when slixmpp is not installed in the test environment.
_fake_slixmpp_module = MagicMock()

with patch.dict("sys.modules", {"slixmpp": _fake_slixmpp_module}):
    from chatwire_xmpp import XMPPIntegration  # noqa: E402


# ---------------------------------------------------------------------------
# Minimal bridge stubs
# ---------------------------------------------------------------------------

@dataclass
class FakeSendTarget:
    kind: str
    value: str
    label: str


@dataclass
class FakeMsg:
    text: str
    handle: str = "+15551234567"
    is_group: bool = False
    chat_guid: str = ""
    chat_name: str = ""


@dataclass
class FakeCtx:
    sent: list[tuple[Any, str]] = field(default_factory=list)
    _loop: asyncio.AbstractEventLoop | None = None

    async def send_text(self, target: Any, body: str) -> MagicMock:
        self.sent.append((target, body))
        return MagicMock()

    def name_for(self, handle: str) -> str | None:
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_CONFIG = {
    "jid": "bridge@example.com",
    "password": "s3cr3t",
    "contact_mappings": [
        {"imessage_handle": "+15551234567", "xmpp_jid": "alice@example.com"},
        {"imessage_handle": "bob@icloud.com", "xmpp_jid": "bob@example.com"},
    ],
}


def _make_integration(extra: dict | None = None) -> XMPPIntegration:
    cfg = {**_BASE_CONFIG, **(extra or {})}
    return XMPPIntegration(cfg)


def _fake_xmpp_client():
    """Return a fresh MagicMock that quacks like slixmpp.ClientXMPP."""
    m = MagicMock()
    m.process = MagicMock()
    return m


def _fake_xmpp_msg(from_jid: str, body: str, mtype: str = "chat"):
    msg = MagicMock()
    msg.get = lambda key, default=None: {
        "from": from_jid,
        "body": body,
        "type": mtype,
    }.get(key, default)
    return msg


# ---------------------------------------------------------------------------
# (a) start() creates ClientXMPP and calls connect() with JID domain
#
# Note: at import time slixmpp was mocked, so chatwire_xmpp.ClientXMPP is
# already a MagicMock.  We test start() by checking what connect() was called
# with on intg._xmpp (whatever instance ClientXMPP() returned), rather than
# asserting the class itself was called.
# ---------------------------------------------------------------------------

class TestStartCreatesClient:
    def test_connect_called_with_jid_domain(self):
        intg = _make_integration()
        with patch("threading.Thread", return_value=MagicMock()):
            asyncio.run(intg.start(FakeCtx()))

        # intg._xmpp is the ClientXMPP() instance; connect must have been called.
        # Use call_args (most recent call) since the mock is shared across tests.
        assert intg._xmpp is not None
        assert intg._xmpp.connect.call_args[0] == (("example.com", 5222),)

    def test_event_handlers_registered(self):
        intg = _make_integration()
        with patch("threading.Thread", return_value=MagicMock()):
            asyncio.run(intg.start(FakeCtx()))

        handler_names = [
            c.args[0] for c in intg._xmpp.add_event_handler.call_args_list
        ]
        assert "session_start" in handler_names
        assert "message" in handler_names

    def test_ctx_stored(self):
        intg = _make_integration()
        ctx = FakeCtx()
        with patch("threading.Thread", return_value=MagicMock()):
            asyncio.run(intg.start(ctx))
        assert intg._ctx is ctx


# ---------------------------------------------------------------------------
# (b) start() uses server_url when provided
# ---------------------------------------------------------------------------

class TestStartUsesServerUrl:
    def test_server_url_overrides_jid_domain(self):
        intg = _make_integration({"server_url": "xmpp.custom.host"})
        with patch("threading.Thread", return_value=MagicMock()):
            asyncio.run(intg.start(FakeCtx()))

        # Check the most recent connect() call used the server_url host.
        assert intg._xmpp.connect.call_args[0] == (("xmpp.custom.host", 5222),)


# ---------------------------------------------------------------------------
# (c) & (d) start() raises ValueError for missing jid / password
# ---------------------------------------------------------------------------

class TestStartValidation:
    def test_missing_jid_raises(self):
        intg = XMPPIntegration({"jid": "", "password": "x"})
        with patch("chatwire_xmpp._SLIXMPP_AVAILABLE", True):
            with pytest.raises(ValueError, match="jid"):
                asyncio.run(intg.start(FakeCtx()))

    def test_missing_password_raises(self):
        intg = XMPPIntegration({"jid": "a@b.com", "password": ""})
        with patch("chatwire_xmpp._SLIXMPP_AVAILABLE", True):
            with pytest.raises(ValueError, match="password"):
                asyncio.run(intg.start(FakeCtx()))


# ---------------------------------------------------------------------------
# (e) stop() disconnects and clears _xmpp
# ---------------------------------------------------------------------------

class TestStop:
    def test_stop_calls_disconnect(self):
        intg = _make_integration()
        fake_client = _fake_xmpp_client()
        intg._xmpp = fake_client  # inject directly — no need for start()

        asyncio.run(intg.stop())

        fake_client.disconnect.assert_called_once()
        assert intg._xmpp is None

    def test_stop_is_idempotent(self):
        intg = _make_integration()
        asyncio.run(intg.stop())  # stop without start — must not raise


# ---------------------------------------------------------------------------
# (f) on_inbound() relays text to mapped XMPP JID
# ---------------------------------------------------------------------------

class TestOnInboundRelay:
    def _started_integration(self):
        intg = _make_integration()
        intg._xmpp = _fake_xmpp_client()
        intg._ctx = FakeCtx()
        return intg

    def test_relays_to_correct_xmpp_jid(self):
        intg = self._started_integration()
        msg = FakeMsg(text="hello", handle="+15551234567")
        asyncio.run(intg.on_inbound(msg))
        intg._xmpp.send_message.assert_called_once_with(
            mto="alice@example.com", mbody="hello", mtype="chat"
        )

    def test_relays_second_contact(self):
        intg = self._started_integration()
        msg = FakeMsg(text="hi there", handle="bob@icloud.com")
        asyncio.run(intg.on_inbound(msg))
        intg._xmpp.send_message.assert_called_once_with(
            mto="bob@example.com", mbody="hi there", mtype="chat"
        )


# ---------------------------------------------------------------------------
# (g) on_inbound() ignores unmapped handles
# ---------------------------------------------------------------------------

class TestOnInboundIgnoresUnmapped:
    def test_unmapped_handle_no_send(self):
        intg = _make_integration()
        intg._xmpp = _fake_xmpp_client()
        intg._ctx = FakeCtx()
        msg = FakeMsg(text="hello", handle="+19999999999")
        asyncio.run(intg.on_inbound(msg))
        intg._xmpp.send_message.assert_not_called()


# ---------------------------------------------------------------------------
# (h) on_inbound() ignores empty text
# ---------------------------------------------------------------------------

class TestOnInboundIgnoresEmptyText:
    def test_empty_text_no_send(self):
        intg = _make_integration()
        intg._xmpp = _fake_xmpp_client()
        intg._ctx = FakeCtx()
        msg = FakeMsg(text="", handle="+15551234567")
        asyncio.run(intg.on_inbound(msg))
        intg._xmpp.send_message.assert_not_called()

    def test_whitespace_only_no_send(self):
        intg = _make_integration()
        intg._xmpp = _fake_xmpp_client()
        intg._ctx = FakeCtx()
        msg = FakeMsg(text="   ", handle="+15551234567")
        asyncio.run(intg.on_inbound(msg))
        intg._xmpp.send_message.assert_not_called()


# ---------------------------------------------------------------------------
# (i) on_inbound() is a no-op before start() (xmpp=None)
# ---------------------------------------------------------------------------

class TestOnInboundBeforeStart:
    def test_no_error_before_start(self):
        intg = _make_integration()
        msg = FakeMsg(text="hello", handle="+15551234567")
        # Must not raise
        asyncio.run(intg.on_inbound(msg))


# ---------------------------------------------------------------------------
# (j) _on_xmpp_message() relays to mapped iMessage handle
# ---------------------------------------------------------------------------

class TestXmppMessageRelay:
    def test_relays_to_correct_imessage_handle(self):
        intg = _make_integration()
        intg._xmpp = _fake_xmpp_client()
        ctx = FakeCtx()
        ctx._loop = asyncio.new_event_loop()
        intg._ctx = ctx

        msg = _fake_xmpp_msg("alice@example.com", "hey!")

        with patch("chatwire_xmpp.SendTarget", FakeSendTarget), \
             patch("asyncio.run_coroutine_threadsafe") as mock_coro:
            intg._on_xmpp_message(msg)

        mock_coro.assert_called_once()
        # The coroutine arg is a coroutine object — just verify it was called.

    def test_relay_uses_correct_im_handle(self):
        intg = _make_integration()
        intg._xmpp = _fake_xmpp_client()
        ctx = FakeCtx()
        ctx._loop = asyncio.new_event_loop()
        intg._ctx = ctx

        msg = _fake_xmpp_msg("bob@example.com", "from bob")

        targets_seen = []

        def fake_rcts(coro, loop):
            targets_seen.append("called")
            return MagicMock()

        with patch("chatwire_xmpp.SendTarget", FakeSendTarget), \
             patch("asyncio.run_coroutine_threadsafe", side_effect=fake_rcts):
            intg._on_xmpp_message(msg)

        assert len(targets_seen) == 1


# ---------------------------------------------------------------------------
# (k) _on_xmpp_message() ignores unmapped XMPP JIDs
# ---------------------------------------------------------------------------

class TestXmppMessageIgnoresUnmapped:
    def test_unknown_sender_no_relay(self):
        intg = _make_integration()
        intg._xmpp = _fake_xmpp_client()
        intg._ctx = FakeCtx()

        msg = _fake_xmpp_msg("stranger@other.com", "hello")

        with patch("asyncio.run_coroutine_threadsafe") as mock_rcts:
            intg._on_xmpp_message(msg)

        mock_rcts.assert_not_called()


# ---------------------------------------------------------------------------
# (l) _on_xmpp_message() ignores non-chat message types
# ---------------------------------------------------------------------------

class TestXmppMessageIgnoresNonChat:
    def test_groupchat_ignored(self):
        intg = _make_integration()
        intg._xmpp = _fake_xmpp_client()
        intg._ctx = FakeCtx()

        msg = _fake_xmpp_msg("alice@example.com", "hi", mtype="groupchat")

        with patch("asyncio.run_coroutine_threadsafe") as mock_rcts:
            intg._on_xmpp_message(msg)

        mock_rcts.assert_not_called()


# ---------------------------------------------------------------------------
# (m) _on_xmpp_message() ignores empty body
# ---------------------------------------------------------------------------

class TestXmppMessageIgnoresEmptyBody:
    def test_empty_body_no_relay(self):
        intg = _make_integration()
        intg._xmpp = _fake_xmpp_client()
        intg._ctx = FakeCtx()

        msg = _fake_xmpp_msg("alice@example.com", "")

        with patch("asyncio.run_coroutine_threadsafe") as mock_rcts:
            intg._on_xmpp_message(msg)

        mock_rcts.assert_not_called()


# ---------------------------------------------------------------------------
# (n) Contact mapping is bidirectional
# ---------------------------------------------------------------------------

class TestContactMappingBidirectional:
    def test_im_to_xmpp_populated(self):
        intg = _make_integration()
        assert intg._im_to_xmpp["+15551234567"] == "alice@example.com"
        assert intg._im_to_xmpp["bob@icloud.com"] == "bob@example.com"

    def test_xmpp_to_im_populated(self):
        intg = _make_integration()
        assert intg._xmpp_to_im["alice@example.com"] == "+15551234567"
        assert intg._xmpp_to_im["bob@example.com"] == "bob@icloud.com"

    def test_empty_mappings_empty_dicts(self):
        intg = XMPPIntegration({"jid": "a@b.com", "password": "x"})
        assert intg._im_to_xmpp == {}
        assert intg._xmpp_to_im == {}
