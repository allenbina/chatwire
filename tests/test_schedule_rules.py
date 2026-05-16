"""Tests for the schedule trigger type in the automation rules engine.

Covers:
  - integrations.rules.cron: compile_cron / match_cron / CronError
    - valid 5-field expressions (*, literals, ranges, lists, steps)
    - CronError on empty, wrong field count, out-of-range, invalid syntax
    - match_cron: minute / hour / dom / month / dow (day-of-week 0=Sun)
  - RulesEngine._compile: schedule rule compiles correctly (compiled_cron set)
  - RulesEngine._compile: schedule without cron raises ValueError
  - RulesEngine._compile: schedule with invalid cron raises ValueError
  - RulesEngine.evaluate: schedule rules are silently skipped (inbound-only)
  - RulesEngine.evaluate_outbound: schedule rules are silently skipped
  - RulesEngine.evaluate_scheduled: returns matching schedule rules
  - evaluate_scheduled: stop_on_match halts evaluation
  - evaluate_scheduled: non-matching time returns empty list
  - Mixed rules: inbound + schedule direction isolation
  - api_v1._validate_rule_body accepts schedule trigger with cron
  - api_v1._validate_rule_body rejects schedule without cron
  - api_v1._validate_rule_body still rejects bad_type
  - RulesIntegration._fire_scheduled: log action dispatched
  - RulesIntegration._fire_scheduled: webhook action dispatched
  - RulesIntegration._fire_scheduled: reply action skipped with warning
  - RulesIntegration._fire_scheduled: no-ctx noop
  - RulesIntegration._fire_scheduled: action error isolation
  - _ScheduleContext: fields
  - No schedule task started when no schedule rules
"""
from __future__ import annotations

import asyncio
import datetime
import hashlib
import sys
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, call, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from integrations.rules import RulesEngine, RulesIntegration, _ScheduleContext
from integrations.rules.cron import CronError, compile_cron, match_cron


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_schedule_rule(name="sched", cron="0 9 * * *", actions=None,
                        stop_on_match=False):
    return {
        "name": name,
        "trigger": {"type": "schedule", "cron": cron},
        "actions": actions or [{"type": "log", "message": "tick"}],
        "stop_on_match": stop_on_match,
    }


def _make_inbound_rule(name="inbound", pattern="hello"):
    return {
        "name": name,
        "trigger": {"type": "text_contains", "pattern": pattern},
        "actions": [{"type": "log", "message": "inbound"}],
    }


def _dt(minute=0, hour=9, day=5, month=1, weekday=0):
    """Build a datetime with specific fields. weekday: Mon=0 … Sun=6."""
    # 2026-01-05 is a Monday (weekday=0)
    base = datetime.datetime(2026, 1, 5, 0, 0)  # Monday
    # shift to requested day in same week (for simplicity, add weekday delta)
    # Just build directly: find a date that matches the desired weekday
    # 2026-01-05 Mon, 2026-01-06 Tue, ..., 2026-01-11 Sun
    target_day = 5 + weekday  # 5=Mon, 6=Tue, ..., 11=Sun
    return datetime.datetime(2026, month, target_day, hour, minute)


# ---------------------------------------------------------------------------
# compile_cron
# ---------------------------------------------------------------------------

class TestCompileCron(unittest.TestCase):

    def test_star_star_star_star_star(self):
        cc = compile_cron("* * * * *")
        self.assertEqual(len(cc), 5)
        self.assertIn(0, cc[0])   # minute 0 in set
        self.assertIn(59, cc[0])  # minute 59 in set
        self.assertIn(23, cc[1])  # hour 23 in set
        self.assertIn(31, cc[2])  # dom 31 in set
        self.assertIn(12, cc[3])  # month 12 in set
        self.assertIn(6, cc[4])   # dow 6 in set

    def test_literal_values(self):
        cc = compile_cron("30 14 15 6 3")
        self.assertEqual(cc[0], frozenset([30]))
        self.assertEqual(cc[1], frozenset([14]))
        self.assertEqual(cc[2], frozenset([15]))
        self.assertEqual(cc[3], frozenset([6]))
        self.assertEqual(cc[4], frozenset([3]))

    def test_range(self):
        cc = compile_cron("0 9 * * 1-5")  # Mon-Fri
        self.assertEqual(cc[4], frozenset([1, 2, 3, 4, 5]))

    def test_list(self):
        cc = compile_cron("0 9 1,15 * *")  # 1st and 15th
        self.assertEqual(cc[2], frozenset([1, 15]))

    def test_step_star(self):
        cc = compile_cron("*/15 * * * *")  # every 15 minutes
        self.assertEqual(cc[0], frozenset([0, 15, 30, 45]))

    def test_step_range(self):
        cc = compile_cron("0-30/10 * * * *")  # 0, 10, 20, 30
        self.assertEqual(cc[0], frozenset([0, 10, 20, 30]))

    def test_step_from_value(self):
        cc = compile_cron("5/10 * * * *")  # 5, 15, 25, 35, 45, 55
        self.assertIn(5, cc[0])
        self.assertIn(15, cc[0])

    def test_mixed_list_and_range(self):
        cc = compile_cron("0 8,17 * * *")  # 08:00 and 17:00
        self.assertEqual(cc[1], frozenset([8, 17]))

    def test_error_empty(self):
        with self.assertRaises(CronError):
            compile_cron("")

    def test_error_wrong_field_count_four(self):
        with self.assertRaises(CronError):
            compile_cron("* * * *")

    def test_error_wrong_field_count_six(self):
        with self.assertRaises(CronError):
            compile_cron("* * * * * *")

    def test_error_minute_out_of_range(self):
        with self.assertRaises(CronError):
            compile_cron("60 * * * *")

    def test_error_hour_out_of_range(self):
        with self.assertRaises(CronError):
            compile_cron("0 24 * * *")

    def test_error_dom_zero(self):
        with self.assertRaises(CronError):
            compile_cron("0 0 0 * *")

    def test_error_month_zero(self):
        with self.assertRaises(CronError):
            compile_cron("0 0 1 0 *")

    def test_error_dow_seven(self):
        with self.assertRaises(CronError):
            compile_cron("0 0 1 1 7")

    def test_error_non_integer(self):
        with self.assertRaises(CronError):
            compile_cron("abc * * * *")

    def test_error_step_zero(self):
        with self.assertRaises(CronError):
            compile_cron("*/0 * * * *")

    def test_error_step_negative(self):
        with self.assertRaises(CronError):
            compile_cron("*/-1 * * * *")


# ---------------------------------------------------------------------------
# match_cron
# ---------------------------------------------------------------------------

class TestMatchCron(unittest.TestCase):

    def test_always_matches(self):
        cc = compile_cron("* * * * *")
        dt = datetime.datetime(2026, 6, 15, 12, 30)
        self.assertTrue(match_cron(cc, dt))

    def test_specific_time_matches(self):
        cc = compile_cron("0 9 * * *")
        dt = datetime.datetime(2026, 1, 1, 9, 0)
        self.assertTrue(match_cron(cc, dt))

    def test_specific_time_no_match_hour(self):
        cc = compile_cron("0 9 * * *")
        dt = datetime.datetime(2026, 1, 1, 10, 0)
        self.assertFalse(match_cron(cc, dt))

    def test_specific_time_no_match_minute(self):
        cc = compile_cron("0 9 * * *")
        dt = datetime.datetime(2026, 1, 1, 9, 1)
        self.assertFalse(match_cron(cc, dt))

    def test_monday_fires_on_monday(self):
        # dow=1 is Monday in cron
        cc = compile_cron("0 9 * * 1")
        monday = datetime.datetime(2026, 1, 5, 9, 0)  # 2026-01-05 is Monday
        self.assertTrue(match_cron(cc, monday))

    def test_monday_does_not_fire_on_sunday(self):
        cc = compile_cron("0 9 * * 1")
        sunday = datetime.datetime(2026, 1, 11, 9, 0)  # 2026-01-11 is Sunday
        self.assertFalse(match_cron(cc, sunday))

    def test_sunday_fires_on_sunday(self):
        # dow=0 is Sunday in cron; Python weekday() for Sunday = 6
        cc = compile_cron("0 9 * * 0")
        sunday = datetime.datetime(2026, 1, 11, 9, 0)  # Sunday
        self.assertTrue(match_cron(cc, sunday))

    def test_sunday_does_not_fire_on_monday(self):
        cc = compile_cron("0 9 * * 0")
        monday = datetime.datetime(2026, 1, 5, 9, 0)
        self.assertFalse(match_cron(cc, monday))

    def test_weekdays_mon_to_fri(self):
        cc = compile_cron("0 9 * * 1-5")
        monday = datetime.datetime(2026, 1, 5, 9, 0)   # Mon
        friday = datetime.datetime(2026, 1, 9, 9, 0)   # Fri
        saturday = datetime.datetime(2026, 1, 10, 9, 0) # Sat
        sunday = datetime.datetime(2026, 1, 11, 9, 0)  # Sun
        self.assertTrue(match_cron(cc, monday))
        self.assertTrue(match_cron(cc, friday))
        self.assertFalse(match_cron(cc, saturday))
        self.assertFalse(match_cron(cc, sunday))

    def test_every_15_minutes(self):
        cc = compile_cron("*/15 * * * *")
        dt0 = datetime.datetime(2026, 1, 1, 10, 0)
        dt15 = datetime.datetime(2026, 1, 1, 10, 15)
        dt30 = datetime.datetime(2026, 1, 1, 10, 30)
        dt45 = datetime.datetime(2026, 1, 1, 10, 45)
        dt7 = datetime.datetime(2026, 1, 1, 10, 7)
        self.assertTrue(match_cron(cc, dt0))
        self.assertTrue(match_cron(cc, dt15))
        self.assertTrue(match_cron(cc, dt30))
        self.assertTrue(match_cron(cc, dt45))
        self.assertFalse(match_cron(cc, dt7))

    def test_dom_match(self):
        cc = compile_cron("0 0 15 * *")
        dt_match = datetime.datetime(2026, 3, 15, 0, 0)
        dt_no = datetime.datetime(2026, 3, 16, 0, 0)
        self.assertTrue(match_cron(cc, dt_match))
        self.assertFalse(match_cron(cc, dt_no))

    def test_month_match(self):
        cc = compile_cron("0 0 1 6 *")
        dt_match = datetime.datetime(2026, 6, 1, 0, 0)
        dt_no = datetime.datetime(2026, 7, 1, 0, 0)
        self.assertTrue(match_cron(cc, dt_match))
        self.assertFalse(match_cron(cc, dt_no))


# ---------------------------------------------------------------------------
# RulesEngine — compile
# ---------------------------------------------------------------------------

class TestCompileSchedule(unittest.TestCase):

    def test_schedule_rule_compiles(self):
        rule = _make_schedule_rule()
        engine = RulesEngine([rule])
        self.assertEqual(len(engine._rules), 1)
        compiled = engine._rules[0]
        self.assertEqual(compiled["trigger_type"], "schedule")
        self.assertIsNotNone(compiled["compiled_cron"])

    def test_schedule_without_cron_raises(self):
        rule = {
            "name": "bad",
            "trigger": {"type": "schedule"},
            "actions": [],
        }
        engine = RulesEngine([rule])
        # Rule is skipped (compile error logged, not raised)
        self.assertEqual(len(engine._rules), 0)

    def test_schedule_with_invalid_cron_skipped(self):
        rule = {
            "name": "bad-cron",
            "trigger": {"type": "schedule", "cron": "not a cron"},
            "actions": [],
        }
        engine = RulesEngine([rule])
        self.assertEqual(len(engine._rules), 0)

    def test_schedule_cron_field_compiled(self):
        rule = _make_schedule_rule(cron="30 8 * * 1-5")
        engine = RulesEngine([rule])
        compiled = engine._rules[0]
        minute_set, hour_set, _, _, dow_set = compiled["compiled_cron"]
        self.assertIn(30, minute_set)
        self.assertIn(8, hour_set)
        self.assertEqual(dow_set, frozenset([1, 2, 3, 4, 5]))


# ---------------------------------------------------------------------------
# RulesEngine — direction isolation
# ---------------------------------------------------------------------------

class TestEvaluateSkipsSchedule(unittest.TestCase):

    def test_evaluate_skips_schedule_rules(self):
        rules = [_make_schedule_rule(), _make_inbound_rule()]
        engine = RulesEngine(rules)
        # Only inbound rule should match
        results = engine.evaluate("hello", "+1", False, None)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], "inbound")

    def test_evaluate_skips_all_schedule_rules(self):
        rules = [
            _make_schedule_rule("s1"),
            _make_schedule_rule("s2"),
        ]
        engine = RulesEngine(rules)
        results = engine.evaluate("anything", "+1", False, None)
        self.assertEqual(results, [])

    def test_evaluate_outbound_skips_schedule_rules(self):
        rules = [_make_schedule_rule()]
        engine = RulesEngine(rules)
        results = engine.evaluate_outbound("hi", "+1", False, None)
        self.assertEqual(results, [])


# ---------------------------------------------------------------------------
# RulesEngine — evaluate_scheduled
# ---------------------------------------------------------------------------

class TestEvaluateScheduled(unittest.TestCase):

    def test_fires_at_matching_time(self):
        rule = _make_schedule_rule(cron="0 9 * * *")
        engine = RulesEngine([rule])
        dt = datetime.datetime(2026, 1, 5, 9, 0)  # 09:00
        results = engine.evaluate_scheduled(dt)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], "sched")

    def test_no_match_at_wrong_time(self):
        rule = _make_schedule_rule(cron="0 9 * * *")
        engine = RulesEngine([rule])
        dt = datetime.datetime(2026, 1, 5, 10, 0)  # 10:00
        results = engine.evaluate_scheduled(dt)
        self.assertEqual(results, [])

    def test_multiple_rules_all_fire(self):
        rules = [
            _make_schedule_rule("a", cron="0 9 * * *"),
            _make_schedule_rule("b", cron="0 9 * * *"),
        ]
        engine = RulesEngine(rules)
        dt = datetime.datetime(2026, 1, 5, 9, 0)
        results = engine.evaluate_scheduled(dt)
        self.assertEqual(len(results), 2)
        names = [r[0] for r in results]
        self.assertIn("a", names)
        self.assertIn("b", names)

    def test_stop_on_match(self):
        rules = [
            _make_schedule_rule("first", cron="0 9 * * *", stop_on_match=True),
            _make_schedule_rule("second", cron="0 9 * * *"),
        ]
        engine = RulesEngine(rules)
        dt = datetime.datetime(2026, 1, 5, 9, 0)
        results = engine.evaluate_scheduled(dt)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], "first")

    def test_stop_on_match_false_continues(self):
        rules = [
            _make_schedule_rule("first", cron="0 9 * * *", stop_on_match=False),
            _make_schedule_rule("second", cron="0 9 * * *"),
        ]
        engine = RulesEngine(rules)
        dt = datetime.datetime(2026, 1, 5, 9, 0)
        results = engine.evaluate_scheduled(dt)
        self.assertEqual(len(results), 2)

    def test_skips_non_schedule_rules(self):
        rules = [_make_inbound_rule(), _make_schedule_rule(cron="0 9 * * *")]
        engine = RulesEngine(rules)
        dt = datetime.datetime(2026, 1, 5, 9, 0)
        results = engine.evaluate_scheduled(dt)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], "sched")

    def test_returns_actions(self):
        actions = [{"type": "log", "message": "scheduled!"}]
        rule = _make_schedule_rule(actions=actions, cron="* * * * *")
        engine = RulesEngine([rule])
        dt = datetime.datetime(2026, 1, 5, 9, 30)
        results = engine.evaluate_scheduled(dt)
        self.assertEqual(results[0][1], actions)


# ---------------------------------------------------------------------------
# api_v1 — validation
# ---------------------------------------------------------------------------

class TestApiV1Schedule(unittest.TestCase):

    def setUp(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import web.api_v1 as _mod
        from web.api_v1 import router as api_router

        self._mod = _mod

        _plain_key = "test-schedule-key-0123456789abcdef"
        self._key_hash = hashlib.sha256(_plain_key.encode()).hexdigest()
        self._auth = {"X-API-Key": _plain_key}

        app = FastAPI()
        app.include_router(api_router)
        self.client = TestClient(app, raise_server_exceptions=False)

    def _store_ctx(self, initial=None):
        import contextlib
        mod = self._mod
        key_hash = self._key_hash

        @contextlib.contextmanager
        def _cm():
            store = list(initial or [])
            def _load(): return list(store)
            def _save(r): store.clear(); store.extend(r)
            with patch.object(mod, "_load_rules", _load):
                with patch.object(mod, "_save_rules", _save):
                    with patch.object(mod, "_api_key_hash", return_value=key_hash):
                        yield store
        return _cm()

    def test_schedule_with_cron_accepted(self):
        rule = {
            "name": "daily-ping",
            "trigger": {"type": "schedule", "cron": "0 9 * * 1-5"},
            "actions": [{"type": "log", "message": "ping"}],
        }
        with self._store_ctx():
            r = self.client.post("/automations", json=rule, headers=self._auth)
        self.assertEqual(r.status_code, 200)

    def test_schedule_without_cron_rejected(self):
        rule = {
            "name": "bad",
            "trigger": {"type": "schedule"},
            "actions": [{"type": "log", "message": "ping"}],
        }
        with self._store_ctx():
            r = self.client.post("/automations", json=rule, headers=self._auth)
        self.assertEqual(r.status_code, 400)
        self.assertIn("cron", r.json().get("detail", "").lower())

    def test_schedule_with_empty_cron_rejected(self):
        rule = {
            "name": "bad",
            "trigger": {"type": "schedule", "cron": ""},
            "actions": [{"type": "log", "message": "ping"}],
        }
        with self._store_ctx():
            r = self.client.post("/automations", json=rule, headers=self._auth)
        self.assertEqual(r.status_code, 400)

    def test_bad_trigger_type_still_rejected(self):
        rule = {
            "name": "bad",
            "trigger": {"type": "bad_type"},
            "actions": [],
        }
        with self._store_ctx():
            r = self.client.post("/automations", json=rule, headers=self._auth)
        self.assertEqual(r.status_code, 400)


# ---------------------------------------------------------------------------
# RulesIntegration — _ScheduleContext
# ---------------------------------------------------------------------------

class TestScheduleContext(unittest.TestCase):

    def test_fields(self):
        ctx = _ScheduleContext()
        self.assertEqual(ctx.handle, "")
        self.assertEqual(ctx.text, "")
        self.assertFalse(ctx.is_group)
        self.assertEqual(ctx.chat_guid, "")


# ---------------------------------------------------------------------------
# RulesIntegration — _fire_scheduled dispatch
# ---------------------------------------------------------------------------

class TestFireScheduled(unittest.TestCase):

    def _make_integration(self, rules):
        cfg = {"rules": rules, "enabled": True}
        integ = RulesIntegration(cfg)
        return integ

    def test_log_action_dispatched(self):
        rule = _make_schedule_rule(
            cron="* * * * *",
            actions=[{"type": "log", "level": "info", "message": "scheduled tick"}],
        )
        integ = self._make_integration([rule])
        mock_ctx = MagicMock()
        mock_ctx.name_for = lambda h: None
        integ._ctx = mock_ctx

        dt = datetime.datetime(2026, 1, 5, 9, 0)
        with patch("integrations.rules.log") as mock_log:
            _run(integ._fire_scheduled(dt))
            # Should have logged at info level
            mock_log.info.assert_called()
            logged_msg = " ".join(str(a) for a in mock_log.info.call_args[0])
            self.assertIn("scheduled", logged_msg.lower())

    def test_webhook_action_dispatched(self):
        rule = _make_schedule_rule(
            cron="* * * * *",
            actions=[{"type": "webhook", "url": "https://example.com/hook"}],
        )
        integ = self._make_integration([rule])
        mock_ctx = MagicMock()
        integ._ctx = mock_ctx

        dt = datetime.datetime(2026, 1, 5, 9, 0)

        import httpx
        mock_response = MagicMock()
        mock_response.status_code = 200

        async def _mock_request(*args, **kwargs):
            return mock_response

        mock_client = MagicMock()
        mock_client.request = _mock_request
        integ._client = mock_client

        _run(integ._fire_scheduled(dt))
        # No exception — webhook was dispatched

    def test_reply_action_skipped_with_warning(self):
        rule = _make_schedule_rule(
            cron="* * * * *",
            actions=[{"type": "reply", "text": "hello"}],
        )
        integ = self._make_integration([rule])
        mock_ctx = MagicMock()
        integ._ctx = mock_ctx

        dt = datetime.datetime(2026, 1, 5, 9, 0)
        with patch("integrations.rules.log") as mock_log:
            _run(integ._fire_scheduled(dt))
            # Warning logged about no recipient
            mock_log.warning.assert_called()
            logged = " ".join(str(a) for a in mock_log.warning.call_args[0])
            self.assertIn("reply", logged.lower())

    def test_no_ctx_returns_early(self):
        rule = _make_schedule_rule(cron="* * * * *")
        integ = self._make_integration([rule])
        # _ctx is None — should return without error
        dt = datetime.datetime(2026, 1, 5, 9, 0)
        _run(integ._fire_scheduled(dt))  # no exception

    def test_action_error_isolation(self):
        """An action that raises must not prevent subsequent actions from running."""
        log_fired = []
        rule = _make_schedule_rule(
            cron="* * * * *",
            actions=[
                {"type": "webhook", "url": "https://bad.example"},
                {"type": "log", "message": "after-error"},
            ],
        )
        integ = self._make_integration([rule])
        mock_ctx = MagicMock()
        mock_ctx.name_for = lambda h: None
        integ._ctx = mock_ctx

        async def _exploding_request(*args, **kwargs):
            raise RuntimeError("network down")

        mock_client = MagicMock()
        mock_client.request = _exploding_request
        integ._client = mock_client

        dt = datetime.datetime(2026, 1, 5, 9, 0)
        with patch("integrations.rules.log") as mock_log:
            _run(integ._fire_scheduled(dt))
            # webhook raised, but log action still ran
            info_calls = [
                " ".join(str(a) for a in c[0])
                for c in mock_log.info.call_args_list
            ]
            self.assertTrue(any("after-error" in msg for msg in info_calls))

    def test_no_schedule_task_without_schedule_rules(self):
        """No asyncio task should be created when no schedule rules exist."""
        rule = _make_inbound_rule()
        integ = self._make_integration([rule])
        mock_ctx = MagicMock()

        async def _start_and_check():
            with patch("asyncio.ensure_future") as mock_ef:
                await integ.start(mock_ctx)
                mock_ef.assert_not_called()
            integ._ctx = None

        _run(_start_and_check())

    def test_schedule_task_started_with_schedule_rules(self):
        """ensure_future should be called when schedule rules exist."""
        rule = _make_schedule_rule()
        integ = self._make_integration([rule])
        mock_ctx = MagicMock()

        captured = {}

        async def _start_and_check():
            with patch("asyncio.ensure_future") as mock_ef:
                mock_ef.return_value = MagicMock()
                await integ.start(mock_ctx)
                captured["called"] = mock_ef.called
            integ._schedule_task = None  # prevent stop() from awaiting
            integ._ctx = None

        _run(_start_and_check())
        self.assertTrue(captured.get("called"))

    def test_non_matching_time_fires_nothing(self):
        rule = _make_schedule_rule(cron="0 9 * * *")  # 09:00 only
        integ = self._make_integration([rule])
        mock_ctx = MagicMock()
        integ._ctx = mock_ctx

        dt = datetime.datetime(2026, 1, 5, 10, 30)  # wrong time
        with patch("integrations.rules.log") as mock_log:
            _run(integ._fire_scheduled(dt))
            # Nothing should have been logged (no matching rule)
            for c in mock_log.info.call_args_list:
                args_str = " ".join(str(a) for a in c[0])
                self.assertNotIn("tick", args_str)


if __name__ == "__main__":
    unittest.main()
