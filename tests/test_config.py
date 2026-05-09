"""Tests for config.py — pure functions (no subprocess, no real home dir).

Strategy:
  - _flatten_v2_to_env: truly pure (dict-in, dict-out); no patching needed.
  - _read_legacy_env: monkeypatches LEGACY_ENV_PATH to a tmp_path file.
  - save_config / load_config: monkeypatches CONFIG_DIR and CONFIG_PATH to
    tmp_path, and stubs _run_migrations to identity so no `migrations` import
    or disk side-effects are needed.
"""
import json
import os
import stat
from pathlib import Path

import pytest

import config as cfg_mod
from config import (
    CURRENT_VERSION,
    _flatten_v2_to_env,
    _read_legacy_env,
    load_config,
    save_config,
)


# ---------------------------------------------------------------------------
# _flatten_v2_to_env — truly pure, no patching
# ---------------------------------------------------------------------------

class TestFlattenV2ToEnv:
    def test_empty_config_returns_empty(self):
        assert _flatten_v2_to_env({}) == {}

    # self_handles
    def test_self_handles_list_joined(self):
        out = _flatten_v2_to_env({"self_handles": ["+15550001111", "+15550002222"]})
        assert out["SELF_HANDLES"] == "+15550001111,+15550002222"

    def test_self_handles_single(self):
        out = _flatten_v2_to_env({"self_handles": ["me@example.com"]})
        assert out["SELF_HANDLES"] == "me@example.com"

    def test_self_handles_empty_list_omitted(self):
        out = _flatten_v2_to_env({"self_handles": []})
        assert "SELF_HANDLES" not in out

    def test_self_handles_null_omitted(self):
        out = _flatten_v2_to_env({"self_handles": None})
        assert "SELF_HANDLES" not in out

    def test_self_handles_non_list_omitted(self):
        # Defensive: if someone hand-edits config with a string value.
        out = _flatten_v2_to_env({"self_handles": "bad"})
        assert "SELF_HANDLES" not in out

    # Telegram
    def test_telegram_enabled_token_present(self):
        cfg = {"integrations": {"telegram": {"enabled": True, "bot_token": "ABC:123"}}}
        out = _flatten_v2_to_env(cfg)
        assert out["TELEGRAM_BOT_TOKEN"] == "ABC:123"

    def test_telegram_disabled_no_keys(self):
        cfg = {"integrations": {"telegram": {"enabled": False, "bot_token": "ABC:123"}}}
        out = _flatten_v2_to_env(cfg)
        assert "TELEGRAM_BOT_TOKEN" not in out

    def test_telegram_enabled_no_token_no_keys(self):
        cfg = {"integrations": {"telegram": {"enabled": True}}}
        out = _flatten_v2_to_env(cfg)
        assert "TELEGRAM_BOT_TOKEN" not in out

    def test_telegram_allowed_user_ids_joined(self):
        cfg = {"integrations": {"telegram": {
            "enabled": True,
            "bot_token": "T",
            "allowed_user_ids": [111, 222, 333],
        }}}
        out = _flatten_v2_to_env(cfg)
        assert out["TELEGRAM_ALLOWED_USER_IDS"] == "111,222,333"

    def test_telegram_allowed_user_ids_empty_list(self):
        cfg = {"integrations": {"telegram": {
            "enabled": True,
            "bot_token": "T",
            "allowed_user_ids": [],
        }}}
        out = _flatten_v2_to_env(cfg)
        # Empty list → comma-join of nothing → empty string, key present.
        assert out.get("TELEGRAM_ALLOWED_USER_IDS") == ""

    def test_telegram_no_allowed_user_ids_empty_string(self):
        # allowed_user_ids absent → `tg.get(...) or []` yields [] → empty join.
        # The key IS emitted (as "") because the isinstance([], list) branch runs.
        cfg = {"integrations": {"telegram": {"enabled": True, "bot_token": "T"}}}
        out = _flatten_v2_to_env(cfg)
        assert out.get("TELEGRAM_ALLOWED_USER_IDS") == ""

    # Webhook
    def test_webhook_enabled_url_present(self):
        cfg = {"integrations": {"webhook": {"enabled": True, "url": "https://example.com/hook"}}}
        out = _flatten_v2_to_env(cfg)
        assert out["WEBHOOK_URL"] == "https://example.com/hook"

    def test_webhook_disabled_no_keys(self):
        cfg = {"integrations": {"webhook": {"enabled": False, "url": "https://example.com/hook"}}}
        out = _flatten_v2_to_env(cfg)
        assert "WEBHOOK_URL" not in out

    def test_webhook_enabled_no_url_no_keys(self):
        cfg = {"integrations": {"webhook": {"enabled": True}}}
        out = _flatten_v2_to_env(cfg)
        assert "WEBHOOK_URL" not in out

    def test_webhook_secret_forwarded(self):
        cfg = {"integrations": {"webhook": {
            "enabled": True, "url": "https://h.example.com/", "secret": "s3cr3t"
        }}}
        out = _flatten_v2_to_env(cfg)
        assert out["WEBHOOK_SECRET"] == "s3cr3t"

    def test_webhook_timeout_forwarded(self):
        cfg = {"integrations": {"webhook": {
            "enabled": True, "url": "https://h.example.com/", "timeout_s": 30
        }}}
        out = _flatten_v2_to_env(cfg)
        assert out["WEBHOOK_TIMEOUT_S"] == "30"

    def test_webhook_no_secret_key_absent(self):
        cfg = {"integrations": {"webhook": {"enabled": True, "url": "https://h.example.com/"}}}
        out = _flatten_v2_to_env(cfg)
        assert "WEBHOOK_SECRET" not in out

    # Web
    def test_web_port_forwarded(self):
        out = _flatten_v2_to_env({"web": {"port": 8080}})
        assert out["WEB_PORT"] == "8080"

    def test_web_no_port_key_absent(self):
        out = _flatten_v2_to_env({"web": {}})
        assert "WEB_PORT" not in out

    def test_vapid_public_forwarded(self):
        out = _flatten_v2_to_env({"web": {"vapid": {"public": "PUB"}}})
        assert out["VAPID_PUBLIC_KEY"] == "PUB"

    def test_vapid_private_forwarded(self):
        out = _flatten_v2_to_env({"web": {"vapid": {"private": "PRIV"}}})
        assert out["VAPID_PRIVATE_KEY"] == "PRIV"

    def test_vapid_contact_forwarded(self):
        out = _flatten_v2_to_env({"web": {"vapid": {"contact": "mailto:a@b.com"}}})
        assert out["VAPID_CONTACT"] == "mailto:a@b.com"

    def test_vapid_no_public_key_absent(self):
        out = _flatten_v2_to_env({"web": {"vapid": {}}})
        assert "VAPID_PUBLIC_KEY" not in out

    def test_secure_cookie_true_forwarded(self):
        out = _flatten_v2_to_env({"web": {"secure_cookie": True}})
        assert out["WEB_SECURE_COOKIE"] == "true"

    def test_secure_cookie_false_key_absent(self):
        out = _flatten_v2_to_env({"web": {"secure_cookie": False}})
        assert "WEB_SECURE_COOKIE" not in out

    def test_secure_cookie_absent_key_absent(self):
        out = _flatten_v2_to_env({"web": {}})
        assert "WEB_SECURE_COOKIE" not in out

    # Debug
    def test_debug_mirror_file_forwarded(self):
        out = _flatten_v2_to_env({"debug": {"mirror_file": "/tmp/mirror.jsonl"}})
        assert out["DEBUG_MIRROR_FILE"] == "/tmp/mirror.jsonl"

    def test_debug_no_mirror_file_key_absent(self):
        out = _flatten_v2_to_env({"debug": {}})
        assert "DEBUG_MIRROR_FILE" not in out

    # Passthrough / escape-hatch root keys
    def test_passthrough_root_string(self):
        out = _flatten_v2_to_env({"POLL_INTERVAL_S": "30"})
        assert out["POLL_INTERVAL_S"] == "30"

    def test_passthrough_root_int_stringified(self):
        out = _flatten_v2_to_env({"POLL_INTERVAL_S": 30})
        assert out["POLL_INTERVAL_S"] == "30"

    def test_passthrough_root_float_stringified(self):
        out = _flatten_v2_to_env({"SOME_FLOAT": 3.14})
        assert out["SOME_FLOAT"] == "3.14"

    def test_passthrough_root_bool_stringified(self):
        out = _flatten_v2_to_env({"MY_FLAG": True})
        assert out["MY_FLAG"] == "True"

    def test_passthrough_root_list_skipped(self):
        out = _flatten_v2_to_env({"MY_LIST": [1, 2, 3]})
        assert "MY_LIST" not in out

    def test_passthrough_root_dict_skipped(self):
        out = _flatten_v2_to_env({"MY_DICT": {"a": 1}})
        assert "MY_DICT" not in out

    def test_consumed_keys_not_passthrough(self):
        # 'version', 'self_handles', 'integrations', 'web', 'debug' must not
        # appear verbatim in the output even if they have scalar values.
        out = _flatten_v2_to_env({"version": 4, "self_handles": [], "integrations": {}, "web": {}, "debug": {}})
        for key in ("version", "self_handles", "integrations", "web", "debug"):
            assert key not in out

    def test_passthrough_does_not_overwrite_mapped_key(self):
        # If someone puts TELEGRAM_BOT_TOKEN at root AND has it in the
        # integrations block, the mapped value wins (setdefault behaviour).
        cfg = {
            "integrations": {"telegram": {"enabled": True, "bot_token": "MAPPED"}},
            "TELEGRAM_BOT_TOKEN": "ROOT",
        }
        out = _flatten_v2_to_env(cfg)
        assert out["TELEGRAM_BOT_TOKEN"] == "MAPPED"


# ---------------------------------------------------------------------------
# _read_legacy_env — monkeypatches LEGACY_ENV_PATH
# ---------------------------------------------------------------------------

class TestReadLegacyEnv:
    def test_absent_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cfg_mod, "LEGACY_ENV_PATH", tmp_path / ".env")
        assert _read_legacy_env() == {}

    def test_basic_key_value(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("TELEGRAM_BOT_TOKEN=ABC:123\n")
        monkeypatch.setattr(cfg_mod, "LEGACY_ENV_PATH", env_file)
        result = _read_legacy_env()
        assert result == {"TELEGRAM_BOT_TOKEN": "ABC:123"}

    def test_multiple_keys(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("KEY_A=val_a\nKEY_B=val_b\n")
        monkeypatch.setattr(cfg_mod, "LEGACY_ENV_PATH", env_file)
        result = _read_legacy_env()
        assert result == {"KEY_A": "val_a", "KEY_B": "val_b"}

    def test_skips_comment_lines(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("# this is a comment\nKEY=val\n")
        monkeypatch.setattr(cfg_mod, "LEGACY_ENV_PATH", env_file)
        result = _read_legacy_env()
        assert result == {"KEY": "val"}

    def test_skips_blank_lines(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("\n\nKEY=val\n\n")
        monkeypatch.setattr(cfg_mod, "LEGACY_ENV_PATH", env_file)
        result = _read_legacy_env()
        assert result == {"KEY": "val"}

    def test_skips_lines_without_equals(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("BADLINE\nKEY=val\n")
        monkeypatch.setattr(cfg_mod, "LEGACY_ENV_PATH", env_file)
        result = _read_legacy_env()
        assert result == {"KEY": "val"}

    def test_strips_whitespace(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("  KEY  =  val  \n")
        monkeypatch.setattr(cfg_mod, "LEGACY_ENV_PATH", env_file)
        result = _read_legacy_env()
        assert result == {"KEY": "val"}

    def test_value_with_equals(self, tmp_path, monkeypatch):
        # Only the first = is the separator; value may contain =.
        env_file = tmp_path / ".env"
        env_file.write_text("KEY=a=b=c\n")
        monkeypatch.setattr(cfg_mod, "LEGACY_ENV_PATH", env_file)
        result = _read_legacy_env()
        assert result == {"KEY": "a=b=c"}

    def test_empty_file_returns_empty(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("")
        monkeypatch.setattr(cfg_mod, "LEGACY_ENV_PATH", env_file)
        assert _read_legacy_env() == {}


# ---------------------------------------------------------------------------
# save_config / load_config — monkeypatches CONFIG_DIR + CONFIG_PATH
# ---------------------------------------------------------------------------

@pytest.fixture()
def isolated_config(tmp_path, monkeypatch):
    """Redirect all config paths to a fresh tmp_path subtree and stub out
    migrations + legacy lookups so tests are hermetic."""
    config_dir = tmp_path / "chatwire"
    config_path = config_dir / "config.json"

    monkeypatch.setattr(cfg_mod, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cfg_mod, "CONFIG_PATH", config_path)
    monkeypatch.setattr(cfg_mod, "LEGACY_CONFIG_PATHS", [])
    monkeypatch.setattr(cfg_mod, "LEGACY_ENV_PATH", tmp_path / ".env_absent")

    # Stub out _run_migrations to identity — we're not testing the migrator.
    monkeypatch.setattr(cfg_mod, "_run_migrations", lambda cfg: cfg)
    # Stub out migrate_state_dir to no-op.
    monkeypatch.setattr(cfg_mod, "migrate_state_dir", lambda: [])

    return config_path


class TestSaveConfig:
    def test_creates_config_dir(self, isolated_config):
        cfg = {"version": CURRENT_VERSION, "self_handles": ["+1555"]}
        save_config(cfg)
        assert isolated_config.exists()

    def test_writes_valid_json(self, isolated_config):
        save_config({"self_handles": ["+1555"]})
        data = json.loads(isolated_config.read_text())
        assert data["self_handles"] == ["+1555"]

    def test_stamps_current_version(self, isolated_config):
        # Even if the caller doesn't pass version, save_config injects it.
        save_config({})
        data = json.loads(isolated_config.read_text())
        assert data["version"] == CURRENT_VERSION

    def test_overrides_caller_version(self, isolated_config):
        # version in the input dict is replaced with CURRENT_VERSION.
        save_config({"version": 1})
        data = json.loads(isolated_config.read_text())
        assert data["version"] == CURRENT_VERSION

    def test_file_permissions_600(self, isolated_config):
        save_config({})
        mode = isolated_config.stat().st_mode & 0o777
        assert mode == 0o600

    def test_round_trip_preserves_nested_data(self, isolated_config):
        original = {
            "integrations": {"telegram": {"enabled": True, "bot_token": "X"}},
            "web": {"port": 9000},
        }
        save_config(original)
        data = json.loads(isolated_config.read_text())
        assert data["integrations"]["telegram"]["bot_token"] == "X"
        assert data["web"]["port"] == 9000


class TestLoadConfig:
    def test_returns_default_version_when_no_config(self, isolated_config):
        # No config file, no legacy env → minimal dict with just version.
        result = load_config()
        assert result == {"version": CURRENT_VERSION}

    def test_reads_saved_config(self, isolated_config):
        save_config({"self_handles": ["+1999"]})
        result = load_config()
        assert result["self_handles"] == ["+1999"]
        assert result["version"] == CURRENT_VERSION

    def test_load_save_roundtrip(self, isolated_config):
        payload = {
            "integrations": {"telegram": {"enabled": False}},
            "web": {"port": 8765},
        }
        save_config(payload)
        result = load_config()
        assert result["integrations"]["telegram"]["enabled"] is False
        assert result["web"]["port"] == 8765

    def test_load_falls_back_to_legacy_env(self, tmp_path, monkeypatch):
        # If no config.json and a .env exists, load returns v1-flat dict.
        env_file = tmp_path / ".env"
        env_file.write_text("TELEGRAM_BOT_TOKEN=LEGACYTOK\n")

        config_dir = tmp_path / "chatwire"
        config_path = config_dir / "config.json"

        monkeypatch.setattr(cfg_mod, "CONFIG_DIR", config_dir)
        monkeypatch.setattr(cfg_mod, "CONFIG_PATH", config_path)
        monkeypatch.setattr(cfg_mod, "LEGACY_CONFIG_PATHS", [])
        monkeypatch.setattr(cfg_mod, "LEGACY_ENV_PATH", env_file)
        monkeypatch.setattr(cfg_mod, "_run_migrations", lambda cfg: cfg)
        monkeypatch.setattr(cfg_mod, "migrate_state_dir", lambda: [])

        result = load_config()
        assert result["TELEGRAM_BOT_TOKEN"] == "LEGACYTOK"
        assert result["version"] == 1
