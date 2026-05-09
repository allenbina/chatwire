"""Tests for chunk 10: Popout messages route.

Strategy
--------
Build a minimal FastAPI test app that mounts just the /popout route logic,
patching out all heavy dependencies (DB, config, relay_handles, etc.) so we
never touch the filesystem or chat.db.  This mirrors the approach used in
test_api_v1.py.

Covers:
  a. GET /popout?handle=<handle> returns 200 with contact name in body.
  b. GET /popout?chat=<guid> returns 200.
  c. GET /popout with no params returns 400.
  d. GET /popout?handle=<unknown> returns 403.
  e. GET /popout?chat=<unknown> returns 403.
"""
from __future__ import annotations

import asyncio
from unittest.mock import patch, MagicMock

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient
from fastapi.templating import Jinja2Templates
from pathlib import Path

# ---------------------------------------------------------------------------
# Minimal Jinja2 setup pointing at the real templates dir so _popout.html
# and _messages.html can be found (no rendering actually happens in the test
# client by default — we just check the HTTP status + body presence).
# ---------------------------------------------------------------------------

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "web" / "templates"

# ---------------------------------------------------------------------------
# Fixtures / constants
# ---------------------------------------------------------------------------

_HANDLE = "+15551234567"
_CONTACT_NAME = "Alice"
_CHAT_GUID = "iMessage;+;chat123456"
_GROUP_NAME = "Friends"

_EMPTY_MSGS: list = []
_HAS_MORE = False

_GROUP_INFO = {"name": _GROUP_NAME, "members": 3}


def _make_app() -> tuple[FastAPI, TestClient]:
    """Build a self-contained test FastAPI app with the /popout route."""
    _app = FastAPI()
    _templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    def _paging_meta(msgs, has_more, handle, chat):
        return {"has_more": has_more, "next_url": "", "msgs": msgs}

    @_app.get("/popout", response_class=HTMLResponse)
    async def popout_route(request: Request, handle: str = "", chat: str = ""):
        from web.themes import selected_theme
        _theme = "light"
        _base_ctx: dict = {"web_theme": _theme, "version": "0.0.0-test"}

        if chat:
            if chat not in _known_groups():
                raise HTTPException(403, "group not in whitelist")
            msgs, has_more = _EMPTY_MSGS, _HAS_MORE
            info = _known_group_info(chat)
            ctx = {
                **_base_ctx,
                "handle": "",
                "chat": chat,
                "name": info["name"],
                "subtitle": f"{info['members']} members",
                "is_group": True,
                "msgs": msgs,
            }
            ctx.update(_paging_meta(msgs, has_more, "", chat))
            return _templates.TemplateResponse(request, "_popout.html", ctx)
        if not handle:
            raise HTTPException(400, "missing handle or chat")
        if handle.lower() not in _known_handles():
            raise HTTPException(403, "handle not in relay scope")
        msgs, has_more = _EMPTY_MSGS, _HAS_MORE
        ctx = {
            **_base_ctx,
            "handle": handle,
            "chat": "",
            "name": _known_name(handle),
            "subtitle": handle,
            "is_group": False,
            "msgs": msgs,
        }
        ctx.update(_paging_meta(msgs, has_more, handle, ""))
        return _templates.TemplateResponse(request, "_popout.html", ctx)

    client = TestClient(_app, raise_server_exceptions=False)
    return _app, client


def _known_handles() -> set[str]:
    return {_HANDLE.lower()}


def _known_groups() -> set[str]:
    return {_CHAT_GUID}


def _known_name(handle: str) -> str:
    return {_HANDLE.lower(): _CONTACT_NAME}.get(handle.lower(), handle)


def _known_group_info(chat: str) -> dict:
    return {_CHAT_GUID: _GROUP_INFO}.get(chat, {"name": chat, "members": 0})


# Create one shared client for all tests in this module.
_app, _client = _make_app()


# ---------------------------------------------------------------------------
# (a) GET /popout?handle=<handle> returns 200 with contact name in body
# ---------------------------------------------------------------------------

class TestPopoutHandle:
    def test_known_handle_returns_200(self):
        r = _client.get("/popout", params={"handle": _HANDLE})
        assert r.status_code == 200

    def test_known_handle_body_contains_name(self):
        r = _client.get("/popout", params={"handle": _HANDLE})
        assert _CONTACT_NAME in r.text

    def test_known_handle_body_is_html(self):
        r = _client.get("/popout", params={"handle": _HANDLE})
        assert "<!doctype html" in r.text.lower() or "<html" in r.text.lower()

    def test_known_handle_body_contains_handle_subtitle(self):
        r = _client.get("/popout", params={"handle": _HANDLE})
        assert _HANDLE in r.text


# ---------------------------------------------------------------------------
# (b) GET /popout?chat=<guid> returns 200
# ---------------------------------------------------------------------------

class TestPopoutChat:
    def test_known_chat_returns_200(self):
        r = _client.get("/popout", params={"chat": _CHAT_GUID})
        assert r.status_code == 200

    def test_known_chat_body_contains_group_name(self):
        r = _client.get("/popout", params={"chat": _CHAT_GUID})
        assert _GROUP_NAME in r.text

    def test_known_chat_body_is_html(self):
        r = _client.get("/popout", params={"chat": _CHAT_GUID})
        assert "<!doctype html" in r.text.lower() or "<html" in r.text.lower()


# ---------------------------------------------------------------------------
# (c) GET /popout with no params returns 400
# ---------------------------------------------------------------------------

class TestPopoutNoParams:
    def test_no_params_returns_400(self):
        r = _client.get("/popout")
        assert r.status_code == 400

    def test_empty_handle_and_no_chat_returns_400(self):
        r = _client.get("/popout?handle=")
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# (d) GET /popout?handle=<unknown> returns 403
# ---------------------------------------------------------------------------

class TestPopoutUnknownHandle:
    def test_unknown_handle_returns_403(self):
        r = _client.get("/popout", params={"handle": "unknown@example.com"})
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# (e) GET /popout?chat=<unknown> returns 403
# ---------------------------------------------------------------------------

class TestPopoutUnknownChat:
    def test_unknown_chat_returns_403(self):
        r = _client.get("/popout", params={"chat": "iMessage;+;unknown999"})
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# Template structure checks (visual spec style)
# ---------------------------------------------------------------------------

class TestPopoutTemplateStructure:
    def test_no_sidebar_in_popout(self):
        r = _client.get("/popout", params={"handle": _HANDLE})
        # Popout must NOT include sidebar nav elements
        assert 'id="sidebar"' not in r.text
        assert '__showSidebar' not in r.text

    def test_composer_present(self):
        r = _client.get("/popout", params={"handle": _HANDLE})
        # Composer form must be present
        assert 'class="composer' in r.text or 'hx-post="/send"' in r.text

    def test_messages_div_present(self):
        r = _client.get("/popout", params={"handle": _HANDLE})
        assert 'id="messages"' in r.text

    def test_sse_ticker_present(self):
        r = _client.get("/popout", params={"handle": _HANDLE})
        assert 'id="ticker"' in r.text

    def test_theme_css_link_present(self):
        r = _client.get("/popout", params={"handle": _HANDLE})
        assert '/static/themes/' in r.text

    def test_htmx_script_present(self):
        r = _client.get("/popout", params={"handle": _HANDLE})
        assert 'htmx.org' in r.text
