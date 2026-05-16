"""Tests for Phase 61: built-in automation rules engine (integrations/rules/).

Strategy
--------
- Import RulesEngine and RulesIntegration directly (sys.path insert).
- RulesEngine tests are synchronous (pure evaluation, no I/O).
- RulesIntegration tests use asyncio.run() — matches project pattern.
- No pytest-asyncio needed; no actual iMessage or network calls.

Coverage
--------
RulesEngine — triggers:
  a. text_exact: exact match fires; non-match does not
  b. text_exact: case-insensitive and strips surrounding whitespace
  c. text_contains: substring match fires; missing substring does not
  d. text_contains: case-insensitive
  e. text_regex: compiled regex match fires; non-match does not
  f. text_regex: flags are IGNORECASE by default
  g. always: fires regardless of message text
  h. bad trigger type: rule is skipped at compile time, no exception
  i. bad regex pattern: rule is skipped at compile time, no exception

RulesEngine — conditions:
  j. from_handles: match fires; non-match skips
  k. not_from_handles: excluded handle is skipped; non-excluded fires
  l. in_group=true: group message fires; 1:1 message skips
  m. in_group=false: 1:1 message fires; group message skips
  n. group_guid: specific GUID fires; different GUID skips
  o. multiple conditions combined: all must pass

RulesEngine — evaluation order / stop_on_match:
  p. all matching rules fire by default
  q. stop_on_match=true: only first matching rule fires
  r. stop_on_match on non-matching rule: has no effect on subsequent rules

RulesIntegration — actions:
  s. reply action sends via ctx.send_text with rendered template
  t. reply template {handle}, {name}, {text} interpolated correctly
  u. reply to group message uses kind='chat' + chat_guid
  v. reply to 1:1 message uses kind='handle' + handle
  w. reply with empty text template sends nothing
  x. webhook action POSTs to URL with JSON context payload
  y. webhook action with HTTP error logs warning, does not crash
  z. webhook action missing url logs warning, does not crash
  aa. log action emits a log line; supports {rule} template variable
  bb. unknown action type logs warning, does not crash
  cc. action exception logs warning; subsequent actions still run

RulesIntegration — lifecycle:
  dd. on_inbound before start() is a silent no-op
  ee. stop() clears ctx; on_inbound after stop() is a silent no-op
"""
from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import the module under test directly from the source tree.
# ---------------------------------------------------------------------------
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from integrations.rules import RulesEngine, RulesIntegration, _render  # noqa: E402


# ---------------------------------------------------------------------------
# Minimal stubs for bridge types (not importing the full bridge)
# ---------------------------------------------------------------------------

@dataclass
class FakeSendTarget:
    kind: str
    value: str
    label: str

    @property
    def is_group(self) -> bool:
        return self.kind == "chat"


@dataclass
class FakeMsg:
    text: str
    handle: str = "+15551234567"
    is_group: bool = False
    chat_guid: str | None = None
    chat_name: str = ""
    chat_identifier: str = ""


@dataclass
class FakeCtx:
    sent: list[tuple[Any, str]] = field(default_factory=list)
    _contacts: dict[str, str] = field(default_factory=dict)

    async def send_text(self, target: Any, body: str) -> MagicMock:
        self.sent.append((target, body))
        return MagicMock(status="delivered")

    def name_for(self, handle: str) -> str | None:
        return self._contacts.get((handle or "").lower())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _engine(rules: list[dict]) -> RulesEngine:
    return RulesEngine(rules)


def _integ(rules: list[dict]) -> RulesIntegration:
    return RulesIntegration({"enabled": True, "rules": rules})


async def _start(integ: RulesIntegration, ctx: FakeCtx | None = None) -> FakeCtx:
    ctx = ctx or FakeCtx()
    # Patch SendTarget so _do_reply can construct one
    import integrations.rules as _mod
    _mod.SendTarget = FakeSendTarget  # type: ignore[attr-defined]
    await integ.start(ctx)
    return ctx


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _eval(engine: RulesEngine, text: str, handle: str = "+15551234567",
          is_group: bool = False, chat_guid: str | None = None) -> list[tuple]:
    return engine.evaluate(
        msg_text=text,
        msg_handle=handle,
        msg_is_group=is_group,
        msg_chat_guid=chat_guid,
    )


# ===========================================================================
# RulesEngine — trigger tests
# ===========================================================================

class TestTriggerExact:
    def test_exact_match_fires(self) -> None:
        """a. text_exact: exact text fires the rule."""
        e = _engine([{"name": "r", "trigger": {"type": "text_exact", "pattern": "hello"}, "actions": []}])
        assert _eval(e, "hello") == [("r", [])]

    def test_exact_non_match_does_not_fire(self) -> None:
        """a. text_exact: different text does not fire."""
        e = _engine([{"name": "r", "trigger": {"type": "text_exact", "pattern": "hello"}, "actions": []}])
        assert _eval(e, "hi there") == []

    def test_exact_case_insensitive(self) -> None:
        """b. text_exact: match is case-insensitive."""
        e = _engine([{"name": "r", "trigger": {"type": "text_exact", "pattern": "hello"}, "actions": []}])
        assert _eval(e, "HELLO") == [("r", [])]

    def test_exact_strips_whitespace(self) -> None:
        """b. text_exact: leading/trailing whitespace stripped before matching."""
        e = _engine([{"name": "r", "trigger": {"type": "text_exact", "pattern": "hello"}, "actions": []}])
        assert _eval(e, "  hello  ") == [("r", [])]

    def test_exact_partial_does_not_match(self) -> None:
        """text_exact does not match when pattern is only a substring."""
        e = _engine([{"name": "r", "trigger": {"type": "text_exact", "pattern": "hello"}, "actions": []}])
        assert _eval(e, "hello world") == []


class TestTriggerContains:
    def test_contains_fires(self) -> None:
        """c. text_contains: substring match fires."""
        e = _engine([{"name": "r", "trigger": {"type": "text_contains", "pattern": "hello"}, "actions": []}])
        assert _eval(e, "say hello to everyone") == [("r", [])]

    def test_contains_no_match(self) -> None:
        """c. text_contains: absent substring does not fire."""
        e = _engine([{"name": "r", "trigger": {"type": "text_contains", "pattern": "hello"}, "actions": []}])
        assert _eval(e, "goodbye world") == []

    def test_contains_case_insensitive(self) -> None:
        """d. text_contains: case-insensitive."""
        e = _engine([{"name": "r", "trigger": {"type": "text_contains", "pattern": "hello"}, "actions": []}])
        assert _eval(e, "HELLO THERE") == [("r", [])]


class TestTriggerRegex:
    def test_regex_match_fires(self) -> None:
        """e. text_regex: matching pattern fires."""
        e = _engine([{"name": "r", "trigger": {"type": "text_regex", "pattern": r"^(hi|hey|hello)"}, "actions": []}])
        assert _eval(e, "hey there") == [("r", [])]

    def test_regex_non_match(self) -> None:
        """e. text_regex: non-matching pattern does not fire."""
        e = _engine([{"name": "r", "trigger": {"type": "text_regex", "pattern": r"^(hi|hey|hello)"}, "actions": []}])
        assert _eval(e, "goodbye") == []

    def test_regex_case_insensitive(self) -> None:
        """f. text_regex: compiled with IGNORECASE flag."""
        e = _engine([{"name": "r", "trigger": {"type": "text_regex", "pattern": r"urgent"}, "actions": []}])
        assert _eval(e, "URGENT request") == [("r", [])]


class TestTriggerAlways:
    def test_always_fires_any_text(self) -> None:
        """g. always: fires regardless of message text."""
        e = _engine([{"name": "r", "trigger": {"type": "always"}, "actions": []}])
        assert _eval(e, "anything at all") == [("r", [])]
        assert _eval(e, "") == [("r", [])]


class TestBadConfig:
    def test_unknown_trigger_type_skipped(self) -> None:
        """h. Unknown trigger type → rule silently skipped; no exception."""
        e = _engine([{"name": "bad", "trigger": {"type": "text_fuzzy"}, "actions": []}])
        assert e._rules == []

    def test_bad_regex_skipped(self) -> None:
        """i. Malformed regex → rule silently skipped; no exception."""
        e = _engine([{"name": "bad", "trigger": {"type": "text_regex", "pattern": "["}, "actions": []}])
        assert e._rules == []

    def test_valid_rule_after_bad_still_loads(self) -> None:
        """Invalid rule does not block subsequent valid rules."""
        e = _engine([
            {"name": "bad", "trigger": {"type": "text_fuzzy"}, "actions": []},
            {"name": "ok", "trigger": {"type": "text_exact", "pattern": "hi"}, "actions": []},
        ])
        assert len(e._rules) == 1
        assert e._rules[0]["name"] == "ok"


# ===========================================================================
# RulesEngine — condition tests
# ===========================================================================

class TestConditionFromHandles:
    def test_in_from_handles_fires(self) -> None:
        """j. Sender in from_handles → fires."""
        e = _engine([{
            "name": "r",
            "trigger": {"type": "always"},
            "conditions": {"from_handles": ["+15551234567"]},
            "actions": [],
        }])
        assert _eval(e, "", handle="+15551234567") == [("r", [])]

    def test_not_in_from_handles_skips(self) -> None:
        """j. Sender not in from_handles → skips."""
        e = _engine([{
            "name": "r",
            "trigger": {"type": "always"},
            "conditions": {"from_handles": ["+15551234567"]},
            "actions": [],
        }])
        assert _eval(e, "", handle="+19998887777") == []

    def test_from_handles_case_insensitive(self) -> None:
        """from_handles matching is case-insensitive (email handles)."""
        e = _engine([{
            "name": "r",
            "trigger": {"type": "always"},
            "conditions": {"from_handles": ["Alice@Example.COM"]},
            "actions": [],
        }])
        assert _eval(e, "", handle="alice@example.com") == [("r", [])]


class TestConditionNotFromHandles:
    def test_excluded_handle_skips(self) -> None:
        """k. Sender in not_from_handles → skips."""
        e = _engine([{
            "name": "r",
            "trigger": {"type": "always"},
            "conditions": {"not_from_handles": ["+15551234567"]},
            "actions": [],
        }])
        assert _eval(e, "", handle="+15551234567") == []

    def test_non_excluded_handle_fires(self) -> None:
        """k. Sender not in not_from_handles → fires."""
        e = _engine([{
            "name": "r",
            "trigger": {"type": "always"},
            "conditions": {"not_from_handles": ["+15551234567"]},
            "actions": [],
        }])
        assert _eval(e, "", handle="+19998887777") == [("r", [])]


class TestConditionInGroup:
    def test_in_group_true_fires_for_group(self) -> None:
        """l. in_group=true: group message fires."""
        e = _engine([{
            "name": "r", "trigger": {"type": "always"},
            "conditions": {"in_group": True}, "actions": [],
        }])
        assert _eval(e, "", is_group=True, chat_guid="iMessage;+;g1") == [("r", [])]

    def test_in_group_true_skips_one_to_one(self) -> None:
        """l. in_group=true: 1:1 message skips."""
        e = _engine([{
            "name": "r", "trigger": {"type": "always"},
            "conditions": {"in_group": True}, "actions": [],
        }])
        assert _eval(e, "", is_group=False) == []

    def test_in_group_false_fires_for_one_to_one(self) -> None:
        """m. in_group=false: 1:1 message fires."""
        e = _engine([{
            "name": "r", "trigger": {"type": "always"},
            "conditions": {"in_group": False}, "actions": [],
        }])
        assert _eval(e, "", is_group=False) == [("r", [])]

    def test_in_group_false_skips_group(self) -> None:
        """m. in_group=false: group message skips."""
        e = _engine([{
            "name": "r", "trigger": {"type": "always"},
            "conditions": {"in_group": False}, "actions": [],
        }])
        assert _eval(e, "", is_group=True, chat_guid="iMessage;+;g1") == []


class TestConditionGroupGuid:
    def test_matching_guid_fires(self) -> None:
        """n. group_guid: specific GUID fires."""
        e = _engine([{
            "name": "r", "trigger": {"type": "always"},
            "conditions": {"group_guid": "iMessage;+;mygroup"}, "actions": [],
        }])
        assert _eval(e, "", is_group=True, chat_guid="iMessage;+;mygroup") == [("r", [])]

    def test_different_guid_skips(self) -> None:
        """n. group_guid: different GUID skips."""
        e = _engine([{
            "name": "r", "trigger": {"type": "always"},
            "conditions": {"group_guid": "iMessage;+;mygroup"}, "actions": [],
        }])
        assert _eval(e, "", is_group=True, chat_guid="iMessage;+;othergroup") == []


class TestConditionsCombined:
    def test_all_conditions_must_pass(self) -> None:
        """o. Multiple conditions: all must pass for rule to fire."""
        e = _engine([{
            "name": "r", "trigger": {"type": "always"},
            "conditions": {
                "from_handles": ["+15551111111"],
                "in_group": False,
            },
            "actions": [],
        }])
        # Right handle, 1:1 → fires
        assert _eval(e, "", handle="+15551111111", is_group=False) == [("r", [])]
        # Wrong handle → skips
        assert _eval(e, "", handle="+19999999999", is_group=False) == []
        # Right handle but group → skips
        assert _eval(e, "", handle="+15551111111", is_group=True, chat_guid="g") == []


# ===========================================================================
# RulesEngine — evaluation order
# ===========================================================================

class TestEvaluationOrder:
    def test_all_matching_rules_fire(self) -> None:
        """p. Multiple matching rules all fire."""
        e = _engine([
            {"name": "r1", "trigger": {"type": "always"}, "actions": [{"type": "log"}]},
            {"name": "r2", "trigger": {"type": "always"}, "actions": [{"type": "log"}]},
        ])
        results = _eval(e, "hi")
        assert [r[0] for r in results] == ["r1", "r2"]

    def test_stop_on_match_halts_evaluation(self) -> None:
        """q. stop_on_match=true on first rule: second rule not evaluated."""
        e = _engine([
            {"name": "r1", "trigger": {"type": "always"}, "stop_on_match": True, "actions": []},
            {"name": "r2", "trigger": {"type": "always"}, "actions": []},
        ])
        results = _eval(e, "hi")
        assert [r[0] for r in results] == ["r1"]

    def test_stop_on_match_on_non_matching_rule_no_effect(self) -> None:
        """r. stop_on_match on a rule that doesn't fire has no effect."""
        e = _engine([
            {"name": "r1", "trigger": {"type": "text_exact", "pattern": "nope"}, "stop_on_match": True, "actions": []},
            {"name": "r2", "trigger": {"type": "always"}, "actions": []},
        ])
        results = _eval(e, "hi")
        assert [r[0] for r in results] == ["r2"]

    def test_empty_rules_list(self) -> None:
        """No rules → empty results, no exception."""
        e = _engine([])
        assert _eval(e, "hello") == []


# ===========================================================================
# RulesIntegration — action tests
# ===========================================================================

class TestReplyAction:
    def test_reply_sends_via_ctx(self) -> None:
        """s. reply action sends via ctx.send_text."""
        async def _go() -> None:
            integ = _integ([{
                "name": "greet",
                "trigger": {"type": "text_exact", "pattern": "hello"},
                "actions": [{"type": "reply", "text": "Hello back!"}],
            }])
            ctx = await _start(integ)
            await integ.on_inbound(FakeMsg(text="hello"))
            assert len(ctx.sent) == 1
            _target, body = ctx.sent[0]
            assert body == "Hello back!"
            await integ.stop()
        _run(_go())

    def test_reply_template_variables(self) -> None:
        """t. {handle}, {name}, {text} are interpolated in reply text."""
        async def _go() -> None:
            integ = _integ([{
                "name": "echo",
                "trigger": {"type": "always"},
                "actions": [{"type": "reply", "text": "Hi {name} ({handle})! You said: {text}"}],
            }])
            ctx = FakeCtx(_contacts={"+15551234567": "Alice"})
            await _start(integ, ctx)
            await integ.on_inbound(FakeMsg(text="test message", handle="+15551234567"))
            assert len(ctx.sent) == 1
            _t, body = ctx.sent[0]
            assert "Alice" in body
            assert "+15551234567" in body
            assert "test message" in body
            await integ.stop()
        _run(_go())

    def test_reply_to_group_uses_chat_guid(self) -> None:
        """u. Group message reply uses kind='chat' and chat_guid."""
        async def _go() -> None:
            integ = _integ([{
                "name": "grp",
                "trigger": {"type": "always"},
                "actions": [{"type": "reply", "text": "got it"}],
            }])
            ctx = await _start(integ)
            msg = FakeMsg(
                text="ping",
                is_group=True,
                chat_guid="iMessage;+;group123",
                chat_name="My Group",
            )
            await integ.on_inbound(msg)
            assert len(ctx.sent) == 1
            target, _ = ctx.sent[0]
            assert target.kind == "chat"
            assert target.value == "iMessage;+;group123"
            await integ.stop()
        _run(_go())

    def test_reply_to_one_to_one_uses_handle(self) -> None:
        """v. 1:1 message reply uses kind='handle'."""
        async def _go() -> None:
            integ = _integ([{
                "name": "r",
                "trigger": {"type": "always"},
                "actions": [{"type": "reply", "text": "pong"}],
            }])
            ctx = await _start(integ)
            await integ.on_inbound(FakeMsg(text="ping", handle="+19998887777"))
            assert len(ctx.sent) == 1
            target, _ = ctx.sent[0]
            assert target.kind == "handle"
            assert target.value == "+19998887777"
            await integ.stop()
        _run(_go())

    def test_reply_empty_text_sends_nothing(self) -> None:
        """w. Empty reply text → ctx.send_text never called."""
        async def _go() -> None:
            integ = _integ([{
                "name": "r",
                "trigger": {"type": "always"},
                "actions": [{"type": "reply", "text": ""}],
            }])
            ctx = await _start(integ)
            await integ.on_inbound(FakeMsg(text="ping"))
            assert ctx.sent == []
            await integ.stop()
        _run(_go())


class TestWebhookAction:
    def test_webhook_posts_json_context(self) -> None:
        """x. webhook action POSTs to configured URL with message context."""
        async def _go() -> None:
            integ = _integ([{
                "name": "hook",
                "trigger": {"type": "always"},
                "actions": [{"type": "webhook", "url": "https://example.com/hook"}],
            }])
            ctx = await _start(integ)

            mock_resp = MagicMock()
            mock_resp.status_code = 200

            with patch("integrations.rules._HTTPX_AVAILABLE", True), \
                 patch("integrations.rules._httpx") as mock_httpx:
                mock_client = AsyncMock()
                mock_client.request = AsyncMock(return_value=mock_resp)
                mock_httpx.AsyncClient.return_value = mock_client

                await integ.on_inbound(FakeMsg(text="trigger me", handle="+15550000001"))

            mock_client.request.assert_awaited_once()
            call_kwargs = mock_client.request.call_args
            assert call_kwargs.args[0] == "POST"
            assert call_kwargs.args[1] == "https://example.com/hook"
            payload = call_kwargs.kwargs["json"]
            assert payload["handle"] == "+15550000001"
            assert payload["text"] == "trigger me"
            assert payload["rule"] == "hook"

            await integ.stop()
        _run(_go())

    def test_webhook_http_error_does_not_crash(self) -> None:
        """y. Webhook returns HTTP 4xx → logs warning, no exception."""
        async def _go() -> None:
            integ = _integ([{
                "name": "hook",
                "trigger": {"type": "always"},
                "actions": [{"type": "webhook", "url": "https://example.com/hook"}],
            }])
            await _start(integ)

            mock_resp = MagicMock()
            mock_resp.status_code = 403
            mock_resp.text = "Forbidden"

            with patch("integrations.rules._HTTPX_AVAILABLE", True), \
                 patch("integrations.rules._httpx") as mock_httpx:
                mock_client = AsyncMock()
                mock_client.request = AsyncMock(return_value=mock_resp)
                mock_httpx.AsyncClient.return_value = mock_client
                await integ.on_inbound(FakeMsg(text="ping"))  # must not raise

            await integ.stop()
        _run(_go())

    def test_webhook_missing_url_does_not_crash(self) -> None:
        """z. Webhook action with no URL → logs warning, no crash."""
        async def _go() -> None:
            integ = _integ([{
                "name": "hook",
                "trigger": {"type": "always"},
                "actions": [{"type": "webhook"}],  # no url
            }])
            await _start(integ)
            await integ.on_inbound(FakeMsg(text="ping"))  # must not raise
            await integ.stop()
        _run(_go())


class TestLogAction:
    def test_log_action_emits_log_line(self, caplog: pytest.LogCaptureFixture) -> None:
        """aa. log action emits a log line including rule name."""
        import logging as _logging
        async def _go() -> None:
            integ = _integ([{
                "name": "audit",
                "trigger": {"type": "always"},
                "actions": [{"type": "log", "level": "info", "message": "fired for {handle}"}],
            }])
            await _start(integ)
            with caplog.at_level(_logging.INFO, logger="integrations.rules"):
                await integ.on_inbound(FakeMsg(text="test", handle="+15559876543"))
            await integ.stop()
        _run(_go())
        assert any("audit" in r.message and "+15559876543" in r.message for r in caplog.records)

    def test_log_action_rule_template_variable(self, caplog: pytest.LogCaptureFixture) -> None:
        """aa (variant). {rule} template variable works in log message."""
        import logging as _logging
        async def _go() -> None:
            integ = _integ([{
                "name": "myrule",
                "trigger": {"type": "always"},
                "actions": [{"type": "log", "message": "rule={rule}"}],
            }])
            await _start(integ)
            with caplog.at_level(_logging.INFO, logger="integrations.rules"):
                await integ.on_inbound(FakeMsg(text="x"))
            await integ.stop()
        _run(_go())
        assert any("myrule" in r.message for r in caplog.records)


class TestUnknownAndErrorHandling:
    def test_unknown_action_type_does_not_crash(self) -> None:
        """bb. Unknown action type → warning logged, no exception."""
        async def _go() -> None:
            integ = _integ([{
                "name": "r",
                "trigger": {"type": "always"},
                "actions": [{"type": "teleport"}],
            }])
            await _start(integ)
            await integ.on_inbound(FakeMsg(text="test"))  # must not raise
            await integ.stop()
        _run(_go())

    def test_action_exception_does_not_stop_subsequent_actions(self) -> None:
        """cc. Exception in one action → warning; next action still runs."""
        async def _go() -> None:
            integ = _integ([{
                "name": "r",
                "trigger": {"type": "always"},
                "actions": [
                    {"type": "reply", "text": "first"},
                    {"type": "reply", "text": "second"},
                ],
            }])
            ctx = await _start(integ)

            # Patch send_text to raise on first call only
            call_count = [0]
            original = ctx.send_text

            async def patched_send(target: Any, body: str) -> Any:
                call_count[0] += 1
                if call_count[0] == 1:
                    raise RuntimeError("simulated failure")
                return await original(target, body)

            ctx.send_text = patched_send  # type: ignore[method-assign]

            await integ.on_inbound(FakeMsg(text="ping"))
            # Second action must still run despite first raising
            assert len(ctx.sent) == 1
            assert ctx.sent[0][1] == "second"

            await integ.stop()
        _run(_go())


# ===========================================================================
# RulesIntegration — lifecycle tests
# ===========================================================================

class TestLifecycle:
    def test_on_inbound_before_start_is_no_op(self) -> None:
        """dd. on_inbound before start() is a silent no-op (ctx=None)."""
        async def _go() -> None:
            integ = _integ([{
                "name": "r", "trigger": {"type": "always"},
                "actions": [{"type": "reply", "text": "hi"}],
            }])
            await integ.on_inbound(FakeMsg(text="ping"))  # must not raise
        _run(_go())

    def test_on_inbound_after_stop_is_no_op(self) -> None:
        """ee. on_inbound after stop() is a silent no-op."""
        async def _go() -> None:
            integ = _integ([{
                "name": "r", "trigger": {"type": "always"},
                "actions": [{"type": "reply", "text": "hi"}],
            }])
            ctx = await _start(integ)
            await integ.stop()
            await integ.on_inbound(FakeMsg(text="ping"))  # must not raise
            assert ctx.sent == []  # nothing sent after stop
        _run(_go())

    def test_double_stop_is_idempotent(self) -> None:
        """Calling stop() twice does not raise."""
        async def _go() -> None:
            integ = _integ([])
            await _start(integ)
            await integ.stop()
            await integ.stop()  # must not raise
        _run(_go())

    def test_no_rules_starts_fine(self) -> None:
        """Integration with empty rules list starts and handles messages cleanly."""
        async def _go() -> None:
            integ = RulesIntegration({"enabled": True})
            ctx = await _start(integ)
            await integ.on_inbound(FakeMsg(text="anything"))
            assert ctx.sent == []
            await integ.stop()
        _run(_go())


# ===========================================================================
# _render helper
# ===========================================================================

class TestRender:
    def test_known_keys_substituted(self) -> None:
        assert _render("Hi {name}!", name="Alice") == "Hi Alice!"

    def test_missing_key_becomes_empty_string(self) -> None:
        assert _render("Hi {name}!") == "Hi !"

    def test_no_placeholders(self) -> None:
        assert _render("plain text") == "plain text"

    def test_multiple_variables(self) -> None:
        result = _render("{handle} → {text}", handle="+1", text="hello")
        assert result == "+1 → hello"
