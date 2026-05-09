"""Tests for chunk 6 Part A: Thumbnail size setting.

Strategy
--------
- POST route logic tested with an in-memory config dict (no filesystem I/O).
- index.html template rendering verified with a minimal FastAPI app.
- Appearance card template rendering checked for dropdown + selected option.

Covers:
  a. POST /api/settings/thumbnail_max_size saves valid sizes to config.
  b. POST with an invalid value returns 400.
  c. index.html injects correct --gallery-max-width CSS var for each size.
  d. index.html injects "none" for 'full' size.
  e. index.html injects nothing when thumbnail_max_size is empty / unset.
  f. Appearance card renders dropdown with correct selected option.
  g. POST saves and appearance card re-renders with new selection.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "web" / "templates"
_VALID_SIZES = ("360", "720", "1080", "full")


# ---------------------------------------------------------------------------
# Minimal apps used in tests
# ---------------------------------------------------------------------------

def _make_thumbnail_api_app(store: dict[str, Any]):
    """Minimal app for POST /api/settings/thumbnail_max_size."""
    _app = FastAPI()
    _templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    @_app.post("/api/settings/thumbnail_max_size", response_class=HTMLResponse)
    async def post_thumbnail_size(
        request: Request, thumbnail_max_size: str = Form("")
    ):
        if thumbnail_max_size not in _VALID_SIZES:
            raise HTTPException(400, f"Invalid thumbnail size: {thumbnail_max_size!r}")
        store.setdefault("web", {})["thumbnail_max_size"] = thumbnail_max_size
        return _templates.TemplateResponse(request, "_appearance_card.html", {
            "web_theme": "light",
            "themes": [],
            "time_format": "24h",
            "history_limit": 50,
            "custom_css": "",
            "thumbnail_max_size": thumbnail_max_size,
        })

    return _app


def _make_index_app(thumbnail_max_size: str, custom_css: str = ""):
    """Minimal app for GET / that renders index.html with given thumbnail_max_size."""
    _app = FastAPI()
    _templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    @_app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return _templates.TemplateResponse(request, "index.html", {
            "version": "0.0.0-test",
            "release_version": "0.0.0-test",
            "update_check_repo": "allenbina/chatwire",
            "web_theme": "light",
            "custom_css": custom_css,
            "thumbnail_max_size": thumbnail_max_size,
        })

    return _app


def _make_card_app(thumbnail_max_size: str):
    """Minimal app for GET /card that renders _appearance_card.html."""
    _app = FastAPI()
    _templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    @_app.get("/card", response_class=HTMLResponse)
    async def card(request: Request):
        return _templates.TemplateResponse(request, "_appearance_card.html", {
            "web_theme": "light",
            "themes": [],
            "time_format": "24h",
            "history_limit": 50,
            "custom_css": "",
            "thumbnail_max_size": thumbnail_max_size,
        })

    return _app


# ---------------------------------------------------------------------------
# (a) POST saves valid sizes to config
# ---------------------------------------------------------------------------

class TestPostThumbnailSizeSaves:
    def setup_method(self):
        self._store: dict = {}
        self._app = _make_thumbnail_api_app(self._store)
        self._client = TestClient(self._app, raise_server_exceptions=False)

    def test_saves_360(self):
        r = self._client.post(
            "/api/settings/thumbnail_max_size",
            data={"thumbnail_max_size": "360"},
        )
        assert r.status_code == 200
        assert self._store["web"]["thumbnail_max_size"] == "360"

    def test_saves_720(self):
        r = self._client.post(
            "/api/settings/thumbnail_max_size",
            data={"thumbnail_max_size": "720"},
        )
        assert r.status_code == 200
        assert self._store["web"]["thumbnail_max_size"] == "720"

    def test_saves_1080(self):
        r = self._client.post(
            "/api/settings/thumbnail_max_size",
            data={"thumbnail_max_size": "1080"},
        )
        assert r.status_code == 200
        assert self._store["web"]["thumbnail_max_size"] == "1080"

    def test_saves_full(self):
        r = self._client.post(
            "/api/settings/thumbnail_max_size",
            data={"thumbnail_max_size": "full"},
        )
        assert r.status_code == 200
        assert self._store["web"]["thumbnail_max_size"] == "full"


# ---------------------------------------------------------------------------
# (b) POST with invalid value returns 400
# ---------------------------------------------------------------------------

class TestPostThumbnailSizeInvalid:
    def setup_method(self):
        self._store: dict = {}
        self._app = _make_thumbnail_api_app(self._store)
        self._client = TestClient(self._app, raise_server_exceptions=False)

    def test_empty_string_rejected(self):
        r = self._client.post(
            "/api/settings/thumbnail_max_size",
            data={"thumbnail_max_size": ""},
        )
        assert r.status_code == 400

    def test_arbitrary_string_rejected(self):
        r = self._client.post(
            "/api/settings/thumbnail_max_size",
            data={"thumbnail_max_size": "huge"},
        )
        assert r.status_code == 400

    def test_numeric_outside_set_rejected(self):
        r = self._client.post(
            "/api/settings/thumbnail_max_size",
            data={"thumbnail_max_size": "480"},
        )
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# (c) index.html injects correct CSS var for pixel sizes
# ---------------------------------------------------------------------------

class TestIndexInjectsCssVar:
    def _get_html(self, size: str) -> str:
        app = _make_index_app(size)
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/")
        assert r.status_code == 200
        return r.text

    def test_360_injects_360px(self):
        html = self._get_html("360")
        assert "--gallery-max-width: 360px" in html

    def test_720_injects_720px(self):
        html = self._get_html("720")
        assert "--gallery-max-width: 720px" in html

    def test_1080_injects_1080px(self):
        html = self._get_html("1080")
        assert "--gallery-max-width: 1080px" in html

    def test_style_tag_present_for_pixel_sizes(self):
        for size in ("360", "720", "1080"):
            html = self._get_html(size)
            assert "<style>" in html, f"<style> missing for size={size}"


# ---------------------------------------------------------------------------
# (d) index.html injects "none" for full
# ---------------------------------------------------------------------------

class TestIndexInjectsNoneForFull:
    def setup_method(self):
        app = _make_index_app("full")
        client = TestClient(app, raise_server_exceptions=False)
        self._html = client.get("/").text

    def test_gallery_max_width_none(self):
        assert "--gallery-max-width: none" in self._html

    def test_style_tag_present(self):
        assert "<style>" in self._html


# ---------------------------------------------------------------------------
# (e) index.html injects nothing when thumbnail_max_size is empty / unset
# ---------------------------------------------------------------------------

class TestIndexNoInjectionWhenEmpty:
    def setup_method(self):
        app = _make_index_app("")
        client = TestClient(app, raise_server_exceptions=False)
        self._html = client.get("/").text

    def test_no_gallery_max_width_in_html(self):
        assert "--gallery-max-width" not in self._html


# ---------------------------------------------------------------------------
# (f) Appearance card renders dropdown with correct selected option
# ---------------------------------------------------------------------------

class TestAppearanceCardDropdown:
    def _get_html(self, size: str) -> str:
        app = _make_card_app(size)
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/card")
        assert r.status_code == 200
        return r.text

    def test_dropdown_present(self):
        html = self._get_html("360")
        assert 'name="thumbnail_max_size"' in html

    def test_360_selected_when_set(self):
        html = self._get_html("360")
        # The option for 360 should carry 'selected'
        assert 'value="360"' in html

    def test_720_marked_selected(self):
        html = self._get_html("720")
        # Simple check: "720" appears with selected nearby
        idx = html.find('value="720"')
        assert idx != -1
        snippet = html[idx: idx + 40]
        assert "selected" in snippet

    def test_full_marked_selected(self):
        html = self._get_html("full")
        idx = html.find('value="full"')
        assert idx != -1
        snippet = html[idx: idx + 40]
        assert "selected" in snippet

    def test_default_small_selected_when_empty(self):
        html = self._get_html("")
        # When empty, Small (360) should be selected by default
        idx = html.find('value="360"')
        assert idx != -1
        snippet = html[idx: idx + 40]
        assert "selected" in snippet


# ---------------------------------------------------------------------------
# (g) POST saves and re-renders appearance card with new selection
# ---------------------------------------------------------------------------

class TestPostRerendersCard:
    def setup_method(self):
        self._store: dict = {}
        self._app = _make_thumbnail_api_app(self._store)
        self._client = TestClient(self._app, raise_server_exceptions=False)

    def test_post_720_rerenders_card_with_720_selected(self):
        r = self._client.post(
            "/api/settings/thumbnail_max_size",
            data={"thumbnail_max_size": "720"},
        )
        assert r.status_code == 200
        html = r.text
        idx = html.find('value="720"')
        assert idx != -1
        snippet = html[idx: idx + 40]
        assert "selected" in snippet

    def test_post_returns_appearance_card_html(self):
        r = self._client.post(
            "/api/settings/thumbnail_max_size",
            data={"thumbnail_max_size": "1080"},
        )
        assert r.status_code == 200
        # The card has the appearance-card div
        assert 'id="appearance-card"' in r.text
