"""Tests for anti-spam / send-guardrail features in chat_send.py.

Strategy
--------
- Import anti-spam primitives directly from chat_send.
- Reset module-level singletons between tests using their _reset() helpers.
- Patch file I/O (audit log, state file) and ntfy calls to avoid side-effects.
- For BridgeContextImpl.spam_whitelist: verify it returns a frozenset and
  that external mutations don't propagate back into the context.
"""
from __future__ import annotations

import json
import time
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_singletons():
    """Reset all module-level anti-spam singletons to a clean state."""
    import chat_send as cs
    cs._rate_bucket._set_tokens(float(cs._RATE_LIMIT_COUNT))
    cs._broadcast._reset()
    cs._escalation._reset()


# ---------------------------------------------------------------------------
# _normalize_text
# ---------------------------------------------------------------------------

class TestNormalizeText:
    def setup_method(self):
        from chat_send import _normalize_text
        self._norm = _normalize_text

    def test_lowercases(self):
        assert self._norm("Hello World", frozenset()) == "hello world"

    def test_strips_punctuation(self):
        assert self._norm("Hello, World!", frozenset()) == "hello world"

    def test_collapses_whitespace(self):
        assert self._norm("Hello   World", frozenset()) == "hello world"

    def test_strips_whitelist_name(self):
        result = self._norm("Hi Alice, how are you?", frozenset({"alice"}))
        assert "alice" not in result

    def test_strips_multiple_names(self):
        result = self._norm("Hey Bob and Alice!", frozenset({"alice", "bob"}))
        assert "alice" not in result
        assert "bob" not in result

    def test_empty_whitelist(self):
        assert self._norm("hello world", frozenset()) == "hello world"

    def test_empty_text(self):
        assert self._norm("", frozenset()) == ""


# ---------------------------------------------------------------------------
# _TokenBucket (rate limiter)
# ---------------------------------------------------------------------------

class TestTokenBucket:
    def setup_method(self):
        import chat_send as cs
        _reset_singletons()

    def test_allows_up_to_limit(self):
        import chat_send as cs
        bucket = cs._TokenBucket(rate=5, window_s=60.0)
        for _ in range(5):
            assert bucket.consume() is True

    def test_blocks_after_limit(self):
        import chat_send as cs
        bucket = cs._TokenBucket(rate=5, window_s=60.0)
        for _ in range(5):
            bucket.consume()
        assert bucket.consume() is False

    def test_refills_over_time(self):
        import chat_send as cs
        bucket = cs._TokenBucket(rate=10, window_s=1.0)
        # Drain all tokens
        for _ in range(10):
            bucket.consume()
        assert bucket.consume() is False
        # Simulate time passing by nudging _last back
        with bucket._lock:
            bucket._last -= 1.5  # 1.5 window_s elapsed
        assert bucket.consume() is True


# ---------------------------------------------------------------------------
# check_send_guard — rate limit
# ---------------------------------------------------------------------------

class TestCheckSendGuardRateLimit:
    def setup_method(self):
        _reset_singletons()

    def _patched(self, cs):
        """Context manager that suppresses everything except rate limiting."""
        return (
            patch.object(cs, "_write_audit"),
            patch.object(cs, "_get_spam_whitelist", return_value=frozenset()),
            # Stub broadcast so it never triggers block; return 0 unique recipients
            patch.object(cs._broadcast, "record", return_value=0),
            patch.object(cs, "_ntfy_warning"),
        )

    def test_allows_20_messages(self):
        import chat_send as cs
        with patch.object(cs, "_write_audit"), \
             patch.object(cs, "_get_spam_whitelist", return_value=frozenset()), \
             patch.object(cs._broadcast, "record", return_value=0), \
             patch.object(cs, "_ntfy_warning"):
            for i in range(20):
                cs.check_send_guard(f"+1555000{i:04d}", "hello", "test")

    def test_blocks_at_21(self):
        import chat_send as cs
        with patch.object(cs, "_write_audit"), \
             patch.object(cs, "_get_spam_whitelist", return_value=frozenset()), \
             patch.object(cs._broadcast, "record", return_value=0), \
             patch.object(cs, "_ntfy_warning"):
            for i in range(20):
                cs.check_send_guard(f"+1555000{i:04d}", "hello", "test")
            with pytest.raises(cs.RateLimitError):
                cs.check_send_guard("+15550099", "hello", "test")

    def test_error_message_is_descriptive(self):
        import chat_send as cs
        cs._rate_bucket._set_tokens(0.0)
        with pytest.raises(cs.RateLimitError, match="rate limit"):
            cs.check_send_guard("+15550001", "hello", "test")


# ---------------------------------------------------------------------------
# check_send_guard — broadcast detection (warning at 3)
# ---------------------------------------------------------------------------

class TestCheckSendGuardBroadcastWarning:
    def setup_method(self):
        _reset_singletons()

    def test_warning_sent_at_3_unique_recipients(self):
        import chat_send as cs
        warnings = []
        with patch.object(cs, "_write_audit"), \
             patch.object(cs, "_get_spam_whitelist", return_value=frozenset()), \
             patch.object(cs, "_ntfy_warning", side_effect=lambda m: warnings.append(m)):
            cs.check_send_guard("+15550001", "same message", "test")
            cs.check_send_guard("+15550002", "same message", "test")
            assert len(warnings) == 0
            cs.check_send_guard("+15550003", "same message", "test")
            assert len(warnings) == 1
            assert "3" in warnings[0]

    def test_no_warning_same_recipient(self):
        import chat_send as cs
        warnings = []
        with patch.object(cs, "_write_audit"), \
             patch.object(cs, "_get_spam_whitelist", return_value=frozenset()), \
             patch.object(cs, "_ntfy_warning", side_effect=lambda m: warnings.append(m)):
            for _ in range(10):
                cs.check_send_guard("+15550001", "same message", "test")
            assert len(warnings) == 0

    def test_different_messages_no_warning(self):
        import chat_send as cs
        warnings = []
        with patch.object(cs, "_write_audit"), \
             patch.object(cs, "_get_spam_whitelist", return_value=frozenset()), \
             patch.object(cs, "_ntfy_warning", side_effect=lambda m: warnings.append(m)):
            cs.check_send_guard("+15550001", "msg alpha", "test")
            cs.check_send_guard("+15550002", "msg beta", "test")
            cs.check_send_guard("+15550003", "msg gamma", "test")
            assert len(warnings) == 0


# ---------------------------------------------------------------------------
# check_send_guard — broadcast detection (timeout escalation at 5)
# ---------------------------------------------------------------------------

class TestCheckSendGuardBroadcastBlock:
    def setup_method(self):
        _reset_singletons()

    def _send_n(self, cs, n: int, base_handle: str = "+1555000") -> None:
        """Send to n unique recipients with the same message."""
        with patch.object(cs, "_write_audit"), \
             patch.object(cs, "_get_spam_whitelist", return_value=frozenset()), \
             patch.object(cs, "_ntfy_warning"):
            for i in range(n):
                try:
                    cs.check_send_guard(f"{base_handle}{i:04d}", "broadcast msg", "test")
                except cs.BroadcastBlockedError:
                    pass

    def test_blocks_at_5_unique_recipients(self):
        import chat_send as cs
        # Send to 4 — should not block yet
        with patch.object(cs, "_write_audit"), \
             patch.object(cs, "_get_spam_whitelist", return_value=frozenset()), \
             patch.object(cs, "_ntfy_warning"):
            for i in range(4):
                cs.check_send_guard(f"+1555000{i}", "broadcast msg", "test")
            # 5th should raise
            with pytest.raises(cs.BroadcastBlockedError):
                cs.check_send_guard("+15550099", "broadcast msg", "test")

    def test_escalation_first_step_is_5min(self):
        import chat_send as cs
        # Trigger block
        with patch.object(cs, "_write_audit"), \
             patch.object(cs, "_get_spam_whitelist", return_value=frozenset()), \
             patch.object(cs, "_ntfy_warning"):
            for i in range(4):
                cs.check_send_guard(f"+1555000{i}", "same text", "test")
            try:
                cs.check_send_guard("+15550099", "same text", "test")
            except cs.BroadcastBlockedError as exc:
                assert exc.retry_after is not None
                assert 4 * 60 < exc.retry_after <= 5 * 60 + 1

    def test_escalation_persists_across_reset(self, tmp_path):
        """Escalation state survives a re-instantiation of _EscalationState."""
        import chat_send as cs
        # Write state file with a known escalation
        now_wall = time.time()
        state_file = tmp_path / "state.json"
        fake_hash = "abc123"
        state_file.write_text(json.dumps({
            fake_hash: {"level": 0, "until_wall": now_wall + 300}
        }))
        with patch.object(cs, "_STATE_FILE", state_file):
            fresh = cs._EscalationState()
            blocked, remaining = fresh.check_blocked(fake_hash)
        assert blocked is True
        assert remaining is not None and remaining > 0

    def test_subsequent_sends_blocked(self):
        import chat_send as cs
        with patch.object(cs, "_write_audit"), \
             patch.object(cs, "_get_spam_whitelist", return_value=frozenset()), \
             patch.object(cs, "_ntfy_warning"):
            # Trigger initial escalation
            for i in range(5):
                try:
                    cs.check_send_guard(f"+1555000{i}", "broadcast msg", "test")
                except cs.BroadcastBlockedError:
                    pass
            # Next attempt should still be blocked
            with pytest.raises(cs.BroadcastBlockedError):
                cs.check_send_guard("+15550099", "broadcast msg", "test")


# ---------------------------------------------------------------------------
# check_send_guard — audit log
# ---------------------------------------------------------------------------

class TestCheckSendGuardAuditLog:
    def setup_method(self):
        _reset_singletons()

    def test_audit_log_written(self, tmp_path):
        import chat_send as cs
        audit_file = tmp_path / "send_audit.log"
        with patch.object(cs, "_AUDIT_LOG", audit_file), \
             patch.object(cs, "_get_spam_whitelist", return_value=frozenset()):
            cs.check_send_guard("+15550001", "hello audit", "web")
        lines = audit_file.read_text().splitlines()
        assert len(lines) == 1
        parts = lines[0].split("\t")
        assert len(parts) == 4
        ts, recipient, source, h = parts
        assert "T" in ts  # ISO timestamp
        assert recipient == "+15550001"
        assert source == "web"
        assert len(h) == 64  # SHA-256 hex

    def test_audit_log_appends(self, tmp_path):
        import chat_send as cs
        audit_file = tmp_path / "send_audit.log"
        with patch.object(cs, "_AUDIT_LOG", audit_file), \
             patch.object(cs, "_get_spam_whitelist", return_value=frozenset()):
            cs.check_send_guard("+15550001", "msg one", "web")
            cs.check_send_guard("+15550002", "msg two", "web")
        lines = audit_file.read_text().splitlines()
        assert len(lines) == 2

    def test_audit_log_source_label(self, tmp_path):
        import chat_send as cs
        audit_file = tmp_path / "send_audit.log"
        with patch.object(cs, "_AUDIT_LOG", audit_file), \
             patch.object(cs, "_get_spam_whitelist", return_value=frozenset()):
            cs.check_send_guard("+15550001", "hi", "my_plugin")
        parts = audit_file.read_text().strip().split("\t")
        assert parts[2] == "my_plugin"


# ---------------------------------------------------------------------------
# BridgeContextImpl.spam_whitelist — read-only from plugin context
# ---------------------------------------------------------------------------

class TestBridgeContextSpamWhitelist:
    def test_returns_frozenset(self):
        from bridge import BridgeContextImpl
        ctx = BridgeContextImpl(contacts={}, chatdb=None)
        assert isinstance(ctx.spam_whitelist, frozenset)

    def test_mutation_of_returned_value_not_stored(self):
        """Mutating the returned frozenset raises (it's immutable by design)."""
        from bridge import BridgeContextImpl
        ctx = BridgeContextImpl(contacts={}, chatdb=None)
        wl = ctx.spam_whitelist
        with pytest.raises((AttributeError, TypeError)):
            wl.add("hacker")  # type: ignore[attr-defined]

    def test_returns_names_from_config(self):
        import bridge as b
        from bridge import BridgeContextImpl
        fake_cfg = {"web": {"spam_whitelist": ["Alice", "Bob"]}}
        with patch.object(b, "CFG", fake_cfg):
            ctx = BridgeContextImpl(contacts={}, chatdb=None)
            wl = ctx.spam_whitelist
        assert "Alice" in wl
        assert "Bob" in wl

    def test_relay_scope_returns_frozensets(self):
        """relay_scope() must return frozensets so plugins can't mutate them."""
        from bridge import BridgeContextImpl
        ctx = BridgeContextImpl(contacts={}, chatdb=None)
        scope = ctx.relay_scope()
        for key in ("self", "handles", "groups"):
            assert isinstance(scope[key], frozenset), f"{key} is not frozenset"
