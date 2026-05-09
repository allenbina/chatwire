"""First-run setup wizard.

Exposes a multi-step wizard at `/setup` that walks a fresh install through
permissions, identity, Telegram, and whitelist setup. Writes results to
`~/.chatwire/config.json` directly — no in-memory wizard state.

Each step is a Jinja fragment swapped into `#wizard` via htmx. Save endpoints
return the next step's HTML and an `HX-Push-Url` header so the browser back
button works.

Mounted by `web/main.py` via `register_setup_routes(app, templates)`.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

import config as _bridge_config
# Probes and preflight live in web.probes (no FastAPI dependency) so that
# chatwire_cli and tests can import them without pulling in the full web stack.
from web.probes import CHAT_DB, preflight_warnings, probe_automation, probe_fda  # noqa: F401

STEPS = ("permissions", "identity", "whitelist", "security", "done")
STEP_TITLES = {
    "permissions": "Permissions",
    "identity": "Identity",
    "whitelist": "Whitelist",
    "security": "Security",
    "done": "Done",
}


def detect_self_handles() -> list[str]:
    """Read distinct chat.account_login values from chat.db.

    These are the iMessage/SMS accounts the user is signed into; they're the
    obvious "self" candidates. Format is "E:user@example.com" or
    "P:+15551234567" — we strip the prefix.
    """
    if not CHAT_DB.exists():
        return []
    try:
        with sqlite3.connect(f"file:{CHAT_DB}?mode=ro", uri=True) as c:
            rows = c.execute(
                "SELECT DISTINCT account_login FROM chat WHERE account_login IS NOT NULL"
            ).fetchall()
    except sqlite3.OperationalError:
        return []
    out = []
    for (login,) in rows:
        if not login:
            continue
        if login.startswith(("E:", "P:")):
            login = login[2:]
        if login and login not in out:
            out.append(login)
    return sorted(out)


# ---------- config helpers ----------

def _save_self_handles(picks: list[str]) -> None:
    """Write the list of self handles to v2 config and persist."""
    cfg = _bridge_config.load_config()
    cfg["self_handles"] = picks
    _ensure_vapid(cfg)
    _bridge_config.save_config(cfg)


def _ensure_vapid(cfg: dict) -> None:
    """Generate a VAPID keypair on first save if absent.

    Web push subscriptions are tied to the public key; rotating means
    re-subscribing every browser. Generate once, persist forever.
    """
    web = cfg.setdefault("web", {})
    vapid = web.setdefault("vapid", {})
    if vapid.get("private") and vapid.get("public"):
        return
    try:
        priv_b64, pub_b64 = _generate_vapid_keypair()
    except Exception:
        # Don't block the wizard on a keygen failure; push is optional.
        return
    vapid["private"] = priv_b64
    vapid["public"] = pub_b64
    vapid.setdefault("contact", "mailto:admin@example.com")


def _generate_vapid_keypair() -> tuple[str, str]:
    """Return (private_b64url_der, public_b64url_raw) — exactly the shapes
    pywebpush and the browser PushManager accept.

    pywebpush.webpush(vapid_private_key=...) routes a non-file string through
    py_vapid.Vapid.from_string, which b64url-decodes and dispatches by length:
    32 bytes → raw scalar, else → DER. We emit DER because it round-trips
    cleanly with cryptography's PKCS8 export.

    Public side is the raw uncompressed P-256 point, base64url-no-pad — what
    `applicationServerKey` requires for PushManager.subscribe.
    """
    import base64
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    priv = ec.generate_private_key(ec.SECP256R1())
    priv_der = priv.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_raw = priv.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    priv_b64url = base64.urlsafe_b64encode(priv_der).rstrip(b"=").decode()
    pub_b64url = base64.urlsafe_b64encode(pub_raw).rstrip(b"=").decode()
    return priv_b64url, pub_b64url


# ---------- step rendering ----------

def _ctx(step: str, *, request: Request, **extra: Any) -> dict:
    cfg = _bridge_config.load_config()
    from web.themes import selected_theme
    return {
        "request": request,
        "step": step,
        "step_title": STEP_TITLES[step],
        "steps": STEPS,
        "step_titles": STEP_TITLES,
        "step_index": STEPS.index(step),
        "cfg": cfg,
        "web_theme": selected_theme(cfg),
        **extra,
    }


def _step_extras(step: str, cfg: dict) -> dict:
    """Per-step extra context, computed from current config + chat.db."""
    if step == "permissions":
        return {
            "fda": probe_fda(),
            "automation": probe_automation(),
            "preflight_warnings": preflight_warnings(),
        }
    if step == "identity":
        configured = list(cfg.get("self_handles") or [])
        detected = detect_self_handles()
        return {
            "configured": configured,
            "detected": detected,
            "all_candidates": sorted(set(detected) | set(configured)),
        }
    if step == "security":
        from web import auth as _auth
        return {"has_password": _auth.has_password(cfg)}
    return {}


def register_setup_routes(app: FastAPI, templates: Jinja2Templates) -> None:
    """Mount wizard routes on the FastAPI app."""

    def render_step(request: Request, step: str, full_page: bool = False,
                    **extra) -> HTMLResponse:
        cfg = _bridge_config.load_config()
        ctx = _ctx(step, request=request, **_step_extras(step, cfg), **extra)
        template = "wizard/index.html" if full_page else f"wizard/_{step}.html"
        return templates.TemplateResponse(request, template, ctx)

    @app.get("/setup", response_class=HTMLResponse)
    async def setup_page(request: Request, step: str = "permissions"):
        if step not in STEPS:
            step = "permissions"
        return render_step(request, step, full_page=True)

    @app.get("/setup/step/{step}", response_class=HTMLResponse)
    async def setup_step(request: Request, step: str):
        if step not in STEPS:
            raise HTTPException(404, "unknown step")
        resp = render_step(request, step)
        resp.headers["HX-Push-Url"] = f"/setup?step={step}"
        return resp

    @app.post("/setup/check/permissions", response_class=HTMLResponse)
    async def setup_check_permissions(request: Request):
        return render_step(request, "permissions")

    @app.post("/setup/save/identity", response_class=HTMLResponse)
    async def setup_save_identity(request: Request):
        form = await request.form()
        # Multiple checkboxes named "self" + a free-text "extra".
        picks = [v.strip() for v in form.getlist("self") if v.strip()]
        extra = (form.get("extra") or "").strip()
        if extra:
            for h in extra.replace(",", " ").split():
                if h not in picks:
                    picks.append(h)
        _save_self_handles(picks)
        resp = render_step(request, "whitelist")
        resp.headers["HX-Push-Url"] = "/setup?step=whitelist"
        return resp

    @app.post("/setup/save/security", response_class=HTMLResponse)
    async def setup_save_security(
        request: Request,
        new_password: str = Form(""),
    ):
        """Set the optional UI password from the wizard. Empty = skip.

        Setting flips auth from off→on; the same browser session that
        just submitted the form needs a cookie now or the next request
        (/setup/step/done) would 302 to /login. We set the cookie on
        the response so the wizard flow doesn't break."""
        new_password = new_password.strip()
        from web import auth as _auth

        # Re-enter only if a password is actually being set; an empty
        # submit is "skip" and shouldn't touch the existing config.
        if new_password:
            if len(new_password) < 6:
                # Re-render the same step with an inline error rather
                # than 500ing — the wizard expects HTML back.
                ctx = _ctx(
                    "security", request=request,
                    has_password=_auth.has_password(_bridge_config.load_config()),
                    error="Password must be at least 6 characters.",
                )
                return templates.TemplateResponse(
                    request, "wizard/_security.html", ctx,
                )
            cfg = _bridge_config.load_config()
            web = cfg.setdefault("web", {})
            web["auth"] = {
                "password_hash": _auth.hash_password(new_password),
                "session_secret": _auth.new_session_secret(),
            }
            _bridge_config.save_config(cfg)
            # Refresh the running app's cached auth state so the gate
            # sees the new password on the next request. Late import to
            # avoid the web.main ↔ web.setup_wizard circular at module
            # load — register_setup_routes() runs while web.main is
            # still being imported, so this name has to be looked up
            # lazily at call time.
            from web.main import _refresh_auth_state
            _refresh_auth_state()

        resp = render_step(request, "done")
        resp.headers["HX-Push-Url"] = "/setup?step=done"

        # If we just turned auth on, mint a session cookie for this
        # browser so the redirected /setup/step/done request still
        # passes the gate. Done unconditionally on a set submit so the
        # user isn't surprised by an instant logout.
        if new_password:
            cfg = _bridge_config.load_config()
            block = _auth.auth_block(cfg)
            if block is not None:
                resp.set_cookie(
                    _auth.COOKIE_NAME,
                    _auth.issue_cookie(block["session_secret"]),
                    max_age=_auth.SESSION_TTL_S,
                    httponly=True,
                    samesite="lax",
                )
        return resp

    @app.get("/setup/done/restart-hint", response_class=HTMLResponse)
    async def setup_restart_hint(request: Request):
        # Convenience endpoint that just prints the kickstart command. The
        # done page links to it because we can't actually restart ourselves
        # from inside the running process (that would orphan the request).
        return HTMLResponse(
            'Run from a terminal:<br>'
            '<code>launchctl kickstart -k gui/$(id -u)/dev.chatwire.bridge</code><br>'
            '<code>launchctl kickstart -k gui/$(id -u)/dev.chatwire.web</code>'
        )
