"""FastAPI web frontend for the iMessage <-> Telegram bridge.

Runs as a separate launchd user agent on the Mac. Reads chat.db via the same
backup-snapshot approach the bridge uses (keeps TCC happy past the 4-min
cliff). Sends iMessages via the same osascript wrappers the bridge uses.
Live updates are streamed via SSE by tailing the bridge's mirror.jsonl file.

Deliberately minimal: htmx swaps fragments into a single HTML page, no JS
framework, no build step. Auth is "you can reach the box" — gate access at
the network layer (Tailscale, LAN-only, CF Access).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

import logging

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("chatwire.web")
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Reuse bridge modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from chat_db import APPLE_EPOCH_OFFSET, ChatDBReader, CHAT_DB  # noqa: E402
from chat_send import (  # noqa: E402
    send_text_confirm, send_file_confirm,
    send_text_to_chat_confirm, send_file_to_chat_confirm,
)
from contacts import load_lookup as load_contacts, load_image_index, fetch_image  # noqa: E402
from echo_log import register as echo_register  # noqa: E402
from whitelist import (  # noqa: E402
    add as wl_add, add_group as wl_add_group,
    all_handles as wl_all, all_groups as wl_all_groups,
    remove as wl_remove, remove_group as wl_remove_group,
)

# Load config from ~/.chatwire/config.json (or legacy fallbacks).
import config as _bridge_config  # noqa: E402
_bridge_config.apply_to_environ()
from config import STATE_DIR  # noqa: E402
from verify import PluginNotTrusted, verify_plugin  # noqa: E402

SELF_HANDLES = {h.strip().lower() for h in os.environ.get("SELF_HANDLES", "").split(",") if h.strip()}

# Plugin marketplace registry
from web.registry import fetch_registry as _fetch_registry, PLUGIN_REGISTRY_URL  # noqa: E402
_REGISTRY_CACHE_FILE = STATE_DIR / "plugin_registry_cache.json"

# Plugin / core version checks
from web.version_check import (  # noqa: E402
    check_updates as _vc_check_updates,
    fetch_pypi_version as _vc_fetch_pypi_version,
    load_version_cache as _vc_load_cache,
    save_version_cache as _vc_save_cache,
)
_VERSION_CACHE_FILE = STATE_DIR / "plugin_version_cache.json"


def _fetch_registry_blocking() -> list[dict]:
    """Thin wrapper: calls web.registry.fetch_registry with the app cache path."""
    return _fetch_registry(_REGISTRY_CACHE_FILE)


def relay_handles() -> set[str]:
    return SELF_HANDLES | wl_all()


MIRROR_FILE = Path(os.environ.get("DEBUG_MIRROR_FILE", str(STATE_DIR / "mirror.jsonl")))

WEB_PORT = int(os.environ.get("WEB_PORT", "8723"))
WEB_SECURE_COOKIE = os.environ.get("WEB_SECURE_COOKIE", "").lower() in ("1", "true", "yes")
HISTORY_LIMIT = 100
CONVO_LIMIT = 50

VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_CONTACT = os.environ.get("VAPID_CONTACT", "mailto:admin@example.com")
PUSH_SUBS_FILE = STATE_DIR / "push_subs.json"

CONTACTS = load_contacts()
IMAGE_INDEX = load_image_index()

def _compute_build_id() -> str:
    """Cache-busting identifier for static assets. Changes whenever the
    code does (commit hash if git is available, mtime otherwise)."""
    repo_root = Path(__file__).resolve().parent.parent
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--short=8", "HEAD"],
            capture_output=True, text=True, timeout=3,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return str(int(Path(__file__).stat().st_mtime))


# Two distinct version-shaped values:
#   RELEASE_VERSION — semver, bumped at release ("0.1.0", "0.2.0-rc1", "0.0.0-dev").
#                     Drives the update-check banner.
#   BUILD_ID       — commit hash or mtime, changes every build.
#                     Drives the static-asset cache-buster.
import _version  # noqa: E402
RELEASE_VERSION = _version.__version__
BUILD_ID = _compute_build_id()
APP_VERSION = BUILD_ID  # legacy alias; /healthz et al. expect this name

# Default GitHub repo to check for updates. The web UI's update-check JS
# reads this from a meta tag on the page, so it's per-render configurable
# without a code change. Override via env to point at a fork.
UPDATE_CHECK_REPO = os.environ.get("UPDATE_CHECK_REPO", "allenbina/chatwire")

app = FastAPI()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

from web import auth as _auth  # noqa: E402
from web.setup_wizard import register_setup_routes  # noqa: E402
from web.themes import available_themes, selected_theme, themes_for_picker  # noqa: E402

register_setup_routes(app, templates)

from web.api_v1 import router as _api_v1_router  # noqa: E402
app.include_router(_api_v1_router, prefix="/api/v1")

from web.api_ui import router as _api_ui_router  # noqa: E402
app.include_router(_api_ui_router, prefix="/api/ui")


def _refresh_auth_state() -> None:
    """Reread `web.auth` from config into app.state. Called at startup and
    whenever the password is set/cleared via settings or wizard. The
    middleware reads from app.state to skip the per-request file load."""
    cfg = _bridge_config.load_config()
    app.state.auth_block = _auth.auth_block(cfg)


_refresh_auth_state()
app.state.login_rate_limiter = _auth.LoginRateLimiter()
# Per-process CSRF secret — rotates on restart (intentional for a home server).
# In-flight forms older than a restart become invalid; that's acceptable.
app.state.csrf_secret = _auth.new_session_secret()


@app.middleware("http")
async def _auth_gate(request: Request, call_next):
    """Cookie-session auth gate. No-op when no password is configured."""
    block = getattr(app.state, "auth_block", None)
    if block is None or _auth.is_public_path(request.url.path):
        return await call_next(request)
    cookie = request.cookies.get(_auth.COOKIE_NAME)
    age = _auth.cookie_age(cookie, block["session_secret"])
    if age is not None:
        response = await call_next(request)
        # Sliding refresh: an active user's cookie keeps rolling forward,
        # while an idle user's still expires at SESSION_TTL_S. Skip the
        # rewrite when the cookie is fresh — set_cookie on every request
        # would ship a Set-Cookie header on every fragment swap. Also
        # skip when the secret rotated mid-request (e.g. /api/auth/password
        # changed the password) — the handler has already set a cookie
        # with the new secret, and reissuing with the pre-rotation secret
        # would shadow it.
        if age >= _auth.SESSION_REFRESH_S:
            cur_block = getattr(app.state, "auth_block", None)
            if cur_block is not None and cur_block["session_secret"] == block["session_secret"]:
                _set_session_cookie(response, block["session_secret"])
        return response
    from urllib.parse import quote
    target = "/app/login"
    nxt = request.url.path
    if request.url.query:
        nxt = f"{nxt}?{request.url.query}"
    if nxt and nxt != "/":
        target = f"/app/login?next={quote(nxt, safe='')}"
    return RedirectResponse(target, status_code=302)


@app.middleware("http")
async def _no_store_html(request: Request, call_next):
    response = await call_next(request)
    ctype = response.headers.get("content-type", "")
    if ctype.startswith("text/html"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/healthz")
async def healthz():
    return {"ok": True, "version": APP_VERSION, "release": RELEASE_VERSION}


@app.get("/version")
async def version():
    return {"release": RELEASE_VERSION, "build": BUILD_ID}


# ------- optional cookie-session auth -------


def _csrf_token() -> str:
    """Fresh signed CSRF token for the current request cycle."""
    return _auth.new_csrf_token(app.state.csrf_secret)


def _set_session_cookie(response: Response, secret: str) -> None:
    response.set_cookie(
        _auth.COOKIE_NAME,
        _auth.issue_cookie(secret),
        max_age=_auth.SESSION_TTL_S,
        httponly=True,
        samesite="lax",
        # `secure` is off by default so LAN-over-http installs work.
        # Set `web.secure_cookie: true` in config.json for deployments
        # behind a TLS-terminating proxy (Tailscale, Caddy, CF Access).
        secure=WEB_SECURE_COOKIE,
    )


def _client_key(request: Request) -> str:
    """Bucket key for rate limiting. `request.client.host` is the immediate
    peer — for direct LAN access that's the user; behind a reverse proxy
    it's the proxy IP. We deliberately don't trust X-Forwarded-For: in
    the home-deployment context we don't know which proxies are
    trustworthy, and a forged header would let an attacker pick a fresh
    bucket per attempt. See `LoginRateLimiter` docstring for the
    behind-a-proxy tradeoff."""
    return (request.client.host if request.client else "") or "unknown"


def _fmt_lockout(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    minutes = (seconds + 59) // 60
    return f"{minutes} minute{'s' if minutes != 1 else ''}"


@app.get("/logout")
async def logout():
    resp = RedirectResponse("/app/login", status_code=303)
    resp.delete_cookie(_auth.COOKIE_NAME, samesite="lax")
    return resp


def _save_auth_block(password: str | None) -> None:
    """Set or clear the password. Empty/None password clears auth.

    Clearing also drops `web.auth` entirely so the absence-means-disabled
    invariant holds. Setting rotates `session_secret` whenever the
    password changes — that's the natural "log out everywhere" hook
    (existing cookies stop verifying)."""
    cfg = _bridge_config.load_config()
    web = cfg.setdefault("web", {})
    if not password:
        web.pop("auth", None)
        if not web:
            cfg.pop("web", None)
    else:
        web["auth"] = {
            "password_hash": _auth.hash_password(password),
            "session_secret": _auth.new_session_secret(),
        }
    _bridge_config.save_config(cfg)
    _refresh_auth_state()


# ------- chat.db queries (read via backup snapshot, like the bridge) -------

_src_conn: sqlite3.Connection | None = None


_src_lock = __import__("threading").Lock()


def _snapshot() -> sqlite3.Connection:
    global _src_conn
    with _src_lock:
        if _src_conn is None:
            _src_conn = sqlite3.connect(
                f"file:{CHAT_DB}?mode=ro", uri=True, check_same_thread=False
            )
        mem = sqlite3.connect(":memory:")
        mem.row_factory = sqlite3.Row
        _src_conn.backup(mem)
        return mem


# Both of these restrict to chat.style=45 (direct/1:1) so a handle's group
# messages don't leak into the 1:1 sidebar entry or thread view. A person can
# be in both a 1:1 and many groups with us; handle_id alone can't tell them
# apart, only the chat row can.
CONVOS_SQL = """
SELECT
    h.id AS handle,
    MAX(m.date) AS last_dt,
    SUM(CASE WHEN m.is_read = 0 AND m.is_from_me = 0 THEN 1 ELSE 0 END) AS n,
    (SELECT COALESCE(SUBSTR(m2.text,1,80), '')
       FROM message m2
       JOIN chat_message_join cmj2 ON cmj2.message_id = m2.ROWID
       JOIN chat c2 ON c2.ROWID = cmj2.chat_id
       WHERE m2.handle_id = h.ROWID AND c2.style = 45
       ORDER BY m2.date DESC LIMIT 1) AS preview
FROM handle h
JOIN message m ON m.handle_id = h.ROWID
JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
JOIN chat c ON c.ROWID = cmj.chat_id
WHERE c.style = 45
GROUP BY h.id
ORDER BY last_dt DESC
"""

HISTORY_SQL_TEMPLATE = """
SELECT
    m.ROWID AS rowid,
    m.is_from_me AS is_from_me,
    m.date AS date,
    COALESCE(m.text, '') AS text,
    m.cache_has_attachments AS has_attachments,
    h.service AS service,
    m.is_sent AS is_sent,
    m.is_delivered AS is_delivered,
    COALESCE(m.error, 0) AS error
FROM message m
LEFT JOIN handle h ON m.handle_id = h.ROWID
JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
JOIN chat c ON c.ROWID = cmj.chat_id
WHERE h.id IN ({placeholders}) AND c.style = 45
  {cursor_clause}
ORDER BY m.date DESC, m.ROWID DESC
LIMIT ?
"""

ATTACH_SQL = """
SELECT a.filename, a.mime_type, a.transfer_state, a.transfer_name, a.total_bytes
FROM message_attachment_join maj
JOIN attachment a ON a.ROWID = maj.attachment_id
WHERE maj.message_id = ?
"""

# ---------------------------------------------------------------------------
# Export SQL — unbounded (no LIMIT), ascending order, optional since filter.
# ---------------------------------------------------------------------------

EXPORT_MSGS_HANDLE_SQL = """
SELECT
    m.ROWID AS rowid,
    m.date AS date,
    m.is_from_me,
    COALESCE(m.text, '') AS text,
    m.cache_has_attachments,
    COALESCE(h.id, '') AS sender_handle
FROM message m
LEFT JOIN handle h ON m.handle_id = h.ROWID
JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
JOIN chat c ON c.ROWID = cmj.chat_id
WHERE h.id IN ({placeholders}) AND c.style = 45
  {since_clause}
ORDER BY m.date ASC, m.ROWID ASC
"""

EXPORT_MSGS_GROUP_SQL = """
SELECT
    m.ROWID AS rowid,
    m.date AS date,
    m.is_from_me,
    COALESCE(m.text, '') AS text,
    m.cache_has_attachments,
    COALESCE(h.id, '') AS sender_handle
FROM message m
LEFT JOIN handle h ON m.handle_id = h.ROWID
JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
JOIN chat c ON c.ROWID = cmj.chat_id
WHERE c.guid = ?
  {since_clause}
ORDER BY m.date ASC, m.ROWID ASC
"""

EXPORT_PHOTOS_HANDLE_SQL = """
SELECT a.filename, a.mime_type, m.date AS date
FROM message m
JOIN handle h ON m.handle_id = h.ROWID
JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
JOIN chat c ON c.ROWID = cmj.chat_id
JOIN message_attachment_join maj ON maj.message_id = m.ROWID
JOIN attachment a ON a.ROWID = maj.attachment_id
WHERE h.id IN ({placeholders}) AND c.style = 45
  AND a.filename IS NOT NULL
  AND (a.mime_type LIKE 'image/%' OR a.mime_type LIKE 'video/%')
  {since_clause}
ORDER BY m.date ASC
"""

EXPORT_PHOTOS_GROUP_SQL = """
SELECT a.filename, a.mime_type, m.date AS date
FROM message m
JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
JOIN chat c ON c.ROWID = cmj.chat_id
JOIN message_attachment_join maj ON maj.message_id = m.ROWID
JOIN attachment a ON a.ROWID = maj.attachment_id
WHERE c.guid = ?
  AND a.filename IS NOT NULL
  AND (a.mime_type LIKE 'image/%' OR a.mime_type LIKE 'video/%')
  {since_clause}
ORDER BY m.date ASC
"""

import re as _re

_URL_RE = _re.compile(r"https?://[^\s]+")


def _domain_from_url(url: str) -> str:
    """Extract display domain from a URL (e.g. 'reddit.com')."""
    from urllib.parse import urlparse
    try:
        host = urlparse(url).hostname or ""
        return host.removeprefix("www.").removeprefix("m.")
    except Exception:
        return ""


def _build_link_preview(text: str, attachments: list[dict]) -> dict | None:
    """If a message has URL text + pluginPayloadAttachment images, return a
    link preview dict; otherwise None.

    Picks the largest plugin attachment as the preview image (the smaller one
    is usually a favicon). Returns dict with keys: url, domain, image_path.
    """
    plugin_atts = [a for a in attachments if a.get("is_plugin")]
    if not plugin_atts:
        return None
    urls = _URL_RE.findall(text or "")
    if not urls:
        return None
    # Pick the largest plugin attachment as the preview image.
    best = max(plugin_atts, key=lambda a: a.get("total_bytes", 0))
    url = urls[0]
    return {
        "url": url,
        "domain": _domain_from_url(url),
        "image_path": best["path"],
    }


def _sniff_image_type(p: Path) -> str:
    """Detect image MIME type from magic bytes. Returns empty string if unknown."""
    try:
        with open(p, "rb") as f:
            header = f.read(16)
    except OSError:
        return ""
    if header[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if header[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp"
    if header[:4] == b"GIF8":
        return "image/gif"
    if header[:4] == b"\x00\x00\x01\x00":
        return "image/x-icon"
    return ""


# Group-chat history: scoped to a single chat GUID. Sender handle comes back
# per row so the UI can label "from Alice" above each bubble (group members
# are only distinguishable by handle_id). Outgoing group rows have handle_id
# NULL, so sender_handle is empty for those — the UI renders them as "me".
HISTORY_GROUP_SQL_TEMPLATE = """
SELECT
    m.ROWID AS rowid,
    m.is_from_me AS is_from_me,
    m.date AS date,
    COALESCE(m.text, '') AS text,
    m.cache_has_attachments AS has_attachments,
    COALESCE(h.id, '') AS sender_handle,
    COALESCE(h.service, '') AS service,
    m.is_sent AS is_sent,
    m.is_delivered AS is_delivered,
    COALESCE(m.error, 0) AS error
FROM message m
LEFT JOIN handle h ON m.handle_id = h.ROWID
JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
JOIN chat c ON c.ROWID = cmj.chat_id
WHERE c.guid = ?
  {cursor_clause}
ORDER BY m.date DESC, m.ROWID DESC
LIMIT ?
"""

ATTACHMENTS_BASE = (Path.home() / "Library" / "Messages" / "Attachments").resolve()

# On-disk thumb cache. Lives outside the Messages.app attachments dir so we
# never risk Messages noticing extra files alongside the originals. Keyed by
# (path, mtime) so renamed/replaced originals invalidate cleanly.
THUMB_CACHE_DIR = (STATE_DIR / "thumb_cache").resolve()
THUMB_MAX_EDGE = 720  # px; covers retina at the chat's ~280–360 displayed size
THUMB_TTL_DAYS = 180


def _thumb_for(orig: Path) -> Path | None:
    """Return a cached JPEG thumbnail for `orig`, generating if needed.

    Returns None if generation fails — caller should fall back to the original.
    Only meaningful for images; videos/audio/files should not call this.
    """
    try:
        st = orig.stat()
    except OSError:
        return None
    import hashlib
    key = hashlib.sha1(f"{orig}:{int(st.st_mtime)}".encode()).hexdigest()[:16]
    THUMB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = THUMB_CACHE_DIR / f"{key}.jpg"
    if cached.exists() and cached.stat().st_mtime >= st.st_mtime:
        return cached
    try:
        subprocess.run(
            ["sips", "-Z", str(THUMB_MAX_EDGE), "-s", "format", "jpeg",
             str(orig), "--out", str(cached)],
            check=True, capture_output=True, timeout=30,
        )
    except Exception:
        return None
    return cached if cached.exists() else None


async def _thumb_cache_evictor():
    """Daily sweep: drop thumbs whose files are older than THUMB_TTL_DAYS.

    Re-viewing an old chat regenerates the thumb on demand; this just bounds
    disk use. Originals in ~/Library/Messages/Attachments are never touched.
    """
    while True:
        try:
            if THUMB_CACHE_DIR.exists():
                cutoff = time.time() - THUMB_TTL_DAYS * 86400
                pruned = 0
                for f in THUMB_CACHE_DIR.iterdir():
                    try:
                        if f.is_file() and f.stat().st_mtime < cutoff:
                            f.unlink()
                            pruned += 1
                    except OSError:
                        continue
                if pruned:
                    log.info("thumb cache: evicted %d files older than %dd",
                             pruned, THUMB_TTL_DAYS)
        except Exception as e:
            log.warning("thumb cache evictor: %s", e)
        await asyncio.sleep(86400)


def _selected_time_format() -> str:
    """Return '12h' or '24h' from web.time_format config."""
    cfg = _bridge_config.load_config()
    return cfg.get("web", {}).get("time_format", "24h")


def _selected_history_limit() -> int:
    """Return the configured message load count from web.history_limit config."""
    cfg = _bridge_config.load_config()
    val = cfg.get("web", {}).get("history_limit", HISTORY_LIMIT)
    if val not in (25, 50, 100, 200):
        return HISTORY_LIMIT
    return int(val)


def _selected_custom_css() -> str:
    """Return the user-defined custom CSS string from web.custom_css config."""
    cfg = _bridge_config.load_config()
    return cfg.get("web", {}).get("custom_css", "")


_VALID_THUMBNAIL_SIZES = ("360", "720", "1080", "full")


def _selected_thumbnail_max_size() -> str:
    """Return the configured thumbnail max size from web.thumbnail_max_size config.

    Valid values: '360', '720', '1080', 'full'.  Empty string means use the
    CSS default (320 px, set in style.css).
    """
    cfg = _bridge_config.load_config()
    val = cfg.get("web", {}).get("thumbnail_max_size", "")
    return val if val in _VALID_THUMBNAIL_SIZES else ""


def _ts(apple_date: int) -> str:
    if not apple_date:
        return ""
    epoch = apple_date / 1_000_000_000 + 978307200  # 2001-01-01
    fmt = "%Y-%m-%d %I:%M %p" if _selected_time_format() == "12h" else "%Y-%m-%d %H:%M"
    return time.strftime(fmt, time.localtime(epoch))


def _short_ts(apple_date: int) -> str:
    """iMessage-style relative timestamp for the conversation list:
    today → HH:MM, yesterday → 'Yesterday', this week → weekday,
    this year → 'Mon DD', older → 'YYYY-MM-DD'."""
    if not apple_date:
        return ""
    epoch = apple_date / 1_000_000_000 + 978307200
    msg = time.localtime(epoch)
    now = time.localtime()
    use_12h = _selected_time_format() == "12h"
    if (msg.tm_year, msg.tm_yday) == (now.tm_year, now.tm_yday):
        return time.strftime("%I:%M %p" if use_12h else "%H:%M", msg)
    yest = time.localtime(time.mktime(now) - 86400)
    if (msg.tm_year, msg.tm_yday) == (yest.tm_year, yest.tm_yday):
        return "Yesterday"
    days_ago = (time.mktime(now) - epoch) / 86400
    if 0 < days_ago < 7:
        return time.strftime("%a", msg)
    if msg.tm_year == now.tm_year:
        return time.strftime("%b %d", msg)
    return time.strftime("%Y-%m-%d", msg)


def _name(handle: str) -> str:
    return CONTACTS.get(handle.lower()) or handle


def _handles_for_canonical(canonical: str) -> list[str]:
    """Return all chat.db handles that map to the same person as `canonical`.

    "Same person" = same Contacts display name. Handles without a name match
    are person-of-one (return [canonical]).
    """
    name = CONTACTS.get(canonical.lower())
    if not name:
        return [canonical]
    scope = relay_handles()
    same = [h for h, n in CONTACTS.items() if n == name and h in scope]
    return same or [canonical]


def _favorites() -> list[str]:
    """Return the ordered list of favorited handles from config."""
    cfg = _bridge_config.load_config()
    return list(cfg.get("web", {}).get("favorites", []))


def _save_favorites(handles: list[str]) -> None:
    cfg = _bridge_config.load_config()
    cfg.setdefault("web", {})["favorites"] = handles
    _bridge_config.save_config(cfg)


def list_conversations() -> list[dict]:
    conn = _snapshot()
    try:
        rows = conn.execute(CONVOS_SQL).fetchall()
    finally:
        conn.close()

    scope = relay_handles()
    seen: dict[str, dict] = {}
    for r in rows:
        h = r["handle"] or ""
        if h.lower() not in scope:
            continue
        name = CONTACTS.get(h.lower())
        key = name or h
        if key in seen:
            # First row per key wins because CONVOS_SQL orders by last_dt DESC.
            seen[key]["n"] += int(r["n"])
            seen[key]["all_handles"].append(h)
            continue
        raw_preview = r["preview"] or ""
        has_media = "￼" in raw_preview or "\ufffd" in raw_preview
        clean_preview = raw_preview.replace("￼", "").replace("\ufffd", "").strip()
        seen[key] = {
            "kind": "handle",
            "handle": h,
            "name": name or h,
            "preview": clean_preview,
            "has_media": has_media,
            "last_dt": int(r["last_dt"] or 0),
            "n": int(r["n"]),
            "all_handles": [h],
        }

    merged = list(seen.values()) + _list_group_convos()

    # Mark favorites and sort: favorites first (recency within each group).
    # Favorites can be stored as contact names or raw handles, so check both.
    favs = {h.lower() for h in _favorites()}
    for c in merged:
        name = (c.get("name") or "").lower()
        handle = (c.get("handle") or "").lower()
        c["is_favorite"] = (bool(name) and name in favs) or (bool(handle) and handle in favs)
    merged.sort(key=lambda c: (not c["is_favorite"], -c["last_dt"]))

    merged = merged[:CONVO_LIMIT]
    for c in merged:
        c["last"] = _short_ts(c["last_dt"])
    return merged


def _list_group_convos() -> list[dict]:
    """Sidebar entry per whitelisted group chat, with latest-message preview.

    Runs in-process (not via ChatDBReader) because the web process has its
    own backup-snapshot source connection; crossing processes would re-open
    chat.db and risk tripping the TCC cliff.
    """
    guids = sorted(wl_all_groups())
    if not guids:
        return []
    placeholders = ",".join("?" * len(guids))
    sql = f"""
        SELECT
            c.guid AS guid,
            COALESCE(c.display_name, '') AS name,
            c.chat_identifier AS chat_identifier,
            MAX(m.date) AS last_dt,
            SUM(CASE WHEN m.is_read = 0 AND m.is_from_me = 0 THEN 1 ELSE 0 END) AS n,
            (SELECT COALESCE(SUBSTR(m2.text,1,80), '')
               FROM message m2
               JOIN chat_message_join cmj2 ON cmj2.message_id = m2.ROWID
               WHERE cmj2.chat_id = c.ROWID
               ORDER BY m2.date DESC LIMIT 1) AS preview
        FROM chat c
        JOIN chat_message_join cmj ON cmj.chat_id = c.ROWID
        JOIN message m ON m.ROWID = cmj.message_id
        WHERE c.style = 43 AND c.guid IN ({placeholders})
        GROUP BY c.ROWID
    """
    conn = _snapshot()
    try:
        rows = conn.execute(sql, list(guids)).fetchall()
    finally:
        conn.close()
    out: list[dict] = []
    for r in rows:
        fallback = (r["chat_identifier"] or "").removeprefix("chat")[-6:]
        name = r["name"] or (f"Group {fallback}" if fallback else "(unnamed group)")
        raw_preview = r["preview"] or ""
        has_media = "￼" in raw_preview or "\ufffd" in raw_preview
        clean_preview = raw_preview.replace("￼", "").replace("\ufffd", "").strip()
        out.append({
            "kind": "group",
            "guid": r["guid"],
            "name": name,
            "preview": clean_preview,
            "has_media": has_media,
            "last_dt": int(r["last_dt"] or 0),
            "n": int(r["n"]),
        })
    return out


def _group_info(guid: str) -> dict:
    """Resolve a group GUID to {name, members} via chat.db. Unnamed groups
    get a synthetic short tag from chat_identifier so the header still shows
    something user-identifiable."""
    conn = _snapshot()
    try:
        row = conn.execute(
            """
            SELECT COALESCE(c.display_name, '') AS name,
                   c.chat_identifier AS chat_identifier,
                   (SELECT COUNT(DISTINCT chj.handle_id)
                      FROM chat_handle_join chj
                      WHERE chj.chat_id = c.ROWID) AS members
            FROM chat c
            WHERE c.guid = ? AND c.style = 43
            LIMIT 1
            """,
            (guid,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return {"name": "(unknown group)", "members": 0}
    fallback = (row["chat_identifier"] or "").removeprefix("chat")[-6:]
    name = row["name"] or (f"Group {fallback}" if fallback else "(unnamed group)")
    return {"name": name, "members": int(row["members"] or 0)}


# 3 seconds expressed as Apple nanoseconds (epoch relative to 2001-01-01).
_GALLERY_BUNDLE_WINDOW_NS: int = 3_000_000_000


def _bundle_galleries(msgs: list[dict]) -> list[dict]:
    """Merge consecutive all-image messages from the same sender within
    _GALLERY_BUNDLE_WINDOW_NS into a single gallery entry.

    Conditions for bundling two adjacent messages:
    - Neither has any text body.
    - Neither has a link_preview.
    - Every attachment in each message is kind='image' and ready=True.
    - Same ``from_me`` value (and same ``sender_handle`` for group chats).
    - The gap between the older message's ``date`` and the newer one's is
      <= _GALLERY_BUNDLE_WINDOW_NS.

    The merged entry inherits the first message's metadata and sets
    ``gallery=True``.  Attachments from all grouped messages are concatenated.
    """
    if not msgs:
        return msgs

    def _is_gallery_candidate(m: dict) -> bool:
        if m.get("text") or m.get("link_preview"):
            return False
        atts = m.get("attachments") or []
        if not atts:
            return False
        return all(a.get("kind") == "image" and a.get("ready") for a in atts)

    out: list[dict] = []
    i = 0
    while i < len(msgs):
        m = msgs[i]
        if not _is_gallery_candidate(m):
            out.append(m)
            i += 1
            continue

        group = [m]
        j = i + 1
        while j < len(msgs):
            nxt = msgs[j]
            if nxt["from_me"] != m["from_me"]:
                break
            # Group-chat: sender must match too.
            if nxt.get("sender_handle") != m.get("sender_handle"):
                break
            if not _is_gallery_candidate(nxt):
                break
            if nxt["date"] - group[-1]["date"] > _GALLERY_BUNDLE_WINDOW_NS:
                break
            group.append(nxt)
            j += 1

        if len(group) == 1:
            out.append(m)
        else:
            merged_atts: list[dict] = []
            for gm in group:
                merged_atts.extend(gm["attachments"])
            merged = dict(group[0])
            merged["attachments"] = merged_atts
            merged["gallery"] = True
            out.append(merged)

        i = j
    return out


def history_for(
    handle: str, before: tuple[int, int] | None = None
) -> tuple[list[dict], bool]:
    """Most-recent history_limit messages for a 1:1, oldest-first for render.

    `before` is an optional `(date, rowid)` cursor \u2014 return messages strictly
    older than that point. Used by the load-older paging endpoint.

    Fetches `history_limit + 1` rows so we can tell whether more pages exist
    without an extra round-trip; the extra row is dropped. Returns
    `(msgs, has_more)`.
    """
    limit = _selected_history_limit()
    handles = _handles_for_canonical(handle)
    placeholders = ",".join("?" * len(handles))
    if before is None:
        sql = HISTORY_SQL_TEMPLATE.format(
            placeholders=placeholders, cursor_clause=""
        )
        params = (*handles, limit + 1)
    else:
        sql = HISTORY_SQL_TEMPLATE.format(
            placeholders=placeholders,
            cursor_clause="AND (m.date, m.ROWID) < (?, ?)",
        )
        params = (*handles, before[0], before[1], limit + 1)
    conn = _snapshot()
    try:
        rows = conn.execute(sql, params).fetchall()
        has_more = len(rows) > limit
        rows = rows[:limit]
        atts_by_msg: dict[int, list[dict]] = defaultdict(list)
        for r in rows:
            if not r["has_attachments"]:
                continue
            for a in conn.execute(ATTACH_SQL, (r["rowid"],)).fetchall():
                fn = a["filename"]
                if not fn:
                    continue
                p = Path(fn).expanduser()
                mt = a["mime_type"] or ""
                tn = a["transfer_name"] or ""
                is_plugin = tn.endswith(".pluginPayloadAttachment")
                kind = "image" if mt.startswith("image/") else \
                       "video" if mt.startswith("video/") else \
                       "audio" if mt.startswith("audio/") else "file"
                atts_by_msg[r["rowid"]].append({
                    "path": str(p),
                    "name": p.name,
                    "mime": mt,
                    "kind": kind,
                    # Trust the filesystem: if the file is there, render it,
                    # regardless of what transfer_state thinks. The flag lags.
                    "ready": p.exists(),
                    "is_plugin": is_plugin,
                    "total_bytes": a["total_bytes"] or 0,
                })
    finally:
        conn.close()
    out = []
    for r in reversed(rows):
        body = (r["text"] or "").replace("\ufffc", "").replace("\ufffd", "").strip()
        atts = atts_by_msg.get(r["rowid"], [])
        preview = _build_link_preview(body, atts)
        # Hide plugin attachments from the normal attachment list when
        # they've been folded into a link preview card.
        if preview:
            atts = [a for a in atts if not a.get("is_plugin")]
        entry = {
            "rowid": r["rowid"],
            "date": int(r["date"] or 0),
            "from_me": bool(r["is_from_me"]),
            "ts": _ts(r["date"]),
            "text": body,
            "attachments": atts,
            "link_preview": preview,
        }
        if entry["from_me"]:
            entry.update(_delivery_status(r))
        out.append(entry)
    return _bundle_galleries(out), has_more


def history_for_group(
    guid: str, before: tuple[int, int] | None = None
) -> tuple[list[dict], bool]:
    """Message history for a single group chat, oldest-first for render.

    Adds sender_handle/sender_name to every entry so the UI can label
    incoming bubbles with the group member's name; outgoing rows keep the
    existing delivery fields.

    `before` is an optional `(date, rowid)` cursor — return messages strictly
    older than that point. Used by the load-older paging endpoint. Returns
    `(msgs, has_more)`; one extra row is fetched and dropped to compute the
    has-more flag without an extra round-trip.
    """
    limit = _selected_history_limit()
    if before is None:
        sql = HISTORY_GROUP_SQL_TEMPLATE.format(cursor_clause="")
        params = (guid, limit + 1)
    else:
        sql = HISTORY_GROUP_SQL_TEMPLATE.format(
            cursor_clause="AND (m.date, m.ROWID) < (?, ?)",
        )
        params = (guid, before[0], before[1], limit + 1)
    conn = _snapshot()
    try:
        rows = conn.execute(sql, params).fetchall()
        has_more = len(rows) > limit
        rows = rows[:limit]
        atts_by_msg: dict[int, list[dict]] = defaultdict(list)
        for r in rows:
            if not r["has_attachments"]:
                continue
            for a in conn.execute(ATTACH_SQL, (r["rowid"],)).fetchall():
                fn = a["filename"]
                if not fn:
                    continue
                p = Path(fn).expanduser()
                mt = a["mime_type"] or ""
                tn = a["transfer_name"] or ""
                is_plugin = tn.endswith(".pluginPayloadAttachment")
                kind = "image" if mt.startswith("image/") else \
                       "video" if mt.startswith("video/") else \
                       "audio" if mt.startswith("audio/") else "file"
                atts_by_msg[r["rowid"]].append({
                    "path": str(p),
                    "name": p.name,
                    "mime": mt,
                    "kind": kind,
                    "ready": p.exists(),
                    "is_plugin": is_plugin,
                    "total_bytes": a["total_bytes"] or 0,
                })
    finally:
        conn.close()
    out: list[dict] = []
    for r in reversed(rows):
        body = (r["text"] or "").replace("￼", "").replace("\ufffd", "").strip()
        sender = r["sender_handle"] or ""
        atts = atts_by_msg.get(r["rowid"], [])
        preview = _build_link_preview(body, atts)
        if preview:
            atts = [a for a in atts if not a.get("is_plugin")]
        entry = {
            "rowid": r["rowid"],
            "date": int(r["date"] or 0),
            "from_me": bool(r["is_from_me"]),
            "ts": _ts(r["date"]),
            "text": body,
            "attachments": atts,
            "link_preview": preview,
            "sender_handle": sender,
            "sender_name": _name(sender) if sender else "",
        }
        if entry["from_me"]:
            entry.update(_delivery_status(r))
        out.append(entry)
    return _bundle_galleries(out), has_more


def _cap_class_for(cap: str) -> str:
    """Map a capability label to one of the cap-* CSS classes used by the
    settings table and the contact view. Centralised here so both sites use
    the same colour-coding for the same string."""
    if "deregistered" in cap or "err=" in cap:
        return "cap-warn"
    if "✓" in cap:
        return "cap-good" if cap.startswith("iMessage") else "cap-warn"
    if "untested" in cap or "never contacted" in cap:
        return "cap-unknown"
    return "cap-unknown"


# Per-contact media gallery: most-recent N images/videos exchanged. Capped at
# CONTACT_MEDIA_LIMIT to keep the page light — the gallery is browse-bias, not
# archival. Audio/files are skipped (no useful thumbnail).
CONTACT_MEDIA_LIMIT = 200

CONTACT_MEDIA_HANDLE_SQL = """
SELECT a.filename, a.mime_type, m.date AS date
FROM message m
JOIN handle h ON m.handle_id = h.ROWID
JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
JOIN chat c ON c.ROWID = cmj.chat_id
JOIN message_attachment_join maj ON maj.message_id = m.ROWID
JOIN attachment a ON a.ROWID = maj.attachment_id
WHERE h.id IN ({placeholders}) AND c.style = 45
  AND a.filename IS NOT NULL
  AND (a.mime_type LIKE 'image/%' OR a.mime_type LIKE 'video/%')
ORDER BY m.date DESC
LIMIT ?
"""

CONTACT_MEDIA_GROUP_SQL = """
SELECT a.filename, a.mime_type, m.date AS date
FROM message m
JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
JOIN chat c ON c.ROWID = cmj.chat_id
JOIN message_attachment_join maj ON maj.message_id = m.ROWID
JOIN attachment a ON a.ROWID = maj.attachment_id
WHERE c.guid = ?
  AND a.filename IS NOT NULL
  AND (a.mime_type LIKE 'image/%' OR a.mime_type LIKE 'video/%')
ORDER BY m.date DESC
LIMIT ?
"""


def _media_rows_to_entries(rows) -> list[dict]:
    out: list[dict] = []
    for r in rows:
        fn = r["filename"]
        if not fn:
            continue
        p = Path(fn).expanduser()
        if not p.exists():
            continue
        mt = r["mime_type"] or ""
        out.append({
            "path": str(p),
            "name": p.name,
            "mime": mt,
            "kind": "video" if mt.startswith("video/") else "image",
        })
    return out


def contact_for(handle: str) -> dict:
    """Render data for the contact page of a 1:1. Includes every handle that
    maps to the same person (so an Alice with both phone and email shows both
    rows with their own capability), plus a thumbnail grid of all photos and
    videos exchanged across those handles."""
    handles = _handles_for_canonical(handle)
    name = _name(handle)
    svc = _services_for_handles(handles)
    outcomes = _outcomes_for_handles(handles)
    handle_rows: list[dict] = []
    for h in handles:
        hl = h.lower()
        cap = _capability_label(svc.get(hl, []), outcomes.get(hl))
        handle_rows.append({
            "handle": h,
            "capability": cap,
            "cap_class": _cap_class_for(cap),
        })
    placeholders = ",".join("?" * len(handles))
    sql = CONTACT_MEDIA_HANDLE_SQL.format(placeholders=placeholders)
    conn = _snapshot()
    try:
        rows = conn.execute(sql, (*handles, CONTACT_MEDIA_LIMIT)).fetchall()
    finally:
        conn.close()
    return {
        "kind": "handle",
        "handle": handle,
        "name": name,
        "subtitle": handle if name != handle else "",
        "handles": handle_rows,
        "media": _media_rows_to_entries(rows),
    }


def _group_members(guid: str) -> list[str]:
    """Return the chat-member handles for a group GUID, sorted."""
    conn = _snapshot()
    try:
        rows = conn.execute(
            """
            SELECT h.id AS handle
            FROM chat c
            JOIN chat_handle_join chj ON chj.chat_id = c.ROWID
            JOIN handle h ON h.ROWID = chj.handle_id
            WHERE c.guid = ? AND c.style = 43
            """,
            (guid,),
        ).fetchall()
    finally:
        conn.close()
    return sorted({r["handle"] for r in rows if r["handle"]})


def contact_for_group(guid: str) -> dict:
    """Render data for the contact page of a group chat: name, members with
    per-handle capability, and the photos+videos exchanged in the chat."""
    info = _group_info(guid)
    members = _group_members(guid)
    svc = _services_for_handles(members)
    outcomes = _outcomes_for_handles(members)
    member_rows: list[dict] = []
    for h in members:
        hl = h.lower()
        cap = _capability_label(svc.get(hl, []), outcomes.get(hl))
        member_rows.append({
            "handle": h,
            "name": CONTACTS.get(hl, ""),
            "capability": cap,
            "cap_class": _cap_class_for(cap),
        })
    conn = _snapshot()
    try:
        rows = conn.execute(
            CONTACT_MEDIA_GROUP_SQL, (guid, CONTACT_MEDIA_LIMIT),
        ).fetchall()
    finally:
        conn.close()
    return {
        "kind": "group",
        "chat": guid,
        "name": info["name"],
        "subtitle": f"{info['members']} members" if info["members"] else "group chat",
        "members": member_rows,
        "media": _media_rows_to_entries(rows),
    }


def _delivery_status(r) -> dict:
    """Derive UI-facing delivery status from a message row.

    Returns {status, label, hint, service} where status is one of
    'delivered' | 'sent' | 'pending' | 'failed'. The frontend renders
    a badge only when status != 'delivered' (delivered is the default
    expectation and would be visual noise on every bubble).
    """
    err = int(r["error"] or 0)
    is_sent = bool(r["is_sent"])
    is_delivered = bool(r["is_delivered"])
    service = r["service"] or ""
    if err:
        from chat_send import ERROR_HINTS
        hint = ERROR_HINTS.get(err) or f"iMessage error {err}"
        return {"status": "failed", "label": f"not delivered ({err})",
                "hint": hint, "service": service}
    if is_delivered:
        return {"status": "delivered", "label": "", "hint": "", "service": service}
    if is_sent:
        return {"status": "sent", "label": "sent", "hint": "awaiting delivery receipt",
                "service": service}
    return {"status": "pending", "label": "pending",
            "hint": "Messages.app hasn't confirmed this send yet",
            "service": service}


# ------- routes -------

@app.get("/")
async def index():
    return RedirectResponse(url="/app/", status_code=302)




async def _send_via_ctx_or_direct(
    request: Request, kind: str, handle: str, chat: str,
    body: str | None = None, file_path: Path | None = None,
) -> dict:
    """Issue one outbound send. In-process mode (`request.app.state.ctx` is
    set by `WebIntegration.start`) routes through the BridgeContext so the
    in-process echo deque sees the send. Standalone mode (no ctx) falls
    back to the direct `chat_send` path and registers in the cross-process
    `echo_log` file so a separately-running bridge.py still dedups.
    """
    ctx = getattr(request.app.state, "ctx", None)
    if ctx is not None:
        from integrations.base import SendTarget  # local import; ctx mode only
        target = SendTarget(
            kind="chat" if chat else "handle",
            value=chat or handle,
            label="",
        )
        if kind == "text":
            assert body is not None
            o = await ctx.send_text(target, body)
        else:
            assert file_path is not None
            o = await ctx.send_file(target, file_path)
        return {
            "kind": kind, "status": o.status, "hint": o.hint,
            "service": o.service, "error": o.error,
            "fell_back_to_sms": o.fell_back_to_sms,
            "original_error": o.original_error,
        }

    # Standalone fallback: direct AppleScript + cross-process echo log.
    if chat:
        if kind == "text":
            r = await asyncio.to_thread(send_text_to_chat_confirm, chat, body or "")
        else:
            r = await asyncio.to_thread(send_file_to_chat_confirm, chat, file_path)
    else:
        if kind == "text":
            r = await asyncio.to_thread(send_text_confirm, handle, body or "")
            echo_register(handle, "text", body or "")
        else:
            r = await asyncio.to_thread(send_file_confirm, handle, file_path)
            echo_register(handle, "photo")
    return {
        "kind": kind, "status": r.status, "hint": r.hint,
        "service": r.service, "error": r.error,
        "fell_back_to_sms": r.fell_back_to_sms,
        "original_error": r.original_error,
    }


@app.post("/send")
async def send(request: Request,
               handle: str = Form(""),
               chat: str = Form(""),
               body: str = Form(""),
               file: UploadFile | None = File(None)):
    """Outbound text and/or file. Exactly one of `handle` (1:1) or `chat`
    (group GUID) must be provided; group sends skip the SMS fallback path
    because the chat's service is fixed by its GUID."""
    if chat:
        if chat not in wl_all_groups():
            raise HTTPException(403, "group not in whitelist")
    elif handle:
        if handle.lower() not in relay_handles():
            raise HTTPException(403, "handle not in relay scope")
    else:
        raise HTTPException(400, "missing handle or chat")
    body = (body or "").strip()
    has_file = file is not None and file.filename
    if not body and not has_file:
        raise HTTPException(400, "empty send")

    results: list[dict] = []
    tmp_path = None
    try:
        if has_file:
            import tempfile
            suffix = Path(file.filename).suffix or ".bin"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(await file.read())
                tmp_path = Path(tmp.name)
            results.append(await _send_via_ctx_or_direct(
                request, "file", handle, chat, file_path=tmp_path,
            ))
        if body:
            results.append(await _send_via_ctx_or_direct(
                request, "text", handle, chat, body=body,
            ))
    finally:
        if tmp_path:
            try:
                tmp_path.unlink()
            except FileNotFoundError:
                pass

    # Worst-case status wins: failed > pending > sent > delivered.
    rank = {"delivered": 0, "sent": 1, "pending": 2, "failed": 3}
    worst = max(results, key=lambda x: rank.get(x["status"], 0)) if results else None
    return {"ok": worst is None or worst["status"] != "failed",
            "status": worst["status"] if worst else "delivered",
            "hint": worst["hint"] if worst else "",
            "fell_back_to_sms": any(r.get("fell_back_to_sms") for r in results),
            "results": results}



@app.get("/events")
async def events():
    """SSE stream tailing mirror.jsonl. Sends one `data: {json}` per relay event."""
    async def gen():
        if not MIRROR_FILE.exists():
            yield "event: ping\ndata: {}\n\n"
        # Seek to end and tail
        try:
            f = open(MIRROR_FILE, "r", encoding="utf-8")
        except FileNotFoundError:
            return
        f.seek(0, 2)
        last_ping = time.time()
        try:
            while True:
                line = f.readline()
                if line:
                    # Enrich with the resolved contact name so the in-page
                    # Notification can show "iMessage from Alice" instead of
                    # the raw handle. Pass through unchanged on parse errors.
                    out = line.strip()
                    try:
                        evt = json.loads(out)
                        h = evt.get("handle")
                        if h and "name" not in evt:
                            evt["name"] = _name(h)
                            out = json.dumps(evt)
                    except Exception:
                        pass
                    yield f"data: {out}\n\n"
                else:
                    await asyncio.sleep(0.5)
                    if time.time() - last_ping > 25:
                        yield "event: ping\ndata: {}\n\n"
                        last_ping = time.time()
        finally:
            f.close()

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/attachment")
async def attachment(path: str, size: str = "", dl: str = ""):
    """Serve an attachment file. Optional `dl` sets the download filename."""
    p = Path(path).expanduser().resolve()
    try:
        p.relative_to(ATTACHMENTS_BASE)
    except ValueError:
        raise HTTPException(403, "outside attachment dir")
    if not p.exists():
        raise HTTPException(404, "missing")
    # Thumbnail mode for inline chat images. Resizes via sips into a separate
    # cache dir; falls through to full-size on any failure so the UI still
    # shows something. Only meaningful for image suffixes — videos/audio
    # should never request size=thumb (the template doesn't).
    if size == "thumb":
        suffix = p.suffix.lower()
        is_image = suffix in (".jpg", ".jpeg", ".png", ".gif", ".heic", ".heif", ".webp")
        # pluginPayloadAttachment files have no extension but are images.
        if not is_image and "pluginPayloadAttachment" in p.name:
            is_image = bool(_sniff_image_type(p))
        if is_image:
            thumb = await asyncio.to_thread(_thumb_for, p)
            if thumb is not None:
                return FileResponse(
                    thumb, media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=2592000"},
                )
        # fall through to full-size on unknown ext or sips failure
    # Convert HEIC to JPEG on the fly so browsers can render it.
    if p.suffix.lower() in (".heic", ".heif"):
        cached = p.with_suffix(".jpg")
        if not (cached.exists() and cached.stat().st_mtime >= p.stat().st_mtime):
            try:
                subprocess.run(["sips", "-s", "format", "jpeg", str(p),
                                "--out", str(cached)],
                               check=True, capture_output=True, timeout=30)
            except Exception:
                return FileResponse(p)
        fname = (Path(dl).stem + ".jpg") if dl else cached.name
        return FileResponse(cached, media_type="image/jpeg", filename=fname)
    # iPhone .mov: relabel as video/mp4 so Chrome/Safari will play inline.
    # Firefox often still rejects (HEVC / QT container), falls back to the
    # download link in the template. See README "Firefox-compatible video
    # playback" for the transcode path if it's ever needed.
    if p.suffix.lower() == ".mov":
        fname = (Path(dl).stem + ".mp4") if dl else p.stem + ".mp4"
        return FileResponse(p, media_type="video/mp4", filename=fname)
    # pluginPayloadAttachment files have no extension — sniff magic bytes.
    if "pluginPayloadAttachment" in p.name:
        mt = _sniff_image_type(p)
        if mt:
            ext = {"image/jpeg": ".jpg", "image/png": ".png",
                   "image/webp": ".webp", "image/gif": ".gif"}.get(mt, "")
            fname = (dl + ext) if dl else p.name
            return FileResponse(
                p, media_type=mt, filename=fname,
                headers={"Cache-Control": "public, max-age=2592000"},
            )
    return FileResponse(p, filename=dl or p.name)


@app.get("/avatar")
async def avatar(handle: str):
    """Return the contact's avatar JPEG. Looks up by the requested handle, or
    falls back to any handle of the same person if that one has no image."""
    h = handle.lower()
    candidates = [h]
    name = CONTACTS.get(h)
    if name:
        candidates.extend(other for other, n in CONTACTS.items() if n == name and other != h)
    for cand in candidates:
        loc = IMAGE_INDEX.get(cand)
        if not loc:
            continue
        blob = await asyncio.to_thread(fetch_image, loc[0], loc[1], True)
        if blob:
            from fastapi.responses import Response
            return Response(content=blob, media_type="image/jpeg",
                             headers={"Cache-Control": "public, max-age=3600"})
    raise HTTPException(404)


# ------- web push notifications (desktop) -------

_push_lock = __import__("threading").Lock()


def _load_subs() -> list[dict]:
    if not PUSH_SUBS_FILE.exists():
        return []
    try:
        return json.loads(PUSH_SUBS_FILE.read_text())
    except Exception:
        return []


def _save_subs(subs: list[dict]) -> None:
    PUSH_SUBS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = PUSH_SUBS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(subs, indent=2))
    tmp.replace(PUSH_SUBS_FILE)


@app.get("/push/vapid-public-key")
async def push_vapid_key():
    if not VAPID_PUBLIC_KEY:
        raise HTTPException(503, "push not configured")
    return {"key": VAPID_PUBLIC_KEY}


@app.post("/push/subscribe")
async def push_subscribe(request: Request):
    body = await request.json()
    sub = body.get("subscription")
    if not sub or not sub.get("endpoint"):
        raise HTTPException(400, "missing subscription.endpoint")
    with _push_lock:
        subs = _load_subs()
        subs = [s for s in subs if s.get("endpoint") != sub["endpoint"]]
        subs.append(sub)
        _save_subs(subs)
    log.info("push subscribed; total=%d", len(subs))
    return {"ok": True, "count": len(subs)}


async def _push_tailer():
    """Tail mirror.jsonl and fan inbound events out as web-push."""
    if not (VAPID_PRIVATE_KEY and VAPID_PUBLIC_KEY):
        log.info("push disabled (no VAPID keys)")
        return
    from pywebpush import webpush, WebPushException

    while not MIRROR_FILE.exists():
        await asyncio.sleep(2)
    f = open(MIRROR_FILE, "r", encoding="utf-8")
    f.seek(0, 2)
    log.info("push tailer watching %s", MIRROR_FILE)
    try:
        while True:
            line = f.readline()
            if not line:
                await asyncio.sleep(0.5)
                continue
            try:
                evt = json.loads(line)
            except Exception:
                continue

            # Track outbound sends for hiatus mode suppression.
            if evt.get("event") == "outbound":
                h = evt.get("handle", "").lower()
                if h:
                    _hiatus_outbound[h] = time.time()

            detail = _notification_detail()
            muted = _notification_muted_contacts()
            mode = _notify_mode()
            selected = _notification_selected_contacts()
            payload = _build_push_payload(
                evt, detail, muted,
                notify_mode=mode,
                selected_contacts=selected,
            )
            if payload is None:
                continue

            # Hiatus suppression: skip if we sent a message to this contact recently.
            hiatus = _hiatus_settings()
            if hiatus["enabled"]:
                h = evt.get("handle", "").lower()
                last_out = _hiatus_outbound.get(h, 0)
                if time.time() - last_out < hiatus["duration_minutes"] * 60:
                    continue

            with _push_lock:
                subs = list(_load_subs())
            dead: list[str] = []
            for sub in subs:
                try:
                    await asyncio.to_thread(
                        webpush,
                        subscription_info=sub,
                        data=payload,
                        vapid_private_key=VAPID_PRIVATE_KEY,
                        vapid_claims={"sub": VAPID_CONTACT},
                    )
                except WebPushException as e:
                    code = getattr(e.response, "status_code", None)
                    if code in (404, 410):
                        dead.append(sub.get("endpoint", ""))
                    else:
                        log.warning("push error (%s): %s", code, e)
                except Exception as e:
                    log.warning("push unexpected: %s", e)
            if dead:
                with _push_lock:
                    subs = [s for s in _load_subs() if s.get("endpoint") not in dead]
                    _save_subs(subs)
                log.info("pruned %d dead push subs", len(dead))
    finally:
        f.close()


async def _reminder_checker():
    """Daily background task: push 'Haven't heard from X in N days' reminders."""
    await asyncio.sleep(60)  # brief startup delay
    while True:
        reminder = _reminder_settings()
        if reminder["enabled"] and (VAPID_PRIVATE_KEY and VAPID_PUBLIC_KEY):
            try:
                await _fire_reminder_pushes(reminder)
            except Exception as e:
                log.warning("reminder checker error: %s", e)
        await asyncio.sleep(86400)  # once per day


async def _fire_reminder_pushes(reminder: dict) -> None:
    """Query chat.db for overdue contacts and push reminder notifications."""
    from pywebpush import webpush, WebPushException

    days = reminder["days"]
    contacts_filter = {h.lower() for h in reminder["contacts"]} if reminder["contacts"] else None
    cutoff_apple = (time.time() - days * 86400 - APPLE_EPOCH_OFFSET) * 1_000_000_000

    db = _snapshot()
    rows = db.execute(
        """
        SELECT h.id AS handle, MAX(m.date) AS last_date
        FROM message m
        JOIN handle h ON m.handle_id = h.rowid
        WHERE m.is_from_me = 0
        GROUP BY h.id
        HAVING last_date < ?
        """,
        (cutoff_apple,),
    ).fetchall()

    with _push_lock:
        subs = list(_load_subs())
    if not subs:
        return

    for row in rows:
        handle = row["handle"]
        if contacts_filter and handle.lower() not in contacts_filter:
            continue
        last_unix = (row["last_date"] / 1_000_000_000) + APPLE_EPOCH_OFFSET
        days_since = max(1, int((time.time() - last_unix) / 86400))
        name = CONTACTS.get(handle.lower()) or CONTACTS.get(handle) or handle
        payload = json.dumps({
            "title": "iMessage Reminder",
            "body": f"Haven't heard from {name} in {days_since} day{'s' if days_since != 1 else ''}",
            "handle": handle,
            "tag": f"reminder-{handle}",
        })
        for sub in subs:
            try:
                await asyncio.to_thread(
                    webpush,
                    subscription_info=sub,
                    data=payload,
                    vapid_private_key=VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": VAPID_CONTACT},
                )
            except WebPushException as e:
                code = getattr(e.response, "status_code", None)
                if code not in (404, 410):
                    log.warning("reminder push error (%s): %s", code, e)
            except Exception as e:
                log.warning("reminder push unexpected: %s", e)


@app.on_event("startup")
async def _start_push_tailer():
    asyncio.create_task(_push_tailer())
    asyncio.create_task(_reminder_checker())
    asyncio.create_task(_thumb_cache_evictor())


@app.post("/refresh_contacts")
async def refresh_contacts():
    global CONTACTS, IMAGE_INDEX
    CONTACTS = await asyncio.to_thread(load_contacts)
    IMAGE_INDEX = await asyncio.to_thread(load_image_index)
    return {"ok": True, "loaded": len(CONTACTS), "with_image": len(IMAGE_INDEX)}


# ------- whitelist management -------

# Groups shown in the datalist are prefixed with this so the backend can tell
# a picked group apart from a contact name typed at the same input.
GROUP_LABEL_PREFIX = "[Group] "


def _list_named_groups() -> list[dict]:
    """Return named group chats from chat.db, most-recent first.

    Mirrors chat_db.ChatDBReader.list_groups but uses this process's
    _snapshot() (each process keeps its own persistent source conn to avoid
    TCC re-open issues). Only named groups appear in the web UI; unnamed
    groups can still be added by pasting a GUID.
    """
    conn = _snapshot()
    try:
        rows = conn.execute(
            """
            SELECT c.guid AS guid,
                   c.chat_identifier AS chat_identifier,
                   COALESCE(c.display_name, '') AS name,
                   MAX(cmj.message_id) AS last_rowid,
                   COUNT(DISTINCT chj.handle_id) AS member_count
            FROM chat c
            JOIN chat_message_join cmj ON cmj.chat_id = c.ROWID
            LEFT JOIN chat_handle_join chj ON chj.chat_id = c.ROWID
            WHERE c.style = 43 AND c.display_name != ''
            GROUP BY c.ROWID
            ORDER BY last_rowid DESC
            """
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "guid": r["guid"],
            "chat_identifier": r["chat_identifier"],
            "name": r["name"],
            "members": int(r["member_count"] or 0),
        }
        for r in rows
    ]


def _looks_like_group_guid(s: str) -> bool:
    s = s.strip()
    return (s.startswith("iMessage;") or s.startswith("SMS;")) and ";+;chat" in s


def _resolve_whitelist_input(s: str) -> tuple[list[str], list[str]]:
    """Name, handle, group name, or group GUID → (handles, group_guids).

    - "[Group] Civi-kids" → look up by display_name in chat.db (most-recent
      match wins if names collide).
    - "iMessage;+;chat…" → take as a literal group GUID.
    - Anything else is a handle/name: if it matches a Contacts display name,
      expand to every known handle for that person; otherwise treat as a
      single literal handle.
    """
    s = (s or "").strip()
    if not s:
        return [], []
    if s.startswith(GROUP_LABEL_PREFIX):
        needle = s[len(GROUP_LABEL_PREFIX):].strip().lower()
        # Pick the most-recent matching group — _list_named_groups is
        # already ordered by last message.
        for g in _list_named_groups():
            if g["name"].lower() == needle:
                return [], [g["guid"]]
        return [], []
    if _looks_like_group_guid(s):
        return [], [s]
    low = s.lower()
    matches = [h for h, name in CONTACTS.items() if name.lower() == low]
    return (matches if matches else [low]), []


def _resolve_handles(s: str) -> list[str]:
    """Back-compat shim. Callers that only want handles (e.g. capability
    lookups) drop any group results."""
    handles, _ = _resolve_whitelist_input(s)
    return handles


def _services_for_handles(handles: list[str]) -> dict[str, list[str]]:
    """{handle_lc: [services...]} — 'iMessage', 'SMS', or empty if unseen.

    Reads `handle.service` from chat.db. A phone number that has both rows
    (one per service) shows both. A handle we've never messaged is absent —
    callers should treat that as "unknown, will be revealed on first send".
    """
    if not handles:
        return {}
    lows = [h.lower() for h in handles]
    placeholders = ",".join("?" * len(lows))
    out: dict[str, list[str]] = {h: [] for h in lows}
    conn = _snapshot()
    try:
        rows = conn.execute(
            f"SELECT LOWER(id) AS id, service FROM handle WHERE LOWER(id) IN ({placeholders})",
            lows,
        ).fetchall()
        for r in rows:
            out.setdefault(r["id"], []).append(r["service"])
    finally:
        conn.close()
    return out


def _outcomes_for_handles(
    handles: list[str], window_days: int = 30
) -> dict[str, dict[str, dict]]:
    """Per-handle-per-service outgoing stats — mirror of ChatDBReader.outcomes_for.

    Uses the web process's _snapshot() instead of the bridge's reader. See
    the bridge-side method for the contract.
    """
    if not handles:
        return {}
    lows = [h.lower() for h in handles]
    placeholders = ",".join("?" * len(lows))
    cutoff_apple_ns = int(
        (time.time() - window_days * 86400 - APPLE_EPOCH_OFFSET) * 1_000_000_000
    )
    out: dict[str, dict[str, dict]] = {h: {} for h in lows}
    conn = _snapshot()
    try:
        agg_sql = f"""
            SELECT LOWER(h.id) AS handle, h.service AS service,
                   COUNT(*) AS total,
                   COALESCE(SUM(m.is_delivered), 0) AS delivered,
                   COALESCE(SUM(CASE WHEN m.error = 22 THEN 1 ELSE 0 END), 0) AS err22
            FROM message m JOIN handle h ON m.handle_id = h.ROWID
            WHERE m.is_from_me = 1
              AND LOWER(h.id) IN ({placeholders})
              AND m.date >= ?
            GROUP BY LOWER(h.id), h.service
        """
        for r in conn.execute(agg_sql, [*lows, cutoff_apple_ns]).fetchall():
            out[r["handle"]][r["service"]] = {
                "total": int(r["total"]),
                "delivered": int(r["delivered"]),
                "err22": int(r["err22"]),
            }
        latest_sql = f"""
            SELECT LOWER(h.id) AS handle, h.service AS service,
                   m.error AS error, m.is_delivered AS is_delivered, m.ROWID AS rowid
            FROM message m JOIN handle h ON m.handle_id = h.ROWID
            WHERE m.is_from_me = 1
              AND LOWER(h.id) IN ({placeholders})
              AND m.ROWID IN (
                  SELECT MAX(m2.ROWID) FROM message m2
                  JOIN handle h2 ON m2.handle_id = h2.ROWID
                  WHERE m2.is_from_me = 1
                    AND LOWER(h2.id) IN ({placeholders})
                  GROUP BY LOWER(h2.id), h2.service
              )
        """
        for r in conn.execute(latest_sql, [*lows, *lows]).fetchall():
            stats = out[r["handle"]].setdefault(
                r["service"], {"total": 0, "delivered": 0, "err22": 0}
            )
            stats["latest_error"] = int(r["error"] or 0)
            stats["latest_delivered"] = bool(r["is_delivered"])
            stats["latest_rowid"] = int(r["rowid"])
    finally:
        conn.close()
    return out


def _capability_label(
    services: list[str], outcomes: dict[str, dict] | None = None
) -> str:
    """Honest capability label for the web UI — see bridge._fmt_capability."""
    outcomes = outcomes or {}
    im = outcomes.get("iMessage") or {}
    sms = outcomes.get("SMS") or {}
    has_im_cfg = "iMessage" in services
    has_sms_cfg = "SMS" in services
    if not services:
        return "never contacted"

    im_total = im.get("total", 0)
    im_delivered = im.get("delivered", 0)
    im_latest_err = im.get("latest_error", 0)
    sms_total = sms.get("total", 0)
    sms_delivered = sms.get("delivered", 0)
    sms_latest_err = sms.get("latest_error", 0)

    # SMS carriers don't return delivery receipts — is_delivered=0 is the norm
    # for SMS even when the message landed. Only err=0 is trustworthy.
    if has_im_cfg:
        if im_latest_err == 22:
            if sms_total > 0 and sms_latest_err == 0:
                return f"iMessage deregistered → SMS ✓ ({sms_total} sent 30d)"
            if sms_total > 0:
                return f"iMessage deregistered → SMS err={sms_latest_err}"
            return "iMessage deregistered (SMS untested)"
        if im_total == 0 and "latest_rowid" not in im:
            if has_sms_cfg and sms_total > 0:
                return f"iMessage configured (untested 30d), SMS {sms_total} sent"
            return "iMessage configured (untested 30d)"
        if im_delivered > 0:
            tail = f", SMS {sms_total} sent" if sms_total > 0 else ""
            return f"iMessage ✓ {im_delivered}/{im_total} 30d{tail}"
        return f"iMessage {im_total} sent / 0 delivered 30d, latest err={im_latest_err}"

    if has_sms_cfg:
        if sms_total == 0:
            return "SMS only (untested 30d)"
        if sms_latest_err == 0:
            return f"SMS ✓ {sms_total} sent 30d"
        return f"SMS err={sms_latest_err} ({sms_total} sent 30d)"

    return "+".join(services) + " (unknown)"




def _contact_names() -> list[str]:
    """Deduped, sorted autocomplete options for the add-input datalist.

    Contacts come as plain names ("Alice Chen"); named groups are prefixed
    with "[Group] " so the backend can disambiguate when the same value
    comes back on form submit (and so the user can see what kind of row
    they're added)."""
    contact = sorted({n for n in CONTACTS.values() if n}, key=str.lower)
    groups = [f"{GROUP_LABEL_PREFIX}{g['name']}" for g in _list_named_groups()]
    return contact + groups


# Public alias used by web/api_ui.py
contact_names_for_autocomplete = _contact_names


def _installed_plugins() -> list[dict]:
    """Discover installed integration plugins and their schemas for settings UI.

    Scans both built-in integrations/ directory and third-party entry points.
    Returns a list of dicts with name, display_name, description, icon,
    schema, config, and enabled flag. Sorted by display name.
    """
    import importlib
    import importlib.metadata
    from integrations.base import integration_ui_meta

    seen: dict[str, dict] = {}
    cfg = _bridge_config.load_config()
    int_cfg = cfg.get("integrations", {})

    def _register(
        cls: type,
        dist_name: str | None = None,
        installed_version: str | None = None,
    ) -> None:
        name = getattr(cls, "NAME", None)
        if not name or name in seen:
            return
        schema = getattr(cls, "SETTINGS_SCHEMA", {})
        meta = integration_ui_meta(cls)
        plugin_cfg = int_cfg.get(name, {})
        seen[name] = {
            "name": name,
            "display_name": meta["display_name"],
            "description": meta["description"],
            "icon": meta["icon"],
            "schema": schema,
            "config": plugin_cfg,
            "enabled": plugin_cfg.get("enabled", False),
            # Third-party EP plugins carry dist metadata; built-ins don't.
            "dist_name": dist_name,
            "installed_version": installed_version,
        }

    # Built-in integrations
    integrations_dir = Path(__file__).resolve().parent.parent / "integrations"
    if integrations_dir.is_dir():
        for child in sorted(integrations_dir.iterdir()):
            if not child.is_dir() or child.name.startswith("_"):
                continue
            try:
                mod = importlib.import_module(f"integrations.{child.name}")
                for attr in dir(mod):
                    obj = getattr(mod, attr)
                    if isinstance(obj, type) and hasattr(obj, "NAME") and hasattr(obj, "SETTINGS_SCHEMA"):
                        _register(obj)
            except Exception:
                pass

    # Third-party entry points
    try:
        eps = importlib.metadata.entry_points(group="chatwire.integrations")
    except Exception:
        eps = []
    for ep in eps:
        try:
            cls = ep.load()
            if hasattr(cls, "NAME") and hasattr(cls, "SETTINGS_SCHEMA"):
                dist = getattr(ep, "dist", None)
                dist_name = dist.name if dist else None
                installed_version = dist.version if dist else None
                _register(cls, dist_name=dist_name, installed_version=installed_version)
        except Exception:
            pass

    return sorted(seen.values(), key=lambda p: p["display_name"].lower())



def _spam_whitelist_text() -> str:
    """Return spam_whitelist as newline-separated text for the settings textarea."""
    names = _bridge_config.load_config().get("web", {}).get("spam_whitelist", [])
    if isinstance(names, list):
        return "\n".join(n for n in names if n.strip())
    return ""


def _ntfy_topic() -> str:
    """Return the configured ntfy topic (empty string if not set)."""
    return str(_bridge_config.load_config().get("web", {}).get("ntfy_topic", "") or "")


_VALID_NOTIFICATION_DETAILS = ("rich", "sender_only", "private")


def _notification_detail() -> str:
    """Return the configured notification detail level (rich/sender_only/private)."""
    val = _bridge_config.load_config().get("web", {}).get("notification_detail", "rich")
    return val if val in _VALID_NOTIFICATION_DETAILS else "rich"


def _notification_muted_contacts() -> list:
    """Return the list of muted contact handles (no push sent for these)."""
    val = _bridge_config.load_config().get("web", {}).get("notification_muted_contacts", [])
    return val if isinstance(val, list) else []


def _notify_mode() -> str:
    """Return 'all' or 'selected' notification mode."""
    val = _bridge_config.load_config().get("web", {}).get("notify_mode", "all")
    return val if val in ("all", "selected") else "all"


def _notification_selected_contacts() -> list:
    """Return handles that should produce push when mode='selected'."""
    val = _bridge_config.load_config().get("web", {}).get("notification_selected_contacts", [])
    return val if isinstance(val, list) else []


def _hiatus_settings() -> dict:
    """Return hiatus mode config: enabled + duration_minutes."""
    web = _bridge_config.load_config().get("web", {})
    return {
        "enabled": bool(web.get("hiatus_enabled", False)),
        "duration_minutes": max(1, int(web.get("hiatus_duration_minutes", 30))),
    }


def _reminder_settings() -> dict:
    """Return reminder config: enabled, days, contacts list."""
    web = _bridge_config.load_config().get("web", {})
    contacts = web.get("reminder_contacts", [])
    return {
        "enabled": bool(web.get("reminder_enabled", False)),
        "days": max(1, int(web.get("reminder_days", 7))),
        "contacts": contacts if isinstance(contacts, list) else [],
    }


# In-memory hiatus tracker: {handle_lower: last_outbound_epoch_float}
_hiatus_outbound: dict[str, float] = {}


from push import build_push_payload as _push_build_payload_raw  # noqa: E402


def _build_push_payload(evt: dict, detail: str, muted: list) -> "str | None":
    """Build push payload using the current module's _name() resolver."""
    return _push_build_payload_raw(evt, detail, muted, name_fn=_name)


def _api_key_hint() -> str:
    """Return a masked display string for the current API key.

    Shows the first 8 plaintext characters stored alongside the hash, or
    "Not set" when no key is configured.
    """
    web_cfg = _bridge_config.load_config().get("web", {})
    prefix = web_cfg.get("api_key_prefix", "")
    if prefix:
        return prefix + "…"
    if web_cfg.get("api_key_hash"):
        return "Configured"  # hash present but prefix missing (older config)
    return "Not set"



@app.post("/api/settings/custom_css")
async def api_settings_custom_css(request: Request):
    """Persist user-defined CSS to web.custom_css in config."""
    body = await request.json()
    css = body.get("custom_css", "")
    if not isinstance(css, str):
        raise HTTPException(400, "custom_css must be a string")
    cfg = _bridge_config.load_config()
    cfg.setdefault("web", {})["custom_css"] = css
    _bridge_config.save_config(cfg)
    return {"ok": True}


@app.post("/api/settings/spam_whitelist")
async def api_settings_spam_whitelist(
    request: Request, spam_whitelist: str = Form(""),
):
    """Persist the broadcast-detection name whitelist to web.spam_whitelist."""
    names = [n.strip() for n in spam_whitelist.splitlines() if n.strip()]
    cfg = _bridge_config.load_config()
    cfg.setdefault("web", {})["spam_whitelist"] = names
    _bridge_config.save_config(cfg)
    return {"ok": True, "count": len(names)}


@app.post("/api/settings/ntfy_topic")
async def api_settings_ntfy_topic(
    request: Request, ntfy_topic: str = Form(""),
):
    """Persist the ntfy topic for spam-alert notifications to web.ntfy_topic."""
    topic = ntfy_topic.strip()
    cfg = _bridge_config.load_config()
    cfg.setdefault("web", {})["ntfy_topic"] = topic
    _bridge_config.save_config(cfg)
    return {"ok": True}


@app.post("/api/settings/notification_detail")
async def api_settings_notification_detail(
    request: Request, notification_detail: str = Form("rich"),
):
    """Persist the web-push notification detail level."""
    if notification_detail not in _VALID_NOTIFICATION_DETAILS:
        raise HTTPException(400, f"Invalid detail level: {notification_detail!r}")
    cfg = _bridge_config.load_config()
    cfg.setdefault("web", {})["notification_detail"] = notification_detail
    _bridge_config.save_config(cfg)
    return {"ok": True}


@app.post("/api/settings/notification_mute_toggle")
async def api_settings_notification_mute_toggle(
    request: Request, handle: str = Form(""), muted: str = Form("false"),
):
    """Toggle a contact's mute state in web.notification_muted_contacts."""
    h = handle.strip().lower()
    if not h:
        raise HTTPException(400, "handle required")
    mute_flag = muted.lower() in ("true", "1", "yes", "on")
    cfg = _bridge_config.load_config()
    web_cfg = cfg.setdefault("web", {})
    current: list = web_cfg.get("notification_muted_contacts", [])
    if isinstance(current, list):
        lowered = [x.lower() for x in current]
        if mute_flag and h not in lowered:
            current = list(current) + [h]
        elif not mute_flag:
            current = [x for x in current if x.lower() != h]
    else:
        current = [h] if mute_flag else []
    web_cfg["notification_muted_contacts"] = current
    _bridge_config.save_config(cfg)
    return {"ok": True, "muted": mute_flag}


@app.post("/api/settings/notify_mode")
async def api_settings_notify_mode(
    request: Request, notify_mode: str = Form("all"),
):
    """Persist notification mode: 'all' or 'selected'."""
    if notify_mode not in ("all", "selected"):
        raise HTTPException(400, f"Invalid notify_mode: {notify_mode!r}")
    cfg = _bridge_config.load_config()
    cfg.setdefault("web", {})["notify_mode"] = notify_mode
    _bridge_config.save_config(cfg)
    return {"ok": True}


@app.post("/api/settings/notification_select_toggle")
async def api_settings_notification_select_toggle(
    request: Request, handle: str = Form(""), selected: str = Form("true"),
):
    """Toggle a contact in the selected-contacts notification list."""
    h = handle.strip()
    if not h:
        raise HTTPException(400, "handle required")
    sel_flag = selected.lower() in ("true", "1", "yes", "on")
    cfg = _bridge_config.load_config()
    web_cfg = cfg.setdefault("web", {})
    current: list = web_cfg.get("notification_selected_contacts", [])
    if isinstance(current, list):
        lowered = [x.lower() for x in current]
        if sel_flag and h.lower() not in lowered:
            current = list(current) + [h]
        elif not sel_flag:
            current = [x for x in current if x.lower() != h.lower()]
    else:
        current = [h] if sel_flag else []
    web_cfg["notification_selected_contacts"] = current
    _bridge_config.save_config(cfg)
    return {"ok": True, "selected": sel_flag}


@app.post("/api/settings/hiatus_settings")
async def api_settings_hiatus_settings(
    request: Request,
    hiatus_enabled: str = Form("false"),
    hiatus_duration_minutes: str = Form("30"),
):
    """Persist hiatus mode settings."""
    enabled = hiatus_enabled.lower() in ("true", "1", "on", "yes")
    try:
        mins = int(hiatus_duration_minutes)
        if not (1 <= mins <= 1440):
            raise ValueError
    except (ValueError, TypeError):
        raise HTTPException(400, "hiatus_duration_minutes must be 1–1440")
    cfg = _bridge_config.load_config()
    web = cfg.setdefault("web", {})
    web["hiatus_enabled"] = enabled
    web["hiatus_duration_minutes"] = mins
    _bridge_config.save_config(cfg)
    return {"ok": True}


@app.post("/api/settings/reminder_settings")
async def api_settings_reminder_settings(
    request: Request,
    reminder_enabled: str = Form("false"),
    reminder_days: str = Form("7"),
):
    """Persist reminder timer settings."""
    enabled = reminder_enabled.lower() in ("true", "1", "on", "yes")
    try:
        days = int(reminder_days)
        if not (1 <= days <= 365):
            raise ValueError
    except (ValueError, TypeError):
        raise HTTPException(400, "reminder_days must be 1–365")
    cfg = _bridge_config.load_config()
    web = cfg.setdefault("web", {})
    web["reminder_enabled"] = enabled
    web["reminder_days"] = days
    _bridge_config.save_config(cfg)
    return {"ok": True}


@app.post("/api/settings/api_key/generate")
async def api_settings_api_key_generate():
    """Generate a new random API key.

    Stores the SHA-256 hash + first-8-char prefix in config.
    Returns the plaintext key exactly once so the caller can copy it.
    """
    key = secrets.token_hex(32)  # 64-char hex string
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    prefix = key[:8]
    cfg = _bridge_config.load_config()
    cfg.setdefault("web", {})["api_key_hash"] = key_hash
    cfg.setdefault("web", {})["api_key_prefix"] = prefix
    _bridge_config.save_config(cfg)
    return {"key": key, "hint": prefix + "…"}


@app.post("/api/settings/api_key/revoke")
async def api_settings_api_key_revoke():
    """Clear the API key from config."""
    cfg = _bridge_config.load_config()
    web_cfg = cfg.setdefault("web", {})
    web_cfg.pop("api_key_hash", None)
    web_cfg.pop("api_key_prefix", None)
    _bridge_config.save_config(cfg)
    return {"ok": True}



@app.get("/api/plugins/registry")
async def api_plugins_registry():
    """Return the cached plugin registry JSON (24 h TTL)."""
    registry = await asyncio.to_thread(_fetch_registry_blocking)
    return registry


@app.post("/api/plugins/install")
async def api_plugins_install(request: Request):
    """Install a plugin package via ``pipx inject chatwire <package>``.

    Request body: ``{"package": "chatwire-ntfy", "force": false}``

    Returns JSON:
      ``{"ok": true, "signed": true}``
      ``{"ok": false, "error": "..."}``
      ``{"ok": true, "signed": false, "warning": "unsigned"}``  ← for unsigned
    """
    body = await request.json()
    package: str = body.get("package", "").strip()
    force: bool = bool(body.get("force", False))

    if not package:
        raise HTTPException(400, "package is required")

    # Basic sanity — package names are alphanumeric + hyphens/underscores/dots.
    import re as _re
    if not _re.fullmatch(r"[A-Za-z0-9_.\-]+(?:==[\w.]+)?", package):
        raise HTTPException(400, f"Invalid package name: {package!r}")

    # Run pipx inject (blocking, wrapped in a thread).
    def _do_inject(pkg: str) -> tuple[bool, str]:
        result = subprocess.run(
            ["pipx", "inject", "chatwire", pkg],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False, (result.stderr or result.stdout).strip()
        return True, ""

    ok, err = await asyncio.to_thread(_do_inject, package)
    if not ok:
        return {"ok": False, "error": err}

    # Derive dist name (strip version specifier if present).
    dist_name = package.split("==")[0]

    # Check signature.
    try:
        verify_plugin(dist_name)
        signed = True
    except PluginNotTrusted:
        signed = False

    if signed:
        return {"ok": True, "signed": True}
    return {"ok": True, "signed": False, "warning": "unsigned"}


# ---------------------------------------------------------------------------
# Plugin + core version-check helpers
# ---------------------------------------------------------------------------

def _plugin_update_available(plugins: list[dict]) -> dict[str, dict]:
    """Return update info for third-party EP plugins that have a newer PyPI version.

    Only considers plugins that have both *dist_name* and *installed_version*
    (i.e. those that came from importlib entry-points, not built-ins).

    Returns::

        {plugin_name: {"current": "0.1.0", "latest": "0.2.0", "dist": "chatwire-ntfy"}}
    """
    dist_map = {
        p["dist_name"]: p["installed_version"]
        for p in plugins
        if p.get("dist_name") and p.get("installed_version")
    }
    if not dist_map:
        return {}

    updates_by_dist = _vc_check_updates(dist_map, _VERSION_CACHE_FILE)

    result: dict[str, dict] = {}
    for p in plugins:
        dist = p.get("dist_name")
        if dist and dist in updates_by_dist:
            result[p["name"]] = {
                "current": p["installed_version"],
                "latest": updates_by_dist[dist],
                "dist": dist,
            }
    return result


def _chatwire_latest_version() -> str | None:
    """Return the latest chatwire version from PyPI (cached 24h), or None."""
    import time as _time
    mem_cache = _vc_load_cache(_VERSION_CACHE_FILE)
    version = _vc_fetch_pypi_version("chatwire", mem_cache, _time.time())
    _vc_save_cache(_VERSION_CACHE_FILE, mem_cache)
    return version


# ---------------------------------------------------------------------------
# Plugin version-check and update routes
# ---------------------------------------------------------------------------

@app.get("/api/plugins/version-check")
async def api_plugins_version_check():
    """Return available updates for installed third-party plugins.

    Response: ``{plugin_name: {"current": "x.y.z", "latest": "a.b.c", "dist": "pkg"}}``
    """
    plugins = _installed_plugins()
    updates = await asyncio.to_thread(_plugin_update_available, plugins)
    return updates


@app.post("/api/plugins/update")
async def api_plugins_update(request: Request):
    """Update a plugin package via ``pipx inject --force chatwire <package>``.

    Request body: ``{"package": "chatwire-ntfy"}``

    Returns JSON:
      ``{"ok": true, "signed": true}``
      ``{"ok": false, "error": "..."}``
      ``{"ok": true, "signed": false, "warning": "unsigned"}``
    """
    body = await request.json()
    package: str = body.get("package", "").strip()

    if not package:
        raise HTTPException(400, "package is required")

    import re as _re
    if not _re.fullmatch(r"[A-Za-z0-9_.\-]+(?:==[\w.]+)?", package):
        raise HTTPException(400, f"Invalid package name: {package!r}")

    def _do_inject_force(pkg: str) -> tuple[bool, str]:
        result = subprocess.run(
            ["pipx", "inject", "--force", "chatwire", pkg],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False, (result.stderr or result.stdout).strip()
        return True, ""

    ok, err = await asyncio.to_thread(_do_inject_force, package)
    if not ok:
        return {"ok": False, "error": err}

    dist_name = package.split("==")[0]

    try:
        verify_plugin(dist_name)
        signed = True
    except PluginNotTrusted:
        signed = False

    if signed:
        return {"ok": True, "signed": True}
    return {"ok": True, "signed": False, "warning": "unsigned"}


@app.get("/api/chatwire/version-check")
async def api_chatwire_version_check():
    """Return chatwire core version info from PyPI (cached 24h).

    Response::

        {"current": "1.1.0", "latest": "1.2.0", "update_available": true}
        {"current": "1.1.0", "latest": "1.1.0", "update_available": false}
        {"current": "1.1.0", "latest": null,     "update_available": false}
    """
    current = _version.__version__
    latest = await asyncio.to_thread(_chatwire_latest_version)
    return {
        "current": current,
        "latest": latest,
        "update_available": bool(latest and latest != current),
    }




@app.post("/whitelist/add")
async def whitelist_add_route(input: str = Form("")):
    handles, groups = _resolve_whitelist_input(input)
    for h in handles:
        wl_add(h)
    for g in groups:
        wl_add_group(g)
    return {"ok": True}


@app.post("/whitelist/remove")
async def whitelist_remove_route(input: str = Form("")):
    """Remove a whitelist entry by handle, contact name, or group GUID."""
    handles, groups = _resolve_whitelist_input(input)
    for h in handles:
        wl_remove(h)
    for g in groups:
        wl_remove_group(g)
    return {"ok": True}



# ---------------------------------------------------------------------------
# Advanced settings routes (chunk 9)
# ---------------------------------------------------------------------------

from web.service_control import LAUNCHD_SERVICES as _LAUNCHD_SERVICES, parse_service_status as _parse_service_status


@app.post("/api/settings/port")
async def api_settings_port(request: Request, port: int = Form(8723)):
    """Validate and persist web.port (1024–65535).  Requires restart."""
    if not (1024 <= port <= 65535):
        raise HTTPException(400, f"Port must be between 1024 and 65535, got {port}")
    cfg = _bridge_config.load_config()
    cfg.setdefault("web", {})["port"] = port
    _bridge_config.save_config(cfg)
    return {"ok": True, "port": port, "restart_required": True}


@app.post("/api/settings/bind")
async def api_settings_bind(request: Request, bind: str = Form("127.0.0.1")):
    """Persist web.bind address (localhost, 0.0.0.0, or custom non-empty string)."""
    b = bind.strip()
    if not b:
        raise HTTPException(400, "bind address cannot be empty")
    cfg = _bridge_config.load_config()
    cfg.setdefault("web", {})["bind"] = b
    _bridge_config.save_config(cfg)
    return {"ok": True, "bind": b}


@app.post("/api/settings/proxy_headers")
async def api_settings_proxy_headers(
    request: Request, proxy_headers: str = Form("false"),
):
    """Persist web.proxy_headers bool (trust X-Forwarded-* headers)."""
    enabled = proxy_headers.lower() in ("true", "1", "yes", "on")
    cfg = _bridge_config.load_config()
    cfg.setdefault("web", {})["proxy_headers"] = enabled
    _bridge_config.save_config(cfg)
    return {"ok": True, "proxy_headers": enabled}


@app.get("/api/service/status")
async def api_service_status():
    """Return running state of each chatwire launchd agent.

    Runs `launchctl list | grep chatwire` via subprocess and parses the
    output into a JSON dict: {bridge: bool, web: bool, keepawake: bool}.
    On platforms without launchctl (e.g. Linux dev boxes) all values are
    false rather than raising.
    """
    import subprocess
    try:
        out = subprocess.check_output(
            ["/bin/launchctl", "list"],
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).decode(errors="replace")
        # Filter to chatwire lines only
        filtered = "\n".join(l for l in out.splitlines() if "chatwire" in l)
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
        filtered = ""
    return _parse_service_status(filtered)


@app.post("/api/service/toggle")
async def api_service_toggle(request: Request):
    """Start or stop a chatwire launchd agent.

    Body: {service: "bridge"|"web"|"keepawake", action: "start"|"stop"}.
    Calls launchctl bootstrap / bootout via subprocess.
    """
    import subprocess
    data = await request.json()
    service = data.get("service", "")
    action = data.get("action", "")
    if service not in _LAUNCHD_SERVICES:
        raise HTTPException(400, f"Unknown service: {service!r}")
    if action not in ("start", "stop"):
        raise HTTPException(400, f"action must be 'start' or 'stop', got {action!r}")
    label = _LAUNCHD_SERVICES[service]
    plist_path = f"{os.path.expanduser('~')}/Library/LaunchAgents/{label}.plist"
    try:
        if action == "start":
            subprocess.check_call(
                ["/bin/launchctl", "bootstrap", f"gui/{os.getuid()}", plist_path],
                timeout=10,
            )
        else:
            subprocess.check_call(
                ["/bin/launchctl", "bootout", f"gui/{os.getuid()}", plist_path],
                timeout=10,
            )
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
        raise HTTPException(500, f"launchctl failed: {exc}") from exc
    return {"ok": True, "service": service, "action": action}


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------

def _apple_to_iso_utc(apple_ns: int) -> str:
    """Convert Apple nanosecond timestamp to UTC ISO-8601 string."""
    unix = apple_ns / 1_000_000_000 + APPLE_EPOCH_OFFSET
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(unix))


def _apple_to_date_str(apple_ns: int) -> str:
    """Convert Apple nanosecond timestamp to YYYY-MM-DD string (local time)."""
    unix = apple_ns / 1_000_000_000 + APPLE_EPOCH_OFFSET
    return time.strftime("%Y-%m-%d", time.localtime(unix))


def _parse_since_ns(since: str) -> int:
    """Parse a YYYY-MM-DD string into Apple epoch nanoseconds. Raises ValueError."""
    t = time.strptime(since, "%Y-%m-%d")
    unix = time.mktime(t)
    return int((unix - APPLE_EPOCH_OFFSET) * 1_000_000_000)


def _export_messages_rows(handle: str, chat: str, since_ns: int | None) -> list[dict]:
    """Fetch all messages for a 1:1 or group conversation, return export dicts."""
    since_clause = "AND m.date >= ?" if since_ns is not None else ""
    conn = _snapshot()
    try:
        if chat:
            sql = EXPORT_MSGS_GROUP_SQL.format(since_clause=since_clause)
            params: tuple = (chat, since_ns) if since_ns is not None else (chat,)
            rows = conn.execute(sql, params).fetchall()
        else:
            handles = _handles_for_canonical(handle)
            placeholders = ",".join("?" * len(handles))
            sql = EXPORT_MSGS_HANDLE_SQL.format(
                placeholders=placeholders, since_clause=since_clause
            )
            params = (*handles, since_ns) if since_ns is not None else tuple(handles)
            rows = conn.execute(sql, params).fetchall()

        # Gather attachment filenames (skip plugin payloads — they have no real name).
        atts_by_msg: dict[int, list[str]] = defaultdict(list)
        for r in rows:
            if not r["cache_has_attachments"]:
                continue
            for a in conn.execute(ATTACH_SQL, (r["rowid"],)).fetchall():
                tn = a["transfer_name"] or ""
                fn = a["filename"] or ""
                if tn.endswith(".pluginPayloadAttachment"):
                    continue
                name = tn or Path(fn).name if fn else ""
                if name:
                    atts_by_msg[r["rowid"]].append(name)
    finally:
        conn.close()

    out: list[dict] = []
    for r in rows:
        sender_handle = r["sender_handle"] or ""
        body = (r["text"] or "").replace("\ufffc", "").replace("\ufffd", "").strip()
        out.append({
            "timestamp": _apple_to_iso_utc(r["date"]),
            "sender_name": "Me" if r["is_from_me"] else (_name(sender_handle) or sender_handle),
            "sender_handle": "" if r["is_from_me"] else sender_handle,
            "text": body,
            "attachments": atts_by_msg.get(r["rowid"], []),
        })
    return out


def _export_photo_rows(handle: str, chat: str, since_ns: int | None) -> list[dict]:
    """Fetch all image/video attachment paths with date info."""
    since_clause = "AND m.date >= ?" if since_ns is not None else ""
    conn = _snapshot()
    try:
        if chat:
            sql = EXPORT_PHOTOS_GROUP_SQL.format(since_clause=since_clause)
            params: tuple = (chat, since_ns) if since_ns is not None else (chat,)
            rows = conn.execute(sql, params).fetchall()
        else:
            handles = _handles_for_canonical(handle)
            placeholders = ",".join("?" * len(handles))
            sql = EXPORT_PHOTOS_HANDLE_SQL.format(
                placeholders=placeholders, since_clause=since_clause
            )
            params = (*handles, since_ns) if since_ns is not None else tuple(handles)
            rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    out: list[dict] = []
    for r in rows:
        fn = r["filename"]
        if not fn:
            continue
        p = Path(fn).expanduser()
        if not p.exists():
            continue
        out.append({
            "path": str(p),
            "date_str": _apple_to_date_str(r["date"]),
        })
    return out


def _export_filename_base(handle: str, chat: str, since: str) -> str:
    """Build a safe filename prefix from handle/chat + optional since date."""
    base = (handle or chat)
    # Strip characters not safe for filenames.
    safe = "".join(c for c in base if c.isalnum() or c in ("_", "-"))
    if since:
        safe += f"_{since}"
    return safe or "export"


# ---------------------------------------------------------------------------
# Export routes
# ---------------------------------------------------------------------------

@app.get("/api/export/messages")
async def api_export_messages(
    handle: str = "", chat: str = "", format: str = "json", since: str = ""
):
    """Export conversation messages as JSON, TXT, or CSV.

    Query params:
      handle  — 1:1 phone/email handle (mutually exclusive with chat)
      chat    — group chat GUID (mutually exclusive with handle)
      format  — json | txt | csv  (default: json)
      since   — optional YYYY-MM-DD date filter; only messages on/after that date
    """
    if not handle and not chat:
        raise HTTPException(400, "handle or chat required")
    if format not in ("json", "txt", "csv"):
        raise HTTPException(400, "format must be json, txt, or csv")
    if chat and chat not in wl_all_groups():
        raise HTTPException(403, "group not in whitelist")
    if handle and handle.lower() not in relay_handles():
        raise HTTPException(403, "handle not in relay scope")

    since_ns: int | None = None
    if since:
        try:
            since_ns = _parse_since_ns(since)
        except ValueError:
            raise HTTPException(400, "since must be YYYY-MM-DD")

    msgs = await asyncio.to_thread(_export_messages_rows, handle, chat, since_ns)
    fname = _export_filename_base(handle, chat, since)

    if format == "json":
        content = json.dumps(msgs, ensure_ascii=False, indent=2)
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{fname}_messages.json"'},
        )
    if format == "txt":
        lines: list[str] = []
        for m in msgs:
            att_str = f" [{', '.join(m['attachments'])}]" if m["attachments"] else ""
            lines.append(f"{m['timestamp']} {m['sender_name']}: {m['text']}{att_str}")
        content = "\n".join(lines)
        return Response(
            content=content,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{fname}_messages.txt"'},
        )
    # csv
    import csv
    import io as _io
    buf = _io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["timestamp", "sender_name", "sender_handle", "text", "attachments"])
    for m in msgs:
        writer.writerow([
            m["timestamp"], m["sender_name"], m["sender_handle"],
            m["text"], "; ".join(m["attachments"]),
        ])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}_messages.csv"'},
    )


@app.get("/api/export/photos")
async def api_export_photos(handle: str = "", chat: str = "", since: str = ""):
    """Export photos/videos as a ZIP file organised into YYYY-MM-DD folders.

    Query params:
      handle  — 1:1 phone/email handle (mutually exclusive with chat)
      chat    — group chat GUID
      since   — optional YYYY-MM-DD date filter
    """
    if not handle and not chat:
        raise HTTPException(400, "handle or chat required")
    if chat and chat not in wl_all_groups():
        raise HTTPException(403, "group not in whitelist")
    if handle and handle.lower() not in relay_handles():
        raise HTTPException(403, "handle not in relay scope")

    since_ns: int | None = None
    if since:
        try:
            since_ns = _parse_since_ns(since)
        except ValueError:
            raise HTTPException(400, "since must be YYYY-MM-DD")

    rows = await asyncio.to_thread(_export_photo_rows, handle, chat, since_ns)
    fname = _export_filename_base(handle, chat, since)

    def _build_zip() -> bytes:
        import io as _io
        import zipfile
        # Track names to avoid collisions within the same date folder.
        seen: dict[str, int] = {}
        buf = _io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for row in rows:
                p = Path(row["path"])
                date_folder = row["date_str"]
                arcname = f"{date_folder}/{p.name}"
                if arcname in seen:
                    seen[arcname] += 1
                    stem, suffix = p.stem, p.suffix
                    arcname = f"{date_folder}/{stem}_{seen[arcname]}{suffix}"
                else:
                    seen[arcname] = 0
                zf.write(p, arcname)
        return buf.getvalue()

    zip_bytes = await asyncio.to_thread(_build_zip)
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}_photos.zip"'},
    )


# --- React SPA (v2 frontend, Phase 1+) ---
_react_dist = Path(__file__).parent / "frontend" / "dist"

if _react_dist.is_dir():
    from starlette.staticfiles import StaticFiles as _SPA_Static

    # Serve built assets (JS, CSS, images) at /app/assets/
    app.mount(
        "/app/assets",
        _SPA_Static(directory=_react_dist / "assets"),
        name="react-assets",
    )

    @app.get("/app/{path:path}")
    @app.get("/app")
    async def react_spa(request: Request, path: str = "") -> FileResponse:
        """Serve React SPA — all /app/* routes return index.html,
        letting React Router handle client-side routing."""
        return FileResponse(_react_dist / "index.html")


def main():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=WEB_PORT, log_level="info")


if __name__ == "__main__":
    main()
