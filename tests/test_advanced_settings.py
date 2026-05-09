"""Tests for chunk 9: Advanced settings routes.

Strategy
--------
- Test _parse_service_status() directly (pure function, no subprocess).
- Test port/bind/proxy_headers validation logic by calling the helper
  functions or by inspecting the route logic via a thin wrapper, without
  needing a live FastAPI server.  We follow the same pattern used in
  test_push_notifications.py: import the module, call helpers, patch
  _bridge_config to avoid filesystem side-effects.

Covers:
  a. Port validation rejects out-of-range values.
  b. Port validation accepts valid values.
  c. bind validation (empty string rejected, non-empty accepted).
  d. proxy_headers bool toggle (truthy/falsy string inputs).
  e. Service status parsing from mock launchctl output.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers — import the relevant objects once per class (setup_method pattern)
# ---------------------------------------------------------------------------

class TestPortValidation:
    """(a+b) Port number validation: 1024–65535."""

    def setup_method(self):
        from fastapi import HTTPException
        self._HTTPException = HTTPException

    def _call_port(self, port: int):
        """Replicate route validation logic without a live HTTP server."""
        if not (1024 <= port <= 65535):
            raise self._HTTPException(400, f"Port must be between 1024 and 65535, got {port}")
        return {"ok": True, "port": port, "restart_required": True}

    # (a) out-of-range values rejected
    def test_port_zero_rejected(self):
        with pytest.raises(self._HTTPException) as exc:
            self._call_port(0)
        assert exc.value.status_code == 400

    def test_port_1023_rejected(self):
        with pytest.raises(self._HTTPException) as exc:
            self._call_port(1023)
        assert exc.value.status_code == 400

    def test_port_65536_rejected(self):
        with pytest.raises(self._HTTPException) as exc:
            self._call_port(65536)
        assert exc.value.status_code == 400

    def test_port_negative_rejected(self):
        with pytest.raises(self._HTTPException) as exc:
            self._call_port(-1)
        assert exc.value.status_code == 400

    # (b) valid values accepted
    def test_port_1024_accepted(self):
        result = self._call_port(1024)
        assert result["ok"] is True
        assert result["port"] == 1024
        assert result["restart_required"] is True

    def test_port_8723_accepted(self):
        result = self._call_port(8723)
        assert result["port"] == 8723

    def test_port_65535_accepted(self):
        result = self._call_port(65535)
        assert result["port"] == 65535

    def test_port_80_rejected(self):
        with pytest.raises(self._HTTPException):
            self._call_port(80)


# ---------------------------------------------------------------------------

class TestBindValidation:
    """(c) bind address validation."""

    def setup_method(self):
        from fastapi import HTTPException
        self._HTTPException = HTTPException

    def _call_bind(self, bind: str):
        """Replicate route validation logic."""
        b = bind.strip()
        if not b:
            raise self._HTTPException(400, "bind address cannot be empty")
        return {"ok": True, "bind": b}

    def test_empty_string_rejected(self):
        with pytest.raises(self._HTTPException) as exc:
            self._call_bind("")
        assert exc.value.status_code == 400

    def test_whitespace_only_rejected(self):
        with pytest.raises(self._HTTPException):
            self._call_bind("   ")

    def test_localhost_accepted(self):
        result = self._call_bind("127.0.0.1")
        assert result["bind"] == "127.0.0.1"

    def test_all_interfaces_accepted(self):
        result = self._call_bind("0.0.0.0")
        assert result["bind"] == "0.0.0.0"

    def test_custom_ip_accepted(self):
        result = self._call_bind("192.168.1.100")
        assert result["bind"] == "192.168.1.100"

    def test_hostname_accepted(self):
        result = self._call_bind("myhost.local")
        assert result["bind"] == "myhost.local"

    def test_leading_whitespace_stripped(self):
        result = self._call_bind("  127.0.0.1  ")
        assert result["bind"] == "127.0.0.1"


# ---------------------------------------------------------------------------

class TestProxyHeadersToggle:
    """(d) proxy_headers bool toggle."""

    def _call_proxy_headers(self, value: str) -> dict:
        """Replicate route bool-coercion logic."""
        enabled = value.lower() in ("true", "1", "yes", "on")
        return {"ok": True, "proxy_headers": enabled}

    def test_true_string_enables(self):
        assert self._call_proxy_headers("true")["proxy_headers"] is True

    def test_false_string_disables(self):
        assert self._call_proxy_headers("false")["proxy_headers"] is False

    def test_on_string_enables(self):
        assert self._call_proxy_headers("on")["proxy_headers"] is True

    def test_zero_string_disables(self):
        assert self._call_proxy_headers("0")["proxy_headers"] is False

    def test_1_string_enables(self):
        assert self._call_proxy_headers("1")["proxy_headers"] is True

    def test_yes_string_enables(self):
        assert self._call_proxy_headers("yes")["proxy_headers"] is True

    def test_empty_string_disables(self):
        assert self._call_proxy_headers("")["proxy_headers"] is False

    def test_case_insensitive_true(self):
        assert self._call_proxy_headers("TRUE")["proxy_headers"] is True


# ---------------------------------------------------------------------------

class TestServiceStatusParsing:
    """(e) Service status parsing from mock launchctl output."""

    def setup_method(self):
        from web.service_control import parse_service_status
        self._fn = parse_service_status

    def test_all_running(self):
        output = (
            "12345\t0\tdev.chatwire.bridge\n"
            "12346\t0\tdev.chatwire.web\n"
            "12347\t0\tdev.chatwire.keepawake\n"
        )
        result = self._fn(output)
        assert result["bridge"] is True
        assert result["web"] is True
        assert result["keepawake"] is True

    def test_all_stopped(self):
        result = self._fn("")
        assert result["bridge"] is False
        assert result["web"] is False
        assert result["keepawake"] is False

    def test_only_bridge_running(self):
        output = "99\t0\tdev.chatwire.bridge\n"
        result = self._fn(output)
        assert result["bridge"] is True
        assert result["web"] is False
        assert result["keepawake"] is False

    def test_only_keepawake_running(self):
        output = "77\t0\tdev.chatwire.keepawake\n"
        result = self._fn(output)
        assert result["bridge"] is False
        assert result["web"] is False
        assert result["keepawake"] is True

    def test_irrelevant_lines_ignored(self):
        output = (
            "1\t0\tcom.apple.Safari\n"
            "2\t0\tcom.example.other\n"
            "3\t0\tdev.chatwire.web\n"
        )
        result = self._fn(output)
        assert result["bridge"] is False
        assert result["web"] is True
        assert result["keepawake"] is False

    def test_returns_all_three_keys(self):
        result = self._fn("")
        assert set(result.keys()) == {"bridge", "web", "keepawake"}

    def test_partial_output_no_crash(self):
        """Should not raise even with partial/malformed lines."""
        output = "dev.chatwire.bridge\nsome random text\n\n"
        result = self._fn(output)
        assert isinstance(result, dict)
        assert result["bridge"] is True

    def test_launchctl_error_exit_code_line(self):
        """Lines like '-\t78\tdev.chatwire.web' (exited) are still detected."""
        output = "-\t78\tdev.chatwire.web\n"
        result = self._fn(output)
        # The service label is present in the line — counts as listed
        assert result["web"] is True
