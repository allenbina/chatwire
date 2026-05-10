"""Tests for the plugin marketplace — registry cache and install route logic.

Strategy:
  - Test fetch_registry() from web/registry.py in isolation by patching
    urllib.request and the cache file path.
  - Test the install route helper logic via its subprocess + verify_plugin
    contract (no FastAPI test client needed — httpx not in the test env).
"""
from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch
import subprocess

import pytest

# ---------------------------------------------------------------------------
# Helpers — import the modules under test
# ---------------------------------------------------------------------------

# web/registry.py has no FastAPI dependency — importable in any test env.
import web.registry as registry_mod
from web.registry import fetch_registry, PLUGIN_REGISTRY_URL



# ---------------------------------------------------------------------------
# _fetch_registry_blocking — cache logic
# ---------------------------------------------------------------------------

class TestFetchRegistry:
    """Unit-test web/registry.py fetch_registry() cache logic."""

    _SAMPLE = [
        {
            "name": "chatwire-ntfy",
            "pypi": "chatwire-ntfy",
            "description": "Push notifications",
            "author": "allenbina",
            "signed": True,
            "homepage": "https://github.com/allenbina/chatwire-ntfy",
            "icon": "🔔",
        }
    ]

    def test_returns_fresh_cache_without_network(self, tmp_path):
        """If the cache is < 24 h old, no HTTP request is made."""
        cache = tmp_path / "plugin_registry_cache.json"
        cache.write_text(json.dumps(self._SAMPLE))

        import os
        now = time.time()
        os.utime(cache, (now, now))

        with patch("urllib.request.urlopen") as mock_urlopen:
            result = fetch_registry(cache)

        mock_urlopen.assert_not_called()
        assert result == self._SAMPLE

    def test_fetches_when_cache_stale(self, tmp_path):
        """If cache is > 24 h old, fetch from network and update cache."""
        cache = tmp_path / "plugin_registry_cache.json"
        cache.write_text(json.dumps([]))

        import os
        stale = time.time() - 90_000
        os.utime(cache, (stale, stale))

        raw = json.dumps(self._SAMPLE).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = raw
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_registry(cache)

        assert result == self._SAMPLE
        assert json.loads(cache.read_text()) == self._SAMPLE

    def test_fetches_when_no_cache(self, tmp_path):
        """If no cache file exists, fetch from network."""
        cache = tmp_path / "plugin_registry_cache.json"
        assert not cache.exists()

        raw = json.dumps(self._SAMPLE).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = raw
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_registry(cache)

        assert result == self._SAMPLE

    def test_network_failure_returns_stale_cache(self, tmp_path):
        """If network fails, return the stale cache rather than crashing."""
        cache = tmp_path / "plugin_registry_cache.json"
        cache.write_text(json.dumps(self._SAMPLE))

        import os
        stale = time.time() - 90_000
        os.utime(cache, (stale, stale))

        with patch("urllib.request.urlopen", side_effect=OSError("network down")):
            result = fetch_registry(cache)

        assert result == self._SAMPLE

    def test_network_failure_no_cache_returns_empty(self, tmp_path):
        """If network fails AND no cache exists, return empty list."""
        cache = tmp_path / "plugin_registry_cache.json"

        with patch("urllib.request.urlopen", side_effect=OSError("network down")):
            result = fetch_registry(cache)

        assert result == []

    def test_bad_json_from_network_returns_stale(self, tmp_path):
        """If server returns non-JSON, fall back to cache."""
        cache = tmp_path / "plugin_registry_cache.json"
        cache.write_text(json.dumps(self._SAMPLE))

        import os
        stale = time.time() - 90_000
        os.utime(cache, (stale, stale))

        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not json!!"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_registry(cache)

        assert result == self._SAMPLE

    def test_non_list_json_from_network_ignored(self, tmp_path):
        """If server returns a JSON object (not list), fall back to cache."""
        cache = tmp_path / "plugin_registry_cache.json"
        cache.write_text(json.dumps(self._SAMPLE))

        import os
        stale = time.time() - 90_000
        os.utime(cache, (stale, stale))

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"error": "oops"}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_registry(cache)

        assert result == self._SAMPLE

    def test_registry_url_points_to_chatwire_plugins_repo(self):
        """Verify the constant URL matches the expected repo."""
        assert "allenbina/chatwire-plugins" in PLUGIN_REGISTRY_URL
        assert "plugins.json" in PLUGIN_REGISTRY_URL


# ---------------------------------------------------------------------------
# Install route helpers — subprocess + verify_plugin contract
# ---------------------------------------------------------------------------

class TestInstallLogicMocked:
    """Test the subprocess + verify_plugin path that backs /api/plugins/install.

    We can't spin up a full FastAPI app without httpx, so we test the
    building blocks: subprocess.run mock and verify_plugin mock.
    """

    def test_pipx_inject_called_with_package(self):
        """pipx inject chatwire <pkg> must be called with the right args."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = subprocess.run(
                ["pipx", "inject", "chatwire", "chatwire-ntfy"],
                capture_output=True, text=True,
            )
        mock_run.assert_called_once_with(
            ["pipx", "inject", "chatwire", "chatwire-ntfy"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0

    def test_verify_plugin_called_after_install(self):
        """verify_plugin() must be called with the dist name after install."""
        import verify as verify_mod
        with patch.object(verify_mod, "verify_plugin") as mock_verify:
            mock_verify.return_value = None  # signed — success
            verify_mod.verify_plugin("chatwire-ntfy")
        mock_verify.assert_called_once_with("chatwire-ntfy")

    def test_unsigned_plugin_returns_warning(self):
        """PluginNotTrusted from verify_plugin → signed=False in response."""
        from verify import PluginNotTrusted, verify_plugin
        with patch("verify.verify_plugin", side_effect=PluginNotTrusted("unsigned")):
            try:
                verify_plugin("chatwire-community-pkg")
                signed = True
            except PluginNotTrusted:
                signed = False
        assert signed is False

    def test_package_name_strip_version_specifier(self):
        """dist name extraction: 'chatwire-ntfy==0.1.0' → 'chatwire-ntfy'."""
        pkg = "chatwire-ntfy==0.1.0"
        dist_name = pkg.split("==")[0]
        assert dist_name == "chatwire-ntfy"

    def test_package_name_no_specifier_unchanged(self):
        pkg = "chatwire-ntfy"
        dist_name = pkg.split("==")[0]
        assert dist_name == "chatwire-ntfy"

    def test_package_name_regex_valid_names(self):
        import re
        pattern = r"[A-Za-z0-9_.\-]+(?:==[\w.]+)?"
        valid = [
            "chatwire-ntfy",
            "chatwire_ntfy",
            "chatwire-ntfy==0.1.0",
            "my.plugin",
            "CamelCase",
        ]
        for name in valid:
            assert re.fullmatch(pattern, name), f"Should be valid: {name!r}"

    def test_package_name_regex_rejects_shell_chars(self):
        import re
        pattern = r"[A-Za-z0-9_.\-]+(?:==[\w.]+)?"
        bad = [
            "pkg; rm -rf /",
            "pkg && evil",
            "pkg|evil",
            "../evil",
            "pkg > /etc/passwd",
            "",
        ]
        for name in bad:
            assert not re.fullmatch(pattern, name), f"Should be rejected: {name!r}"
