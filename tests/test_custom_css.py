"""Tests for chunk 12: Custom CSS textarea.

Strategy
--------
- Test POST /api/settings/custom_css route logic with an in-memory config dict
  to avoid filesystem side-effects.
- Test GET / template rendering by building a minimal FastAPI app backed by the
  real index.html template, verifying the <style> block is present or absent.

Covers:
  a. POST /api/settings/custom_css saves value to config.
  b. GET / renders <style> block when custom_css is set.
  c. GET / renders no <style> block when custom_css is empty/unset.
  d. POST with empty string clears the setting.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "web" / "templates"


# ---------------------------------------------------------------------------
# Minimal FastAPI apps used in tests
# ---------------------------------------------------------------------------

def _make_css_api_app(store: dict[str, Any]):
    """Build a minimal app for the POST /api/settings/custom_css route."""
    _app = FastAPI()

    @_app.post("/api/settings/custom_css")
    async def post_custom_css(request: Request):
        body = await request.json()
        css = body.get("custom_css", "")
        if not isinstance(css, str):
            raise HTTPException(400, "custom_css must be a string")
        store.setdefault("web", {})["custom_css"] = css
        return {"ok": True}

    return _app


def _make_index_app(custom_css: str):
    """Build a minimal app for GET / that renders index.html with given custom_css."""
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
        })

    return _app


# ---------------------------------------------------------------------------
# (a) POST /api/settings/custom_css saves value to config
# ---------------------------------------------------------------------------

class TestPostCustomCssSaves:
    def setup_method(self):
        self._store: dict = {}
        self._app = _make_css_api_app(self._store)
        self._client = TestClient(self._app, raise_server_exceptions=False)

    def test_saves_css_to_store(self):
        r = self._client.post(
            "/api/settings/custom_css",
            json={"custom_css": "body { background: red; }"},
        )
        assert r.status_code == 200
        assert r.json() == {"ok": True}
        assert self._store["web"]["custom_css"] == "body { background: red; }"

    def test_returns_ok_true(self):
        r = self._client.post(
            "/api/settings/custom_css",
            json={"custom_css": "/* anything */"},
        )
        assert r.json()["ok"] is True

    def test_multiline_css_preserved(self):
        css = "body {\n  background: blue;\n  color: white;\n}"
        r = self._client.post("/api/settings/custom_css", json={"custom_css": css})
        assert r.status_code == 200
        assert self._store["web"]["custom_css"] == css

    def test_non_string_returns_400(self):
        r = self._client.post("/api/settings/custom_css", json={"custom_css": 123})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# (b) GET / renders <style> block when custom_css is set
# ---------------------------------------------------------------------------

class TestIndexRendersStyleBlock:
    def setup_method(self):
        css = "body { background: hotpink; }"
        self._app = _make_index_app(css)
        self._client = TestClient(self._app, raise_server_exceptions=False)

    def test_style_tag_present(self):
        r = self._client.get("/")
        assert r.status_code == 200
        assert "<style>" in r.text

    def test_custom_css_content_in_body(self):
        r = self._client.get("/")
        assert "hotpink" in r.text

    def test_style_block_after_stylesheet_links(self):
        r = self._client.get("/")
        # The custom <style> block must appear after the theme link tag.
        idx_link = r.text.find('style.css')
        idx_style = r.text.find('<style>')
        assert idx_link < idx_style, "Custom <style> must come after theme stylesheet"


# ---------------------------------------------------------------------------
# (c) GET / renders no <style> block when custom_css is empty / unset
# ---------------------------------------------------------------------------

class TestIndexNoStyleBlockWhenEmpty:
    def setup_method(self):
        self._app_empty = _make_index_app("")
        self._client_empty = TestClient(self._app_empty, raise_server_exceptions=False)

    def test_no_custom_style_tag_when_empty(self):
        r = self._client_empty.get("/")
        assert r.status_code == 200
        # There should be no inline <style> tag (only link tags for stylesheets).
        assert "<style>" not in r.text

    def test_page_still_loads_correctly_when_empty(self):
        r = self._client_empty.get("/")
        assert r.status_code == 200
        # The page should still have normal stylesheet links.
        assert "style.css" in r.text


# ---------------------------------------------------------------------------
# (d) POST with empty string clears the setting
# ---------------------------------------------------------------------------

class TestPostCustomCssClears:
    def setup_method(self):
        self._store: dict = {"web": {"custom_css": "body { color: red; }"}}
        self._app = _make_css_api_app(self._store)
        self._client = TestClient(self._app, raise_server_exceptions=False)

    def test_empty_string_clears_setting(self):
        r = self._client.post("/api/settings/custom_css", json={"custom_css": ""})
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert self._store["web"]["custom_css"] == ""

    def test_empty_string_returns_ok(self):
        r = self._client.post("/api/settings/custom_css", json={"custom_css": ""})
        assert r.json() == {"ok": True}

    def test_overwrite_existing_css(self):
        r = self._client.post(
            "/api/settings/custom_css",
            json={"custom_css": "body { color: blue; }"},
        )
        assert r.status_code == 200
        assert self._store["web"]["custom_css"] == "body { color: blue; }"
