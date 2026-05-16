"""Tests for anti-spam / send-guardrail features in chat_send.py.

Strategy
--------
- Import anti-spam primitives directly from chat_send.
- Reset module-level singletons between tests using their _reset() helpers.
- Patch file I/O (audit log, fuse/lockout state files) to avoid side-effects.
- Global fuse (_FuseState) is the new escalation mechanism; per-hash
  _EscalationState is gone.
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
    cs._fuse._reset()


# ---------------------------------------------------------------------------
# _normalize_text  (no whitelist stripping anymore)
# ---------------------------------------------------------------------------

class TestNormalizeText:
    def setup_method(self):
        from chat_send import _normalize_text
        self._norm = _normalize_text

    def test_lowercases(self):
        assert self._norm("Hello World") == "hello world"

    def test_strips_punctuation(self):
        assert self._norm("Hello, World!") == "hello world"

    def test_collapses_whitespace(self):
        assert self._norm("Hello   World") == "hello world"

    def test_empty_text(self):
        assert self._norm("") == ""

    def test_numbers_preserved(self):
        result = self._norm("Meeting at 3pm")
        assert "3" in result
        assert "pm" in result


# ---------------------------------------------------------------------------
# _TokenBucket (rate limiter)
# ---------------------------------------------------------------------------

class TestTokenBucket:
    def setup_method(self):
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
        for _ in range(10):
            bucket.consume()
        assert bucket.consume() is False
        with bucket._lock:
            bucket._last -= 1.5
        assert bucket.consume() is True


# ---------------------------------------------------------------------------
# _FuseState — global escalating fuse
# ---------------------------------------------------------------------------

class TestFuseState:
    def setup_method(self):
        _reset_singletons()

    def test_initial_state_not_locked(self):
        import chat_send as cs
        cs._fuse.check()  # should not raise

    def test_trigger_step1_returns_5min(self):
        import chat_send as cs
        cooldown = cs._fuse.trigger()
        assert cooldown == 5 * 60

    def test_trigger_step1_blocks_subsequent_check(self):
        import chat_send as cs
        cs._fuse.trigger()
        with pytest.raises(cs.BroadcastBlockedError) as exc_info:
            cs._fuse.check()
        assert exc_info.value.retry_after is not None
        assert exc_info.value.retry_after > 0

    def test_trigger_escalation_steps(self):
        """Sequential triggers (cold, >1h apart) must follow the 6-step chain."""
        import chat_send as cs
        expected = [5 * 60, 30 * 60, 2 * 3600, 24 * 3600, 24 * 3600, None]
        # Simulate each trigger happening > 1h after the previous
        for i, exp_cooldown in enumerate(expected):
            cs._fuse._reset()
            # Prime the fuse to step i, then do one more cold trigger
            cs._fuse._step = i
            cs._fuse._last_trigger = None  # cold (no rapid flag)
            cs._fuse._cooldown_until = None
            result = cs._fuse.trigger()
            assert result == exp_cooldown, f"step {i+1}: expected {exp_cooldown}, got {result}"

    def test_rapid_retrigger_skips_step(self):
        """A second trigger within 1 hour must skip an extra step."""
        import chat_send as cs
        # First trigger: cold → step 1
        cs._fuse.trigger()
        assert cs._fuse._step == 1
        # Second trigger within 1h → increment by 2 → step 3
        result = cs._fuse.trigger()
        assert cs._fuse._step == 3
        assert result == 2 * 3600  # step 3 = 2 hours

    def test_step6_is_permanent(self):
        import chat_send as cs
        cs._fuse._step = 5
        cs._fuse._last_trigger = None
        result = cs._fuse.trigger()
        assert result is None
        assert cs._fuse._step == 6
        with pytest.raises(cs.BroadcastBlockedError) as exc_info:
            cs._fuse.check()
        assert exc_info.value.retry_after is None

    def test_status_inactive(self):
        import chat_send as cs
        s = cs._fuse.status()
        assert s["locked"] is False
        assert s["step"] == 0
        assert s["cooldown_remaining_s"] is None
        assert s["unlock_code"] is None

    def test_status_while_locked(self):
        import chat_send as cs
        cs._fuse.trigger()
        s = cs._fuse.status()
        assert s["locked"] is True
        assert s["step"] == 1
        assert s["cooldown_remaining_s"] is not None
        assert s["cooldown_remaining_s"] > 0

    def test_persistence_across_restart(self, tmp_path):
        """Fuse state persists across _FuseState re-instantiation."""
        import chat_send as cs
        fuse_file = tmp_path / "fuse_state.json"
        state = {
            "step": 2,
            "cooldown_until": time.time() + 1800,
            "last_trigger": time.time() - 60,
        }
        fuse_file.write_text(json.dumps(state))
        with patch.object(cs, "_FUSE_FILE", fuse_file):
            fresh = cs._FuseState()
            with pytest.raises(cs.BroadcastBlockedError):
                fresh.check()

    def test_unlock_code_written_on_step4(self, tmp_path):
        """Unlock code must be written to lockout.json on step 4+."""
        import chat_send as cs
        lockout_file = tmp_path / "lockout.json"
        fuse_file = tmp_path / "fuse_state.json"
        cs._fuse._step = 3  # next trigger → step 4
        cs._fuse._last_trigger = None
        with patch.object(cs, "_LOCKOUT_FILE", lockout_file), \
             patch.object(cs, "_FUSE_FILE", fuse_file):
            cs._fuse.trigger()
        assert lockout_file.exists()
        data = json.loads(lockout_file.read_text())
        assert "unlock_code" in data
        assert data["unlock_code"].startswith("CW-")

    def test_unlock_code_format(self):
        """Unlock code must be CW-XXXX-YYYY (uppercase hex)."""
        import chat_send as cs
        with patch.object(cs, "_get_machine_id", return_value="test-machine"), \
             patch.object(cs, "_get_first_run_ts", return_value="12345"):
            code = cs._generate_unlock_code()
        assert code.startswith("CW-")
        parts = code.split("-")
        assert len(parts) == 3
        assert len(parts[1]) == 4
        assert len(parts[2]) == 4
        assert parts[1] == parts[1].upper()
        assert parts[2] == parts[2].upper()


# ---------------------------------------------------------------------------
# check_send_guard — rate limit
# ---------------------------------------------------------------------------

class TestCheckSendGuardRateLimit:
    def setup_method(self):
        _reset_singletons()

    def test_allows_20_messages(self):
        import chat_send as cs
        with patch.object(cs, "_write_audit"), \
             patch.object(cs._broadcast, "record", return_value=0):
            for i in range(20):
                cs.check_send_guard(f"+1555000{i:04d}", "hello", "test")

    def test_blocks_at_21(self):
        import chat_send as cs
        with patch.object(cs, "_write_audit"), \
             patch.object(cs._broadcast, "record", return_value=0):
            for i in range(20):
                cs.check_send_guard(f"+1555000{i:04d}", "hello", "test")
            with pytest.raises(cs.RateLimitError):
                cs.check_send_guard("+15550099", "hello", "test")

    def test_error_message_is_descriptive(self):
        import chat_send as cs
        cs._rate_bucket._set_tokens(0.0)
        with pytest.raises(cs.RateLimitError, match="rate limit"):
            cs.check_send_guard("+15550001", "hello", "test")

    def test_fuse_blocks_before_rate_limit(self):
        """Active fuse should block before consuming a rate limit token."""
        import chat_send as cs
        cs._fuse.trigger()  # activate fuse step 1
        cs._rate_bucket._set_tokens(float(cs._RATE_LIMIT_COUNT))  # full bucket
        with pytest.raises(cs.BroadcastBlockedError):
            cs.check_send_guard("+15550001", "hello", "test")
        # Token bucket should be untouched
        assert cs._rate_bucket._tokens >= cs._RATE_LIMIT_COUNT


# ---------------------------------------------------------------------------
# check_send_guard — broadcast detection (warning at 3)
# ---------------------------------------------------------------------------

class TestCheckSendGuardBroadcastWarning:
    def setup_method(self):
        _reset_singletons()

    def test_warning_sent_at_3_unique_recipients(self):
        import chat_send as cs
        with patch.object(cs, "_write_audit"):
            cs.check_send_guard("+15550001", "same message", "test")
            cs.check_send_guard("+15550002", "same message", "test")
            # 3rd unique recipient triggers log warning but no exception
            cs.check_send_guard("+15550003", "same message", "test")

    def test_no_warning_same_recipient(self):
        import chat_send as cs
        with patch.object(cs, "_write_audit"):
            for _ in range(10):
                cs.check_send_guard("+15550001", "same message", "test")

    def test_different_messages_no_warning(self):
        import chat_send as cs
        with patch.object(cs, "_write_audit"):
            cs.check_send_guard("+15550001", "msg alpha", "test")
            cs.check_send_guard("+15550002", "msg beta", "test")
            cs.check_send_guard("+15550003", "msg gamma", "test")


# ---------------------------------------------------------------------------
# check_send_guard — broadcast detection trips the global fuse
# ---------------------------------------------------------------------------

class TestCheckSendGuardBroadcastBlock:
    def setup_method(self):
        _reset_singletons()

    def _send_to_n(self, cs, n: int, base: str = "+1555000") -> None:
        """Send the same message to n unique recipients."""
        with patch.object(cs, "_write_audit"):
            for i in range(n):
                try:
                    cs.check_send_guard(f"{base}{i:04d}", "broadcast msg", "test")
                except (cs.BroadcastBlockedError, cs.RateLimitError):
                    pass

    def test_blocks_at_5_unique_recipients(self):
        import chat_send as cs
        with patch.object(cs, "_write_audit"):
            for i in range(4):
                cs.check_send_guard(f"+1555000{i}", "broadcast msg", "test")
            with pytest.raises(cs.BroadcastBlockedError):
                cs.check_send_guard("+15550099", "broadcast msg", "test")

    def test_fuse_trips_to_step1_on_first_block(self):
        import chat_send as cs
        with patch.object(cs, "_write_audit"):
            for i in range(4):
                cs.check_send_guard(f"+1555000{i}", "same text", "test")
            try:
                cs.check_send_guard("+15550099", "same text", "test")
            except cs.BroadcastBlockedError as exc:
                assert exc.retry_after is not None
                assert 4 * 60 < exc.retry_after <= 5 * 60 + 1

    def test_fuse_is_global_blocks_different_messages(self):
        """After fuse trips, even unrelated messages are blocked."""
        import chat_send as cs
        # Trip the fuse
        self._send_to_n(cs, 5)
        # Try to send a completely different message
        with pytest.raises(cs.BroadcastBlockedError):
            cs.check_send_guard("+15550999", "totally different message", "test")

    def test_subsequent_sends_blocked(self):
        import chat_send as cs
        self._send_to_n(cs, 5)
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
        with patch.object(cs, "_AUDIT_LOG", audit_file):
            cs.check_send_guard("+15550001", "hello audit", "web")
        lines = audit_file.read_text().splitlines()
        assert len(lines) == 1
        parts = lines[0].split("\t")
        assert len(parts) == 4
        ts, recipient, source, h = parts
        assert "T" in ts
        assert recipient == "+15550001"
        assert source == "web"
        assert len(h) == 64  # SHA-256 hex

    def test_audit_log_appends(self, tmp_path):
        import chat_send as cs
        audit_file = tmp_path / "send_audit.log"
        with patch.object(cs, "_AUDIT_LOG", audit_file):
            cs.check_send_guard("+15550001", "msg one", "web")
            cs.check_send_guard("+15550002", "msg two", "web")
        lines = audit_file.read_text().splitlines()
        assert len(lines) == 2

    def test_audit_log_source_label(self, tmp_path):
        import chat_send as cs
        audit_file = tmp_path / "send_audit.log"
        with patch.object(cs, "_AUDIT_LOG", audit_file):
            cs.check_send_guard("+15550001", "hi", "my_plugin")
        parts = audit_file.read_text().strip().split("\t")
        assert parts[2] == "my_plugin"


# ---------------------------------------------------------------------------
# validate_and_reset_fuse — HMAC unlock code validation
# ---------------------------------------------------------------------------

class TestValidateAndResetFuse:
    def setup_method(self):
        _reset_singletons()

    def _trip_to_step(self, cs, target: int, fuse_file, lockout_file) -> None:
        """Trip the fuse enough times to reach target step."""
        with (
            patch.object(cs, "_FUSE_FILE", fuse_file),
            patch.object(cs, "_LOCKOUT_FILE", lockout_file),
        ):
            for _ in range(target):
                cs._fuse.trigger()

    def test_compute_unlock_response_format(self):
        """Generated unlock code has UL-XXXX-XXXX shape."""
        import chat_send as cs
        result = cs._compute_unlock_response("CW-ABCD-1234", "secret")
        assert result.startswith("UL-")
        parts = result.split("-")
        assert len(parts) == 3
        assert len(parts[1]) == 4
        assert len(parts[2]) == 4

    def test_compute_unlock_response_deterministic(self):
        """Same inputs always produce the same code."""
        import chat_send as cs
        r1 = cs._compute_unlock_response("CW-ABCD-1234", "mysecret")
        r2 = cs._compute_unlock_response("CW-ABCD-1234", "mysecret")
        assert r1 == r2

    def test_compute_unlock_response_differs_on_different_cw_code(self):
        import chat_send as cs
        r1 = cs._compute_unlock_response("CW-AAAA-1111", "s")
        r2 = cs._compute_unlock_response("CW-BBBB-2222", "s")
        assert r1 != r2

    def test_validate_and_reset_fuse_no_lockout(self):
        """Returns False when no lockout file exists (no active lockout)."""
        import chat_send as cs
        with patch.object(cs, "_read_unlock_code", return_value=None):
            assert cs.validate_and_reset_fuse("UL-ABCD-1234") is False

    def test_validate_and_reset_fuse_valid_code(self, tmp_path):
        """Valid HMAC unlock code resets the fuse to step 0."""
        import chat_send as cs
        cw_code = "CW-ABCD-EFGH"
        secret = "deadbeef" * 8  # 64-char hex

        expected = cs._compute_unlock_response(cw_code, secret)

        with patch.object(cs, "_read_unlock_code", return_value=cw_code):
            with patch.object(cs, "_get_unlock_secret", return_value=secret):
                with patch.object(cs, "_FUSE_FILE", tmp_path / "fuse_state.json"):
                    with patch.object(cs, "_LOCKOUT_FILE", tmp_path / "lockout.json"):
                        result = cs.validate_and_reset_fuse(expected)

        assert result is True
        # Fuse should be at step 0 after reset
        assert cs._fuse._step == 0

    def test_validate_and_reset_fuse_invalid_code(self):
        """Wrong code returns False without resetting the fuse."""
        import chat_send as cs
        cw_code = "CW-ABCD-EFGH"
        secret = "deadbeef" * 8

        with patch.object(cs, "_read_unlock_code", return_value=cw_code):
            with patch.object(cs, "_get_unlock_secret", return_value=secret):
                result = cs.validate_and_reset_fuse("UL-ZZZZ-ZZZZ")

        assert result is False

    def test_validate_and_reset_fuse_case_insensitive(self, tmp_path):
        """Code comparison is case-insensitive."""
        import chat_send as cs
        cw_code = "CW-ABCD-EFGH"
        secret = "cafebabe" * 8

        expected = cs._compute_unlock_response(cw_code, secret)

        with patch.object(cs, "_read_unlock_code", return_value=cw_code):
            with patch.object(cs, "_get_unlock_secret", return_value=secret):
                with patch.object(cs, "_FUSE_FILE", tmp_path / "fuse_state.json"):
                    with patch.object(cs, "_LOCKOUT_FILE", tmp_path / "lockout.json"):
                        result = cs.validate_and_reset_fuse(expected.lower())

        assert result is True

    def test_get_unlock_secret_generates_and_persists(self):
        """_get_unlock_secret creates a 64-char hex secret if absent."""
        import chat_send as cs
        fake_cfg: dict = {}

        def fake_load():
            return fake_cfg

        def fake_save(cfg):
            fake_cfg.update(cfg)

        with patch("config.load_config", side_effect=fake_load):
            with patch("config.save_config", side_effect=fake_save):
                secret = cs._get_unlock_secret()

        assert len(secret) == 64
        assert all(c in "0123456789abcdef" for c in secret)
