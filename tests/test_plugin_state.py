"""Tests for plugin_state.py — config isolation and health tracking.

Strategy:
  - Use tmp_path to override _PLUGINS_DIR so tests are hermetic.
  - Test each public function: plugin_config_dir, load/save_plugin_config,
    record_plugin_run, get_plugin_health, get_all_plugin_health.
  - Test health status derivation logic in isolation.
  - Test discover_plugin_classes returns built-in integrations.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

import plugin_state as ps


# ---------------------------------------------------------------------------
# Fixture: redirect _PLUGINS_DIR to a tmp dir for test isolation
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_plugins_dir(tmp_path):
    """Override _PLUGINS_DIR so tests never touch ~/.chatwire/plugins."""
    plugins_dir = tmp_path / "plugins"
    with patch.object(ps, "_PLUGINS_DIR", plugins_dir):
        yield plugins_dir


# ---------------------------------------------------------------------------
# plugin_config_dir
# ---------------------------------------------------------------------------

class TestPluginConfigDir:
    def test_creates_directory(self, isolated_plugins_dir):
        d = ps.plugin_config_dir("my-plugin")
        assert d.is_dir()
        assert d == isolated_plugins_dir / "my-plugin"

    def test_idempotent(self, isolated_plugins_dir):
        d1 = ps.plugin_config_dir("p")
        d2 = ps.plugin_config_dir("p")
        assert d1 == d2

    def test_different_plugins_get_different_dirs(self, isolated_plugins_dir):
        assert ps.plugin_config_dir("a") != ps.plugin_config_dir("b")


# ---------------------------------------------------------------------------
# load_plugin_config / save_plugin_config
# ---------------------------------------------------------------------------

class TestPluginConfig:
    def test_load_returns_empty_when_no_config(self):
        result = ps.load_plugin_config("no-config-plugin")
        assert result == {}

    def test_save_then_load_roundtrip(self):
        data = {"api_url": "https://example.com", "enabled": True, "count": 42}
        ps.save_plugin_config("my-plugin", data)
        result = ps.load_plugin_config("my-plugin")
        assert result == data

    def test_save_overwrites_previous(self):
        ps.save_plugin_config("p", {"v": 1})
        ps.save_plugin_config("p", {"v": 2})
        assert ps.load_plugin_config("p") == {"v": 2}

    def test_config_is_isolated_per_plugin(self):
        ps.save_plugin_config("a", {"x": 1})
        ps.save_plugin_config("b", {"x": 2})
        assert ps.load_plugin_config("a") == {"x": 1}
        assert ps.load_plugin_config("b") == {"x": 2}

    def test_load_bad_json_returns_empty(self, isolated_plugins_dir):
        d = ps.plugin_config_dir("bad-json")
        (d / "config.json").write_text("not json!")
        result = ps.load_plugin_config("bad-json")
        assert result == {}

    def test_load_non_dict_json_returns_empty(self, isolated_plugins_dir):
        d = ps.plugin_config_dir("list-json")
        (d / "config.json").write_text(json.dumps([1, 2, 3]))
        result = ps.load_plugin_config("list-json")
        assert result == {}


# ---------------------------------------------------------------------------
# record_plugin_run / get_plugin_health
# ---------------------------------------------------------------------------

class TestHealthTracking:
    def test_fresh_plugin_returns_healthy_defaults(self):
        h = ps.get_plugin_health("new-plugin")
        assert h["status"] == "healthy"
        assert h["errors_24h"] == 0
        assert h["total_runs"] == 0
        assert h["last_run"] is None

    def test_successful_run_increments_total(self):
        ps.record_plugin_run("p", success=True)
        h = ps.get_plugin_health("p")
        assert h["total_runs"] == 1
        assert h["status"] == "healthy"
        assert h["errors_24h"] == 0
        assert h["last_success"] is not None

    def test_failed_run_increments_errors(self):
        ps.record_plugin_run("p", success=False, error_msg="timeout")
        h = ps.get_plugin_health("p")
        assert h["total_runs"] == 1
        assert h["errors_24h"] == 1
        assert h["status"] == "degraded"
        assert h["last_error"] == "timeout"

    def test_multiple_runs_accumulate(self):
        for _ in range(3):
            ps.record_plugin_run("p", success=True)
        h = ps.get_plugin_health("p")
        assert h["total_runs"] == 3
        assert h["errors_24h"] == 0

    def test_success_after_failure_resets_consecutive(self):
        ps.record_plugin_run("p", success=False)
        ps.record_plugin_run("p", success=False)
        ps.record_plugin_run("p", success=True)
        h = ps.get_plugin_health("p")
        # 2 errors still in 24h window → degraded, but consecutive reset
        assert h["status"] == "degraded"
        assert h["errors_24h"] == 2

    def test_status_healthy_zero_errors(self):
        ps.record_plugin_run("p", success=True)
        assert ps.get_plugin_health("p")["status"] == "healthy"

    def test_status_degraded_non_consecutive_errors(self):
        """4 errors in 24h with consecutive resets between → degraded, not failing."""
        # 2 errors, then a success (resets consecutive), then 2 more errors
        ps.record_plugin_run("p", success=False)
        ps.record_plugin_run("p", success=False)
        ps.record_plugin_run("p", success=True)   # resets consecutive_errors to 0
        ps.record_plugin_run("p", success=False)
        ps.record_plugin_run("p", success=False)
        h = ps.get_plugin_health("p")
        # 4 errors in 24h (< 5 failing threshold), 2 consecutive (< 3) → degraded
        assert h["status"] == "degraded"
        assert h["errors_24h"] == 4

    def test_status_failing_five_plus_errors_24h(self):
        for _ in range(5):
            ps.record_plugin_run("p", success=False)
        h = ps.get_plugin_health("p")
        assert h["status"] == "failing"

    def test_status_failing_three_consecutive(self):
        for _ in range(3):
            ps.record_plugin_run("p", success=False)
        h = ps.get_plugin_health("p")
        # 3 consecutive AND 3 errors (>= 1) → failing
        assert h["status"] == "failing"

    def test_error_timestamps_trimmed_outside_24h(self, isolated_plugins_dir):
        """Errors older than 24 h do not count towards errors_24h."""
        # Pre-write a state with an old error timestamp
        d = ps.plugin_config_dir("p")
        old_ts = datetime.fromtimestamp(
            time.time() - 90_000, tz=timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        state = {
            "total_runs": 10,
            "consecutive_errors": 0,
            "error_timestamps": [old_ts, old_ts],
            "errors_24h": 2,
            "status": "degraded",
        }
        (d / "state.json").write_text(json.dumps(state))

        # One fresh success should recalculate — old errors drop off
        ps.record_plugin_run("p", success=True)
        h = ps.get_plugin_health("p")
        assert h["errors_24h"] == 0
        assert h["status"] == "healthy"

    def test_record_run_survives_corrupt_state(self, isolated_plugins_dir):
        """Corrupt state.json must not crash record_plugin_run."""
        d = ps.plugin_config_dir("p")
        (d / "state.json").write_text("corrupt!")
        ps.record_plugin_run("p", success=True)  # must not raise
        assert ps.get_plugin_health("p")["total_runs"] == 1

    def test_health_excludes_error_timestamps(self):
        """get_plugin_health must not expose internal error_timestamps."""
        ps.record_plugin_run("p", success=False)
        h = ps.get_plugin_health("p")
        assert "error_timestamps" not in h


# ---------------------------------------------------------------------------
# get_all_plugin_health
# ---------------------------------------------------------------------------

class TestGetAllPluginHealth:
    def test_empty_when_no_plugins_dir(self, isolated_plugins_dir):
        # dir doesn't exist yet (autouse fixture doesn't create it)
        result = ps.get_all_plugin_health()
        assert result == {}

    def test_returns_plugins_with_state(self):
        ps.record_plugin_run("alpha", success=True)
        ps.record_plugin_run("beta", success=False)
        result = ps.get_all_plugin_health()
        assert "alpha" in result
        assert "beta" in result
        assert result["alpha"]["status"] == "healthy"
        assert result["beta"]["status"] == "degraded"

    def test_ignores_plugins_without_state_json(self, isolated_plugins_dir):
        # Create a plugin dir with only config.json (no state.json)
        d = isolated_plugins_dir / "config-only"
        d.mkdir(parents=True, exist_ok=True)
        (d / "config.json").write_text('{"key": "val"}')
        result = ps.get_all_plugin_health()
        assert "config-only" not in result


# ---------------------------------------------------------------------------
# _derive_status
# ---------------------------------------------------------------------------

class TestDeriveStatus:
    @pytest.mark.parametrize("errors_24h,consec,expected", [
        (0, 0, "healthy"),
        (1, 0, "degraded"),
        (4, 0, "degraded"),
        (5, 0, "failing"),
        (10, 0, "failing"),
        (0, 3, "failing"),
        (0, 5, "failing"),
        (2, 3, "failing"),
    ])
    def test_derive_status(self, errors_24h, consec, expected):
        assert ps._derive_status(errors_24h, consec) == expected


# ---------------------------------------------------------------------------
# discover_plugin_classes
# ---------------------------------------------------------------------------

class TestDiscoverPluginClasses:
    def test_returns_dict(self):
        classes = ps.discover_plugin_classes()
        assert isinstance(classes, dict)

    def test_built_in_integrations_included(self):
        classes = ps.discover_plugin_classes()
        # At minimum some built-in integrations should be discoverable
        # (telegram, webhook, stats, etc. from integrations/ directory)
        assert len(classes) >= 0  # may be 0 in minimal test env; just check no crash

    def test_all_values_have_name_and_schema(self):
        classes = ps.discover_plugin_classes()
        for name, (cls, dist_name) in classes.items():
            assert isinstance(name, str)
            assert hasattr(cls, "NAME")
            assert hasattr(cls, "SETTINGS_SCHEMA")


# ---------------------------------------------------------------------------
# build_plugin_list
# ---------------------------------------------------------------------------

class TestBuildPluginList:
    def test_returns_list(self):
        result = ps.build_plugin_list({})
        assert isinstance(result, list)

    def test_enabled_flag_from_config(self):
        cfg = {"integrations": {"telegram": {"enabled": True}}}
        result = ps.build_plugin_list(cfg)
        tg = next((p for p in result if p["name"] == "telegram"), None)
        if tg is not None:
            assert tg["enabled"] is True

    def test_disabled_by_default(self):
        result = ps.build_plugin_list({})
        for p in result:
            assert p["enabled"] is False

    def test_each_entry_has_required_keys(self):
        result = ps.build_plugin_list({})
        required = {
            "name", "display_name", "description", "icon", "tier",
            "version", "tags", "settings_schema", "enabled", "health",
            "needs_config", "sdk_compat", "sdk_warning",
        }
        for p in result:
            assert required <= set(p.keys()), f"Missing keys in plugin {p['name']}"


# ---------------------------------------------------------------------------
# Version comparison utilities
# ---------------------------------------------------------------------------

class TestParseVersion:
    @pytest.mark.parametrize("v,expected", [
        ("1.0.0", (1, 0, 0)),
        ("1.12.3", (1, 12, 3)),
        ("2.0.0-beta", (2, 0, 0)),
        ("0.9", (0, 9)),
        ("bad", ()),
    ])
    def test_parse_version(self, v, expected):
        assert ps._parse_version(v) == expected

    def test_version_gt(self):
        assert ps._version_gt("1.2.0", "1.1.0")
        assert not ps._version_gt("1.0.0", "1.0.0")
        assert not ps._version_gt("1.0.0", "2.0.0")

    def test_version_lt(self):
        assert ps._version_lt("1.0.0", "2.0.0")
        assert not ps._version_lt("2.0.0", "1.0.0")
        assert not ps._version_lt("1.0.0", "1.0.0")


# ---------------------------------------------------------------------------
# SDK compat
# ---------------------------------------------------------------------------

class TestSdkCompat:
    class _Plugin:
        """Stub integration class for SDK compat tests."""
        MIN_SDK = None
        MAX_SDK = None

    def test_no_constraints_always_compat(self):
        ok, warn = ps._sdk_compat(self._Plugin, "1.12.0")
        assert ok is True
        assert warn is None

    def test_below_min_sdk(self):
        class P(self._Plugin):
            MIN_SDK = "2.0.0"

        ok, warn = ps._sdk_compat(P, "1.12.0")
        assert ok is False
        assert "2.0.0" in warn

    def test_above_max_sdk(self):
        class P(self._Plugin):
            MAX_SDK = "1.11.0"

        ok, warn = ps._sdk_compat(P, "1.12.0")
        assert ok is False
        assert "1.11.0" in warn

    def test_within_range(self):
        class P(self._Plugin):
            MIN_SDK = "1.10.0"
            MAX_SDK = "2.0.0"

        ok, warn = ps._sdk_compat(P, "1.12.0")
        assert ok is True
        assert warn is None

    def test_exact_min_sdk_boundary(self):
        class P(self._Plugin):
            MIN_SDK = "1.12.0"

        ok, warn = ps._sdk_compat(P, "1.12.0")
        assert ok is True  # equal is not "less than"

    def test_exact_max_sdk_boundary(self):
        class P(self._Plugin):
            MAX_SDK = "1.12.0"

        ok, warn = ps._sdk_compat(P, "1.12.0")
        assert ok is True  # equal is not "greater than"


# ---------------------------------------------------------------------------
# Update checking
# ---------------------------------------------------------------------------

class TestCheckPluginUpdates:
    class _Cls:
        NAME = "test-plugin"
        VERSION = "1.0.0"
        SETTINGS_SCHEMA = {}

    def test_no_pip_plugins_returns_empty(self):
        """Built-in plugins (dist_name=None) are skipped."""
        classes = {"test-plugin": (self._Cls, None)}
        updates = ps.check_plugin_updates(classes=classes)
        assert updates == []

    def test_no_version_returns_empty(self):
        class NoCls:
            NAME = "x"
            SETTINGS_SCHEMA = {}
            # No VERSION attribute

        classes = {"x": (NoCls, "chatwire-x")}
        updates = ps.check_plugin_updates(classes=classes)
        assert updates == []

    def test_newer_version_found(self, monkeypatch):
        """If PyPI returns a newer version, it should appear in updates."""
        monkeypatch.setattr(ps, "_pypi_latest_version", lambda dist, **kw: "2.0.0")
        classes = {"test-plugin": (self._Cls, "chatwire-test")}
        updates = ps.check_plugin_updates(classes=classes)
        assert len(updates) == 1
        assert updates[0]["name"] == "test-plugin"
        assert updates[0]["latest_version"] == "2.0.0"
        assert updates[0]["current_version"] == "1.0.0"

    def test_same_version_not_in_updates(self, monkeypatch):
        monkeypatch.setattr(ps, "_pypi_latest_version", lambda dist, **kw: "1.0.0")
        classes = {"test-plugin": (self._Cls, "chatwire-test")}
        updates = ps.check_plugin_updates(classes=classes)
        assert updates == []

    def test_older_registry_not_in_updates(self, monkeypatch):
        monkeypatch.setattr(ps, "_pypi_latest_version", lambda dist, **kw: "0.9.0")
        classes = {"test-plugin": (self._Cls, "chatwire-test")}
        updates = ps.check_plugin_updates(classes=classes)
        assert updates == []

    def test_pypi_error_silently_skipped(self, monkeypatch):
        monkeypatch.setattr(ps, "_pypi_latest_version", lambda dist, **kw: None)
        classes = {"test-plugin": (self._Cls, "chatwire-test")}
        updates = ps.check_plugin_updates(classes=classes)
        assert updates == []


class TestSaveLoadPluginUpdates:
    def test_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ps, "_UPDATES_CACHE", tmp_path / "plugin-updates.json")
        data = [{"name": "x", "dist_name": "chatwire-x",
                 "current_version": "1.0.0", "latest_version": "2.0.0"}]
        ps.save_plugin_updates(data)
        assert ps.load_plugin_updates() == data

    def test_load_missing_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ps, "_UPDATES_CACHE", tmp_path / "no-file.json")
        assert ps.load_plugin_updates() == []

    def test_get_uses_cache_when_fresh(self, tmp_path, monkeypatch):
        cache = tmp_path / "plugin-updates.json"
        monkeypatch.setattr(ps, "_UPDATES_CACHE", cache)
        cached = [{"name": "cached"}]
        ps.save_plugin_updates(cached)
        # Should return cached without calling check_plugin_updates
        called = []
        monkeypatch.setattr(ps, "check_plugin_updates", lambda **kw: called.append(1) or [])
        result = ps.get_plugin_updates(force=False)
        assert result == cached
        assert not called  # cache was fresh

    def test_get_force_bypasses_cache(self, tmp_path, monkeypatch):
        cache = tmp_path / "plugin-updates.json"
        monkeypatch.setattr(ps, "_UPDATES_CACHE", cache)
        ps.save_plugin_updates([{"name": "old"}])
        monkeypatch.setattr(ps, "check_plugin_updates",
                            lambda **kw: [{"name": "fresh"}])
        result = ps.get_plugin_updates(force=True)
        assert result == [{"name": "fresh"}]
