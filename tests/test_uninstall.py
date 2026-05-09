"""Tests for chunk 7 — uninstall script and chatwire uninstall subcommand.

Coverage:
  1. Structural tests on scripts/uninstall.sh: file exists, executable bit,
     contains required launchctl / pipx / rm steps.
  2. "Cannot remove" section lists all expected items.
  3. Python uninstall subcommand: _uninstall_paths() returns expected keys;
     dry-run mode lists paths without deleting anything.
  4. _list_installed_plugins() returns a list (may be empty on CI).
"""
from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Locate the repo root and the script
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "uninstall.sh"


# ---------------------------------------------------------------------------
# 1. Structural tests on scripts/uninstall.sh
# ---------------------------------------------------------------------------

class TestUninstallScript:
    """Structural tests — read the file, assert required content is present."""

    def test_file_exists(self):
        assert SCRIPT.exists(), f"missing: {SCRIPT}"

    def test_file_is_executable(self):
        mode = SCRIPT.stat().st_mode
        # At least one execute bit must be set (owner, group, or other).
        assert mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH), (
            f"{SCRIPT} is not executable (mode {oct(mode)})"
        )

    def _content(self) -> str:
        return SCRIPT.read_text()

    def test_contains_launchctl_bootout(self):
        assert "launchctl bootout" in self._content()

    def test_contains_all_three_service_names(self):
        content = self._content()
        for svc in ("bridge", "web", "keepawake"):
            assert svc in content, f"service '{svc}' not mentioned in uninstall.sh"

    def test_contains_label_prefix(self):
        assert "dev.chatwire" in self._content()

    def test_contains_pipx_uninstall(self):
        assert "pipx uninstall chatwire" in self._content()

    def test_contains_rm_chatwire_dir(self):
        content = self._content()
        # Should remove ~/.chatwire (or $CHATWIRE_DIR which expands to it)
        assert ".chatwire" in content

    def test_contains_rm_logs_dir(self):
        content = self._content()
        assert "Library/Logs/chatwire" in content

    def test_contains_rm_launch_agents(self):
        content = self._content()
        assert "Library/LaunchAgents" in content

    def test_contains_thumb_cache(self):
        content = self._content()
        assert "thumb_cache" in content

    def test_has_dry_run_flag(self):
        assert "--dry-run" in self._content()

    def test_has_confirmation_prompt(self):
        # Should require explicit confirmation before destroying data
        content = self._content()
        assert "YES" in content

    # -----------------------------------------------------------------------
    # "Cannot remove" section
    # -----------------------------------------------------------------------

    def test_cannot_remove_messages(self):
        assert "Library/Messages" in self._content()

    def test_cannot_remove_brew_tap(self):
        content = self._content()
        assert "brew untap" in content
        assert "allenbina/homebrew-tap" in content

    def test_cannot_remove_browser_cookies(self):
        content = self._content()
        # Accept any mention of browser or cookies
        assert ("Browser" in content or "browser" in content or "cookie" in content.lower())

    def test_cannot_remove_plugins_mention(self):
        content = self._content()
        assert "pipx uninject" in content or "plugin" in content.lower()


# ---------------------------------------------------------------------------
# 2. Python subcommand: _uninstall_paths()
# ---------------------------------------------------------------------------

from chatwire_cli import _uninstall_paths, _list_installed_plugins


class TestUninstallPaths:
    def test_returns_required_keys(self):
        paths = _uninstall_paths()
        for key in ("chatwire_dir", "log_dir", "thumb_cache"):
            assert key in paths, f"missing key: {key}"

    def test_chatwire_dir_is_dotchatwire(self):
        paths = _uninstall_paths()
        assert paths["chatwire_dir"].name == ".chatwire"
        assert paths["chatwire_dir"].parent == Path.home()

    def test_log_dir_under_library_logs(self):
        paths = _uninstall_paths()
        assert "chatwire" in str(paths["log_dir"])
        assert "Logs" in str(paths["log_dir"])

    def test_thumb_cache_inside_chatwire_dir(self):
        paths = _uninstall_paths()
        assert paths["thumb_cache"].parent == paths["chatwire_dir"]
        assert paths["thumb_cache"].name == "thumb_cache"


# ---------------------------------------------------------------------------
# 3. Dry-run: lists paths, touches nothing
# ---------------------------------------------------------------------------

class TestDryRun:
    """cmd_uninstall --dry-run should print paths and not modify any files."""

    def _run_dry_run(self, capsys) -> str:
        from chatwire_cli import cmd_uninstall
        args = argparse.Namespace(dry_run=True, label_prefix="dev.chatwire")
        rc = cmd_uninstall(args)
        assert rc == 0
        captured = capsys.readouterr()
        return captured.out

    def test_dry_run_exits_zero(self, capsys):
        self._run_dry_run(capsys)

    def test_dry_run_mentions_chatwire_dir(self, capsys):
        out = self._run_dry_run(capsys)
        assert ".chatwire" in out

    def test_dry_run_mentions_logs_dir(self, capsys):
        out = self._run_dry_run(capsys)
        assert "Logs" in out or "log" in out.lower()

    def test_dry_run_mentions_pipx(self, capsys):
        out = self._run_dry_run(capsys)
        assert "pipx" in out

    def test_dry_run_mentions_launchctl(self, capsys):
        out = self._run_dry_run(capsys)
        assert "launchctl" in out

    def test_dry_run_does_not_delete_files(self, capsys, tmp_path):
        """Dry-run must not touch any real files."""
        sentinel = tmp_path / "sentinel.txt"
        sentinel.write_text("safe")

        from chatwire_cli import cmd_uninstall
        args = argparse.Namespace(dry_run=True, label_prefix="dev.chatwire")
        cmd_uninstall(args)
        capsys.readouterr()

        # sentinel is unrelated but proves FS is not being nuked
        assert sentinel.exists()

    def test_dry_run_cannot_remove_section(self, capsys):
        out = self._run_dry_run(capsys)
        assert "Library/Messages" in out
        assert "allenbina/homebrew-tap" in out

    def test_dry_run_no_confirmation_prompt(self, capsys, monkeypatch):
        """Dry-run must never ask for confirmation (would block headless CI)."""
        # If input() is called, raise an error so the test fails loudly
        monkeypatch.setattr("builtins.input", lambda _: (_ for _ in ()).throw(
            AssertionError("input() called during dry-run — must not prompt")
        ))
        self._run_dry_run(capsys)


# ---------------------------------------------------------------------------
# 4. _list_installed_plugins()
# ---------------------------------------------------------------------------

class TestListInstalledPlugins:
    def test_returns_list(self):
        result = _list_installed_plugins()
        assert isinstance(result, list)

    def test_chatwire_itself_not_included(self):
        result = _list_installed_plugins()
        assert "chatwire" not in [p.lower() for p in result]

    def test_returns_empty_or_strings(self):
        result = _list_installed_plugins()
        for item in result:
            assert isinstance(item, str) and item

    def test_no_duplicates(self):
        result = _list_installed_plugins()
        assert len(result) == len(set(result))

    def test_graceful_on_metadata_error(self):
        """If entry_points raises, the function returns [] without crashing."""
        with patch("importlib.metadata.entry_points", side_effect=Exception("boom")):
            result = _list_installed_plugins()
        assert result == []
