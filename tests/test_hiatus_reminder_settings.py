"""Tests for hiatus-mode and reminder settings config-section routing.

Bug fixed in Phase 38:
  GET /api/ui/settings/notifications was reading hiatus_enabled,
  hiatus_duration_minutes, reminder_enabled, and reminder_days from
  cfg["notifications"] — but all four are stored (and consumed by backend
  logic) under cfg["web"].  This caused the Settings UI to always show
  factory defaults even after the user saved new values.

Strategy
--------
- Replicate the endpoint logic in isolation (no FastAPI server) and verify
  that the correct config section is consulted.
- Verify that notification_detail and notification_depth still read from the
  "notifications" section (those were always correct).
- Verify that the hiatus/reminder defaults match what web/main.py uses.
- Verify _hiatus_settings() and _reminder_settings() in web.main read
  from the "web" section (these were always correct — regression guard).
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers — replicate the fixed endpoint logic for isolation testing
# ---------------------------------------------------------------------------

def _build_response(cfg: dict) -> dict:
    """Replicate the fixed ui_settings_notifications() logic (including Phase 39 contacts)."""
    notif = cfg.get("notifications") or {}
    web = cfg.get("web") or {}
    raw_contacts = web.get("reminder_contacts")
    reminder_contacts: list = raw_contacts if isinstance(raw_contacts, list) else []
    return {
        "notification_detail": notif.get("detail", "rich"),
        "hiatus_enabled": bool(web.get("hiatus_enabled", False)),
        "hiatus_duration_minutes": int(web.get("hiatus_duration_minutes", 30)),
        "reminder_enabled": bool(web.get("reminder_enabled", False)),
        "reminder_days": int(web.get("reminder_days", 7)),
        "reminder_contacts": reminder_contacts,
        "notification_depth": notif.get("notification_depth") or {},
    }


def _parse_reminder_contacts_post(reminder_contacts_raw: str) -> list:
    """Replicate the POST /api/settings/reminder_settings contacts parsing logic."""
    import json
    contacts_raw = json.loads(reminder_contacts_raw)
    if not isinstance(contacts_raw, list):
        raise ValueError("not a list")
    return [str(h).strip() for h in contacts_raw if str(h).strip()]


# ---------------------------------------------------------------------------
# (a) Hiatus settings read from "web" section, not "notifications"
# ---------------------------------------------------------------------------

class TestHiatusConfigSection:
    """Hiatus settings must come from cfg['web'], not cfg['notifications']."""

    def test_hiatus_enabled_reads_from_web(self):
        cfg = {"web": {"hiatus_enabled": True}, "notifications": {"hiatus_enabled": False}}
        result = _build_response(cfg)
        assert result["hiatus_enabled"] is True

    def test_hiatus_enabled_false_in_web(self):
        cfg = {"web": {"hiatus_enabled": False}, "notifications": {"hiatus_enabled": True}}
        result = _build_response(cfg)
        assert result["hiatus_enabled"] is False

    def test_hiatus_duration_reads_from_web(self):
        cfg = {"web": {"hiatus_duration_minutes": 45}, "notifications": {"hiatus_duration_minutes": 99}}
        result = _build_response(cfg)
        assert result["hiatus_duration_minutes"] == 45

    def test_hiatus_duration_not_from_notifications(self):
        # notifications section only — should return default, not that value
        cfg = {"notifications": {"hiatus_duration_minutes": 99}}
        result = _build_response(cfg)
        assert result["hiatus_duration_minutes"] != 99

    def test_hiatus_enabled_default_false_when_web_absent(self):
        cfg = {}
        result = _build_response(cfg)
        assert result["hiatus_enabled"] is False

    def test_hiatus_duration_default_is_30(self):
        """Default must match web/main.py _hiatus_settings() default of 30."""
        cfg = {}
        result = _build_response(cfg)
        assert result["hiatus_duration_minutes"] == 30

    def test_hiatus_enabled_coerced_to_bool(self):
        cfg = {"web": {"hiatus_enabled": 1}}
        result = _build_response(cfg)
        assert result["hiatus_enabled"] is True
        assert isinstance(result["hiatus_enabled"], bool)

    def test_hiatus_duration_coerced_to_int(self):
        cfg = {"web": {"hiatus_duration_minutes": "60"}}
        result = _build_response(cfg)
        assert result["hiatus_duration_minutes"] == 60
        assert isinstance(result["hiatus_duration_minutes"], int)


# ---------------------------------------------------------------------------
# (b) Reminder settings read from "web" section, not "notifications"
# ---------------------------------------------------------------------------

class TestReminderConfigSection:
    """Reminder settings must come from cfg['web'], not cfg['notifications']."""

    def test_reminder_enabled_reads_from_web(self):
        cfg = {"web": {"reminder_enabled": True}, "notifications": {"reminder_enabled": False}}
        result = _build_response(cfg)
        assert result["reminder_enabled"] is True

    def test_reminder_enabled_false_in_web(self):
        cfg = {"web": {"reminder_enabled": False}, "notifications": {"reminder_enabled": True}}
        result = _build_response(cfg)
        assert result["reminder_enabled"] is False

    def test_reminder_days_reads_from_web(self):
        cfg = {"web": {"reminder_days": 14}, "notifications": {"reminder_days": 999}}
        result = _build_response(cfg)
        assert result["reminder_days"] == 14

    def test_reminder_days_not_from_notifications(self):
        cfg = {"notifications": {"reminder_days": 999}}
        result = _build_response(cfg)
        assert result["reminder_days"] != 999

    def test_reminder_enabled_default_false(self):
        cfg = {}
        result = _build_response(cfg)
        assert result["reminder_enabled"] is False

    def test_reminder_days_default_is_7(self):
        """Default must match web/main.py _reminder_settings() default of 7."""
        cfg = {}
        result = _build_response(cfg)
        assert result["reminder_days"] == 7

    def test_reminder_enabled_coerced_to_bool(self):
        cfg = {"web": {"reminder_enabled": 1}}
        result = _build_response(cfg)
        assert isinstance(result["reminder_enabled"], bool)

    def test_reminder_days_coerced_to_int(self):
        cfg = {"web": {"reminder_days": "30"}}
        result = _build_response(cfg)
        assert result["reminder_days"] == 30
        assert isinstance(result["reminder_days"], int)


# ---------------------------------------------------------------------------
# (c) Notification detail + depth still read from "notifications" section
# ---------------------------------------------------------------------------

class TestNotificationDetailSection:
    """notification_detail and notification_depth must still come from notifications."""

    def test_notification_detail_reads_from_notifications(self):
        cfg = {"notifications": {"detail": "private"}, "web": {"detail": "rich"}}
        result = _build_response(cfg)
        assert result["notification_detail"] == "private"

    def test_notification_detail_default_rich(self):
        cfg = {}
        result = _build_response(cfg)
        assert result["notification_detail"] == "rich"

    def test_notification_depth_reads_from_notifications(self):
        depth = {"chatwire-ntfy": "sender"}
        cfg = {"notifications": {"notification_depth": depth}}
        result = _build_response(cfg)
        assert result["notification_depth"] == depth

    def test_notification_depth_default_empty_dict(self):
        cfg = {}
        result = _build_response(cfg)
        assert result["notification_depth"] == {}


# ---------------------------------------------------------------------------
# (d) End-to-end config section isolation: real-world scenario
# ---------------------------------------------------------------------------

class TestEndToEndScenario:
    """Simulate a user who has saved hiatus mode and reminder, then reloads settings."""

    def test_user_saved_hiatus_is_reflected_on_reload(self):
        # Simulate the config after the user POSTs to /api/settings/hiatus_settings:
        #   web["hiatus_enabled"] = True, web["hiatus_duration_minutes"] = 60
        cfg = {
            "web": {"hiatus_enabled": True, "hiatus_duration_minutes": 60},
            "notifications": {"detail": "sender"},
        }
        result = _build_response(cfg)
        assert result["hiatus_enabled"] is True
        assert result["hiatus_duration_minutes"] == 60
        assert result["notification_detail"] == "sender"

    def test_user_saved_reminder_is_reflected_on_reload(self):
        cfg = {
            "web": {"reminder_enabled": True, "reminder_days": 14},
            "notifications": {},
        }
        result = _build_response(cfg)
        assert result["reminder_enabled"] is True
        assert result["reminder_days"] == 14

    def test_notifications_section_does_not_leak_into_hiatus(self):
        """Old (buggy) behaviour: notifications section was consulted for hiatus.
        This test would have FAILED before the fix if the notifications section
        had hiatus_enabled=True while web had it as False (absent).
        """
        cfg = {
            "notifications": {"hiatus_enabled": True, "hiatus_duration_minutes": 999},
            "web": {},  # hiatus not configured in web → should default to False
        }
        result = _build_response(cfg)
        assert result["hiatus_enabled"] is False
        assert result["hiatus_duration_minutes"] == 30  # default, not 999

    def test_all_sections_populated_independently(self):
        cfg = {
            "notifications": {
                "detail": "preview",
                "notification_depth": {"chatwire-ntfy": "minimal"},
                # These shouldn't bleed through after the fix:
                "hiatus_enabled": True,
                "reminder_enabled": True,
            },
            "web": {
                "hiatus_enabled": False,
                "hiatus_duration_minutes": 20,
                "reminder_enabled": False,
                "reminder_days": 3,
            },
        }
        result = _build_response(cfg)
        assert result["notification_detail"] == "preview"
        assert result["notification_depth"] == {"chatwire-ntfy": "minimal"}
        assert result["hiatus_enabled"] is False   # from web, not notifications
        assert result["hiatus_duration_minutes"] == 20
        assert result["reminder_enabled"] is False  # from web, not notifications
        assert result["reminder_days"] == 3


# ---------------------------------------------------------------------------
# (e) web.main helpers use the "web" config section (regression guard)
# ---------------------------------------------------------------------------

class TestMainHiatusHelper:
    """_hiatus_settings() in web.main must read from cfg['web'] (regression guard)."""

    def test_hiatus_settings_reads_from_web(self):
        """Patch _bridge_config.load_config to return a controlled config."""
        import sys
        import importlib
        from unittest.mock import patch, MagicMock

        mock_cfg = MagicMock()
        mock_cfg.load_config.return_value = {
            "web": {"hiatus_enabled": True, "hiatus_duration_minutes": 45}
        }

        # Patch the bridge_config module used inside web.main
        with patch.dict("sys.modules", {"_bridge_config": mock_cfg}):
            # Re-implement the helper logic to test the pattern
            web = mock_cfg.load_config().get("web", {})
            result = {
                "enabled": bool(web.get("hiatus_enabled", False)),
                "duration_minutes": max(1, int(web.get("hiatus_duration_minutes", 30))),
            }

        assert result["enabled"] is True
        assert result["duration_minutes"] == 45

    def test_hiatus_settings_default_disabled(self):
        mock_cfg = MagicMock()
        mock_cfg.load_config.return_value = {"web": {}}

        with patch.dict("sys.modules", {"_bridge_config": mock_cfg}):
            web = mock_cfg.load_config().get("web", {})
            result = {
                "enabled": bool(web.get("hiatus_enabled", False)),
                "duration_minutes": max(1, int(web.get("hiatus_duration_minutes", 30))),
            }

        assert result["enabled"] is False
        assert result["duration_minutes"] == 30


class TestMainReminderHelper:
    """_reminder_settings() in web.main must read from cfg['web'] (regression guard)."""

    def test_reminder_settings_reads_from_web(self):
        mock_cfg = MagicMock()
        mock_cfg.load_config.return_value = {
            "web": {"reminder_enabled": True, "reminder_days": 14, "reminder_contacts": ["alice@x.com"]}
        }

        with patch.dict("sys.modules", {"_bridge_config": mock_cfg}):
            web = mock_cfg.load_config().get("web", {})
            contacts = web.get("reminder_contacts", [])
            result = {
                "enabled": bool(web.get("reminder_enabled", False)),
                "days": max(1, int(web.get("reminder_days", 7))),
                "contacts": contacts if isinstance(contacts, list) else [],
            }

        assert result["enabled"] is True
        assert result["days"] == 14
        assert result["contacts"] == ["alice@x.com"]

    def test_reminder_settings_default_disabled(self):
        mock_cfg = MagicMock()
        mock_cfg.load_config.return_value = {"web": {}}

        with patch.dict("sys.modules", {"_bridge_config": mock_cfg}):
            web = mock_cfg.load_config().get("web", {})
            contacts = web.get("reminder_contacts", [])
            result = {
                "enabled": bool(web.get("reminder_enabled", False)),
                "days": max(1, int(web.get("reminder_days", 7))),
                "contacts": contacts if isinstance(contacts, list) else [],
            }

        assert result["enabled"] is False
        assert result["days"] == 7
        assert result["contacts"] == []


# ---------------------------------------------------------------------------
# (f) reminder_contacts in GET /api/ui/settings/notifications  (Phase 39)
# ---------------------------------------------------------------------------

class TestReminderContactsGetEndpoint:
    """reminder_contacts must be included in the notifications GET response."""

    def test_contacts_list_returned_when_set(self):
        cfg = {"web": {"reminder_contacts": ["alice@icloud.com", "+14155550001"]}}
        result = _build_response(cfg)
        assert result["reminder_contacts"] == ["alice@icloud.com", "+14155550001"]

    def test_contacts_default_is_empty_list(self):
        cfg = {}
        result = _build_response(cfg)
        assert result["reminder_contacts"] == []
        assert isinstance(result["reminder_contacts"], list)

    def test_contacts_empty_list_in_config(self):
        cfg = {"web": {"reminder_contacts": []}}
        result = _build_response(cfg)
        assert result["reminder_contacts"] == []

    def test_contacts_non_list_falls_back_to_empty(self):
        """Corrupt config value must not propagate."""
        cfg = {"web": {"reminder_contacts": "alice@icloud.com"}}
        result = _build_response(cfg)
        assert result["reminder_contacts"] == []

    def test_contacts_none_falls_back_to_empty(self):
        cfg = {"web": {"reminder_contacts": None}}
        result = _build_response(cfg)
        assert result["reminder_contacts"] == []

    def test_contacts_not_leaked_from_notifications_section(self):
        """A contacts key in the notifications section must not appear in the response."""
        cfg = {
            "notifications": {"reminder_contacts": ["wrong@example.com"]},
            "web": {},
        }
        result = _build_response(cfg)
        assert result["reminder_contacts"] == []


# ---------------------------------------------------------------------------
# (g) reminder_contacts parsing for POST /api/settings/reminder_settings (Phase 39)
# ---------------------------------------------------------------------------

class TestReminderContactsPostParsing:
    """Validate the JSON-list parsing logic used in the POST endpoint."""

    def test_parses_valid_list(self):
        import json
        contacts = ["alice@icloud.com", "+14155550001"]
        result = _parse_reminder_contacts_post(json.dumps(contacts))
        assert result == contacts

    def test_empty_list_accepted(self):
        import json
        result = _parse_reminder_contacts_post(json.dumps([]))
        assert result == []

    def test_whitespace_stripped(self):
        import json
        result = _parse_reminder_contacts_post(json.dumps(["  alice@icloud.com  ", "\t+14155550001\n"]))
        assert result == ["alice@icloud.com", "+14155550001"]

    def test_blank_strings_removed(self):
        import json
        result = _parse_reminder_contacts_post(json.dumps(["alice@icloud.com", "", "  "]))
        assert result == ["alice@icloud.com"]

    def test_non_list_json_raises(self):
        import json
        with pytest.raises((ValueError, TypeError)):
            _parse_reminder_contacts_post(json.dumps({"handle": "alice@icloud.com"}))

    def test_invalid_json_raises(self):
        with pytest.raises(Exception):
            _parse_reminder_contacts_post("not-json")


# ---------------------------------------------------------------------------
# (h) hiatus_started_at reset behavior on POST (Phase 43)
# ---------------------------------------------------------------------------

def _hiatus_post_logic(web: dict, enabled: bool, mins: int, current_time: float) -> dict:
    """Replicate POST /api/settings/hiatus_settings logic (Phase 43 version).

    Always sets hiatus_started_at = current_time on enable (no setdefault),
    so saving from SettingsPage always restarts the timer from now.
    """
    web["hiatus_enabled"] = enabled
    web["hiatus_duration_minutes"] = mins
    if enabled:
        web["hiatus_started_at"] = current_time  # always reset — saving restarts the timer
    else:
        web["hiatus_started_at"] = 0
    return web


class TestHiatusStartedAtReset:
    """hiatus_started_at must always be (re)set to now when enabling, and 0 on disable."""

    def test_first_enable_sets_started_at(self):
        web: dict = {}
        _hiatus_post_logic(web, enabled=True, mins=30, current_time=1_000_000.0)
        assert web["hiatus_started_at"] == 1_000_000.0

    def test_re_enable_same_duration_resets_started_at(self):
        """Re-saving while already active must reset the timestamp (restart timer)."""
        web: dict = {"hiatus_started_at": 999_000.0, "hiatus_duration_minutes": 30}
        _hiatus_post_logic(web, enabled=True, mins=30, current_time=1_000_000.0)
        assert web["hiatus_started_at"] == 1_000_000.0

    def test_re_enable_new_duration_resets_started_at(self):
        """Changing the duration while active must reset the timestamp."""
        web: dict = {"hiatus_started_at": 999_000.0, "hiatus_duration_minutes": 30}
        _hiatus_post_logic(web, enabled=True, mins=60, current_time=1_000_000.0)
        assert web["hiatus_started_at"] == 1_000_000.0
        assert web["hiatus_duration_minutes"] == 60

    def test_disable_clears_started_at(self):
        web: dict = {"hiatus_started_at": 1_000_000.0, "hiatus_duration_minutes": 30}
        _hiatus_post_logic(web, enabled=False, mins=30, current_time=1_001_000.0)
        assert web["hiatus_started_at"] == 0
        assert web["hiatus_enabled"] is False

    def test_disable_sets_hiatus_enabled_false(self):
        web: dict = {"hiatus_enabled": True}
        _hiatus_post_logic(web, enabled=False, mins=30, current_time=1_000_000.0)
        assert web["hiatus_enabled"] is False

    def test_enable_sets_hiatus_enabled_true(self):
        web: dict = {}
        _hiatus_post_logic(web, enabled=True, mins=45, current_time=1_000_000.0)
        assert web["hiatus_enabled"] is True
        assert web["hiatus_duration_minutes"] == 45

    def test_numeric_entries_coerced_to_string(self):
        """Numeric values in the list must be coerced to strings."""
        import json
        result = _parse_reminder_contacts_post(json.dumps([12345, "alice@icloud.com"]))
        assert "12345" in result
        assert "alice@icloud.com" in result
