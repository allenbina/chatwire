"""Tests for the plugin-themes API endpoint (GET /api/ui/plugin-themes).

Strategy:
  - Build a minimal FastAPI test app from the api_ui router.
  - Patch importlib.metadata.entry_points to return mock entries.
  - Verify the endpoint merges SCHEMES + CSS from all loaded modules.
"""
from __future__ import annotations

import types
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import web.api_ui as _mod
from web.api_ui import router as api_router

# ---------------------------------------------------------------------------
# Test app
# ---------------------------------------------------------------------------

_test_app = FastAPI()
_test_app.include_router(api_router)
client = TestClient(_test_app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_module(schemes, css=""):
    """Return a mock module with SCHEMES and CSS attributes."""
    mod = types.ModuleType("mock_theme_plugin")
    mod.SCHEMES = schemes
    mod.CSS = css
    return mod


def _make_ep(mod):
    """Return a mock entry-point whose .load() returns *mod*."""
    ep = MagicMock()
    ep.load.return_value = mod
    return ep


# ---------------------------------------------------------------------------
# GET /plugin-themes
# ---------------------------------------------------------------------------

class TestPluginThemes:
    def test_empty_when_no_plugins_installed(self):
        with patch("importlib.metadata.entry_points", return_value=[]):
            r = client.get("/plugin-themes")
        assert r.status_code == 200
        data = r.json()
        assert data["schemes"] == []
        assert data["css"] == ""

    def test_single_plugin_returned(self):
        schemes = [
            {"name": "rose-pine", "label": "Rosé Pine", "isLight": False, "swatch": "#c4a7e7"},
        ]
        css = '[data-theme="rose-pine"] { --background: 249 22% 12%; }'
        mod = _make_module(schemes, css)
        ep = _make_ep(mod)

        with patch("importlib.metadata.entry_points", return_value=[ep]):
            r = client.get("/plugin-themes")
        assert r.status_code == 200
        data = r.json()
        assert len(data["schemes"]) == 1
        s = data["schemes"][0]
        assert s["name"] == "rose-pine"
        assert s["label"] == "Rosé Pine"
        assert s["isLight"] is False
        assert s["swatch"] == "#c4a7e7"
        assert css in data["css"]

    def test_multiple_variants_merged(self):
        schemes = [
            {"name": "rose-pine",      "label": "Rosé Pine",      "isLight": False, "swatch": "#c4a7e7"},
            {"name": "rose-pine-moon", "label": "Rosé Pine Moon",  "isLight": False, "swatch": "#c4a7e7"},
            {"name": "rose-pine-dawn", "label": "Rosé Pine Dawn",  "isLight": True,  "swatch": "#907aa9"},
        ]
        css = "[data-theme=\"rose-pine\"] {}\n[data-theme=\"rose-pine-dawn\"] {}"
        mod = _make_module(schemes, css)
        ep = _make_ep(mod)

        with patch("importlib.metadata.entry_points", return_value=[ep]):
            r = client.get("/plugin-themes")
        assert r.status_code == 200
        data = r.json()
        assert len(data["schemes"]) == 3
        names = {s["name"] for s in data["schemes"]}
        assert names == {"rose-pine", "rose-pine-moon", "rose-pine-dawn"}

    def test_multiple_plugins_merged(self):
        """CSS from two separate plugins is concatenated."""
        mod_a = _make_module(
            [{"name": "theme-a", "label": "Theme A", "isLight": False, "swatch": "#aaa"}],
            "[data-theme='theme-a'] { --bg: 0 0% 10%; }",
        )
        mod_b = _make_module(
            [{"name": "theme-b", "label": "Theme B", "isLight": True, "swatch": "#bbb"}],
            "[data-theme='theme-b'] { --bg: 0 0% 95%; }",
        )
        with patch(
            "importlib.metadata.entry_points",
            return_value=[_make_ep(mod_a), _make_ep(mod_b)],
        ):
            r = client.get("/plugin-themes")
        assert r.status_code == 200
        data = r.json()
        assert len(data["schemes"]) == 2
        assert "theme-a" in data["css"]
        assert "theme-b" in data["css"]

    def test_entry_point_load_failure_is_skipped(self):
        """A broken entry point should not crash the endpoint."""
        bad_ep = MagicMock()
        bad_ep.load.side_effect = ImportError("missing dep")

        good_mod = _make_module(
            [{"name": "good-theme", "label": "Good Theme", "isLight": False, "swatch": "#999"}],
            "[data-theme='good-theme'] {}",
        )
        with patch(
            "importlib.metadata.entry_points",
            return_value=[bad_ep, _make_ep(good_mod)],
        ):
            r = client.get("/plugin-themes")
        assert r.status_code == 200
        data = r.json()
        assert len(data["schemes"]) == 1
        assert data["schemes"][0]["name"] == "good-theme"

    def test_scheme_missing_required_key_is_skipped(self):
        """Schemes missing required keys are silently dropped."""
        incomplete = {"name": "no-swatch", "label": "No Swatch", "isLight": False}  # missing swatch
        valid = {"name": "full", "label": "Full", "isLight": False, "swatch": "#abc"}
        mod = _make_module([incomplete, valid], "")

        with patch("importlib.metadata.entry_points", return_value=[_make_ep(mod)]):
            r = client.get("/plugin-themes")
        assert r.status_code == 200
        data = r.json()
        assert len(data["schemes"]) == 1
        assert data["schemes"][0]["name"] == "full"

    def test_module_without_schemes_attribute_skipped(self):
        """Modules missing SCHEMES do not crash the endpoint."""
        mod = types.ModuleType("no_schemes_plugin")
        mod.CSS = "/* no SCHEMES */"

        with patch("importlib.metadata.entry_points", return_value=[_make_ep(mod)]):
            r = client.get("/plugin-themes")
        assert r.status_code == 200
        data = r.json()
        assert data["schemes"] == []
        # CSS is still included (module has CSS even without SCHEMES)
        assert "no SCHEMES" in data["css"]

    def test_no_css_attribute_is_ok(self):
        """Modules without a CSS attribute contribute schemes only."""
        mod = types.ModuleType("no_css_plugin")
        mod.SCHEMES = [{"name": "x", "label": "X", "isLight": False, "swatch": "#000"}]

        with patch("importlib.metadata.entry_points", return_value=[_make_ep(mod)]):
            r = client.get("/plugin-themes")
        assert r.status_code == 200
        data = r.json()
        assert len(data["schemes"]) == 1
        assert data["css"] == ""
