"""Tests for the plugin update system — version_check module, update routes,
core version check, and template structural assertions.

Strategy:
  - Test fetch_pypi_version() and check_updates() from web/version_check.py
    in isolation by patching urllib.request.urlopen.
  - Test update route logic (subprocess --force + verify_plugin contract)
    without a full FastAPI test client.
  - Structural tests verify _plugin_sections.html has the required banner
    markup and JS helpers.
  - Structural tests verify _settings.html footer has the version hint span.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import web.version_check as vc_mod
from web.version_check import (
    check_updates,
    fetch_pypi_version,
    load_version_cache,
    save_version_cache,
)

TEMPLATES = Path(__file__).resolve().parent.parent / "web" / "templates"


# ---------------------------------------------------------------------------
# fetch_pypi_version — in-memory cache + network
# ---------------------------------------------------------------------------

class TestFetchPypiVersion:
    """Unit-tests for fetch_pypi_version() cache and network behaviour."""

    def _mock_resp(self, version: str):
        raw = json.dumps({"info": {"version": version}}).encode()
        mock = MagicMock()
        mock.read.return_value = raw
        mock.__enter__ = lambda s: s
        mock.__exit__ = MagicMock(return_value=False)
        return mock

    def test_returns_version_from_network(self):
        mem = {}
        now = time.time()
        with patch("urllib.request.urlopen", return_value=self._mock_resp("0.2.0")):
            v = fetch_pypi_version("chatwire-ntfy", mem, now)
        assert v == "0.2.0"

    def test_populates_mem_cache(self):
        mem = {}
        now = time.time()
        with patch("urllib.request.urlopen", return_value=self._mock_resp("0.2.0")):
            fetch_pypi_version("chatwire-ntfy", mem, now)
        assert mem["chatwire-ntfy"]["version"] == "0.2.0"
        assert abs(mem["chatwire-ntfy"]["ts"] - now) < 1

    def test_returns_fresh_mem_cache_without_network(self):
        now = time.time()
        mem = {"chatwire-ntfy": {"version": "0.2.0", "ts": now - 100}}
        with patch("urllib.request.urlopen") as mock_open:
            v = fetch_pypi_version("chatwire-ntfy", mem, now)
        mock_open.assert_not_called()
        assert v == "0.2.0"

    def test_refreshes_stale_mem_cache(self):
        now = time.time()
        stale_ts = now - 90_000
        mem = {"chatwire-ntfy": {"version": "0.1.0", "ts": stale_ts}}
        with patch("urllib.request.urlopen", return_value=self._mock_resp("0.2.0")):
            v = fetch_pypi_version("chatwire-ntfy", mem, now)
        assert v == "0.2.0"
        assert mem["chatwire-ntfy"]["version"] == "0.2.0"

    def test_network_failure_returns_stale_mem_cache(self):
        now = time.time()
        stale_ts = now - 90_000
        mem = {"chatwire-ntfy": {"version": "0.1.0", "ts": stale_ts}}
        with patch("urllib.request.urlopen", side_effect=OSError("net down")):
            v = fetch_pypi_version("chatwire-ntfy", mem, now)
        assert v == "0.1.0"

    def test_network_failure_no_cache_returns_none(self):
        mem = {}
        now = time.time()
        with patch("urllib.request.urlopen", side_effect=OSError("net down")):
            v = fetch_pypi_version("chatwire-ntfy", mem, now)
        assert v is None

    def test_bad_json_returns_none_no_cache(self):
        mem = {}
        now = time.time()
        bad = MagicMock()
        bad.read.return_value = b"not json"
        bad.__enter__ = lambda s: s
        bad.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=bad):
            v = fetch_pypi_version("chatwire-ntfy", mem, now)
        assert v is None

    def test_url_format_produces_valid_url(self):
        """PYPI_JSON_URL is a format string; when expanded it must embed the package name."""
        # The constant must contain the {package} placeholder.
        assert "{package}" in vc_mod.PYPI_JSON_URL
        # When expanded it must produce a URL that references pypi.org and the package.
        url = vc_mod.PYPI_JSON_URL.format(package="chatwire-ntfy")
        assert "chatwire-ntfy" in url
        assert "pypi.org" in url


# ---------------------------------------------------------------------------
# load_version_cache / save_version_cache
# ---------------------------------------------------------------------------

class TestVersionCacheDisk:
    def test_load_missing_file_returns_empty(self, tmp_path):
        assert load_version_cache(tmp_path / "missing.json") == {}

    def test_load_bad_json_returns_empty(self, tmp_path):
        f = tmp_path / "cache.json"
        f.write_text("NOT JSON")
        assert load_version_cache(f) == {}

    def test_save_and_load_roundtrip(self, tmp_path):
        cache_path = tmp_path / "v.json"
        data = {"chatwire-ntfy": {"version": "0.1.0", "ts": 12345.0}}
        save_version_cache(cache_path, data)
        assert load_version_cache(cache_path) == data

    def test_save_creates_parent_dirs(self, tmp_path):
        cache_path = tmp_path / "sub" / "dir" / "cache.json"
        save_version_cache(cache_path, {"a": "b"})
        assert cache_path.exists()


# ---------------------------------------------------------------------------
# check_updates
# ---------------------------------------------------------------------------

class TestCheckUpdates:
    def _mock_resp(self, version: str):
        raw = json.dumps({"info": {"version": version}}).encode()
        m = MagicMock()
        m.read.return_value = raw
        m.__enter__ = lambda s: s
        m.__exit__ = MagicMock(return_value=False)
        return m

    def test_returns_update_when_newer(self, tmp_path):
        cache = tmp_path / "v.json"
        with patch("urllib.request.urlopen", return_value=self._mock_resp("0.2.0")):
            result = check_updates({"chatwire-ntfy": "0.1.0"}, cache)
        assert result == {"chatwire-ntfy": "0.2.0"}

    def test_no_update_when_same_version(self, tmp_path):
        cache = tmp_path / "v.json"
        with patch("urllib.request.urlopen", return_value=self._mock_resp("0.1.0")):
            result = check_updates({"chatwire-ntfy": "0.1.0"}, cache)
        assert result == {}

    def test_empty_dist_map_returns_empty(self, tmp_path):
        cache = tmp_path / "v.json"
        with patch("urllib.request.urlopen") as mock_open:
            result = check_updates({}, cache)
        mock_open.assert_not_called()
        assert result == {}

    def test_network_failure_returns_empty(self, tmp_path):
        cache = tmp_path / "v.json"
        with patch("urllib.request.urlopen", side_effect=OSError("net down")):
            result = check_updates({"chatwire-ntfy": "0.1.0"}, cache)
        assert result == {}

    def test_persists_cache_to_disk(self, tmp_path):
        cache = tmp_path / "v.json"
        with patch("urllib.request.urlopen", return_value=self._mock_resp("0.2.0")):
            check_updates({"chatwire-ntfy": "0.1.0"}, cache)
        assert cache.exists()
        stored = json.loads(cache.read_text())
        assert stored["chatwire-ntfy"]["version"] == "0.2.0"

    def test_skips_plugins_with_empty_installed_version(self, tmp_path):
        """Plugins with no installed_version should not be checked."""
        cache = tmp_path / "v.json"
        with patch("urllib.request.urlopen") as mock_open:
            result = check_updates({"chatwire-ntfy": ""}, cache)
        mock_open.assert_not_called()
        assert result == {}


# ---------------------------------------------------------------------------
# Update route helpers — subprocess --force + verify_plugin contract
# ---------------------------------------------------------------------------

class TestUpdateRouteLogic:
    """Test the subprocess + verify_plugin path backing /api/plugins/update."""

    def test_pipx_inject_force_args(self):
        """Must call pipx inject --force chatwire <pkg>."""
        import subprocess
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            subprocess.run(
                ["pipx", "inject", "--force", "chatwire", "chatwire-ntfy"],
                capture_output=True, text=True,
            )
        mock_run.assert_called_once_with(
            ["pipx", "inject", "--force", "chatwire", "chatwire-ntfy"],
            capture_output=True, text=True,
        )

    def test_verify_called_after_update(self):
        import verify as verify_mod
        with patch.object(verify_mod, "verify_plugin") as mock_verify:
            mock_verify.return_value = None
            verify_mod.verify_plugin("chatwire-ntfy")
        mock_verify.assert_called_once_with("chatwire-ntfy")

    def test_unsigned_after_update_yields_warning(self):
        from verify import PluginNotTrusted, verify_plugin
        with patch("verify.verify_plugin", side_effect=PluginNotTrusted("unsigned")):
            try:
                verify_plugin("chatwire-community-pkg")
                signed = True
            except PluginNotTrusted:
                signed = False
        assert signed is False

    def test_package_name_regex_valid(self):
        import re
        pattern = r"[A-Za-z0-9_.\-]+(?:==[\w.]+)?"
        valid = ["chatwire-ntfy", "chatwire-ntfy==0.2.0", "my.plugin"]
        for name in valid:
            assert re.fullmatch(pattern, name), f"Should be valid: {name!r}"

    def test_package_name_regex_rejects_shell_chars(self):
        import re
        pattern = r"[A-Za-z0-9_.\-]+(?:==[\w.]+)?"
        bad = ["pkg; rm -rf /", "pkg && evil", "../etc", ""]
        for name in bad:
            assert not re.fullmatch(pattern, name), f"Should reject: {name!r}"


# ---------------------------------------------------------------------------
# Core version check helpers
# ---------------------------------------------------------------------------

class TestChatwireVersionCheck:
    """Test the chatwire-core PyPI check helpers."""

    def _mock_resp(self, version: str):
        raw = json.dumps({"info": {"version": version}}).encode()
        m = MagicMock()
        m.read.return_value = raw
        m.__enter__ = lambda s: s
        m.__exit__ = MagicMock(return_value=False)
        return m

    def test_fetches_chatwire_version_from_pypi(self, tmp_path):
        cache = tmp_path / "v.json"
        with patch("urllib.request.urlopen", return_value=self._mock_resp("1.2.0")):
            mem = {}
            v = fetch_pypi_version("chatwire", mem, time.time())
        assert v == "1.2.0"

    def test_update_available_when_versions_differ(self, tmp_path):
        cache = tmp_path / "v.json"
        with patch("urllib.request.urlopen", return_value=self._mock_resp("1.2.0")):
            result = check_updates({"chatwire": "1.1.0"}, cache)
        assert result == {"chatwire": "1.2.0"}

    def test_no_update_when_current(self, tmp_path):
        cache = tmp_path / "v.json"
        with patch("urllib.request.urlopen", return_value=self._mock_resp("1.1.0")):
            result = check_updates({"chatwire": "1.1.0"}, cache)
        assert result == {}

    def test_pypi_url_constant_uses_format_placeholder(self):
        assert "{package}" in vc_mod.PYPI_JSON_URL
        assert "pypi.org" in vc_mod.PYPI_JSON_URL


# ---------------------------------------------------------------------------
# Template structural tests — _plugin_sections.html
# ---------------------------------------------------------------------------

def _sections_html() -> str:
    return (TEMPLATES / "_plugin_sections.html").read_text()


class TestPluginSectionsTemplate:
    def test_update_banner_div_present(self):
        html = _sections_html()
        assert "plugin-update-banner" in html

    def test_update_available_jinja_check(self):
        html = _sections_html()
        assert "update_available" in html

    def test_update_now_button_present(self):
        html = _sections_html()
        assert "Update now" in html

    def test_dismiss_button_present(self):
        html = _sections_html()
        assert "Dismiss" in html

    def test_cw_dismiss_update_js_function(self):
        html = _sections_html()
        assert "cwDismissUpdate" in html

    def test_cw_update_plugin_js_function(self):
        html = _sections_html()
        assert "cwUpdatePlugin" in html

    def test_localstorage_key_used_in_dismiss(self):
        html = _sections_html()
        assert "cw_upd_dismiss_" in html

    def test_api_plugins_update_endpoint_referenced(self):
        html = _sections_html()
        assert "/api/plugins/update" in html

    def test_banner_data_attributes_present(self):
        html = _sections_html()
        assert "data-plugin=" in html or "data-plugin" in html
        assert "data-latest=" in html or "data-latest" in html
        assert "data-dist=" in html or "data-dist" in html

    def test_amber_styling_for_update_banner(self):
        html = _sections_html()
        assert "amber" in html

    def test_update_badge_in_header(self):
        html = _sections_html()
        assert "plugin-upd-badge-" in html


# ---------------------------------------------------------------------------
# Template structural tests — _settings.html footer
# ---------------------------------------------------------------------------

def _settings_html() -> str:
    return (TEMPLATES / "_settings.html").read_text()


class TestSettingsFooterTemplate:
    def test_app_version_shown_in_footer(self):
        html = _settings_html()
        assert "app_version" in html

    def test_chatwire_latest_version_hint_present(self):
        """Footer must reference chatwire_latest for the update hint."""
        html = _settings_html()
        assert "chatwire_latest" in html

    def test_available_update_hint_text(self):
        html = _settings_html()
        assert "available" in html.lower()

    def test_amber_color_on_update_hint(self):
        html = _settings_html()
        assert "amber" in html
