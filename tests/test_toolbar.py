"""Tests for chatwire_toolbar — pure status-checking helpers.

The rumps GUI layer is macOS-only and is NOT tested here (it requires a
running AppKit event loop and PyObjC). Only the platform-independent helper
functions are covered.

Strategy:
- Patch subprocess.run and urllib.request.urlopen so tests run on Linux CI
  without launchd or a running web server.
- Use monkeypatch / unittest.mock for isolation.
"""
from __future__ import annotations

import subprocess
import sys
import urllib.error
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import chatwire_toolbar as tb


# ---------------------------------------------------------------------------
# _launchctl_list
# ---------------------------------------------------------------------------

class TestLaunchctlList:
    def test_returns_empty_on_non_macos(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        assert tb._launchctl_list() == set()

    def test_parses_launchctl_output(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        sample = (
            "PID\tStatus\tLabel\n"
            "123\t0\tdev.chatwire.bridge\n"
            "-\t0\tdev.chatwire.web\n"
            "456\t0\tcom.apple.other\n"
        )
        mock_result = MagicMock()
        mock_result.stdout = sample
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = tb._launchctl_list()
        mock_run.assert_called_once()
        assert "dev.chatwire.bridge" in result
        assert "dev.chatwire.web" in result
        assert "com.apple.other" in result

    def test_returns_empty_on_timeout(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("launchctl", 5)):
            assert tb._launchctl_list() == set()

    def test_returns_empty_on_file_not_found(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert tb._launchctl_list() == set()

    def test_empty_output_gives_empty_set(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        mock_result = MagicMock()
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            assert tb._launchctl_list() == set()


# ---------------------------------------------------------------------------
# _healthz_ok
# ---------------------------------------------------------------------------

class TestHealthzOk:
    def test_returns_true_on_200(self):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert tb._healthz_ok() is True

    def test_returns_false_on_url_error(self):
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("refused"),
        ):
            assert tb._healthz_ok() is False

    def test_returns_false_on_os_error(self):
        with patch("urllib.request.urlopen", side_effect=OSError):
            assert tb._healthz_ok() is False

    def test_returns_false_on_non_200(self):
        mock_resp = MagicMock()
        mock_resp.status = 503
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert tb._healthz_ok() is False


# ---------------------------------------------------------------------------
# get_service_statuses
# ---------------------------------------------------------------------------

class TestGetServiceStatuses:
    def _patch_all(self, monkeypatch, loaded_labels: set[str], web_ok: bool):
        monkeypatch.setattr(tb, "_launchctl_list", lambda: loaded_labels)
        monkeypatch.setattr(tb, "_healthz_ok", lambda: web_ok)

    def test_all_running(self, monkeypatch):
        labels = {"dev.chatwire.bridge", "dev.chatwire.web"}
        self._patch_all(monkeypatch, labels, web_ok=True)
        statuses = tb.get_service_statuses()
        assert len(statuses) == 2
        bridge = next(s for s in statuses if s.name == "bridge")
        web = next(s for s in statuses if s.name == "web")
        assert bridge.loaded is True
        assert bridge.responding is False  # only web gets healthz
        assert web.loaded is True
        assert web.responding is True

    def test_all_stopped(self, monkeypatch):
        self._patch_all(monkeypatch, set(), web_ok=False)
        statuses = tb.get_service_statuses()
        assert all(not s.loaded for s in statuses)
        assert all(not s.responding for s in statuses)

    def test_web_loaded_but_not_responding(self, monkeypatch):
        labels = {"dev.chatwire.web"}
        self._patch_all(monkeypatch, labels, web_ok=False)
        statuses = tb.get_service_statuses()
        web = next(s for s in statuses if s.name == "web")
        assert web.loaded is True
        assert web.responding is False

    def test_returns_all_services(self, monkeypatch):
        self._patch_all(monkeypatch, set(), web_ok=False)
        names = [s.name for s in tb.get_service_statuses()]
        assert set(names) == {"bridge", "web"}


# ---------------------------------------------------------------------------
# service_status_line
# ---------------------------------------------------------------------------

class TestServiceStatusLine:
    def _make(self, name, loaded, responding=False):
        return tb.ServiceStatus(name=name, loaded=loaded, responding=responding)

    def test_web_running(self):
        s = self._make("web", loaded=True, responding=True)
        assert tb.service_status_line(s) == "web: running"

    def test_web_loaded_not_responding(self):
        s = self._make("web", loaded=True, responding=False)
        assert tb.service_status_line(s) == "web: loaded (not responding)"

    def test_web_stopped(self):
        s = self._make("web", loaded=False, responding=False)
        assert tb.service_status_line(s) == "web: stopped"

    def test_bridge_running(self):
        s = self._make("bridge", loaded=True)
        assert tb.service_status_line(s) == "bridge: running"

    def test_bridge_stopped(self):
        s = self._make("bridge", loaded=False)
        assert tb.service_status_line(s) == "bridge: stopped"

    def test_other_service_running(self):
        s = self._make("bridge", loaded=True)
        assert tb.service_status_line(s) == "bridge: running"


# ---------------------------------------------------------------------------
# _list_installed_plugins
# ---------------------------------------------------------------------------

class TestListInstalledPlugins:
    def test_returns_plugin_names(self):
        mock_ep = MagicMock()
        mock_ep.name = "ntfy"
        with patch("importlib.metadata.entry_points", return_value=[mock_ep]):
            result = tb._list_installed_plugins()
        assert result == ["ntfy"]

    def test_returns_empty_list_on_error(self):
        with patch("importlib.metadata.entry_points", side_effect=Exception("boom")):
            result = tb._list_installed_plugins()
        assert result == []

    def test_returns_empty_when_no_plugins(self):
        with patch("importlib.metadata.entry_points", return_value=[]):
            result = tb._list_installed_plugins()
        assert result == []


# ---------------------------------------------------------------------------
# main() — platform guard
# ---------------------------------------------------------------------------

class TestMain:
    def test_exits_on_non_macos(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        with pytest.raises(SystemExit) as exc_info:
            tb.main()
        assert exc_info.value.code != 0

    def test_exits_when_rumps_missing(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        import builtins
        real_import = builtins.__import__

        def _no_rumps(name, *args, **kwargs):
            if name == "rumps":
                raise ImportError("No module named 'rumps'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _no_rumps)
        with pytest.raises(SystemExit) as exc_info:
            tb.main()
        assert exc_info.value.code != 0
