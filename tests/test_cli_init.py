"""Tests for chatwire init (first-run wizard)."""
from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path, monkeypatch):
    """Redirect CONFIG_DIR / CONFIG_PATH to a temp dir for every test."""
    import config as _cfg

    fake_dir = tmp_path / ".chatwire"
    fake_dir.mkdir()
    monkeypatch.setattr(_cfg, "CONFIG_DIR", fake_dir)
    monkeypatch.setattr(_cfg, "CONFIG_PATH", fake_dir / "config.json")
    # Also patch STATE_DIR so save_config doesn't touch the real home.
    monkeypatch.setattr(_cfg, "STATE_DIR", fake_dir)


def _config_path():
    import config as _cfg
    return _cfg.CONFIG_PATH


# ---------- VAPID key generation ----------

def test_vapid_key_generation():
    """Generated VAPID keys should be valid base64url strings of expected lengths."""
    from chatwire_cli import _generate_vapid_keypair

    priv, pub = _generate_vapid_keypair()

    # Both should be non-empty base64url strings (no padding)
    assert priv
    assert pub
    assert "=" not in priv
    assert "=" not in pub

    # Decode and check sizes
    # Private: DER-encoded PKCS8 EC key (variable length, typically 138 bytes for P-256)
    priv_bytes = base64.urlsafe_b64decode(priv + "==")
    assert len(priv_bytes) > 100  # DER PKCS8 P-256 is ~138 bytes

    # Public: uncompressed P-256 point = 65 bytes (0x04 + 32 + 32)
    pub_bytes = base64.urlsafe_b64decode(pub + "==")
    assert len(pub_bytes) == 65
    assert pub_bytes[0] == 0x04  # uncompressed point marker


def test_vapid_keys_are_unique():
    """Each call should produce a different keypair."""
    from chatwire_cli import _generate_vapid_keypair

    pair1 = _generate_vapid_keypair()
    pair2 = _generate_vapid_keypair()
    assert pair1 != pair2


# ---------- self_handles parsing ----------

def test_self_handles_single(monkeypatch, tmp_path):
    """Single handle is stored as a one-element list."""
    import config as _cfg
    from chatwire_cli import cmd_init
    import argparse

    monkeypatch.setattr("builtins.input", lambda prompt: "+15551234567")
    # Not on macOS for this test
    monkeypatch.setattr("sys.platform", "linux")

    args = argparse.Namespace()
    rc = cmd_init(args)
    assert rc == 0

    data = json.loads(_cfg.CONFIG_PATH.read_text())
    assert data["self_handles"] == ["+15551234567"]


def test_self_handles_multiple_strips_whitespace(monkeypatch, tmp_path):
    """Comma-separated handles are split and stripped."""
    import config as _cfg
    from chatwire_cli import cmd_init
    import argparse

    monkeypatch.setattr("builtins.input", lambda prompt: " +15551234567 , user@icloud.com , +15559876543 ")
    monkeypatch.setattr("sys.platform", "linux")

    args = argparse.Namespace()
    rc = cmd_init(args)
    assert rc == 0

    data = json.loads(_cfg.CONFIG_PATH.read_text())
    assert data["self_handles"] == ["+15551234567", "user@icloud.com", "+15559876543"]


def test_empty_handles_returns_error(monkeypatch, capsys):
    """Empty input should return 1 without writing config."""
    import config as _cfg
    from chatwire_cli import cmd_init
    import argparse

    monkeypatch.setattr("builtins.input", lambda prompt: "")
    monkeypatch.setattr("sys.platform", "linux")

    args = argparse.Namespace()
    rc = cmd_init(args)
    assert rc == 1
    assert not _cfg.CONFIG_PATH.exists()


def test_whitespace_only_handles_returns_error(monkeypatch, capsys):
    """Whitespace-only or all-empty-after-split should fail."""
    import config as _cfg
    from chatwire_cli import cmd_init
    import argparse

    monkeypatch.setattr("builtins.input", lambda prompt: " , , ")
    monkeypatch.setattr("sys.platform", "linux")

    args = argparse.Namespace()
    rc = cmd_init(args)
    assert rc == 1
    assert not _cfg.CONFIG_PATH.exists()


# ---------- Config file creation ----------

def test_config_written_with_correct_structure(monkeypatch, tmp_path):
    """Config should have version, self_handles, web.vapid keys."""
    import config as _cfg
    from chatwire_cli import cmd_init
    import argparse

    monkeypatch.setattr("builtins.input", lambda prompt: "+15551234567")
    monkeypatch.setattr("sys.platform", "linux")

    args = argparse.Namespace()
    rc = cmd_init(args)
    assert rc == 0

    data = json.loads(_cfg.CONFIG_PATH.read_text())
    assert data["version"] == 4
    assert "self_handles" in data
    assert "web" in data
    assert "vapid" in data["web"]
    assert "private" in data["web"]["vapid"]
    assert "public" in data["web"]["vapid"]
    assert "contact" in data["web"]["vapid"]
    assert data["web"]["port"] == 8723


def test_config_file_permissions(monkeypatch, tmp_path):
    """Config should be written with mode 0600."""
    import config as _cfg
    from chatwire_cli import cmd_init
    import argparse

    monkeypatch.setattr("builtins.input", lambda prompt: "+15551234567")
    monkeypatch.setattr("sys.platform", "linux")

    args = argparse.Namespace()
    cmd_init(args)

    mode = _cfg.CONFIG_PATH.stat().st_mode & 0o777
    assert mode == 0o600


# ---------- Existing config detection ----------

def test_existing_config_abort(monkeypatch, tmp_path):
    """If config exists and user says N, wizard aborts cleanly."""
    import config as _cfg
    from chatwire_cli import cmd_init
    import argparse

    # Pre-create config
    _cfg.CONFIG_PATH.write_text('{"version": 4}')

    inputs = iter(["n"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))
    monkeypatch.setattr("sys.platform", "linux")

    args = argparse.Namespace()
    rc = cmd_init(args)
    assert rc == 0

    # Config should be unchanged
    data = json.loads(_cfg.CONFIG_PATH.read_text())
    assert data == {"version": 4}


def test_existing_config_rerun(monkeypatch, tmp_path):
    """If config exists and user says y, wizard proceeds and overwrites."""
    import config as _cfg
    from chatwire_cli import cmd_init
    import argparse

    # Pre-create config
    _cfg.CONFIG_PATH.write_text('{"version": 4}')

    inputs = iter(["y", "+15559999999"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))
    monkeypatch.setattr("sys.platform", "linux")

    args = argparse.Namespace()
    rc = cmd_init(args)
    assert rc == 0

    data = json.loads(_cfg.CONFIG_PATH.read_text())
    assert data["self_handles"] == ["+15559999999"]
    assert data["version"] == 4


# ---------- main() no-config hint ----------

def test_main_no_subcommand_no_config(monkeypatch, capsys):
    """With no subcommand and no config, main should suggest chatwire init."""
    import config as _cfg
    from chatwire_cli import main

    # Ensure config doesn't exist
    if _cfg.CONFIG_PATH.exists():
        _cfg.CONFIG_PATH.unlink()

    monkeypatch.setattr("sys.argv", ["chatwire"])
    rc = main()
    assert rc == 1
    captured = capsys.readouterr()
    assert "chatwire init" in captured.out


def test_main_no_subcommand_with_config(monkeypatch, capsys):
    """With no subcommand but config exists, print help."""
    import config as _cfg
    from chatwire_cli import main

    _cfg.CONFIG_PATH.write_text('{"version": 4}')

    monkeypatch.setattr("sys.argv", ["chatwire"])
    rc = main()
    assert rc == 1
    captured = capsys.readouterr()
    # Should show usage/help, not the init hint
    assert "chatwire init" not in captured.out
