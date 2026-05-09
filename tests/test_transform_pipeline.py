"""Tests for the message transform pipeline.

Strategy:
  - Test _run_transform_inbound and _run_transform_outbound directly from
    bridge.py (module-level helpers, no side-effects).
  - Test _scope_applies for all scope variants.
  - Test BridgeContextImpl.send_text calls the outbound pipeline by mocking
    send_text_confirm.
  - Verify: uppercasing transform fires; missing method is skipped; scope
    filtering (scope="web") skips bridge calls; multiple transforms chain in
    load order.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch, patch as _patch


def _run(coro):
    """Run a coroutine synchronously (no async test plugin required)."""
    return asyncio.get_event_loop().run_until_complete(coro)

import pytest

from bridge import (
    BridgeContextImpl,
    SendTarget,
    _run_transform_inbound,
    _run_transform_outbound,
    _scope_applies,
)


# ---------------------------------------------------------------------------
# Tiny stub integrations
# ---------------------------------------------------------------------------

class _UpperInteg:
    NAME = "upper"
    SETTINGS_SCHEMA = {}
    TRANSFORM_SCOPE = "all"

    def transform_inbound(self, text: str, context: dict) -> str:
        return text.upper()

    def transform_outbound(self, text: str, target) -> str:
        return text.upper()


class _SuffixInteg:
    NAME = "suffix"
    SETTINGS_SCHEMA = {}
    TRANSFORM_SCOPE = "all"

    def transform_inbound(self, text: str, context: dict) -> str:
        return text + "!"

    def transform_outbound(self, text: str, target) -> str:
        return text + "!"


class _NoTransformInteg:
    NAME = "no_transform"
    SETTINGS_SCHEMA = {}
    # No transform_inbound / transform_outbound methods at all.


class _WebScopeInteg:
    NAME = "web_scope"
    SETTINGS_SCHEMA = {}
    TRANSFORM_SCOPE = "web"  # should NOT fire on bridge surface

    def transform_inbound(self, text: str, context: dict) -> str:
        return text + "[web]"

    def transform_outbound(self, text: str, target) -> str:
        return text + "[web]"


class _ListScopeInteg:
    NAME = "list_scope"
    SETTINGS_SCHEMA = {}
    TRANSFORM_SCOPE = ["bridge", "telegram"]

    def transform_inbound(self, text: str, context: dict) -> str:
        return text + "[list]"


class _RaisingInteg:
    NAME = "raises"
    SETTINGS_SCHEMA = {}
    TRANSFORM_SCOPE = "all"

    def transform_inbound(self, text: str, context: dict) -> str:
        raise RuntimeError("transform exploded")

    def transform_outbound(self, text: str, target) -> str:
        raise RuntimeError("outbound exploded")


# ---------------------------------------------------------------------------
# _scope_applies
# ---------------------------------------------------------------------------

class TestScopeApplies:
    def test_all_scope_default(self):
        class I:
            pass
        assert _scope_applies(I(), "bridge") is True
        assert _scope_applies(I(), "web") is True

    def test_all_scope_explicit(self):
        class I:
            TRANSFORM_SCOPE = "all"
        assert _scope_applies(I(), "bridge") is True

    def test_string_scope_match(self):
        class I:
            TRANSFORM_SCOPE = "bridge"
        assert _scope_applies(I(), "bridge") is True
        assert _scope_applies(I(), "web") is False

    def test_string_scope_web(self):
        class I:
            TRANSFORM_SCOPE = "web"
        assert _scope_applies(I(), "web") is True
        assert _scope_applies(I(), "bridge") is False

    def test_list_scope_match(self):
        class I:
            TRANSFORM_SCOPE = ["bridge", "telegram"]
        assert _scope_applies(I(), "bridge") is True
        assert _scope_applies(I(), "telegram") is True
        assert _scope_applies(I(), "web") is False


# ---------------------------------------------------------------------------
# _run_transform_inbound
# ---------------------------------------------------------------------------

class TestRunTransformInbound:
    CTX = {"handle": "+1555", "is_from_me": False, "chat_guid": None}

    def test_uppercase_fires(self):
        result = _run_transform_inbound([_UpperInteg()], "hello", self.CTX)
        assert result == "HELLO"

    def test_no_method_skipped(self):
        result = _run_transform_inbound([_NoTransformInteg()], "hello", self.CTX)
        assert result == "hello"

    def test_web_scope_skipped_on_bridge(self):
        result = _run_transform_inbound([_WebScopeInteg()], "hello", self.CTX)
        assert result == "hello"

    def test_list_scope_bridge_applies(self):
        result = _run_transform_inbound([_ListScopeInteg()], "hello", self.CTX)
        assert result == "hello[list]"

    def test_multiple_plugins_chain_in_order(self):
        # upper first → "HELLO", then suffix → "HELLO!"
        result = _run_transform_inbound(
            [_UpperInteg(), _SuffixInteg()], "hello", self.CTX
        )
        assert result == "HELLO!"

    def test_order_matters(self):
        # suffix first → "hello!", then upper → "HELLO!"
        result = _run_transform_inbound(
            [_SuffixInteg(), _UpperInteg()], "hello", self.CTX
        )
        assert result == "HELLO!"

    def test_raising_transform_skipped_rest_continues(self):
        # raises first, then suffix should still run on original text
        result = _run_transform_inbound(
            [_RaisingInteg(), _SuffixInteg()], "hello", self.CTX
        )
        assert result == "hello!"

    def test_empty_integrations(self):
        result = _run_transform_inbound([], "hello", self.CTX)
        assert result == "hello"

    def test_context_passed_through(self):
        received = {}

        class CtxCapture:
            NAME = "ctx_capture"
            SETTINGS_SCHEMA = {}

            def transform_inbound(self, text: str, context: dict) -> str:
                received.update(context)
                return text

        ctx = {"handle": "+1999", "is_from_me": True, "chat_guid": "iMessage;+;abc"}
        _run_transform_inbound([CtxCapture()], "hi", ctx)
        assert received["handle"] == "+1999"
        assert received["is_from_me"] is True
        assert received["chat_guid"] == "iMessage;+;abc"


# ---------------------------------------------------------------------------
# _run_transform_outbound
# ---------------------------------------------------------------------------

class TestRunTransformOutbound:
    TARGET = SendTarget(kind="handle", value="+15551234567", label="Alice")

    def test_uppercase_fires(self):
        result = _run_transform_outbound([_UpperInteg()], "hello", self.TARGET)
        assert result == "HELLO"

    def test_no_method_skipped(self):
        result = _run_transform_outbound([_NoTransformInteg()], "hello", self.TARGET)
        assert result == "hello"

    def test_web_scope_skipped_on_bridge(self):
        result = _run_transform_outbound([_WebScopeInteg()], "hello", self.TARGET)
        assert result == "hello"

    def test_multiple_plugins_chain_in_order(self):
        result = _run_transform_outbound(
            [_UpperInteg(), _SuffixInteg()], "hello", self.TARGET
        )
        assert result == "HELLO!"

    def test_raising_transform_skipped_rest_continues(self):
        result = _run_transform_outbound(
            [_RaisingInteg(), _SuffixInteg()], "hello", self.TARGET
        )
        assert result == "hello!"

    def test_target_passed_through(self):
        received = {}

        class TargetCapture:
            NAME = "target_capture"
            SETTINGS_SCHEMA = {}

            def transform_outbound(self, text: str, target) -> str:
                received["kind"] = target.kind
                received["value"] = target.value
                return text

        _run_transform_outbound([TargetCapture()], "hi", self.TARGET)
        assert received["kind"] == "handle"
        assert received["value"] == "+15551234567"


# ---------------------------------------------------------------------------
# BridgeContextImpl.send_text integration — outbound pipeline wired in
# ---------------------------------------------------------------------------

class TestBridgeContextImplSendText:
    """Verify that BridgeContextImpl.send_text invokes the outbound pipeline.

    We patch bridge._run_transform_outbound to capture its arguments and
    return value, avoiding asyncio.to_thread (Python 3.9+ only) entirely.
    """

    def test_send_text_calls_transform_pipeline(self):
        """_run_transform_outbound is called with ctx.integrations and the body."""
        import bridge as _bridge_mod

        ctx = BridgeContextImpl(contacts={}, chatdb=None)
        ctx.integrations = [_UpperInteg()]
        target = SendTarget(kind="handle", value="+15551234567", label="Alice")
        calls = []

        def _fake_pipeline(integrations, text, tgt):
            calls.append({"integrations": integrations, "text": text, "target": tgt})
            return text.upper()  # simulate transform

        from chat_send import SendResult
        fake_result = SendResult(osascript_ok=True, service="iMessage", is_sent=True)

        async def _fake_to_thread(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        def _fake_send(handle, body):
            return fake_result

        with patch.object(_bridge_mod, "_run_transform_outbound", side_effect=_fake_pipeline), \
             patch("bridge.send_text_confirm", side_effect=_fake_send), \
             patch.object(_bridge_mod.asyncio, "to_thread", side_effect=_fake_to_thread,
                          create=True):
            _run(ctx.send_text(target, "hello"))

        assert len(calls) == 1
        assert calls[0]["text"] == "hello"
        assert calls[0]["integrations"] is ctx.integrations
        assert calls[0]["target"] is target

    def test_send_text_transform_result_sent(self):
        """The body that reaches send_text_confirm is the transformed body."""
        import bridge as _bridge_mod

        ctx = BridgeContextImpl(contacts={}, chatdb=None)
        ctx.integrations = [_UpperInteg()]
        target = SendTarget(kind="handle", value="+15551234567", label="Alice")
        captured = {}

        from chat_send import SendResult
        fake_result = SendResult(osascript_ok=True, service="iMessage", is_sent=True)

        async def _fake_to_thread(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        def _fake_send(handle, body):
            captured["body"] = body
            return fake_result

        with patch("bridge.send_text_confirm", side_effect=_fake_send), \
             patch.object(_bridge_mod.asyncio, "to_thread", side_effect=_fake_to_thread,
                          create=True):
            _run(ctx.send_text(target, "hello"))

        assert captured["body"] == "HELLO"

    def test_send_text_web_scope_not_transformed(self):
        """Transforms with TRANSFORM_SCOPE='web' do not alter the outbound body."""
        import bridge as _bridge_mod

        ctx = BridgeContextImpl(contacts={}, chatdb=None)
        ctx.integrations = [_WebScopeInteg()]
        target = SendTarget(kind="handle", value="+15551234567", label="Alice")
        captured = {}

        from chat_send import SendResult
        fake_result = SendResult(osascript_ok=True, service="iMessage", is_sent=True)

        async def _fake_to_thread(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        def _fake_send(handle, body):
            captured["body"] = body
            return fake_result

        with patch("bridge.send_text_confirm", side_effect=_fake_send), \
             patch.object(_bridge_mod.asyncio, "to_thread", side_effect=_fake_to_thread,
                          create=True):
            _run(ctx.send_text(target, "hello"))

        assert captured["body"] == "hello"

    def test_send_text_empty_integrations_passthrough(self):
        """With no integrations, body passes through unchanged."""
        import bridge as _bridge_mod

        ctx = BridgeContextImpl(contacts={}, chatdb=None)
        target = SendTarget(kind="handle", value="+15551234567", label="Alice")
        captured = {}

        from chat_send import SendResult
        fake_result = SendResult(osascript_ok=True, service="iMessage", is_sent=True)

        async def _fake_to_thread(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        def _fake_send(handle, body):
            captured["body"] = body
            return fake_result

        with patch("bridge.send_text_confirm", side_effect=_fake_send), \
             patch.object(_bridge_mod.asyncio, "to_thread", side_effect=_fake_to_thread,
                          create=True):
            _run(ctx.send_text(target, "hello"))

        assert captured["body"] == "hello"
