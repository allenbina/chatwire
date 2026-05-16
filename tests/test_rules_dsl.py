"""Tests for integrations/rules/dsl.py — trigger grammar DSL parser.

Covers:
  - Individual predicate types (always, contains, exact, regex, from, not_from,
    in:group, in:1to1, in:dm, in:direct, group:GUID)
  - Boolean operators: AND (explicit + implicit), OR, NOT
  - Grouping with parentheses
  - Quoted string values with backslash escapes
  - Operator precedence: AND binds tighter than OR
  - Error cases: empty expr, unknown predicate, bad regex, bad 'in' value,
    missing operand after AND/OR/NOT, unmatched parenthesis
  - RulesEngine integration: dsl trigger type end-to-end
  - DSL rule with stop_on_match
  - Mix of DSL and non-DSL rules
  - Bad DSL expr at compile time — rule is skipped with a warning
  - api_v1._validate_rule_body accepts dsl trigger type
  - api_v1._validate_rule_body rejects dsl without expr
"""
import sys
import os
import unittest
from unittest.mock import patch

# Ensure repo root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from integrations.rules.dsl import DSLError, parse_dsl
from integrations.rules import RulesEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _eval(expr, text="", handle="+15550000000", is_group=False, chat_guid=None):
    """Compile *expr* and evaluate it against the given message context."""
    fn = parse_dsl(expr)
    return fn(text, handle.lower(), is_group, chat_guid)


# ---------------------------------------------------------------------------
# Individual predicates
# ---------------------------------------------------------------------------

class TestPredicateAlways(unittest.TestCase):
    def test_always_any_text(self):
        self.assertTrue(_eval("always", text="anything"))

    def test_always_empty_text(self):
        self.assertTrue(_eval("always", text=""))

    def test_always_group(self):
        self.assertTrue(_eval("always", is_group=True))


class TestPredicateContains(unittest.TestCase):
    def test_contains_hit(self):
        self.assertTrue(_eval("contains:hello", text="say hello world"))

    def test_contains_miss(self):
        self.assertFalse(_eval("contains:hello", text="bye"))

    def test_contains_case_insensitive(self):
        self.assertTrue(_eval("contains:Hello", text="say HELLO"))

    def test_contains_quoted(self):
        self.assertTrue(_eval('contains:"hello world"', text="say hello world please"))

    def test_contains_quoted_space_miss(self):
        self.assertFalse(_eval('contains:"hello world"', text="say hello"))

    def test_contains_quoted_backslash_escape(self):
        # contains:"it\"s" should match the literal: it"s
        self.assertTrue(_eval('contains:"it\\"s"', text='say it"s nice'))

    def test_contains_empty_value(self):
        # empty needle matches everything
        self.assertTrue(_eval("contains:", text="any text"))


class TestPredicateExact(unittest.TestCase):
    def test_exact_hit(self):
        self.assertTrue(_eval("exact:bye", text="bye"))

    def test_exact_miss(self):
        self.assertFalse(_eval("exact:bye", text="bye bye"))

    def test_exact_case_insensitive(self):
        self.assertTrue(_eval("exact:BYE", text="bye"))

    def test_exact_strips_whitespace(self):
        self.assertTrue(_eval("exact:bye", text="  bye  "))

    def test_exact_quoted(self):
        self.assertTrue(_eval('exact:"hello world"', text="hello world"))


class TestPredicateRegex(unittest.TestCase):
    def test_regex_hit(self):
        self.assertTrue(_eval("regex:hel+o", text="hello"))

    def test_regex_miss(self):
        self.assertFalse(_eval("regex:hel+o", text="heo"))

    def test_regex_case_insensitive(self):
        self.assertTrue(_eval("regex:HELLO", text="hello there"))

    def test_regex_anchored(self):
        self.assertTrue(_eval("regex:^hello$", text="hello"))
        self.assertFalse(_eval("regex:^hello$", text="hello world"))

    def test_regex_quoted(self):
        self.assertTrue(_eval('regex:"order\\s+#\\d+"', text="order #123"))

    def test_regex_invalid_raises(self):
        with self.assertRaises(DSLError):
            parse_dsl("regex:[invalid")


class TestPredicateFrom(unittest.TestCase):
    def test_from_hit(self):
        self.assertTrue(_eval("from:+15551234567", handle="+15551234567"))

    def test_from_miss(self):
        self.assertFalse(_eval("from:+15551234567", handle="+19999999999"))

    def test_from_case_insensitive(self):
        # email handles
        self.assertTrue(_eval("from:Alice@example.com", handle="alice@example.com"))

    def test_from_handle_lowercased(self):
        self.assertTrue(_eval("from:+15551234567", handle="+15551234567"))


class TestPredicateNotFrom(unittest.TestCase):
    def test_not_from_hit_when_different(self):
        self.assertTrue(_eval("not_from:+15551234567", handle="+19999999999"))

    def test_not_from_miss_when_same(self):
        self.assertFalse(_eval("not_from:+15551234567", handle="+15551234567"))


class TestPredicateInGroup(unittest.TestCase):
    def test_in_group_true(self):
        self.assertTrue(_eval("in:group", is_group=True))

    def test_in_group_false_for_1to1(self):
        self.assertFalse(_eval("in:group", is_group=False))

    def test_in_1to1_true(self):
        self.assertTrue(_eval("in:1to1", is_group=False))

    def test_in_1to1_false_for_group(self):
        self.assertFalse(_eval("in:1to1", is_group=True))

    def test_in_dm_alias(self):
        self.assertTrue(_eval("in:dm", is_group=False))
        self.assertFalse(_eval("in:dm", is_group=True))

    def test_in_direct_alias(self):
        self.assertTrue(_eval("in:direct", is_group=False))

    def test_in_invalid_raises(self):
        with self.assertRaises(DSLError):
            parse_dsl("in:channel")


class TestPredicateGroupGuid(unittest.TestCase):
    def test_group_guid_match(self):
        self.assertTrue(_eval("group:chat-GUID-123", chat_guid="chat-GUID-123"))

    def test_group_guid_no_match(self):
        self.assertFalse(_eval("group:chat-GUID-123", chat_guid="other-guid"))

    def test_group_guid_none(self):
        self.assertFalse(_eval("group:chat-GUID-123", chat_guid=None))


# ---------------------------------------------------------------------------
# Boolean operators and implicit AND
# ---------------------------------------------------------------------------

class TestBooleanAnd(unittest.TestCase):
    def test_explicit_and_both_true(self):
        self.assertTrue(_eval(
            "contains:hello AND from:+1",
            text="say hello", handle="+1"
        ))

    def test_explicit_and_first_false(self):
        self.assertFalse(_eval(
            "contains:hello AND from:+1",
            text="no match", handle="+1"
        ))

    def test_explicit_and_second_false(self):
        self.assertFalse(_eval(
            "contains:hello AND from:+1",
            text="say hello", handle="+2"
        ))

    def test_implicit_and(self):
        # Space between predicates without AND keyword
        self.assertTrue(_eval(
            "from:+1 contains:hello",
            text="say hello", handle="+1"
        ))

    def test_implicit_and_miss(self):
        self.assertFalse(_eval(
            "from:+1 contains:hello",
            text="say hello", handle="+2"
        ))

    def test_three_way_implicit_and(self):
        self.assertTrue(_eval(
            "from:+1 contains:hi in:group",
            text="hi there", handle="+1", is_group=True
        ))

    def test_three_way_implicit_and_miss(self):
        self.assertFalse(_eval(
            "from:+1 contains:hi in:group",
            text="hi there", handle="+1", is_group=False
        ))


class TestBooleanOr(unittest.TestCase):
    def test_or_first_true(self):
        self.assertTrue(_eval("contains:hello OR contains:bye", text="hello"))

    def test_or_second_true(self):
        self.assertTrue(_eval("contains:hello OR contains:bye", text="bye"))

    def test_or_both_true(self):
        self.assertTrue(_eval("contains:hello OR contains:bye", text="hello bye"))

    def test_or_both_false(self):
        self.assertFalse(_eval("contains:hello OR contains:bye", text="nothing"))


class TestBooleanNot(unittest.TestCase):
    def test_not_group(self):
        self.assertTrue(_eval("NOT in:group", is_group=False))
        self.assertFalse(_eval("NOT in:group", is_group=True))

    def test_not_from(self):
        self.assertTrue(_eval("NOT from:+1", handle="+2"))
        self.assertFalse(_eval("NOT from:+1", handle="+1"))

    def test_double_not(self):
        self.assertTrue(_eval("NOT NOT always"))


class TestPrecedence(unittest.TestCase):
    """AND binds tighter than OR."""

    def test_and_before_or(self):
        # "A OR B AND C" = "A OR (B AND C)"
        # A=contains:x, B=contains:y, C=in:group
        # text="x" is_group=False → A=True, (B AND C)=False → True
        self.assertTrue(_eval(
            "contains:x OR contains:y AND in:group",
            text="x", is_group=False
        ))
        # text="y" is_group=False → A=False, (B AND C)=False → False
        self.assertFalse(_eval(
            "contains:x OR contains:y AND in:group",
            text="y", is_group=False
        ))
        # text="y" is_group=True → A=False, (B AND C)=True → True
        self.assertTrue(_eval(
            "contains:x OR contains:y AND in:group",
            text="y", is_group=True
        ))

    def test_grouping_overrides_precedence(self):
        # "(A OR B) AND C"
        # text="x" is_group=True → (A OR B)=True, C=True → True
        self.assertTrue(_eval(
            "(contains:x OR contains:y) AND in:group",
            text="x", is_group=True
        ))
        # text="x" is_group=False → (A OR B)=True, C=False → False
        self.assertFalse(_eval(
            "(contains:x OR contains:y) AND in:group",
            text="x", is_group=False
        ))


class TestGrouping(unittest.TestCase):
    def test_simple_group(self):
        self.assertTrue(_eval("(always)", text="hi"))

    def test_nested_groups(self):
        self.assertTrue(_eval(
            "((contains:a OR contains:b) AND NOT in:group)",
            text="a", is_group=False
        ))
        self.assertFalse(_eval(
            "((contains:a OR contains:b) AND NOT in:group)",
            text="a", is_group=True
        ))

    def test_complex_expression(self):
        # (from:+1 OR from:+2) AND contains:urgent AND NOT in:group
        expr = "(from:+1 OR from:+2) AND contains:urgent AND NOT in:group"
        self.assertTrue(_eval(expr, text="urgent message", handle="+1", is_group=False))
        self.assertTrue(_eval(expr, text="urgent message", handle="+2", is_group=False))
        self.assertFalse(_eval(expr, text="urgent message", handle="+3", is_group=False))
        self.assertFalse(_eval(expr, text="normal message", handle="+1", is_group=False))
        self.assertFalse(_eval(expr, text="urgent message", handle="+1", is_group=True))


# ---------------------------------------------------------------------------
# Edge cases and tokenizer
# ---------------------------------------------------------------------------

class TestTokenizerEdgeCases(unittest.TestCase):
    def test_extra_whitespace(self):
        self.assertTrue(_eval("  contains:hello  ", text="hello"))

    def test_mixed_case_and(self):
        self.assertTrue(_eval("contains:hi AnD in:group", text="hi", is_group=True))

    def test_mixed_case_or(self):
        self.assertTrue(_eval("contains:hi Or contains:bye", text="bye"))

    def test_mixed_case_not(self):
        self.assertFalse(_eval("NoT always"))

    def test_quoted_value_with_spaces_inside(self):
        fn = parse_dsl('contains:"hello world"')
        self.assertTrue(fn("say hello world", "", False, None))
        self.assertFalse(fn("say hello", "", False, None))

    def test_quoted_value_escaped_quote(self):
        fn = parse_dsl('exact:"say \\"hi\\""')
        self.assertTrue(fn('say "hi"', "", False, None))
        self.assertFalse(fn('say hi', "", False, None))


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

class TestDSLErrors(unittest.TestCase):
    def test_empty_expr(self):
        with self.assertRaises(DSLError):
            parse_dsl("")

    def test_blank_expr(self):
        with self.assertRaises(DSLError):
            parse_dsl("   ")

    def test_unknown_predicate(self):
        with self.assertRaises(DSLError):
            parse_dsl("banana:yes")

    def test_invalid_in_value(self):
        with self.assertRaises(DSLError):
            parse_dsl("in:channel")

    def test_invalid_regex(self):
        with self.assertRaises(DSLError):
            parse_dsl("regex:[unclosed")

    def test_and_without_right_operand(self):
        with self.assertRaises(DSLError):
            parse_dsl("contains:hi AND")

    def test_or_without_right_operand(self):
        with self.assertRaises(DSLError):
            parse_dsl("contains:hi OR")

    def test_not_without_operand(self):
        with self.assertRaises(DSLError):
            parse_dsl("NOT")

    def test_unmatched_open_paren(self):
        with self.assertRaises(DSLError):
            parse_dsl("(contains:hi")

    def test_unmatched_close_paren(self):
        with self.assertRaises(DSLError):
            parse_dsl("contains:hi)")

    def test_trailing_tokens_after_expr(self):
        # valid paren but then extra junk
        with self.assertRaises(DSLError):
            parse_dsl("(contains:hi) extra")

    def test_not_before_and(self):
        with self.assertRaises(DSLError):
            parse_dsl("NOT AND contains:hi")


# ---------------------------------------------------------------------------
# RulesEngine integration
# ---------------------------------------------------------------------------

class TestRulesEngineDSL(unittest.TestCase):
    """End-to-end tests using RulesEngine with dsl trigger rules."""

    def _engine(self, rules):
        return RulesEngine(rules)

    def _eval_engine(self, engine, text="", handle="+15550000000",
                     is_group=False, chat_guid=None):
        return engine.evaluate(
            msg_text=text,
            msg_handle=handle,
            msg_is_group=is_group,
            msg_chat_guid=chat_guid,
        )

    def test_dsl_rule_fires(self):
        engine = self._engine([{
            "name": "greet",
            "trigger": {"type": "dsl", "expr": "contains:hello AND in:1to1"},
            "actions": [{"type": "log", "message": "fired"}],
        }])
        results = self._eval_engine(engine, text="hello there", is_group=False)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], "greet")

    def test_dsl_rule_does_not_fire(self):
        engine = self._engine([{
            "name": "greet",
            "trigger": {"type": "dsl", "expr": "contains:hello AND in:1to1"},
            "actions": [{"type": "log", "message": "fired"}],
        }])
        # is_group=True — condition fails
        results = self._eval_engine(engine, text="hello", is_group=True)
        self.assertEqual(results, [])

    def test_dsl_rule_stop_on_match(self):
        engine = self._engine([
            {
                "name": "first",
                "trigger": {"type": "dsl", "expr": "always"},
                "actions": [{"type": "log", "message": "first"}],
                "stop_on_match": True,
            },
            {
                "name": "second",
                "trigger": {"type": "dsl", "expr": "always"},
                "actions": [{"type": "log", "message": "second"}],
            },
        ])
        results = self._eval_engine(engine, text="hi")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], "first")

    def test_dsl_and_non_dsl_rules_coexist(self):
        engine = self._engine([
            {
                "name": "text_rule",
                "trigger": {"type": "text_contains", "pattern": "hello"},
                "actions": [{"type": "log", "message": "text"}],
            },
            {
                "name": "dsl_rule",
                "trigger": {"type": "dsl", "expr": "contains:hello AND in:group"},
                "actions": [{"type": "log", "message": "dsl"}],
            },
        ])
        # Both fire for group "hello"
        results = self._eval_engine(engine, text="hello", is_group=True)
        self.assertEqual(len(results), 2)
        names = [r[0] for r in results]
        self.assertIn("text_rule", names)
        self.assertIn("dsl_rule", names)

        # Only text_rule fires for 1:1 "hello"
        results = self._eval_engine(engine, text="hello", is_group=False)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], "text_rule")

    def test_dsl_from_filter(self):
        engine = self._engine([{
            "name": "vip",
            "trigger": {"type": "dsl", "expr": "from:+15551234567"},
            "actions": [{"type": "log", "message": "vip"}],
        }])
        results = self._eval_engine(engine, handle="+15551234567")
        self.assertEqual(len(results), 1)
        results = self._eval_engine(engine, handle="+19999999999")
        self.assertEqual(results, [])

    def test_dsl_regex_trigger(self):
        engine = self._engine([{
            "name": "order",
            "trigger": {"type": "dsl", "expr": "regex:order\\s+#\\d+"},
            "actions": [{"type": "log", "message": "order"}],
        }])
        results = self._eval_engine(engine, text="Your order #42 is ready")
        self.assertEqual(len(results), 1)
        results = self._eval_engine(engine, text="no match")
        self.assertEqual(results, [])

    def test_dsl_complex_or_condition(self):
        expr = "(from:+1 OR from:+2) AND contains:urgent"
        engine = self._engine([{
            "name": "urgent",
            "trigger": {"type": "dsl", "expr": expr},
            "actions": [{"type": "log", "message": "urgent"}],
        }])
        self.assertEqual(
            len(self._eval_engine(engine, text="urgent", handle="+1")), 1
        )
        self.assertEqual(
            len(self._eval_engine(engine, text="urgent", handle="+2")), 1
        )
        self.assertEqual(
            len(self._eval_engine(engine, text="urgent", handle="+3")), 0
        )
        self.assertEqual(
            len(self._eval_engine(engine, text="normal", handle="+1")), 0
        )

    def test_bad_dsl_rule_skipped_at_compile(self):
        """A rule with an unparseable DSL expression is skipped; no crash."""
        import logging
        with patch.object(logging.getLogger("integrations.rules"), "warning") as mock_warn:
            engine = self._engine([
                {
                    "name": "bad",
                    "trigger": {"type": "dsl", "expr": "regex:[unclosed"},
                    "actions": [{"type": "log", "message": "bad"}],
                },
                {
                    "name": "good",
                    "trigger": {"type": "dsl", "expr": "always"},
                    "actions": [{"type": "log", "message": "good"}],
                },
            ])
        # "bad" rule skipped; "good" rule still fires
        results = self._eval_engine(engine, text="hi")
        names = [r[0] for r in results]
        self.assertNotIn("bad", names)
        self.assertIn("good", names)
        # warning was logged for the bad rule
        self.assertTrue(mock_warn.called)

    def test_dsl_missing_expr_at_compile(self):
        """A dsl rule without 'expr' is skipped at compile time."""
        import logging
        with patch.object(logging.getLogger("integrations.rules"), "warning") as mock_warn:
            engine = self._engine([{
                "name": "no_expr",
                "trigger": {"type": "dsl"},
                "actions": [{"type": "log", "message": "x"}],
            }])
        results = self._eval_engine(engine, text="hi")
        self.assertEqual(results, [])
        self.assertTrue(mock_warn.called)


# ---------------------------------------------------------------------------
# api_v1 validation
# ---------------------------------------------------------------------------

class TestApiV1DslValidation(unittest.TestCase):
    """_validate_rule_body in api_v1.py must accept dsl and reject dsl without expr."""

    def _get_validate_fn(self):
        """Import _validate_rule_body without triggering web.main side-effects."""
        import importlib
        import sys

        # Stub out the heavy web.main dependencies that api_v1 may import transitively
        for mod_name in list(sys.modules.keys()):
            if mod_name.startswith("web.main"):
                del sys.modules[mod_name]

        # We only need _validate_rule_body; grab it without importing the whole router
        spec = importlib.util.spec_from_file_location(
            "_api_v1_test",
            os.path.join(os.path.dirname(__file__), "..", "web", "api_v1.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        # Pre-populate required globals that api_v1 expects
        import types
        mod.__builtins__ = __builtins__
        try:
            spec.loader.exec_module(mod)
        except Exception:
            pass  # allow partial load; we only need _validate_rule_body

        return getattr(mod, "_validate_rule_body", None)

    def _make_rule(self, trigger):
        return {"name": "test", "trigger": trigger, "actions": []}

    def test_accepts_dsl_with_expr(self):
        from web.api_v1 import _validate_rule_body
        rule = self._make_rule({"type": "dsl", "expr": "contains:hello"})
        result = _validate_rule_body(rule)
        self.assertEqual(result["name"], "test")

    def test_rejects_dsl_without_expr(self):
        from web.api_v1 import _validate_rule_body
        from starlette.exceptions import HTTPException
        rule = self._make_rule({"type": "dsl"})
        with self.assertRaises(HTTPException) as cm:
            _validate_rule_body(rule)
        self.assertEqual(cm.exception.status_code, 400)

    def test_rejects_dsl_with_empty_expr(self):
        from web.api_v1 import _validate_rule_body
        from starlette.exceptions import HTTPException
        rule = self._make_rule({"type": "dsl", "expr": ""})
        with self.assertRaises(HTTPException) as cm:
            _validate_rule_body(rule)
        self.assertEqual(cm.exception.status_code, 400)

    def test_accepts_existing_trigger_types(self):
        from web.api_v1 import _validate_rule_body
        for ttype in ("text_exact", "text_contains", "text_regex", "always"):
            rule = self._make_rule({"type": ttype, "pattern": "hi"})
            result = _validate_rule_body(rule)
            self.assertEqual(result["trigger"]["type"], ttype)

    def test_rejects_unknown_trigger_type(self):
        from web.api_v1 import _validate_rule_body
        from starlette.exceptions import HTTPException
        rule = self._make_rule({"type": "banana"})
        with self.assertRaises(HTTPException) as cm:
            _validate_rule_body(rule)
        self.assertEqual(cm.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
