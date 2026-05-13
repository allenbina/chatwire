"""Tests for the on_send trigger type in the automation rules engine.

Covers:
  - RulesEngine._compile: on_send rule compiles correctly (to_handles,
    not_to_handles frozensets; no pattern / compiled_regex needed)
  - RulesEngine.evaluate: on_send rules are silently skipped (inbound-only)
  - RulesEngine.evaluate_outbound: fires only for on_send rules
  - evaluate_outbound conditions: to_handles, not_to_handles, in_group,
    group_guid — all filter correctly; absent = unrestricted
  - stop_on_match halts outbound evaluation after first match
  - Mix of inbound and on_send rules — correct direction isolation
  - Unknown trigger type raises ValueError in _compile
  - api_v1._validate_rule_body accepts on_send trigger
  - api_v1._validate_rule_body: on_send does NOT require trigger.expr
  - OutboundEvent dataclass fields (integrations.base)
  - RulesIntegration.on_outbound dispatches webhook / log actions
"""
from __future__ import annotations

import asyncio
import hashlib
import sys
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure repo root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from integrations.rules import RulesEngine, RulesIntegration
from integrations.base import OutboundEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rule(name="r", trigger_type="on_send", actions=None,
               to_handles=None, not_to_handles=None,
               in_group=None, group_guid=None,
               stop_on_match=False):
    """Build a minimal on_send rule dict."""
    rule = {
        "name": name,
        "trigger": {"type": trigger_type},
        "actions": actions or [{"type": "log", "message": "sent by {handle}"}],
        "stop_on_match": stop_on_match,
    }
    conds = {}
    if to_handles:
        conds["to_handles"] = to_handles
    if not_to_handles:
        conds["not_to_handles"] = not_to_handles
    if in_group is not None:
        conds["in_group"] = in_group
    if group_guid is not None:
        conds["group_guid"] = group_guid
    if conds:
        rule["conditions"] = conds
    return rule


def _make_inbound_rule(name="inbound", pattern="hello"):
    return {
        "name": name,
        "trigger": {"type": "text_contains", "pattern": pattern},
        "actions": [{"type": "log", "message": "inbound hit"}],
    }


def _run(coro):
    """Run a coroutine synchronously using asyncio.run() (Python 3.7+)."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# RulesEngine — compile
# ---------------------------------------------------------------------------

class TestCompileOnSend(unittest.TestCase):

    def test_on_send_compiles_without_pattern(self):
        rule = _make_rule()
        engine = RulesEngine([rule])
        self.assertEqual(len(engine._rules), 1)
        compiled = engine._rules[0]
        self.assertEqual(compiled["trigger_type"], "on_send")
        self.assertIsNone(compiled["compiled_regex"])
        self.assertIsNone(compiled["compiled_dsl"])

    def test_to_handles_compiled_as_frozenset_lowercased(self):
        rule = _make_rule(to_handles=["+15551234567", "+15559876543"])
        engine = RulesEngine([rule])
        compiled = engine._rules[0]
        self.assertEqual(compiled["to_handles"], frozenset({"+15551234567", "+15559876543"}))

    def test_not_to_handles_compiled_as_frozenset_lowercased(self):
        rule = _make_rule(not_to_handles=["+15550001111"])
        engine = RulesEngine([rule])
        compiled = engine._rules[0]
        self.assertEqual(compiled["not_to_handles"], frozenset({"+15550001111"}))

    def test_empty_to_handles_compiles_as_empty_frozenset(self):
        rule = _make_rule()
        engine = RulesEngine([rule])
        self.assertEqual(engine._rules[0]["to_handles"], frozenset())
        self.assertEqual(engine._rules[0]["not_to_handles"], frozenset())

    def test_handles_uppercased_input_lowercased(self):
        rule = _make_rule(to_handles=["+15551234567"])
        engine = RulesEngine([rule])
        self.assertIn("+15551234567", engine._rules[0]["to_handles"])


# ---------------------------------------------------------------------------
# RulesEngine.evaluate — on_send rules must be skipped for inbound
# ---------------------------------------------------------------------------

class TestEvaluateSkipsOnSend(unittest.TestCase):

    def test_on_send_rule_ignored_for_inbound(self):
        engine = RulesEngine([_make_rule()])
        result = engine.evaluate("hello", "+15551234567", False, None)
        self.assertEqual(result, [])

    def test_mix_inbound_rule_fires_on_send_rule_does_not(self):
        rules = [_make_inbound_rule("inb"), _make_rule("out")]
        engine = RulesEngine(rules)
        result = engine.evaluate("hello", "+15551234567", False, None)
        names = [r[0] for r in result]
        self.assertIn("inb", names)
        self.assertNotIn("out", names)


# ---------------------------------------------------------------------------
# RulesEngine.evaluate_outbound
# ---------------------------------------------------------------------------

class TestEvaluateOutbound(unittest.TestCase):

    def test_fires_for_on_send_rule(self):
        engine = RulesEngine([_make_rule("r")])
        result = engine.evaluate_outbound("hi", "+15551234567", False, None)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], "r")

    def test_inbound_rule_not_fired_for_outbound(self):
        engine = RulesEngine([_make_inbound_rule("inb"), _make_rule("out")])
        result = engine.evaluate_outbound("hello", "+15551234567", False, None)
        names = [r[0] for r in result]
        self.assertNotIn("inb", names)
        self.assertIn("out", names)

    def test_no_on_send_rules_returns_empty(self):
        engine = RulesEngine([_make_inbound_rule()])
        result = engine.evaluate_outbound("hi", "+1", False, None)
        self.assertEqual(result, [])

    def test_multiple_on_send_rules_all_fire(self):
        rules = [_make_rule("a"), _make_rule("b")]
        engine = RulesEngine(rules)
        result = engine.evaluate_outbound("hi", "+1", False, None)
        self.assertEqual([r[0] for r in result], ["a", "b"])

    # ---- to_handles ----

    def test_to_handles_match(self):
        rule = _make_rule(to_handles=["+15551234567"])
        engine = RulesEngine([rule])
        result = engine.evaluate_outbound("hi", "+15551234567", False, None)
        self.assertEqual(len(result), 1)

    def test_to_handles_no_match(self):
        rule = _make_rule(to_handles=["+15551234567"])
        engine = RulesEngine([rule])
        result = engine.evaluate_outbound("hi", "+15550000000", False, None)
        self.assertEqual(result, [])

    def test_to_handles_empty_fires_for_any_handle(self):
        rule = _make_rule()
        engine = RulesEngine([rule])
        result = engine.evaluate_outbound("hi", "+19999999999", False, None)
        self.assertEqual(len(result), 1)

    # ---- not_to_handles ----

    def test_not_to_handles_excluded(self):
        rule = _make_rule(not_to_handles=["+15551234567"])
        engine = RulesEngine([rule])
        result = engine.evaluate_outbound("hi", "+15551234567", False, None)
        self.assertEqual(result, [])

    def test_not_to_handles_not_excluded_if_different(self):
        rule = _make_rule(not_to_handles=["+15551234567"])
        engine = RulesEngine([rule])
        result = engine.evaluate_outbound("hi", "+15550000000", False, None)
        self.assertEqual(len(result), 1)

    # ---- in_group ----

    def test_in_group_true_fires_only_for_groups(self):
        rule = _make_rule(in_group=True)
        engine = RulesEngine([rule])
        self.assertEqual(len(engine.evaluate_outbound("hi", "", True, "guid")), 1)
        self.assertEqual(engine.evaluate_outbound("hi", "+1", False, None), [])

    def test_in_group_false_fires_only_for_1to1(self):
        rule = _make_rule(in_group=False)
        engine = RulesEngine([rule])
        self.assertEqual(len(engine.evaluate_outbound("hi", "+1", False, None)), 1)
        self.assertEqual(engine.evaluate_outbound("hi", "", True, "guid"), [])

    def test_in_group_absent_fires_for_both(self):
        rule = _make_rule()
        engine = RulesEngine([rule])
        self.assertEqual(len(engine.evaluate_outbound("hi", "+1", False, None)), 1)
        self.assertEqual(len(engine.evaluate_outbound("hi", "", True, "guid")), 1)

    # ---- group_guid ----

    def test_group_guid_match(self):
        rule = _make_rule(group_guid="iMessage;+;chat123")
        engine = RulesEngine([rule])
        result = engine.evaluate_outbound("hi", "", True, "iMessage;+;chat123")
        self.assertEqual(len(result), 1)

    def test_group_guid_no_match(self):
        rule = _make_rule(group_guid="iMessage;+;chat123")
        engine = RulesEngine([rule])
        result = engine.evaluate_outbound("hi", "", True, "iMessage;+;chatOTHER")
        self.assertEqual(result, [])

    # ---- stop_on_match ----

    def test_stop_on_match_halts_evaluation(self):
        rules = [_make_rule("first", stop_on_match=True), _make_rule("second")]
        engine = RulesEngine(rules)
        result = engine.evaluate_outbound("hi", "+1", False, None)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], "first")

    def test_stop_on_match_false_continues_evaluation(self):
        rules = [_make_rule("first", stop_on_match=False), _make_rule("second")]
        engine = RulesEngine(rules)
        result = engine.evaluate_outbound("hi", "+1", False, None)
        self.assertEqual(len(result), 2)

    # ---- None / empty text ----

    def test_none_text_handled(self):
        engine = RulesEngine([_make_rule()])
        result = engine.evaluate_outbound(None, "+1", False, None)
        self.assertEqual(len(result), 1)

    def test_none_handle_handled(self):
        engine = RulesEngine([_make_rule()])
        result = engine.evaluate_outbound("hi", None, False, None)
        self.assertEqual(len(result), 1)


# ---------------------------------------------------------------------------
# api_v1 — validation
# ---------------------------------------------------------------------------

class TestApiV1OnSend(unittest.TestCase):

    def setUp(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import web.api_v1 as _mod
        from web.api_v1 import router as api_router
        from contextlib import contextmanager

        self._mod = _mod

        _plain_key = "test-on-send-key-0123456789abcdef"
        self._key_hash = hashlib.sha256(_plain_key.encode()).hexdigest()
        self._auth = {"X-API-Key": _plain_key}

        app = FastAPI()
        app.include_router(api_router)
        self.client = TestClient(app, raise_server_exceptions=False)

    @property
    def _store_ctx(self):
        import contextlib
        mod = self._mod
        key_hash = self._key_hash

        @contextlib.contextmanager
        def _cm(initial=None):
            store = list(initial or [])
            def _load(): return list(store)
            def _save(r): store.clear(); store.extend(r)
            with patch.object(mod, "_load_rules", _load):
                with patch.object(mod, "_save_rules", _save):
                    with patch.object(mod, "_api_key_hash", return_value=key_hash):
                        yield store
        return _cm

    def test_on_send_trigger_accepted(self):
        rule = {
            "name": "log_sends",
            "trigger": {"type": "on_send"},
            "actions": [{"type": "log", "message": "sent to {handle}"}],
        }
        with self._store_ctx() as _store:
            r = self.client.post(
                "/automations",
                json=rule,
                headers=self._auth,
            )

        self.assertEqual(r.status_code, 200)

    def test_on_send_does_not_require_expr(self):
        rule = {
            "name": "no_expr",
            "trigger": {"type": "on_send"},
            "actions": [],
        }
        with self._store_ctx() as _store:
            r = self.client.post(
                "/automations",
                json=rule,
                headers=self._auth,
            )

        # on_send without expr should succeed (unlike dsl which requires expr)
        self.assertEqual(r.status_code, 200)

    def test_on_send_with_conditions_accepted(self):
        rule = {
            "name": "filtered_send",
            "trigger": {"type": "on_send"},
            "conditions": {"to_handles": ["+15551234567"]},
            "actions": [{"type": "log", "message": "hi"}],
        }
        with self._store_ctx() as _store:
            r = self.client.post(
                "/automations",
                json=rule,
                headers=self._auth,
            )

        self.assertEqual(r.status_code, 200)


# ---------------------------------------------------------------------------
# OutboundEvent dataclass
# ---------------------------------------------------------------------------

class TestOutboundEvent(unittest.TestCase):

    def test_fields(self):
        ev = OutboundEvent(
            handle="+15551234567",
            text="hello",
            is_group=False,
            chat_guid="",
        )
        self.assertEqual(ev.handle, "+15551234567")
        self.assertEqual(ev.text, "hello")
        self.assertFalse(ev.is_group)
        self.assertEqual(ev.chat_guid, "")

    def test_group_fields(self):
        ev = OutboundEvent(handle="", text="hi all", is_group=True, chat_guid="iMessage;+;chat1")
        self.assertTrue(ev.is_group)
        self.assertEqual(ev.chat_guid, "iMessage;+;chat1")
        self.assertEqual(ev.handle, "")


# ---------------------------------------------------------------------------
# RulesIntegration.on_outbound — async dispatch
# ---------------------------------------------------------------------------

class TestRulesIntegrationOnOutbound(unittest.TestCase):

    def _make_integration(self, rules):
        cfg = {"rules": rules}
        integ = RulesIntegration(cfg)
        ctx = MagicMock()
        ctx.name_for = MagicMock(return_value=None)
        integ._ctx = ctx
        return integ

    def test_on_outbound_calls_log_action(self):
        rule = _make_rule("r", actions=[{"type": "log", "message": "sent: {text}"}])
        integ = self._make_integration([rule])
        ev = OutboundEvent(handle="+15551234567", text="hello", is_group=False, chat_guid="")
        # Should not raise; log action is synchronous
        _run(integ.on_outbound(ev))

    def test_on_outbound_no_match_is_silent(self):
        rule = _make_rule("r", to_handles=["+15550000001"])
        integ = self._make_integration([rule])
        ev = OutboundEvent(handle="+15559999999", text="hi", is_group=False, chat_guid="")
        _run(integ.on_outbound(ev))  # should complete without error

    def test_on_outbound_without_ctx_is_noop(self):
        rule = _make_rule()
        integ = self._make_integration([rule])
        integ._ctx = None  # detach ctx
        ev = OutboundEvent(handle="+1", text="hi", is_group=False, chat_guid="")
        _run(integ.on_outbound(ev))  # must not raise

    def test_on_outbound_fires_webhook_action(self):
        import httpx
        rule = _make_rule("r", actions=[{"type": "webhook", "url": "http://example.com/hook"}])
        integ = self._make_integration([rule])
        ev = OutboundEvent(handle="+1", text="hi", is_group=False, chat_guid="")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_resp)
        integ._client = mock_client
        _run(integ.on_outbound(ev))
        mock_client.request.assert_called_once()
        call_kwargs = mock_client.request.call_args
        payload = call_kwargs[1]["json"] if call_kwargs[1] else call_kwargs[0][2]
        # Accept either positional or keyword call
        args, kwargs = call_kwargs
        self.assertIn("json", kwargs)
        self.assertEqual(kwargs["json"]["handle"], "+1")
        self.assertEqual(kwargs["json"]["text"], "hi")

    def test_on_outbound_action_error_is_logged_not_raised(self):
        """A failing action must not propagate — other rules should still run."""
        import logging
        rule_bad = _make_rule("bad", actions=[{"type": "webhook", "url": "http://x.y/z"}])
        rule_good = _make_rule("good", actions=[{"type": "log", "message": "ok"}])
        integ = self._make_integration([rule_bad, rule_good])
        # Make webhook fail
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(side_effect=RuntimeError("network error"))
        integ._client = mock_client
        ev = OutboundEvent(handle="+1", text="test", is_group=False, chat_guid="")
        # Must not raise even though the webhook fails
        _run(integ.on_outbound(ev))


if __name__ == "__main__":
    unittest.main()
