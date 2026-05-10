"""Tests for the accent color API endpoints.

Strategy: validate the color-parsing logic directly (same pattern as
test_advanced_settings.py) — no live FastAPI server needed.

Covers:
  a. GET returns empty string when accent_color is absent from config.
  b. GET returns stored value when accent_color is set.
  c. POST with valid #rrggbb persists and returns ok.
  d. POST with empty string clears the stored value.
  e. POST rejects non-hex / malformed color strings (400).
  f. POST rejects 8-digit (#rrggbbaa) colors (we only accept 6-digit).
"""
from __future__ import annotations

import re
import pytest


# ---------------------------------------------------------------------------
# Pure validation helper (mirrors the route logic)
# ---------------------------------------------------------------------------

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _validate_color(color: str) -> None:
    """Raise ValueError for invalid color values (mirrors the route guard)."""
    if color and not _HEX_RE.match(color):
        raise ValueError(f"color must be #rrggbb or empty string, got {color!r}")


def _apply_color(cfg: dict, color: str) -> dict:
    """Simulate the POST handler's config mutation."""
    _validate_color(color)
    web = cfg.setdefault("web", {})
    if color:
        web["accent_color"] = color
    else:
        web.pop("accent_color", None)
    return cfg


def _read_color(cfg: dict) -> str:
    """Simulate the GET handler's config read."""
    web = cfg.get("web") or {}
    return web.get("accent_color", "")


# ---------------------------------------------------------------------------
# GET behaviour
# ---------------------------------------------------------------------------

class TestGetAccentColor:
    def test_absent_returns_empty(self):
        assert _read_color({}) == ""

    def test_absent_web_key_returns_empty(self):
        assert _read_color({"web": {}}) == ""

    def test_null_web_returns_empty(self):
        assert _read_color({"web": None}) == ""

    def test_stored_value_returned(self):
        cfg = {"web": {"accent_color": "#ff0000"}}
        assert _read_color(cfg) == "#ff0000"

    def test_lowercase_hex_returned_as_is(self):
        cfg = {"web": {"accent_color": "#aabbcc"}}
        assert _read_color(cfg) == "#aabbcc"


# ---------------------------------------------------------------------------
# POST — valid inputs
# ---------------------------------------------------------------------------

class TestSetAccentColorValid:
    def test_valid_hex_persisted(self):
        cfg = _apply_color({}, "#bd93f9")
        assert cfg["web"]["accent_color"] == "#bd93f9"

    def test_valid_uppercase_hex(self):
        cfg = _apply_color({}, "#BD93F9")
        assert cfg["web"]["accent_color"] == "#BD93F9"

    def test_empty_string_clears_value(self):
        cfg = {"web": {"accent_color": "#ff0000"}}
        cfg = _apply_color(cfg, "")
        assert "accent_color" not in cfg["web"]

    def test_empty_string_on_absent_key_is_noop(self):
        cfg = _apply_color({}, "")
        assert cfg.get("web", {}).get("accent_color") is None

    def test_roundtrip(self):
        cfg = {}
        cfg = _apply_color(cfg, "#50fa7b")
        assert _read_color(cfg) == "#50fa7b"
        cfg = _apply_color(cfg, "")
        assert _read_color(cfg) == ""

    def test_overwrite_existing_value(self):
        cfg = {"web": {"accent_color": "#ff0000"}}
        cfg = _apply_color(cfg, "#00ff00")
        assert cfg["web"]["accent_color"] == "#00ff00"


# ---------------------------------------------------------------------------
# POST — invalid inputs
# ---------------------------------------------------------------------------

class TestSetAccentColorInvalid:
    def _assert_invalid(self, color: str):
        with pytest.raises(ValueError):
            _validate_color(color)

    def test_missing_hash_rejected(self):
        self._assert_invalid("bd93f9")

    def test_three_digit_hex_rejected(self):
        self._assert_invalid("#fff")

    def test_eight_digit_hex_rejected(self):
        self._assert_invalid("#bd93f9ff")

    def test_named_color_rejected(self):
        self._assert_invalid("red")

    def test_rgb_function_rejected(self):
        self._assert_invalid("rgb(255,0,0)")

    def test_random_string_rejected(self):
        self._assert_invalid("banana")

    def test_hash_only_rejected(self):
        self._assert_invalid("#")

    def test_five_digit_rejected(self):
        self._assert_invalid("#12345")

    def test_seven_digit_rejected(self):
        self._assert_invalid("#1234567")

    def test_valid_empty_passes(self):
        # Empty string should NOT raise
        _validate_color("")
