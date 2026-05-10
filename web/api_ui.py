"""React UI JSON API — session-cookie authenticated.

Mounted at /api/ui in web/main.py.  Auth is handled by the _auth_gate
middleware already installed on the app, so no per-route API-key
dependency is needed here.  Returns JSON, not HTML.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import functools
import sys
import uuid
from pathlib import Path

# asyncio.to_thread polyfill (Python 3.8)
if not hasattr(asyncio, "to_thread"):
    _pool = concurrent.futures.ThreadPoolExecutor()

    async def _to_thread(func, *args, **kwargs):  # type: ignore[misc]
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_pool, functools.partial(func, *args, **kwargs))

    asyncio.to_thread = _to_thread  # type: ignore[attr-defined]

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel

router = APIRouter()

# Temp dir for uploaded attachments; created on first use.
_UPLOAD_DIR = Path.home() / ".chatwire" / "uploads"


# ---------------------------------------------------------------------------
# Lazy imports — mirror the pattern in api_v1.py to avoid circular imports
# ---------------------------------------------------------------------------

def _list_conversations() -> list:
    from web.main import list_conversations  # noqa: PLC0415
    return list_conversations()


def _history_for(handle: str, before: tuple[int, int] | None = None):
    from web.main import history_for  # noqa: PLC0415
    return history_for(handle, before=before)


def _history_for_group(guid: str, before: tuple[int, int] | None = None):
    from web.main import history_for_group  # noqa: PLC0415
    return history_for_group(guid, before=before)


def _relay_handles() -> set:
    from web.main import relay_handles  # noqa: PLC0415
    return relay_handles()


def _wl_all_groups() -> set:
    from web.whitelist import all_groups  # noqa: PLC0415
    return all_groups()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class SendBody(BaseModel):
    handle: str
    text: str
    guid: str = ""  # non-empty → send to group chat


class PasswordBody(BaseModel):
    current_password: str = ""
    new_password: str = ""
    clear: bool = False


class LoginBody(BaseModel):
    password: str = ""
    next: str = "/"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/conversations")
async def ui_conversations():
    """Conversations list in sidebar shape for the React UI.

    Returns the full list including group chats, favorites, and previews.
    No pagination — same as the Jinja2 sidebar.
    """
    convos = await asyncio.to_thread(_list_conversations)
    return {"conversations": convos}


@router.get("/messages")
async def ui_messages(
    handle: str = Query(""),
    guid: str = Query("", description="Group chat GUID; use instead of handle for group chats"),
    since: int = Query(0, ge=0, description="Return only messages with rowid > since"),
    before_date: int = Query(0, ge=0, description="Load-older cursor: Apple date epoch of oldest visible msg"),
    before_rowid: int = Query(0, ge=0, description="Load-older cursor: rowid of oldest visible msg"),
    limit: int = Query(50, ge=1, le=500),
):
    """Message history for a 1:1 or group conversation (oldest-first).

    For 1:1 chats pass `handle`; for group chats pass `guid`.

    Supports incremental polling via `since` (rowid cursor) and
    reverse paging via `before_date` + `before_rowid` cursors.
    """
    before = (before_date, before_rowid) if before_date and before_rowid else None

    if guid:
        if guid not in _wl_all_groups():
            raise HTTPException(403, "guid not in group whitelist")
        msgs, has_more = await asyncio.to_thread(_history_for_group, guid, before)
        key = guid
    elif handle:
        if handle.lower() not in _relay_handles():
            raise HTTPException(403, "handle not in relay scope")
        msgs, has_more = await asyncio.to_thread(_history_for, handle, before)
        key = handle
    else:
        raise HTTPException(400, "supply handle or guid")

    if since:
        msgs = [m for m in msgs if m["rowid"] > since]
    msgs = msgs[-limit:]
    return {"handle": key, "messages": msgs, "has_more": has_more}


@router.post("/send")
async def ui_send(body: SendBody):
    """Send a text message through the existing anti-spam guardrails.

    For group chats set `guid` instead of (or in addition to) `handle`.
    """
    from chat_send import (  # noqa: PLC0415
        BroadcastBlockedError,
        RateLimitError,
        check_send_guard,
        send_text_confirm,
        send_text_to_chat_confirm,
    )

    if body.guid:
        if body.guid not in _wl_all_groups():
            raise HTTPException(403, "guid not in group whitelist")
        try:
            await asyncio.to_thread(check_send_guard, body.guid, body.text, "ui-group")
        except RateLimitError as exc:
            raise HTTPException(429, str(exc)) from exc
        except BroadcastBlockedError as exc:
            raise HTTPException(
                429, {"error": str(exc), "retry_after": exc.retry_after}
            ) from exc
        result = await asyncio.to_thread(send_text_to_chat_confirm, body.guid, body.text)
        return {"status": result.status, "hint": result.hint, "service": result.service}

    if body.handle.lower() not in _relay_handles():
        raise HTTPException(403, "handle not in relay scope")
    try:
        await asyncio.to_thread(check_send_guard, body.handle, body.text, "ui")
    except RateLimitError as exc:
        raise HTTPException(429, str(exc)) from exc
    except BroadcastBlockedError as exc:
        raise HTTPException(
            429, {"error": str(exc), "retry_after": exc.retry_after}
        ) from exc
    result = await asyncio.to_thread(send_text_confirm, body.handle, body.text)
    return {"status": result.status, "hint": result.hint, "service": result.service}


@router.post("/upload")
async def ui_upload(
    handle: str = Form(""),
    guid: str = Form(""),
    file: UploadFile = File(...),
):
    """Upload a file and send it as an attachment.

    Supply exactly one of `handle` (1:1) or `guid` (group).
    The file is written to ~/.chatwire/uploads/, sent via Messages.app,
    then deleted.  Max 50 MB.
    """
    from chat_send import (  # noqa: PLC0415
        send_file_confirm,
        send_file_to_chat_confirm,
    )

    MAX_BYTES = 50 * 1024 * 1024
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "File exceeds 50 MB limit")

    if not guid and not handle:
        raise HTTPException(400, "supply handle or guid")
    if guid and guid not in _wl_all_groups():
        raise HTTPException(403, "guid not in group whitelist")
    if handle and handle.lower() not in _relay_handles():
        raise HTTPException(403, "handle not in relay scope")

    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    # Preserve original extension for MIME detection by Messages.app
    suffix = Path(file.filename or "upload").suffix
    tmp = _UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"
    tmp.write_bytes(data)

    try:
        if guid:
            result = await asyncio.to_thread(send_file_to_chat_confirm, guid, tmp)
        else:
            result = await asyncio.to_thread(send_file_confirm, handle, tmp)
    finally:
        tmp.unlink(missing_ok=True)

    return {"status": result.status, "hint": result.hint, "service": result.service}


@router.get("/themes")
async def ui_themes():
    """List available theme names and the currently selected theme."""
    from web.themes import available_themes, selected_theme  # noqa: PLC0415
    import config as _cfg  # noqa: PLC0415, E402
    cfg = _cfg.load_config()
    themes = available_themes()
    current = selected_theme(cfg)
    return {"themes": themes, "current": current}


@router.post("/themes")
async def ui_themes_set(theme: str = Form(...)):
    """Persist the selected theme to server config (same as /api/settings/theme)."""
    from web.themes import available_themes  # noqa: PLC0415
    import config as _cfg  # noqa: PLC0415, E402
    if theme not in available_themes():
        raise HTTPException(400, f"unknown theme: {theme!r}")
    cfg = _cfg.load_config()
    web = cfg.setdefault("web", {})
    web["theme"] = theme
    _cfg.save_config(cfg)
    return {"ok": True, "theme": theme}


# ---------------------------------------------------------------------------
# Settings read endpoints for the React UI
# ---------------------------------------------------------------------------

@router.get("/settings/self_handles")
async def ui_settings_self_handles():
    """Return the SELF_HANDLES list from config."""
    import config as _cfg  # noqa: PLC0415
    cfg = _cfg.load_config()
    return {"self_handles": cfg.get("self_handles") or []}


@router.get("/settings/whitelist")
async def ui_settings_whitelist():
    """Return the whitelist rows and contact names for autocomplete."""
    def _get():
        from web.whitelist import all_entries  # noqa: PLC0415
        from web.main import contact_names_for_autocomplete  # noqa: PLC0415
        rows = [{"label": e, "value": e} for e in sorted(all_entries())]
        names = sorted(contact_names_for_autocomplete())
        return {"rows": rows, "contact_names": names}

    try:
        return await asyncio.to_thread(_get)
    except Exception:
        return {"rows": [], "contact_names": []}


@router.get("/settings/api_key")
async def ui_settings_api_key():
    """Return the API key hint (masked) for display."""
    import config as _cfg  # noqa: PLC0415
    cfg = _cfg.load_config()
    key = (cfg.get("api") or {}).get("key") or ""
    if key:
        hint = key[:4] + "…" + key[-4:] if len(key) > 8 else "set"
    else:
        hint = "Not set"
    return {"api_key_hint": hint}


@router.get("/settings/notifications")
async def ui_settings_notifications():
    """Return notification-related settings."""
    import config as _cfg  # noqa: PLC0415
    cfg = _cfg.load_config()
    notif = cfg.get("notifications") or {}
    return {
        "notification_detail": notif.get("detail", "rich"),
        "hiatus_enabled": bool(notif.get("hiatus_enabled", False)),
        "hiatus_duration_minutes": int(notif.get("hiatus_duration_minutes", 10)),
        "reminder_enabled": bool(notif.get("reminder_enabled", False)),
        "reminder_days": int(notif.get("reminder_days", 7)),
    }


@router.get("/settings/antispam")
async def ui_settings_antispam():
    """Return anti-spam settings."""
    import config as _cfg  # noqa: PLC0415
    cfg = _cfg.load_config()
    spam = cfg.get("spam") or {}
    ntfy_topic = (cfg.get("notifications") or {}).get("ntfy_topic", "")
    whitelist_entries = spam.get("whitelist") or []
    return {
        "spam_whitelist_text": "\n".join(whitelist_entries),
        "ntfy_topic": ntfy_topic,
    }


@router.get("/settings/advanced")
async def ui_settings_advanced():
    """Return advanced server settings."""
    import config as _cfg  # noqa: PLC0415
    cfg = _cfg.load_config()
    web = cfg.get("web") or {}
    return {
        "web_port": int(web.get("port", 8723)),
        "web_bind": web.get("bind", "127.0.0.1"),
        "web_proxy_headers": bool(web.get("proxy_headers", False)),
    }


@router.get("/settings/password")
async def ui_settings_password_status():
    """Return whether a web UI password is currently set."""
    from web.main import app as _app  # noqa: PLC0415
    auth_enabled = getattr(_app.state, "auth_block", None) is not None
    return {"auth_enabled": auth_enabled}


@router.post("/settings/password")
async def ui_settings_password(body: PasswordBody, request: Request, response: Response):
    """Set, change, or clear the web UI password.

    When auth is already enabled, ``current_password`` must be supplied and
    correct before any change is accepted — same rate-limit bucket as /login.

    - ``clear=true`` + valid ``current_password`` → disables auth, clears cookie.
    - ``new_password`` (≥ 6 chars) → sets / changes the password.  On success
      the response includes a fresh session cookie so the caller stays logged in
      with the new secret.
    """
    from web.main import (  # noqa: PLC0415
        app as _app,
        _save_auth_block,
        _client_key,
        _fmt_lockout,
        _set_session_cookie,
    )
    import web.auth as _auth  # noqa: PLC0415

    block = getattr(_app.state, "auth_block", None)
    if block is not None:
        limiter: _auth.LoginRateLimiter = _app.state.login_rate_limiter
        key = _client_key(request)
        locked = limiter.locked_for(key)
        if locked:
            raise HTTPException(429, f"Too many attempts. Try again in {_fmt_lockout(locked)}.")
        if not _auth.verify_password(body.current_password, block["password_hash"]):
            limiter.record_fail(key)
            raise HTTPException(403, "Wrong current password.")
        limiter.record_success(key)

    if body.clear:
        _save_auth_block(None)
        response.delete_cookie(_auth.COOKIE_NAME, samesite="lax")
        return {"ok": True, "auth_enabled": False}

    new_pw = body.new_password.strip()
    if len(new_pw) < 6:
        raise HTTPException(400, "Password must be at least 6 characters.")
    _save_auth_block(new_pw)
    new_block = getattr(_app.state, "auth_block", None)
    if new_block is not None:
        _set_session_cookie(response, new_block["session_secret"])
    return {"ok": True, "auth_enabled": True}


# ---------------------------------------------------------------------------
# Auth — public login endpoint (no session cookie required)
# ---------------------------------------------------------------------------

@router.post("/auth/login")
async def ui_auth_login(body: LoginBody, request: Request, response: Response):
    """Exchange a password for a session cookie.

    This endpoint is on the public path list (``/api/ui/auth/login``) so the
    auth-gate middleware never intercepts it.  Rate-limiting and password
    verification use the same shared LoginRateLimiter as ``/login`` and
    ``/api/ui/settings/password``.

    Returns ``{"ok": true, "next": "<safe redirect url>"}`` on success.
    On failure: 403 (wrong password) or 429 (rate-limited).
    """
    from web.main import (  # noqa: PLC0415
        app as _app,
        _client_key,
        _fmt_lockout,
        _set_session_cookie,
    )
    import web.auth as _auth  # noqa: PLC0415

    block = getattr(_app.state, "auth_block", None)
    if block is None:
        # Auth is disabled — issue no cookie; redirect to app root.
        return {"ok": True, "next": "/app/"}

    limiter: _auth.LoginRateLimiter = _app.state.login_rate_limiter
    key = _client_key(request)
    locked = limiter.locked_for(key)
    if locked:
        raise HTTPException(429, f"Too many attempts. Try again in {_fmt_lockout(locked)}.")

    if not _auth.verify_password(body.password, block["password_hash"]):
        limiter.record_fail(key)
        raise HTTPException(403, "Wrong password.")

    limiter.record_success(key)
    _set_session_cookie(response, block["session_secret"])

    # Validate next: must be a path (starts with /) but not a protocol-relative
    # URL (starts with //) — same guard as the old Jinja2 _safe_next().
    nxt = body.next.strip()
    if not nxt or not nxt.startswith("/") or nxt.startswith("//"):
        nxt = "/app/"
    return {"ok": True, "next": nxt}


# ---------------------------------------------------------------------------
# Stats JSON endpoint (consumed by the React StatsWidget plugin)
# ---------------------------------------------------------------------------

@router.get("/stats")
async def ui_stats():
    """Return messaging analytics as JSON for the React StatsWidget.

    Reads the date_range from the stats integration config and returns the
    same data that /plugins/stats/report renders as HTML.

    Response::

        {
            "enabled": true,
            "date_range": "30d",
            "sent_total": 1234,
            "received_total": 5678,
            "top_contacts": [{"name": "Alice", "handle": "+1…", "count": 42}],
            "top_groups": [{"name": "Family", "count": 100}],
            "hour_counts": [0, 0, ..., 120, ...],  // 24 ints
            "dow_counts": [45, 67, ..., 30]         // 7 ints Mon-Sun
        }

    Returns ``{"enabled": false}`` when the stats integration is disabled.
    """
    import time as _time  # noqa: PLC0415
    import config as _cfg  # noqa: PLC0415

    cfg = _cfg.load_config()
    stats_cfg = cfg.get("integrations", {}).get("stats", {})
    if not stats_cfg.get("enabled", False):
        return {"enabled": False}

    date_range = stats_cfg.get("date_range", "30d")

    from web.main import _snapshot, APPLE_EPOCH_OFFSET, CONTACTS  # noqa: PLC0415

    def _compute():
        if date_range == "all":
            cutoff_ns = None
        else:
            days = {"30d": 30, "90d": 90, "365d": 365}.get(date_range, 30)
            cutoff_ns = int(
                (_time.time() - days * 86400 - APPLE_EPOCH_OFFSET) * 1_000_000_000
            )

        cutoff_clause = "AND m.date >= :cutoff" if cutoff_ns is not None else ""
        params: dict = {"cutoff": cutoff_ns} if cutoff_ns is not None else {}

        conn = _snapshot()

        # Sent vs received
        totals_row = conn.execute(f"""
            SELECT
                SUM(CASE WHEN m.is_from_me = 1 THEN 1 ELSE 0 END) AS sent,
                SUM(CASE WHEN m.is_from_me = 0 THEN 1 ELSE 0 END) AS received
            FROM message m
            WHERE 1=1 {cutoff_clause}
        """, params).fetchone()
        sent_total = int(totals_row["sent"] or 0)
        received_total = int(totals_row["received"] or 0)

        # Top 10 contacts (1:1)
        top_contacts_rows = conn.execute(f"""
            SELECT COALESCE(h.id, 'unknown') AS handle, COUNT(*) AS msg_count
            FROM message m
            LEFT JOIN handle h ON h.ROWID = m.handle_id
            JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
            JOIN chat c ON c.ROWID = cmj.chat_id
            WHERE c.style = 45 {cutoff_clause}
            GROUP BY handle
            ORDER BY msg_count DESC
            LIMIT 10
        """, params).fetchall()
        top_contacts = [
            {
                "handle": r["handle"],
                "name": CONTACTS.get(r["handle"].lower(), r["handle"]),
                "count": int(r["msg_count"]),
            }
            for r in top_contacts_rows
        ]

        # Hour-of-day distribution (24 buckets)
        hour_rows = conn.execute(f"""
            SELECT
                CAST(strftime('%H',
                    datetime(m.date / 1000000000 + {APPLE_EPOCH_OFFSET},
                             'unixepoch', 'localtime')) AS INTEGER) AS hour,
                COUNT(*) AS msg_count
            FROM message m
            WHERE 1=1 {cutoff_clause}
            GROUP BY hour ORDER BY hour
        """, params).fetchall()
        hour_counts = [0] * 24
        for row in hour_rows:
            if row["hour"] is not None:
                hour_counts[row["hour"]] = int(row["msg_count"])

        # Day-of-week distribution (7 buckets, Mon=0)
        dow_rows = conn.execute(f"""
            SELECT
                CAST(strftime('%w',
                    datetime(m.date / 1000000000 + {APPLE_EPOCH_OFFSET},
                             'unixepoch', 'localtime')) AS INTEGER) AS dow_sun,
                COUNT(*) AS msg_count
            FROM message m
            WHERE 1=1 {cutoff_clause}
            GROUP BY dow_sun ORDER BY dow_sun
        """, params).fetchall()
        dow_counts = [0] * 7
        for row in dow_rows:
            if row["dow_sun"] is not None:
                mon_idx = (row["dow_sun"] - 1) % 7
                dow_counts[mon_idx] = int(row["msg_count"])

        # Top 5 group chats
        group_rows = conn.execute(f"""
            SELECT COALESCE(c.display_name, c.chat_identifier, c.guid) AS name,
                   COUNT(*) AS msg_count
            FROM message m
            JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
            JOIN chat c ON c.ROWID = cmj.chat_id
            WHERE c.style != 45 {cutoff_clause}
            GROUP BY c.ROWID ORDER BY msg_count DESC LIMIT 5
        """, params).fetchall()
        top_groups = [{"name": r["name"], "count": int(r["msg_count"])} for r in group_rows]

        conn.close()

        return {
            "enabled": True,
            "date_range": date_range,
            "sent_total": sent_total,
            "received_total": received_total,
            "top_contacts": top_contacts,
            "top_groups": top_groups,
            "hour_counts": hour_counts,
            "dow_counts": dow_counts,
        }

    return await asyncio.to_thread(_compute)
