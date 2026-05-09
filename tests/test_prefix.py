"""Tests for prefix.py — the relay prefix format/parse roundtrip.

The prefix shape is the routing contract between iMessage-inbound relay and
Telegram-outbound reply: whatever handle/chat information the bridge embeds
in the outbound text must survive a round trip through Telegram's plain-text
message so parse_reply_target can extract a valid SendTarget.

  1:1:    "From <name> (<handle>): <body>"
  group:  "[<chat_name>] From <name> (<handle>): <body>"
"""
import pytest
from prefix import ReplyTarget, format_inbound, parse_reply_target


# ---------------------------------------------------------------------------
# format_inbound
# ---------------------------------------------------------------------------

class TestFormatInbound:
    def test_with_display_name(self):
        assert format_inbound("+15551234567", "Alice", "hey") == \
            "From Alice (+15551234567): hey"

    def test_without_display_name_uses_handle(self):
        # name = display_name or handle → handle becomes the name
        assert format_inbound("+15551234567", None, "hey") == \
            "From +15551234567 (+15551234567): hey"

    def test_empty_display_name_uses_handle(self):
        assert format_inbound("+15551234567", "", "hey") == \
            "From +15551234567 (+15551234567): hey"

    def test_group_prefix(self):
        result = format_inbound("+15551234567", "Alice", "hey", chat_name="Family")
        assert result == "[Family] From Alice (+15551234567): hey"

    def test_no_chat_name_no_bracket(self):
        result = format_inbound("+15551234567", "Alice", "hey", chat_name=None)
        assert "[" not in result

    def test_body_preserved_verbatim(self):
        body = "line1\nline2\nline3"
        result = format_inbound("+1555", "X", body)
        assert body in result

    def test_email_handle(self):
        result = format_inbound("alice@example.com", "Alice", "hi")
        assert "alice@example.com" in result


# ---------------------------------------------------------------------------
# parse_reply_target
# ---------------------------------------------------------------------------

class TestParseReplyTarget:
    def test_1to1_basic(self):
        text = "From Alice (+15551234567): hello world"
        rt = parse_reply_target(text)
        assert rt is not None
        assert rt.handle == "+15551234567"
        assert rt.chat_name == ""
        assert not rt.is_group

    def test_group_basic(self):
        text = "[Family] From Alice (+15551234567): hello"
        rt = parse_reply_target(text)
        assert rt is not None
        assert rt.handle == "+15551234567"
        assert rt.chat_name == "Family"
        assert rt.is_group

    def test_group_with_spaces_in_name(self):
        text = "[My Family Chat] From Bob (bob@example.com): yo"
        rt = parse_reply_target(text)
        assert rt is not None
        assert rt.chat_name == "My Family Chat"
        assert rt.handle == "bob@example.com"

    def test_not_a_relay_returns_none(self):
        assert parse_reply_target("✓ sent → Alice") is None
        assert parse_reply_target("muted relay until 2026-01-01") is None
        assert parse_reply_target("No target. Reply to a relayed message.") is None

    def test_empty_string_returns_none(self):
        assert parse_reply_target("") is None

    def test_none_safe(self):
        # The implementation does `replied_text or ""` so None is safe.
        assert parse_reply_target(None) is None

    def test_bot_ack_not_parsed(self):
        # Delivery acks look like "✓ delivered → Alice" — not a relay prefix.
        assert parse_reply_target("✓ delivered → Alice (+15551234567)") is None

    def test_multiline_body_parsed(self):
        body = "hello\nworld"
        text = format_inbound("+1555", "X", body)
        rt = parse_reply_target(text)
        assert rt is not None
        assert rt.handle == "+1555"


# ---------------------------------------------------------------------------
# roundtrip: format_inbound → parse_reply_target
# ---------------------------------------------------------------------------

class TestRoundtrip:
    def test_1to1_roundtrip(self):
        text = format_inbound("+15551234567", "Alice", "hello world")
        rt = parse_reply_target(text)
        assert rt is not None
        assert rt.handle == "+15551234567"
        assert not rt.is_group

    def test_group_roundtrip(self):
        text = format_inbound("+15551234567", "Alice", "hello", chat_name="Family Chat")
        rt = parse_reply_target(text)
        assert rt is not None
        assert rt.handle == "+15551234567"
        assert rt.chat_name == "Family Chat"
        assert rt.is_group

    def test_email_handle_roundtrip(self):
        text = format_inbound("alice@example.com", "Alice", "hi")
        rt = parse_reply_target(text)
        assert rt is not None
        assert rt.handle == "alice@example.com"

    def test_no_name_roundtrip(self):
        text = format_inbound("+1555", None, "hey")
        rt = parse_reply_target(text)
        assert rt is not None
        assert rt.handle == "+1555"

    def test_group_roundtrip_parentheses_in_name(self):
        # Group names have brackets replaced with parens to avoid parser
        # confusion; round-trip through that transformation.
        chat = "Family (Smith)"
        text = format_inbound("+1555", "Alice", "hi", chat_name=chat)
        rt = parse_reply_target(text)
        assert rt is not None
        assert rt.chat_name == chat


# ---------------------------------------------------------------------------
# ReplyTarget dataclass
# ---------------------------------------------------------------------------

class TestReplyTarget:
    def test_is_group_true(self):
        rt = ReplyTarget(handle="+1555", chat_name="Fam")
        assert rt.is_group

    def test_is_group_false(self):
        rt = ReplyTarget(handle="+1555", chat_name="")
        assert not rt.is_group

    def test_is_group_default(self):
        rt = ReplyTarget(handle="+1555")
        assert not rt.is_group
