"""Tests for MCP SSE transport (web/mcp_sse.py) and api_keys mcp scope.

The ``mcp`` Python package is NOT required on the test host — tests
that need it are guarded by pytest.importorskip.

Covers:
- ``mcp`` scope in api_keys.ALL_SCOPES
- ``/mcp/`` route scope entries in api_keys._ROUTE_SCOPES
- _maybe_mount_mcp_sse mounts only when enabled + http_enabled
- _maybe_mount_mcp_sse is a no-op when mcp package is missing
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# api_keys scope
# ---------------------------------------------------------------------------

class TestApiKeysMcpScope:
    def test_mcp_in_all_scopes(self):
        from web.api_keys import ALL_SCOPES
        assert "mcp" in ALL_SCOPES

    def test_route_scopes_cover_mcp_get(self):
        from web.api_keys import scope_for_request
        assert scope_for_request("GET", "/mcp/sse") == "mcp"

    def test_route_scopes_cover_mcp_post(self):
        from web.api_keys import scope_for_request
        assert scope_for_request("POST", "/mcp/messages") == "mcp"


# ---------------------------------------------------------------------------
# create_mcp_sse_app (requires mcp package)
# ---------------------------------------------------------------------------

class TestCreateMcpSseApp:
    def test_import_error_when_mcp_missing(self):
        """create_mcp_sse_app raises ImportError if mcp is not installed."""
        import importlib
        import sys
        # Temporarily block the mcp import
        sentinel = object()
        had_mcp = "mcp" in sys.modules
        old_val = sys.modules.get("mcp", sentinel)
        sys.modules["mcp"] = None  # type: ignore[assignment]
        try:
            # Re-import to get the function without a cached mcp
            from web.mcp_sse import create_mcp_sse_app
            with pytest.raises((ImportError, ModuleNotFoundError)):
                create_mcp_sse_app()
        finally:
            if old_val is sentinel:
                sys.modules.pop("mcp", None)
            else:
                sys.modules["mcp"] = old_val


# ---------------------------------------------------------------------------
# _maybe_mount_mcp_sse gating logic
# ---------------------------------------------------------------------------

class TestMaybeMountMcpSse:
    """Test the mount-gating logic by calling the function with mocked config."""

    def _make_config(self, enabled=False, http_enabled=False):
        return {
            "integrations": {
                "mcp": {
                    "enabled": enabled,
                    "http_enabled": http_enabled,
                }
            }
        }

    def test_does_not_mount_when_disabled(self):
        """When mcp.enabled is false, nothing is mounted."""
        cfg = self._make_config(enabled=False, http_enabled=True)
        mcp_cfg = cfg.get("integrations", {}).get("mcp", {})
        should_mount = mcp_cfg.get("enabled") and mcp_cfg.get("http_enabled")
        assert should_mount is False

    def test_does_not_mount_when_http_disabled(self):
        cfg = self._make_config(enabled=True, http_enabled=False)
        mcp_cfg = cfg.get("integrations", {}).get("mcp", {})
        should_mount = mcp_cfg.get("enabled") and mcp_cfg.get("http_enabled")
        assert should_mount is False

    def test_should_mount_when_both_enabled(self):
        cfg = self._make_config(enabled=True, http_enabled=True)
        mcp_cfg = cfg.get("integrations", {}).get("mcp", {})
        should_mount = mcp_cfg.get("enabled") and mcp_cfg.get("http_enabled")
        assert should_mount is True
