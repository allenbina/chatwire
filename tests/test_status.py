"""Tests for the `chatwire status` subcommand (Phase 51).

cmd_status is a read-only probe — it always exits 0. Tests cover:
  1. Parser: 'status' is a recognised subcommand.
  2. Output: version string is present.
  3. Output: config path is mentioned.
  4. Output: graceful message when config is absent.
  5. Output: port shown when config is present.
  6. Output: plugins listed when present / "none" when absent.
  7. On non-macOS: no agents section (or graceful skip).
  8. _uninstall_paths() now includes 'img_cache'.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import _version
from chatwire_cli import (
    DEFAULT_LABEL_PREFIX,
    _list_installed_plugins,
    _uninstall_paths,
    build_parser,
    cmd_status,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _run_status(capsys, *, label_prefix=DEFAULT_LABEL_PREFIX) -> tuple[int, str]:
    args = argparse.Namespace(label_prefix=label_prefix)
    rc = cmd_status(args)
    out = capsys.readouterr().out
    return rc, out


# ---------------------------------------------------------------------------
# 1. Parser recognises 'status'
# ---------------------------------------------------------------------------

class TestStatusParser:
    def test_status_in_subcommands(self):
        p = build_parser()
        # Attempt to parse 'status' — should not raise.
        args = p.parse_args(["status"])
        assert args.cmd == "status"

    def test_status_func_is_cmd_status(self):
        p = build_parser()
        args = p.parse_args(["status"])
        from chatwire_cli import cmd_status as _cmd_status
        assert args.func is _cmd_status


# ---------------------------------------------------------------------------
# 2. Exit code is always 0
# ---------------------------------------------------------------------------

class TestStatusExitCode:
    def test_exits_zero_no_config(self, capsys):
        with patch("config.CONFIG_PATH", Path("/nonexistent/config.json")):
            rc, _ = _run_status(capsys)
        assert rc == 0

    def test_exits_zero_with_config(self, capsys, tmp_path):
        fake_config = tmp_path / "config.json"
        fake_config.write_text('{"version": 2, "web": {"port": 9000}}')
        with patch("config.CONFIG_PATH", fake_config):
            rc, _ = _run_status(capsys)
        assert rc == 0


# ---------------------------------------------------------------------------
# 3. Version string is in output
# ---------------------------------------------------------------------------

class TestStatusVersion:
    def test_version_in_output(self, capsys):
        with patch("config.CONFIG_PATH", Path("/nonexistent/config.json")):
            _, out = _run_status(capsys)
        assert _version.__version__ in out

    def test_chatwire_prefix_in_output(self, capsys):
        with patch("config.CONFIG_PATH", Path("/nonexistent/config.json")):
            _, out = _run_status(capsys)
        assert "chatwire" in out


# ---------------------------------------------------------------------------
# 4. Config path in output — absent case
# ---------------------------------------------------------------------------

class TestStatusNoConfig:
    def test_no_config_message_shown(self, capsys):
        with patch("config.CONFIG_PATH", Path("/nonexistent/config.json")):
            _, out = _run_status(capsys)
        assert "not found" in out.lower() or "setup" in out.lower()


# ---------------------------------------------------------------------------
# 5. Port shown when config is present
# ---------------------------------------------------------------------------

class TestStatusWithConfig:
    def test_config_path_shown(self, capsys, tmp_path):
        fake_config = tmp_path / "config.json"
        fake_config.write_text('{"version": 2, "web": {"port": 9001}}')
        with patch("config.CONFIG_PATH", fake_config):
            _, out = _run_status(capsys)
        assert str(fake_config) in out

    def test_port_shown(self, capsys, tmp_path):
        fake_config = tmp_path / "config.json"
        fake_config.write_text('{"version": 2, "web": {"port": 9001}}')
        with patch("config.CONFIG_PATH", fake_config):
            _, out = _run_status(capsys)
        assert "9001" in out

    def test_default_port_shown_when_no_web_section(self, capsys, tmp_path):
        fake_config = tmp_path / "config.json"
        fake_config.write_text('{"version": 2}')
        with patch("config.CONFIG_PATH", fake_config):
            _, out = _run_status(capsys)
        assert "8723" in out


# ---------------------------------------------------------------------------
# 6. Plugins section
# ---------------------------------------------------------------------------

class TestStatusPlugins:
    def test_no_plugins_message(self, capsys):
        with patch("config.CONFIG_PATH", Path("/nonexistent/config.json")):
            with patch("chatwire_cli._list_installed_plugins", return_value=[]):
                _, out = _run_status(capsys)
        assert "none" in out.lower()

    def test_plugins_listed(self, capsys):
        fake_plugins = ["chatwire-telegram", "chatwire-webhook"]
        with patch("config.CONFIG_PATH", Path("/nonexistent/config.json")):
            with patch("chatwire_cli._list_installed_plugins", return_value=fake_plugins):
                _, out = _run_status(capsys)
        assert "chatwire-telegram" in out
        assert "chatwire-webhook" in out

    def test_plugin_count_shown(self, capsys):
        fake_plugins = ["chatwire-telegram", "chatwire-webhook"]
        with patch("config.CONFIG_PATH", Path("/nonexistent/config.json")):
            with patch("chatwire_cli._list_installed_plugins", return_value=fake_plugins):
                _, out = _run_status(capsys)
        assert "2" in out


# ---------------------------------------------------------------------------
# 7. Agents section only on macOS
# ---------------------------------------------------------------------------

class TestStatusAgents:
    def test_no_agents_section_on_linux(self, capsys):
        with patch("sys.platform", "linux"):
            with patch("config.CONFIG_PATH", Path("/nonexistent/config.json")):
                _, out = _run_status(capsys)
        # On non-macOS, "Agents:" must not appear
        assert "Agents:" not in out

    def test_agents_section_on_darwin(self, capsys):
        with patch("sys.platform", "darwin"):
            with patch("config.CONFIG_PATH", Path("/nonexistent/config.json")):
                # Patch _agent_path to return a non-existent path (no real plists)
                with patch("chatwire_cli._agent_path",
                           side_effect=lambda prefix, name: Path(f"/fake/{prefix}.{name}.plist")):
                    _, out = _run_status(capsys)
        assert "Agents:" in out

    def test_agent_checkmark_when_plist_exists(self, capsys, tmp_path):
        fake_plist = tmp_path / "dev.chatwire.bridge.plist"
        fake_plist.write_text("")
        with patch("sys.platform", "darwin"):
            with patch("config.CONFIG_PATH", Path("/nonexistent/config.json")):
                with patch("chatwire_cli._agent_path",
                           side_effect=lambda prefix, name: (
                               fake_plist if name == "bridge"
                               else Path(f"/fake/{prefix}.{name}.plist")
                           )):
                    _, out = _run_status(capsys)
        # At least one ✓ should be present for the existing plist
        assert "✓" in out

    def test_agent_cross_when_plist_missing(self, capsys):
        with patch("sys.platform", "darwin"):
            with patch("config.CONFIG_PATH", Path("/nonexistent/config.json")):
                with patch("chatwire_cli._agent_path",
                           side_effect=lambda prefix, name: Path(f"/nonexistent/{name}.plist")):
                    _, out = _run_status(capsys)
        assert "✗" in out


# ---------------------------------------------------------------------------
# 8. _uninstall_paths() includes img_cache (Phase 48 gap closed)
# ---------------------------------------------------------------------------

class TestUninstallPathsImgCache:
    def test_img_cache_key_present(self):
        paths = _uninstall_paths()
        assert "img_cache" in paths

    def test_img_cache_inside_chatwire_dir(self):
        paths = _uninstall_paths()
        assert paths["img_cache"].parent == paths["chatwire_dir"]
        assert paths["img_cache"].name == "img_cache"
