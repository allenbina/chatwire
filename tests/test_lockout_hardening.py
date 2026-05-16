"""Tests for anti-spam lockout hardening (Phase 70).

Covers:
- Defense-in-depth fuse check in raw send_text / send_file /
  send_text_to_chat / send_file_to_chat functions.
- Permanent lockout BroadcastBlockedError message includes CW code and form URL.
- MQTT _log_send_future_error callback logs correctly.
- XMPP _log_send_future_error callback logs correctly.

NOTE: Python 3.8 — no walrus operator, no match, no parenthesized with.
Use asyncio.run() (not get_event_loop().run_until_complete) to avoid
test_mcp.py event-loop teardown interference.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
from concurrent.futures import Future

import pytest

# ---------------------------------------------------------------------------
# Make plugin modules importable (mirror pattern from existing plugin tests).
# ---------------------------------------------------------------------------
_REPO = Path(__file__).resolve().parent.parent

_MQTT_ROOT = _REPO / "chatwire-plugins" / "chatwire-mqtt"
if str(_MQTT_ROOT) not in sys.path:
    sys.path.insert(0, str(_MQTT_ROOT))

_XMPP_ROOT = _REPO / "chatwire-plugins" / "chatwire-xmpp"
if str(_XMPP_ROOT) not in sys.path:
    sys.path.insert(0, str(_XMPP_ROOT))

# Stub out heavy optional deps before the modules are imported.
_paho_stub = MagicMock()
_paho_stub.Client = MagicMock
sys.modules.setdefault("paho", MagicMock())
sys.modules.setdefault("paho.mqtt", MagicMock())
sys.modules.setdefault("paho.mqtt.client", _paho_stub)
sys.modules.setdefault("slixmpp", MagicMock())

import chatwire_mqtt  # noqa: E402
import chatwire_xmpp  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_singletons():
    import chat_send as cs
    cs._rate_bucket._set_tokens(float(cs._RATE_LIMIT_COUNT))
    cs._broadcast._reset()
    cs._fuse._reset()


# ---------------------------------------------------------------------------
# Defense-in-depth: fuse check in raw send functions
# ---------------------------------------------------------------------------

class TestRawSendFuseCheck:
    """send_text / send_file / send_text_to_chat / send_file_to_chat must raise
    BroadcastBlockedError when the fuse is active, even without check_send_guard.
    """

    def setup_method(self):
        _reset_singletons()

    def teardown_method(self):
        _reset_singletons()

    def _arm_fuse(self):
        import chat_send as cs
        # Directly set step=1 and a future cooldown so fuse is active.
        cs._fuse._step = 1
        cs._fuse._cooldown_until = time.time() + 300

    def test_send_text_blocked_by_fuse(self):
        import chat_send as cs
        self._arm_fuse()
        with patch("chat_send._run_osascript"):
            with pytest.raises(cs.BroadcastBlockedError):
                cs.send_text("test@example.com", "hello")

    def test_send_file_blocked_by_fuse(self):
        import chat_send as cs
        self._arm_fuse()
        with patch("chat_send._run_osascript"):
            with pytest.raises(cs.BroadcastBlockedError):
                cs.send_file("test@example.com", Path("/tmp/file.jpg"))

    def test_send_text_to_chat_blocked_by_fuse(self):
        import chat_send as cs
        self._arm_fuse()
        with patch("chat_send._run_osascript"):
            with pytest.raises(cs.BroadcastBlockedError):
                cs.send_text_to_chat("iMessage;+;chat123", "hello")

    def test_send_file_to_chat_blocked_by_fuse(self):
        import chat_send as cs
        self._arm_fuse()
        with patch("chat_send._run_osascript"):
            with pytest.raises(cs.BroadcastBlockedError):
                cs.send_file_to_chat("iMessage;+;chat123", Path("/tmp/file.jpg"))

    def test_send_text_passes_when_fuse_inactive(self):
        """Fuse at step=0 — send_text should NOT raise (osascript stubbed out)."""
        import chat_send as cs
        # step=0 — fuse inactive
        with patch("chat_send._run_osascript"):
            # Should not raise; osascript call is stubbed
            cs.send_text("test@example.com", "hello")

    def test_send_text_permanent_lockout_step6(self):
        import chat_send as cs
        cs._fuse._step = 6
        cs._fuse._cooldown_until = None
        with patch("chat_send._run_osascript"):
            with pytest.raises(cs.BroadcastBlockedError) as exc_info:
                cs.send_text("test@example.com", "hello")
        assert exc_info.value.step == 6
        assert exc_info.value.retry_after is None


# ---------------------------------------------------------------------------
# Permanent lockout message includes challenge code and form URL
# ---------------------------------------------------------------------------

class TestPermanentLockoutMessage:
    """_fuse.check() at step 6 must embed CW code + form URL in the error str."""

    def setup_method(self):
        _reset_singletons()

    def teardown_method(self):
        _reset_singletons()

    def test_message_includes_cw_code_when_present(self):
        import chat_send as cs
        cs._fuse._step = 6
        cs._fuse._cooldown_until = None
        with patch("chat_send._read_unlock_code", return_value="CW-ABCD-1234"):
            with patch("chat_send._get_unlock_form_url", return_value="https://example.com/unlock"):
                with pytest.raises(cs.BroadcastBlockedError) as exc_info:
                    cs._fuse.check()
        msg = str(exc_info.value)
        assert "CW-ABCD-1234" in msg
        assert "https://example.com/unlock" in msg

    def test_message_uses_fallback_url_when_no_config(self):
        import chat_send as cs
        cs._fuse._step = 6
        cs._fuse._cooldown_until = None
        with patch("chat_send._read_unlock_code", return_value=None):
            with patch("chat_send._get_unlock_form_url", return_value=None):
                with pytest.raises(cs.BroadcastBlockedError) as exc_info:
                    cs._fuse.check()
        msg = str(exc_info.value)
        # Fallback URL should appear
        assert "chatwire.app" in msg

    def test_message_omits_code_line_when_no_code(self):
        import chat_send as cs
        cs._fuse._step = 6
        cs._fuse._cooldown_until = None
        with patch("chat_send._read_unlock_code", return_value=None):
            with patch("chat_send._get_unlock_form_url", return_value="https://example.com/unlock"):
                with pytest.raises(cs.BroadcastBlockedError) as exc_info:
                    cs._fuse.check()
        msg = str(exc_info.value)
        assert "CW-" not in msg
        assert "https://example.com/unlock" in msg

    def test_timed_lockout_message_unchanged(self):
        """Steps 1-5 should still show cooldown time, not CW code."""
        import chat_send as cs
        cs._fuse._step = 2
        cs._fuse._cooldown_until = time.time() + 1800
        with pytest.raises(cs.BroadcastBlockedError) as exc_info:
            cs._fuse.check()
        msg = str(exc_info.value)
        assert "paused" in msg.lower() or "blocked" in msg.lower() or "min" in msg


# ---------------------------------------------------------------------------
# MQTT _log_send_future_error callback
# ---------------------------------------------------------------------------

class TestMqttSendFutureErrorCallback:
    """_log_send_future_error logs BroadcastBlockedError and RateLimitError."""

    def _make_failed_future(self, exc):
        """Return a concurrent.futures.Future that has already failed with exc."""
        fut = Future()
        fut.set_exception(exc)
        return fut

    def _make_ok_future(self):
        fut = Future()
        fut.set_result(None)
        return fut

    def test_broadcast_blocked_error_is_logged(self):
        try:
            from chat_send import BroadcastBlockedError
        except ImportError:
            pytest.skip("chat_send not available")

        exc = BroadcastBlockedError("Chatwire locked. Code: CW-AA-BB. Request unlock: https://example.com", None, step=6)
        fut = self._make_failed_future(exc)

        with patch("chatwire_mqtt.log") as mock_log:
            chatwire_mqtt._log_send_future_error(fut, "mqtt:test@example.com")

        mock_log.error.assert_called_once()
        call_args = mock_log.error.call_args[0]
        assert "blocked" in call_args[0].lower() or "fuse" in call_args[0].lower()

    def test_rate_limit_error_is_logged_as_warning(self):
        try:
            from chat_send import RateLimitError
        except ImportError:
            pytest.skip("chat_send not available")

        exc = RateLimitError("rate limited")
        fut = self._make_failed_future(exc)

        with patch("chatwire_mqtt.log") as mock_log:
            chatwire_mqtt._log_send_future_error(fut, "mqtt:test@example.com")

        mock_log.warning.assert_called_once()

    def test_success_future_does_not_log(self):
        fut = self._make_ok_future()
        with patch("chatwire_mqtt.log") as mock_log:
            chatwire_mqtt._log_send_future_error(fut, "mqtt:test@example.com")

        mock_log.error.assert_not_called()
        mock_log.warning.assert_not_called()

    def test_other_exception_is_logged_as_error(self):
        exc = RuntimeError("osascript failed")
        fut = self._make_failed_future(exc)

        with patch("chatwire_mqtt.log") as mock_log:
            chatwire_mqtt._log_send_future_error(fut, "mqtt:test@example.com")

        mock_log.error.assert_called_once()


# ---------------------------------------------------------------------------
# XMPP _log_send_future_error callback
# ---------------------------------------------------------------------------

class TestXmppSendFutureErrorCallback:
    """Same semantics as MQTT version."""

    def _make_failed_future(self, exc):
        fut = Future()
        fut.set_exception(exc)
        return fut

    def _make_ok_future(self):
        fut = Future()
        fut.set_result(None)
        return fut

    def test_broadcast_blocked_error_is_logged(self):
        try:
            from chat_send import BroadcastBlockedError
        except ImportError:
            pytest.skip("chat_send not available")

        exc = BroadcastBlockedError("locked", None, step=6)
        fut = self._make_failed_future(exc)

        with patch("chatwire_xmpp.log") as mock_log:
            chatwire_xmpp._log_send_future_error(fut, "xmpp:alice@example.com")

        mock_log.error.assert_called_once()

    def test_rate_limit_error_is_logged_as_warning(self):
        try:
            from chat_send import RateLimitError
        except ImportError:
            pytest.skip("chat_send not available")

        exc = RateLimitError("rate limited")
        fut = self._make_failed_future(exc)

        with patch("chatwire_xmpp.log") as mock_log:
            chatwire_xmpp._log_send_future_error(fut, "xmpp:alice@example.com")

        mock_log.warning.assert_called_once()

    def test_success_future_does_not_log(self):
        fut = self._make_ok_future()
        with patch("chatwire_xmpp.log") as mock_log:
            chatwire_xmpp._log_send_future_error(fut, "xmpp:alice@example.com")

        mock_log.error.assert_not_called()
        mock_log.warning.assert_not_called()
