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

from typing import Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel
from web import log_stream as _ls

router = APIRouter()

# Temp dir for uploaded attachments; created on first use.
_UPLOAD_DIR = Path.home() / ".chatwire" / "uploads"

# Custom notification sounds directory.
_SOUNDS_DIR = Path.home() / ".chatwire" / "sounds"
_VALID_SOUND_EXTS = frozenset({".wav", ".mp3", ".ogg", ".m4a", ".aac"})
_SOUND_TYPES = frozenset({"sent", "received"})
_SOUND_MODES = frozenset({"default", "none", "custom"})


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
    reply_to_guid: str = ""  # non-empty → threaded reply (informational; AppleScript doesn't wire threading)


class PasswordBody(BaseModel):
    current_password: str = ""
    new_password: str = ""
    clear: bool = False


class UiSettingsPatchBody(BaseModel):
    theme_mode: Optional[str] = None


class SoundsConfigBody(BaseModel):
    sent: Optional[str] = None
    received: Optional[str] = None


class LoginBody(BaseModel):
    password: str = ""
    next: str = "/"


class UnlockBody(BaseModel):
    code: str


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


# ---------------------------------------------------------------------------
# Read-state endpoints
# ---------------------------------------------------------------------------

class ReadStateIn(BaseModel):
    conversation_id: str
    last_rowid: int


@router.get("/read-state")
async def ui_get_read_state():
    """Return {conversation_id: last_seen_rowid} across all interfaces."""
    from read_state import get_all_last_seen  # noqa: PLC0415
    mapping = await asyncio.to_thread(get_all_last_seen)
    return mapping


@router.post("/read-state")
async def ui_mark_seen(body: ReadStateIn):
    """Mark a conversation as seen from the web interface up to last_rowid."""
    from read_state import mark_seen  # noqa: PLC0415
    await asyncio.to_thread(mark_seen, body.conversation_id, "web", body.last_rowid)
    return {"ok": True}


@router.post("/read-state/all")
async def ui_mark_all_seen():
    """Mark all conversations as seen (clear unread badges)."""
    from read_state import mark_all_seen  # noqa: PLC0415
    convos = await asyncio.to_thread(_list_conversations)
    await asyncio.to_thread(mark_all_seen, "web", convos)
    return {"ok": True}


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

    # No whitelist guard on READ — if a conversation is in chat.db the user
    # owns it.  Whitelist controls who can SEND, not who can READ.
    if guid:
        msgs, has_more = await asyncio.to_thread(_history_for_group, guid, before)
        key = guid
    elif handle:
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
            raise HTTPException(
                429, {"message": str(exc), "cooldown_remaining": None, "step": 0}
            ) from exc
        except BroadcastBlockedError as exc:
            raise HTTPException(
                429, {"message": str(exc), "cooldown_remaining": exc.retry_after, "step": exc.step}
            ) from exc
        result = await asyncio.to_thread(send_text_to_chat_confirm, body.guid, body.text)
        _ls.info("core", f"outbound send to group {body.guid} ({result.status})")
        return {"status": result.status, "hint": result.hint, "service": result.service}

    if body.handle.lower() not in _relay_handles():
        raise HTTPException(403, "handle not in relay scope")
    try:
        await asyncio.to_thread(check_send_guard, body.handle, body.text, "ui")
    except RateLimitError as exc:
        raise HTTPException(
            429, {"message": str(exc), "cooldown_remaining": None, "step": 0}
        ) from exc
    except BroadcastBlockedError as exc:
        raise HTTPException(
            429, {"message": str(exc), "cooldown_remaining": exc.retry_after, "step": exc.step}
        ) from exc
    result = await asyncio.to_thread(send_text_confirm, body.handle, body.text)
    _ls.info("core", f"outbound send to {body.handle} ({result.status})")
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
        BroadcastBlockedError,
        RateLimitError,
        check_send_guard,
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

    recipient = guid if guid else handle
    source = "ui-group-upload" if guid else "ui-upload"
    try:
        await asyncio.to_thread(check_send_guard, recipient, "", source)
    except RateLimitError as exc:
        raise HTTPException(
            429, {"message": str(exc), "cooldown_remaining": None, "step": 0}
        ) from exc
    except BroadcastBlockedError as exc:
        raise HTTPException(
            429, {"message": str(exc), "cooldown_remaining": exc.retry_after, "step": exc.step}
        ) from exc

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


# ---------------------------------------------------------------------------
# Tapback reactions, edit, unsend
# ---------------------------------------------------------------------------

_TAPBACK_EMOJI_TO_APPLE: dict[str, str] = {
    "❤️": "heartTapback",
    "👍": "thumbsUpTapback",
    "👎": "thumbsDownTapback",
    "😂": "hahaTapback",
    "‼️": "emphasisTapback",
    "❓": "questionTapback",
}


def _run_osascript(script: str) -> None:
    from chat_send import _run_osascript as _cs_run  # noqa: PLC0415
    _cs_run(script)


class TapbackBody(BaseModel):
    rowid: int
    type: str  # emoji, e.g. "❤️"


@router.post("/tapback")
async def ui_tapback(body: TapbackBody):
    """Send a tapback reaction to a message via Messages.app AppleScript.

    Requires macOS 13 (Ventura) or later for AppleScript tapback support.
    Returns 422 for unknown type, 500 if osascript fails.
    """
    apple_type = _TAPBACK_EMOJI_TO_APPLE.get(body.type)
    if apple_type is None:
        raise HTTPException(422, f"unknown tapback type: {body.type!r}")
    script = f"""
tell application "Messages"
    set theMsg to message id {body.rowid}
    react with reaction {apple_type} for theMsg
end tell
"""
    try:
        await asyncio.to_thread(_run_osascript, script)
    except Exception as exc:
        raise HTTPException(500, f"tapback failed: {exc}") from exc
    return {"ok": True}


@router.get("/macos-version")
async def ui_macos_version():
    """Return the running macOS major/minor version for feature gating.

    Used by the frontend to disable Edit/Unsend on macOS < 13 (Ventura).
    Returns {major: 0, minor: 0} on non-macOS platforms.
    """
    import platform  # noqa: PLC0415
    ver = platform.mac_ver()[0]  # e.g. "13.5.1" or "" on non-Mac
    parts = ver.split(".") if ver else []
    try:
        major = int(parts[0]) if parts else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        major, minor = 0, 0
    return {"major": major, "minor": minor}


class UnsendBody(BaseModel):
    rowid: int


@router.post("/unsend")
async def ui_unsend(body: UnsendBody):
    """Unsend (retract) a sent iMessage.

    Requires macOS 13 (Ventura) or later. Returns 500 if the AppleScript
    command fails (e.g. older macOS or message not eligible for retraction).
    """
    script = f"""
tell application "Messages"
    unsend message id {body.rowid}
end tell
"""
    try:
        await asyncio.to_thread(_run_osascript, script)
    except Exception as exc:
        raise HTTPException(500, f"unsend failed: {exc}") from exc
    return {"ok": True}


class EditBody(BaseModel):
    rowid: int
    text: str


@router.post("/edit")
async def ui_edit(body: EditBody):
    """Edit the text of a sent iMessage.

    Requires macOS 13 (Ventura) or later. Returns 500 if the AppleScript
    command fails (e.g. older macOS or message not eligible for editing).
    """
    # Escape the text for safe embedding in an AppleScript string literal.
    escaped = body.text.replace("\\", "\\\\").replace('"', '\\"')
    script = f"""
tell application "Messages"
    edit message id {body.rowid} to "{escaped}"
end tell
"""
    try:
        await asyncio.to_thread(_run_osascript, script)
    except Exception as exc:
        raise HTTPException(500, f"edit failed: {exc}") from exc
    return {"ok": True}


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


@router.get("/plugin-themes")
async def ui_plugin_themes():
    """Return scheme metadata and CSS contributed by installed theme plugins.

    Discovers all packages registered under the ``chatwire.themes`` entry-point
    group.  Each module must expose:

    - ``SCHEMES`` — ``list[dict]`` with keys ``name``, ``label``, ``isLight``,
      ``swatch``.  One dict per color scheme variant.
    - ``CSS`` — ``str`` of raw CSS containing ``[data-theme="<slug>"] { … }``
      blocks.  Injected into the browser after the built-in schemes.css.

    The frontend calls this endpoint on startup, injects the CSS, and merges the
    scheme list into the theme-picker dropdown.  When a plugin is uninstalled,
    its schemes disappear from the list and the browser falls back to the default
    theme.
    """
    import importlib.metadata  # noqa: PLC0415

    schemes: list[dict] = []
    css_parts: list[str] = []

    try:
        eps = importlib.metadata.entry_points(group="chatwire.themes")
    except Exception:
        eps = []

    for ep in eps:
        try:
            mod = ep.load()
            if hasattr(mod, "SCHEMES") and isinstance(mod.SCHEMES, list):
                for s in mod.SCHEMES:
                    if isinstance(s, dict) and all(
                        k in s for k in ("name", "label", "isLight", "swatch")
                    ):
                        schemes.append(
                            {
                                "name": str(s["name"]),
                                "label": str(s["label"]),
                                "isLight": bool(s["isLight"]),
                                "swatch": str(s["swatch"]),
                            }
                        )
            if hasattr(mod, "CSS") and isinstance(mod.CSS, str):
                css_parts.append(mod.CSS)
        except Exception:
            pass

    return {"schemes": schemes, "css": "\n".join(css_parts)}


@router.get("/theme-packages")
async def ui_theme_packages_list():
    """List all user-installed theme packages from ~/.chatwire/themes/*.json."""
    from web.theme_loader import load_packages  # noqa: PLC0415
    packages = load_packages()
    # Return metadata only (no CSS in list response)
    return {
        "packages": [
            {
                "name": p["name"],
                "author": p["author"],
                "version": p["version"],
                "has_colors": bool(p["colors"]),
                "has_structure": bool(p["structure"]),
                "has_decorations": bool(p["decorations"]),
                "has_custom_css": bool(p["custom_css"]),
                "custom_css_sanitized": bool(p.get("custom_css_sanitized")),
                "scheme_dark": p.get("scheme_dark"),
                "scheme_light": p.get("scheme_light"),
            }
            for p in packages
        ]
    }


@router.post("/theme-packages/apply")
async def ui_theme_packages_apply(name: str = Form(...)):
    """Generate and return the CSS for a named theme package.

    The frontend injects the returned CSS into the document head and sets
    ``data-theme-pack="<name>"`` on ``<html>`` to activate the variables.
    Returns 404 if no package with that name is installed.
    """
    from web.theme_loader import load_packages, css_for_package  # noqa: PLC0415
    packages = load_packages()
    pkg = next((p for p in packages if p["name"] == name), None)
    if pkg is None:
        raise HTTPException(404, f"theme package not found: {name!r}")
    css = css_for_package(pkg)
    return {
        "name": name,
        "css": css,
        "scheme_dark": pkg.get("scheme_dark"),
        "scheme_light": pkg.get("scheme_light"),
    }


class ThemePackSaveBody(BaseModel):
    name: str
    author: str = ""
    version: str = ""
    colors: dict = {}
    structure: dict = {}
    decorations: dict = {}
    custom_css: str = ""
    scheme_dark: Optional[str] = None
    scheme_light: Optional[str] = None


@router.post("/theme-packages/save")
async def ui_theme_packages_save(body: ThemePackSaveBody):
    """Validate and save a theme package to ~/.chatwire/themes/<name>.json.

    The frontend sends a full package dict (from export or "Save as New Theme").
    The package is validated via ``parse_package`` before writing to disk.
    Returns the saved package metadata.
    """
    import json as _json  # noqa: PLC0415
    from web.theme_loader import THEME_PACKS_DIR, parse_package  # noqa: PLC0415

    raw = {
        "name": body.name,
        "author": body.author,
        "version": body.version,
        "colors": body.colors,
        "structure": body.structure,
        "decorations": body.decorations,
        "custom_css": body.custom_css,
        "scheme_dark": body.scheme_dark,
        "scheme_light": body.scheme_light,
    }
    pkg = parse_package(raw)
    if pkg is None:
        raise HTTPException(400, "invalid package name (must be lowercase kebab-case)")

    # Write to ~/.chatwire/themes/<name>.json
    THEME_PACKS_DIR.mkdir(parents=True, exist_ok=True)
    dest = THEME_PACKS_DIR / f"{pkg['name']}.json"
    dest.write_text(_json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "name": pkg["name"],
        "author": pkg["author"],
        "version": pkg["version"],
        "saved_to": str(dest),
    }


# ---------------------------------------------------------------------------
# Theme color overrides — per-theme CSS variable overrides
# ---------------------------------------------------------------------------

_THEME_OVERRIDES_DIR = Path.home() / ".chatwire" / "theme-overrides"


class ThemeOverridePatchBody(BaseModel):
    theme: str
    colors: dict = {}


@router.get("/theme-override/css")
async def ui_theme_override_css():
    """Return combined CSS for all stored theme overrides.

    Generates ``[data-theme="<slug>"] { --var: value; … }`` blocks for every
    theme that has stored overrides.  The frontend injects this into ``<head>``
    on page load so overrides persist across reloads without baking them into
    the built CSS files.
    """
    import json as _json  # noqa: PLC0415
    from web.theme_loader import _COLOR_VARS, _safe_value, _safe_name  # noqa: PLC0415

    if not _THEME_OVERRIDES_DIR.is_dir():
        return {"css": ""}

    css_blocks: list[str] = []
    for path in sorted(_THEME_OVERRIDES_DIR.glob("*.json")):
        slug = path.stem
        if not _safe_name(slug):
            continue
        try:
            data = _json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        colors = data.get("colors") or {}
        if not isinstance(colors, dict) or not colors:
            continue
        var_lines: list[str] = []
        for k, v in colors.items():
            if k in _COLOR_VARS:
                safe = _safe_value(v)
                if safe:
                    var_lines.append(f"  --{k}: {safe};")
        if var_lines:
            css_blocks.append(f'[data-theme="{slug}"] {{\n' + "\n".join(var_lines) + "\n}")

    return {"css": "\n\n".join(css_blocks)}


@router.get("/theme-override")
async def ui_theme_override_get(theme: str = Query(...)):
    """Return stored color overrides for a given theme slug, or empty dict."""
    import json as _json  # noqa: PLC0415
    from web.theme_loader import _safe_name  # noqa: PLC0415

    if not _safe_name(theme):
        raise HTTPException(400, "invalid theme name")

    path = _THEME_OVERRIDES_DIR / f"{theme}.json"
    if not path.exists():
        return {"theme": theme, "colors": {}}
    try:
        data = _json.loads(path.read_text(encoding="utf-8"))
        return {"theme": theme, "colors": data.get("colors") or {}}
    except (ValueError, OSError):
        return {"theme": theme, "colors": {}}


@router.patch("/theme-override")
async def ui_theme_override_patch(body: ThemeOverridePatchBody):
    """Save or update color variable overrides for a theme.

    Merges the supplied ``colors`` dict into any existing overrides for that
    theme.  Entries with an empty-string value are removed (clearing a single
    override without touching others).
    """
    import json as _json  # noqa: PLC0415
    from web.theme_loader import _COLOR_VARS, _safe_value, _safe_name  # noqa: PLC0415

    if not _safe_name(body.theme):
        raise HTTPException(400, "invalid theme name")

    # Sanitize incoming colors — reject unknown vars and unsafe values
    safe_colors: dict[str, str] = {}
    for k, v in body.colors.items():
        if k not in _COLOR_VARS:
            continue
        if v == "":
            safe_colors[k] = ""  # explicit clear
        else:
            safe = _safe_value(v)
            if safe:
                safe_colors[k] = safe

    _THEME_OVERRIDES_DIR.mkdir(parents=True, exist_ok=True)
    path = _THEME_OVERRIDES_DIR / f"{body.theme}.json"

    # Load existing, merge
    existing: dict = {}
    if path.exists():
        try:
            existing = _json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            existing = {}

    merged = dict(existing.get("colors") or {})
    merged.update(safe_colors)
    # Remove entries explicitly cleared (empty string)
    merged = {k: v for k, v in merged.items() if v}

    existing["colors"] = merged
    path.write_text(_json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

    return {"ok": True, "theme": body.theme, "colors": merged}


@router.delete("/theme-override")
async def ui_theme_override_delete(theme: str = Query(...)):
    """Clear all stored color overrides for a theme."""
    from web.theme_loader import _safe_name  # noqa: PLC0415

    if not _safe_name(theme):
        raise HTTPException(400, "invalid theme name")

    path = _THEME_OVERRIDES_DIR / f"{theme}.json"
    path.unlink(missing_ok=True)
    return {"ok": True, "theme": theme}


# ---------------------------------------------------------------------------
# Theme skin — portable ZIP containing override.json + manifest.json
# Shareable like a Winamp skin: export your color tweaks, import on another
# machine or share with another Chatwire user.
# ---------------------------------------------------------------------------

_SKIN_MAX_BYTES = 256 * 1024  # 256 KB


@router.get("/theme-skin/download")
async def ui_theme_skin_download(theme: str = Query(...)):
    """Download theme color overrides as a portable ZIP skin file.

    The ZIP contains:
      - ``override.json``  — ``{"theme": "<slug>", "colors": {...}}``
      - ``manifest.json``  — metadata (theme, exported timestamp, app name)

    Returns the ZIP as ``application/zip`` with a browser-download header.
    Downloads an empty-colors ZIP if no overrides have been saved yet.
    """
    import datetime  # noqa: PLC0415
    import io as _io  # noqa: PLC0415
    import json as _json  # noqa: PLC0415
    import zipfile  # noqa: PLC0415
    from web.theme_loader import _safe_name  # noqa: PLC0415

    if not _safe_name(theme):
        raise HTTPException(400, "invalid theme name")

    colors: dict = {}
    path = _THEME_OVERRIDES_DIR / f"{theme}.json"
    if path.exists():
        try:
            data = _json.loads(path.read_text(encoding="utf-8"))
            colors = data.get("colors") or {}
        except (ValueError, OSError):
            pass

    override_payload = _json.dumps({"theme": theme, "colors": colors}, indent=2)
    manifest_payload = _json.dumps(
        {
            "theme": theme,
            "exported": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "app": "chatwire",
        },
        indent=2,
    )

    def _build_zip() -> bytes:
        buf = _io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("override.json", override_payload)
            zf.writestr("manifest.json", manifest_payload)
        return buf.getvalue()

    zip_bytes = await asyncio.to_thread(_build_zip)
    fname = f"chatwire-override-{theme}.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/theme-skin/upload")
async def ui_theme_skin_upload(file: UploadFile = File(...)):
    """Import theme color overrides from a ZIP skin file.

    The ZIP must contain ``override.json`` with keys ``theme`` (a valid
    kebab-case slug) and ``colors`` (a dict of CSS variable overrides).
    Unknown variable names and unsafe values are silently dropped.
    Returns ``{"ok": true, "theme": "<slug>", "colors_imported": N}``.
    """
    import io as _io  # noqa: PLC0415
    import json as _json  # noqa: PLC0415
    import zipfile  # noqa: PLC0415
    from web.theme_loader import _COLOR_VARS, _safe_name, _safe_value  # noqa: PLC0415

    content = await file.read()
    if len(content) > _SKIN_MAX_BYTES:
        raise HTTPException(400, f"ZIP too large (max {_SKIN_MAX_BYTES // 1024} KB)")

    try:
        buf = _io.BytesIO(content)
        with zipfile.ZipFile(buf, "r") as zf:
            names = zf.namelist()
            if "override.json" not in names:
                raise HTTPException(400, "ZIP is missing override.json")
            raw_bytes = zf.read("override.json")
    except zipfile.BadZipFile:
        raise HTTPException(400, "not a valid ZIP file")

    try:
        data = _json.loads(raw_bytes.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "override.json is not valid JSON")

    theme = data.get("theme", "")
    if not isinstance(theme, str) or not _safe_name(theme):
        raise HTTPException(400, "override.json has an invalid or missing 'theme' slug")

    colors_raw = data.get("colors") or {}
    if not isinstance(colors_raw, dict):
        raise HTTPException(400, "override.json 'colors' must be an object")

    safe_colors: dict[str, str] = {}
    for k, v in colors_raw.items():
        if not isinstance(k, str) or k not in _COLOR_VARS:
            continue
        if isinstance(v, str):
            safe = _safe_value(v)
            if safe:
                safe_colors[k] = safe

    _THEME_OVERRIDES_DIR.mkdir(parents=True, exist_ok=True)
    dest = _THEME_OVERRIDES_DIR / f"{theme}.json"
    dest.write_text(
        _json.dumps({"theme": theme, "colors": safe_colors}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return {"ok": True, "theme": theme, "colors_imported": len(safe_colors)}


@router.get("/settings/accent_color")
async def ui_settings_accent_color():
    """Return the user-configured accent color override, or empty string if unset."""
    import config as _cfg  # noqa: PLC0415
    cfg = _cfg.load_config()
    web = cfg.get("web") or {}
    return {"accent_color": web.get("accent_color", "")}


@router.post("/settings/accent_color")
async def ui_settings_accent_color_set(color: str = Form(...)):
    """Persist an accent color override to config.

    ``color`` must be a 6-digit hex CSS color (``#rrggbb``) or an empty
    string to clear the override and revert to the theme default.
    """
    import re  # noqa: PLC0415
    import config as _cfg  # noqa: PLC0415
    if color and not re.match(r"^#[0-9a-fA-F]{6}$", color):
        raise HTTPException(400, "color must be #rrggbb or empty string")
    cfg = _cfg.load_config()
    web = cfg.setdefault("web", {})
    if color:
        web["accent_color"] = color
    else:
        web.pop("accent_color", None)
    _cfg.save_config(cfg)
    return {"ok": True, "accent_color": color}


# ---------------------------------------------------------------------------
# Per-theme user custom CSS (#15)
# ---------------------------------------------------------------------------

_CUSTOM_CSS_DIR = Path.home() / ".chatwire" / "custom-css"

# 64 KB per theme — generous but bounded
_MAX_PER_THEME_CSS = 64 * 1024


@router.get("/custom-css/combined")
async def ui_custom_css_combined():
    """Return per-theme user custom CSS wrapped in ``[data-theme="slug"] { … }`` blocks.

    Reads ``~/.chatwire/custom-css/<slug>.css`` files and wraps each file's
    contents with a scoping selector so the CSS only applies when that theme
    is active.  Also returns the raw per-theme map (``themes``) so the
    frontend editor can display the CSS for the current theme without a
    second round-trip.

    Returns::

        {
          "css": "[data-theme=\\"dracula\\"] {\\n.foo { color: red; }\\n}",
          "themes": {"dracula": ".foo { color: red; }"}
        }
    """
    from web.theme_loader import _safe_name  # noqa: PLC0415

    if not _CUSTOM_CSS_DIR.is_dir():
        return {"css": "", "themes": {}}

    themes: dict = {}
    blocks: list = []

    for path in sorted(_CUSTOM_CSS_DIR.glob("*.css")):
        slug = path.stem
        if not _safe_name(slug):
            continue
        try:
            raw = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not raw:
            continue
        themes[slug] = raw
        blocks.append(f'[data-theme="{slug}"] {{\n{raw}\n}}')

    return {"css": "\n\n".join(blocks), "themes": themes}


@router.get("/settings/custom_css")
async def ui_settings_custom_css_get(theme: Optional[str] = Query(default=None)):
    """Return the user-defined custom CSS.

    When ``theme`` is supplied, reads from the per-theme file
    ``~/.chatwire/custom-css/<slug>.css``.  When absent, falls back to the
    legacy ``web.custom_css`` config key so old clients keep working.
    """
    from web.theme_loader import _safe_name  # noqa: PLC0415

    if theme is not None:
        if not _safe_name(theme):
            raise HTTPException(400, "invalid theme name")
        path = _CUSTOM_CSS_DIR / f"{theme}.css"
        if path.exists():
            try:
                return {"custom_css": path.read_text(encoding="utf-8"), "theme": theme}
            except OSError:
                pass
        return {"custom_css": "", "theme": theme}

    # Legacy fallback — used by old frontends that don't pass ?theme=
    import config as _cfg  # noqa: PLC0415
    cfg = _cfg.load_config()
    web = cfg.get("web") or {}
    return {"custom_css": web.get("custom_css", "")}


@router.get("/settings")
async def ui_settings_get():
    """Return general UI settings (theme_mode, etc.)."""
    import config as _cfg  # noqa: PLC0415
    cfg = _cfg.load_config()
    web = cfg.get("web") or {}
    return {"theme_mode": web.get("theme_mode", "auto")}


@router.patch("/settings")
async def ui_settings_patch(body: UiSettingsPatchBody):
    """Persist general UI settings.

    Currently supports:
      - ``theme_mode``: "auto" | "light" | "dark"
    """
    import config as _cfg  # noqa: PLC0415
    if body.theme_mode is not None and body.theme_mode not in ("auto", "light", "dark"):
        raise HTTPException(400, "theme_mode must be 'auto', 'light', or 'dark'")
    cfg = _cfg.load_config()
    web = cfg.setdefault("web", {})
    if body.theme_mode is not None:
        web["theme_mode"] = body.theme_mode
    _cfg.save_config(cfg)
    return {"ok": True, "theme_mode": web.get("theme_mode", "auto")}


# ---------------------------------------------------------------------------
# Custom notification sounds
# ---------------------------------------------------------------------------

def _custom_sound_path(sound_type: str) -> "Path | None":
    """Return the path to the custom sound file for *sound_type*, or None."""
    for ext in _VALID_SOUND_EXTS:
        p = _SOUNDS_DIR / f"custom-{sound_type}{ext}"
        if p.exists():
            return p
    return None


@router.get("/sounds/config")
async def ui_sounds_config_get():
    """Return the current notification sound configuration.

    Each key is ``"default"`` (built-in wav), ``"none"`` (silent), or
    ``"custom"`` (user-uploaded file served from ``/api/ui/sounds/custom-*``).
    """
    import config as _cfg  # noqa: PLC0415
    cfg = _cfg.load_config()
    web = cfg.get("web") or {}
    sounds = web.get("sounds") or {}
    return {
        "sent": sounds.get("sent", "default"),
        "received": sounds.get("received", "default"),
    }


@router.post("/sounds/config")
async def ui_sounds_config_set(body: SoundsConfigBody):
    """Persist the notification sound mode for sent / received events."""
    import config as _cfg  # noqa: PLC0415
    if body.sent is not None and body.sent not in _SOUND_MODES:
        raise HTTPException(400, f"sent must be one of {sorted(_SOUND_MODES)}")
    if body.received is not None and body.received not in _SOUND_MODES:
        raise HTTPException(400, f"received must be one of {sorted(_SOUND_MODES)}")
    cfg = _cfg.load_config()
    web = cfg.setdefault("web", {})
    sounds = web.setdefault("sounds", {})
    if body.sent is not None:
        sounds["sent"] = body.sent
    if body.received is not None:
        sounds["received"] = body.received
    _cfg.save_config(cfg)
    return {"ok": True, "sent": sounds.get("sent", "default"), "received": sounds.get("received", "default")}


@router.post("/sounds/upload")
async def ui_sounds_upload(
    sound_type: str = Form(...),
    file: UploadFile = File(...),
):
    """Upload a custom notification sound (WAV/MP3/OGG/M4A/AAC, max 5 MB).

    Stores the file as ``~/.chatwire/sounds/custom-{sent|received}.{ext}``,
    replacing any previous custom file for that type, and sets the mode to
    ``"custom"`` in config.
    """
    import config as _cfg  # noqa: PLC0415
    if sound_type not in _SOUND_TYPES:
        raise HTTPException(400, "sound_type must be 'sent' or 'received'")

    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    if not ext:
        raise HTTPException(400, "file must have an audio extension (.wav, .mp3, .ogg, .m4a, .aac)")
    if ext not in _VALID_SOUND_EXTS:
        raise HTTPException(400, f"unsupported extension {ext!r}")

    MAX_BYTES = 5 * 1024 * 1024
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "File exceeds 5 MB limit")

    _SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
    # Remove any previous custom file for this type before writing the new one.
    for old_ext in _VALID_SOUND_EXTS:
        (_SOUNDS_DIR / f"custom-{sound_type}{old_ext}").unlink(missing_ok=True)

    dest = _SOUNDS_DIR / f"custom-{sound_type}{ext}"
    dest.write_bytes(data)

    cfg = _cfg.load_config()
    web = cfg.setdefault("web", {})
    sounds = web.setdefault("sounds", {})
    sounds[sound_type] = "custom"
    _cfg.save_config(cfg)

    return {"ok": True, "sound_type": sound_type, "filename": dest.name}


@router.get("/sounds/custom-sent")
async def ui_sounds_custom_sent():
    """Serve the user-uploaded sent sound file."""
    from fastapi.responses import FileResponse  # noqa: PLC0415
    path = _custom_sound_path("sent")
    if path is None:
        raise HTTPException(404, "no custom sent sound uploaded")
    return FileResponse(str(path))


@router.get("/sounds/custom-received")
async def ui_sounds_custom_received():
    """Serve the user-uploaded received sound file."""
    from fastapi.responses import FileResponse  # noqa: PLC0415
    path = _custom_sound_path("received")
    if path is None:
        raise HTTPException(404, "no custom received sound uploaded")
    return FileResponse(str(path))


@router.delete("/sounds/custom-sent")
async def ui_sounds_custom_sent_delete():
    """Delete the custom sent sound and reset mode to 'default'."""
    import config as _cfg  # noqa: PLC0415
    for ext in _VALID_SOUND_EXTS:
        (_SOUNDS_DIR / f"custom-sent{ext}").unlink(missing_ok=True)
    cfg = _cfg.load_config()
    web = cfg.setdefault("web", {})
    sounds = web.setdefault("sounds", {})
    sounds["sent"] = "default"
    _cfg.save_config(cfg)
    return {"ok": True, "sent": "default"}


@router.delete("/sounds/custom-received")
async def ui_sounds_custom_received_delete():
    """Delete the custom received sound and reset mode to 'default'."""
    import config as _cfg  # noqa: PLC0415
    for ext in _VALID_SOUND_EXTS:
        (_SOUNDS_DIR / f"custom-received{ext}").unlink(missing_ok=True)
    cfg = _cfg.load_config()
    web = cfg.setdefault("web", {})
    sounds = web.setdefault("sounds", {})
    sounds["received"] = "default"
    _cfg.save_config(cfg)
    return {"ok": True, "received": "default"}


# ---------------------------------------------------------------------------
# Scoped API key management
# ---------------------------------------------------------------------------

class ApiKeyCreateBody(BaseModel):
    name: str
    scopes: List[str]


class ApiKeyUpdateBody(BaseModel):
    name: str
    scopes: List[str]


@router.get("/api-keys")
async def ui_api_keys_list():
    """Return all API keys (no hashes — safe for UI display)."""
    from web.api_keys import load_keys  # noqa: PLC0415
    keys = await asyncio.to_thread(load_keys)
    return {"keys": [k.to_display() for k in keys]}


@router.post("/api-keys")
async def ui_api_keys_create(body: ApiKeyCreateBody):
    """Create a new scoped API key.

    Returns the plaintext key once — it is not recoverable after this call.
    """
    import time as _time  # noqa: PLC0415
    from web.api_keys import ALL_SCOPES, APIKey, generate_key, hash_key, load_keys, save_keys  # noqa: PLC0415

    name = body.name.strip()
    if not name:
        raise HTTPException(400, "name is required")
    invalid = [s for s in body.scopes if s not in ALL_SCOPES]
    if invalid:
        raise HTTPException(400, f"unknown scopes: {invalid!r}")
    if not body.scopes:
        raise HTTPException(400, "at least one scope is required")

    plaintext = await asyncio.to_thread(generate_key)
    key_hash = await asyncio.to_thread(hash_key, plaintext)
    prefix = plaintext[4:12]  # 8 hex chars after "cwk_"
    entry = APIKey(
        name=name,
        key_hash=key_hash,
        scopes=list(body.scopes),
        created_at=_time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
        prefix=prefix,
    )

    def _save():
        from web.api_keys import load_keys as _load, save_keys as _save  # noqa: PLC0415
        keys = _load()
        keys.append(entry)
        _save(keys)

    await asyncio.to_thread(_save)
    return {"key": plaintext, "info": entry.to_display()}


@router.delete("/api-keys/{prefix}")
async def ui_api_keys_delete(prefix: str):
    """Delete the key whose prefix matches (8 hex chars)."""
    def _delete():
        from web.api_keys import load_keys, save_keys  # noqa: PLC0415
        keys = load_keys()
        new_keys = [k for k in keys if k.prefix != prefix]
        if len(new_keys) == len(keys):
            raise HTTPException(404, "key not found")
        save_keys(new_keys)

    await asyncio.to_thread(_delete)
    return {"ok": True, "deleted": prefix}


@router.patch("/api-keys/{prefix}")
async def ui_api_keys_update(prefix: str, body: ApiKeyUpdateBody):
    """Rename a key and/or update its scopes (identified by prefix)."""
    from web.api_keys import ALL_SCOPES  # noqa: PLC0415
    invalid = [s for s in body.scopes if s not in ALL_SCOPES]
    if invalid:
        raise HTTPException(400, f"unknown scopes: {invalid!r}")
    if not body.scopes:
        raise HTTPException(400, "at least one scope is required")
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "name is required")

    def _update():
        from web.api_keys import load_keys, save_keys  # noqa: PLC0415
        keys = load_keys()
        for k in keys:
            if k.prefix == prefix:
                k.name = name
                k.scopes = list(body.scopes)
                save_keys(keys)
                return k.to_display()
        raise HTTPException(404, "key not found")

    result = await asyncio.to_thread(_update)
    return {"ok": True, "key": result}


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


@router.get("/settings/whitelist/grouped")
async def ui_settings_whitelist_grouped():
    """Return whitelist entries grouped by contact name.

    Response shape:
      contacts  — [{name, all_handles, whitelisted_handles, whitelisted}]
      unknown   — [handle, ...]  (whitelisted handles with no contact name)
      groups    — [{guid, name, members, whitelisted}]
    """
    def _get():
        from web.whitelist import grouped_entries  # noqa: PLC0415
        return grouped_entries()

    try:
        return await asyncio.to_thread(_get)
    except Exception:
        return {"contacts": [], "unknown": [], "groups": []}


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
    """Return notification-related settings.

    Note: hiatus and reminder settings live in cfg["web"] (saved by
    /api/settings/hiatus_settings and /api/settings/reminder_settings).
    Push-notification settings (detail, depth) live in cfg["notifications"].
    """
    import config as _cfg  # noqa: PLC0415
    cfg = _cfg.load_config()
    notif = cfg.get("notifications") or {}
    web = cfg.get("web") or {}
    raw_contacts = web.get("reminder_contacts")
    reminder_contacts: list = raw_contacts if isinstance(raw_contacts, list) else []
    return {
        "notification_detail": notif.get("detail", "rich"),
        "hiatus_enabled": bool(web.get("hiatus_enabled", False)),
        "hiatus_duration_minutes": int(web.get("hiatus_duration_minutes", 30)),
        "hiatus_started_at": float(web.get("hiatus_started_at", 0)),
        "reminder_enabled": bool(web.get("reminder_enabled", False)),
        "reminder_days": int(web.get("reminder_days", 7)),
        "reminder_contacts": reminder_contacts,
        "notification_depth": notif.get("notification_depth") or {},
    }


class NotificationDepthBody(BaseModel):
    """Per-plugin notification depth settings.

    ``depths`` maps plugin names to depth levels:
      "minimal"  — no sender name, no content
      "sender"   — sender display name only (default)
      "preview"  — sender name + first ~50 chars of message text

    The special key ``"default"`` sets the fallback for all unnamed plugins.
    """
    depths: Dict[str, str]


@router.get("/settings/notification_depth")
async def ui_settings_notification_depth():
    """Return per-plugin notification depth map."""
    import config as _cfg  # noqa: PLC0415
    cfg = _cfg.load_config()
    notif = cfg.get("notifications") or {}
    return {"notification_depth": notif.get("notification_depth") or {}}


@router.post("/settings/notification_depth")
async def ui_settings_notification_depth_set(body: NotificationDepthBody):
    """Persist per-plugin notification depth settings.

    Validates each depth value is one of: "minimal", "sender", "preview".
    Unknown plugin names (and the "default" key) are accepted without
    validation — the bridge reads them verbatim.
    """
    valid_depths = {"minimal", "sender", "preview"}
    for plugin_name, depth in body.depths.items():
        if depth not in valid_depths:
            raise HTTPException(
                400,
                f"Invalid depth {depth!r} for plugin {plugin_name!r}. "
                f"Must be one of: {', '.join(sorted(valid_depths))}",
            )
    import config as _cfg  # noqa: PLC0415
    cfg = _cfg.load_config()
    notif = cfg.setdefault("notifications", {})
    notif["notification_depth"] = body.depths
    _cfg.save_config(cfg)
    return {"ok": True, "notification_depth": body.depths}


@router.get("/fuse-status")
async def ui_fuse_status():
    """Return the current anti-spam fuse status.

    Response schema::

        {
          "locked": bool,
          "step": int,           # 0 = inactive, 1-5 = timed, 6 = permanent
          "cooldown_remaining_s": float | null,
          "unlock_code": str | null   # present on step 4+
        }
    """
    from chat_send import get_fuse_status  # noqa: PLC0415
    return get_fuse_status()


@router.post("/unlock")
async def ui_unlock(body: UnlockBody):
    """Validate an admin-issued unlock code and reset the anti-spam fuse.

    The unlock code is computed by the admin's Google Apps Script as
    ``HMAC-SHA256(cw_code, unlock_secret)`` formatted as ``UL-XXXX-XXXX``.
    The same secret is stored in ``~/.chatwire/config.json`` as
    ``unlock_secret``.

    Returns ``{"ok": true}`` on success. Raises 400 on invalid code.
    """
    from chat_send import validate_and_reset_fuse  # noqa: PLC0415
    ok = await asyncio.to_thread(validate_and_reset_fuse, body.code)
    if not ok:
        raise HTTPException(400, "Invalid unlock code")
    return {"ok": True}


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

@router.get("/auth/has-password")
async def ui_auth_has_password():
    """Return whether a web UI password is currently configured.

    Used by the sidebar to decide whether to show the logout icon.
    This endpoint is intentionally public (no auth required) so the
    login page can also check it — it reveals no sensitive data.
    """
    from web.main import app as _app  # noqa: PLC0415
    has_pw = getattr(_app.state, "auth_block", None) is not None
    return {"has_password": has_pw}


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


# ---------------------------------------------------------------------------
# Contact info sheet
# ---------------------------------------------------------------------------

@router.get("/contact-info")
async def ui_contact_info(
    handle: Optional[str] = Query(None),
    guid: Optional[str] = Query(None),
):
    """Return metadata + shared media for the contact info sheet.

    Pass ``handle`` for 1:1 conversations, ``guid`` for group chats.
    """
    if not handle and not guid:
        raise HTTPException(400, "handle or guid required")

    def _get():
        from web.main import contact_for, contact_for_group  # noqa: PLC0415
        if guid:
            return contact_for_group(guid)
        return contact_for(handle)

    try:
        return await asyncio.to_thread(_get)
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@router.post("/whitelist")
async def ui_whitelist_add(
    handle: Optional[str] = Query(None),
    guid: Optional[str] = Query(None),
):
    """Add one handle or group GUID to the whitelist."""
    if not handle and not guid:
        raise HTTPException(400, "handle or guid required")

    def _add():
        import whitelist as wl  # noqa: PLC0415
        if guid:
            wl.add_group(guid)
            return {"ok": True, "added": guid}
        wl.add(handle)
        return {"ok": True, "added": handle}

    try:
        return await asyncio.to_thread(_add)
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@router.delete("/whitelist")
async def ui_whitelist_remove(
    handle: Optional[str] = Query(None),
    guid: Optional[str] = Query(None),
):
    """Remove one handle or group GUID from the whitelist."""
    if not handle and not guid:
        raise HTTPException(400, "handle or guid required")

    def _remove():
        import whitelist as wl  # noqa: PLC0415
        if guid:
            wl.remove_group(guid)
            return {"ok": True, "removed": guid}
        wl.remove(handle)
        return {"ok": True, "removed": handle}

    try:
        return await asyncio.to_thread(_remove)
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc

    return await asyncio.to_thread(_compute)


# ---------------------------------------------------------------------------
# Plugin management
# ---------------------------------------------------------------------------

import re as _re
import subprocess as _subprocess
import sys as _sys
import shutil as _shutil

_PACKAGE_NAME_RE = _re.compile(r'^[A-Za-z0-9_.\-]+(?:==[\w.]+)?$')


class PluginConfigBody(BaseModel):
    config: dict


class PluginInstallBody(BaseModel):
    package_name: str
    upgrade: bool = False


@router.get("/plugins")
async def ui_plugins_list():
    """List all installed plugins with health, tier, and settings schema.

    Returns every Integration class found via built-in discovery and pip
    entry points, merged with the current enabled/disabled state from
    config.json and live health stats.
    """
    def _get():
        import config as _cfg  # noqa: PLC0415
        from plugin_state import build_plugin_list  # noqa: PLC0415
        cfg = _cfg.load_config()
        return build_plugin_list(cfg)

    try:
        plugins = await asyncio.to_thread(_get)
        return {"plugins": plugins}
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@router.get("/plugins/marketplace")
async def ui_plugins_marketplace():
    """Return the plugin marketplace registry (24-hour cached)."""
    def _get():
        from config import STATE_DIR  # noqa: PLC0415
        from web.registry import fetch_registry  # noqa: PLC0415
        cache = STATE_DIR / "plugin_registry_cache.json"
        return fetch_registry(cache)

    try:
        plugins = await asyncio.to_thread(_get)
        return {"plugins": plugins}
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@router.get("/plugins/updates")
async def ui_plugins_updates():
    """Return plugins that have newer versions available on PyPI.

    Results are cached in ~/.chatwire/plugin-updates.json for 24 hours.
    The cache is refreshed automatically when it is stale.

    Response::

        {"updates": [{"name": "...", "dist_name": "...",
                      "current_version": "...", "latest_version": "..."}]}
    """
    def _check():
        from plugin_state import get_plugin_updates  # noqa: PLC0415
        return get_plugin_updates()

    try:
        updates = await asyncio.to_thread(_check)
        return {"updates": updates}
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@router.get("/plugins/{name}/config")
async def ui_plugin_config_get(name: str):
    """Return the current isolated config for plugin *name*."""
    def _get():
        from plugin_state import load_plugin_config  # noqa: PLC0415
        return load_plugin_config(name)

    try:
        cfg = await asyncio.to_thread(_get)
        return {"config": cfg}
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@router.post("/plugins/{name}/config")
async def ui_plugin_config_set(name: str, body: PluginConfigBody):
    """Save the isolated config for plugin *name*."""
    def _save():
        from plugin_state import save_plugin_config  # noqa: PLC0415
        save_plugin_config(name, body.config)

    try:
        await asyncio.to_thread(_save)
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@router.post("/plugins/{name}/enable")
async def ui_plugin_enable(name: str):
    """Set integrations.<name>.enabled = true in config.json."""
    def _enable():
        import config as _cfg  # noqa: PLC0415
        cfg = _cfg.load_config()
        cfg.setdefault("integrations", {}).setdefault(name, {})["enabled"] = True
        _cfg.save_config(cfg)

    try:
        await asyncio.to_thread(_enable)
        return {"ok": True, "enabled": True}
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@router.post("/plugins/{name}/disable")
async def ui_plugin_disable(name: str):
    """Set integrations.<name>.enabled = false in config.json."""
    def _disable():
        import config as _cfg  # noqa: PLC0415
        cfg = _cfg.load_config()
        cfg.setdefault("integrations", {}).setdefault(name, {})["enabled"] = False
        _cfg.save_config(cfg)

    try:
        await asyncio.to_thread(_disable)
        return {"ok": True, "enabled": False}
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


class McpConfigBody(BaseModel):
    enabled: Optional[bool] = None
    enabled_tools: Optional[List[str]] = None
    http_enabled: Optional[bool] = None
    contact_filter: Optional[str] = None
    confirmation_mode: Optional[str] = None
    send_allowed_contacts: Optional[List[str]] = None
    read_window_days: Optional[int] = None
    pause_sends: Optional[bool] = None
    scopes: Optional[List[str]] = None
    tools: Optional[dict] = None


@router.get("/integrations/mcp/config")
async def ui_mcp_config_get():
    """Return the current MCP integration config from config.json."""
    def _mcp_available():
        try:
            import mcp as _mcp_pkg  # noqa: F401, PLC0415
            return True
        except ImportError:
            return False

    def _get():
        import config as _cfg  # noqa: PLC0415
        cfg = _cfg.load_config()
        mcp = cfg.get("integrations", {}).get("mcp", {})
        available = _mcp_available()
        # Tool/scope metadata only available if mcp package is installed
        all_tools = []
        available_scopes = []
        if available:
            from integrations.mcp import TOOL_DEFINITIONS, SCOPES  # noqa: PLC0415
            all_tools = [{"name": t["name"], "description": t["description"]} for t in TOOL_DEFINITIONS]
            available_scopes = list(SCOPES.keys())
        return {
            "mcp_available": available,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
            "enabled": mcp.get("enabled", False),
            "http_enabled": mcp.get("http_enabled", False),
            "contact_filter": mcp.get("contact_filter", "whitelist"),
            "confirmation_mode": mcp.get("confirmation_mode", "never"),
            "send_allowed_contacts": mcp.get("send_allowed_contacts", []),
            "read_window_days": mcp.get("read_window_days", None),
            "pause_sends": mcp.get("pause_sends", False),
            "scopes": mcp.get("scopes", ["mcp:read", "mcp:contacts", "mcp:meta"]),
            "tools": mcp.get("tools", {}),
            "all_tools": all_tools,
            "available_scopes": available_scopes,
        }

    try:
        result = await asyncio.to_thread(_get)
        return result
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@router.post("/integrations/mcp/config")
async def ui_mcp_config_set(body: McpConfigBody):
    """Update MCP integration config fields in config.json."""
    def _save():
        import config as _cfg  # noqa: PLC0415
        cfg = _cfg.load_config()
        mcp = cfg.setdefault("integrations", {}).setdefault("mcp", {})
        if body.enabled is not None:
            mcp["enabled"] = body.enabled
        if body.enabled_tools is not None:
            mcp["enabled_tools"] = body.enabled_tools
        if body.http_enabled is not None:
            mcp["http_enabled"] = body.http_enabled
        if body.contact_filter is not None:
            mcp["contact_filter"] = body.contact_filter
        if body.confirmation_mode is not None:
            mcp["confirmation_mode"] = body.confirmation_mode
        if body.send_allowed_contacts is not None:
            mcp["send_allowed_contacts"] = body.send_allowed_contacts
        if body.read_window_days is not None:
            mcp["read_window_days"] = body.read_window_days if body.read_window_days > 0 else None
        if body.pause_sends is not None:
            mcp["pause_sends"] = body.pause_sends
        if body.scopes is not None:
            mcp["scopes"] = body.scopes
        if body.tools is not None:
            mcp["tools"] = body.tools
        _cfg.save_config(cfg)

    try:
        await asyncio.to_thread(_save)
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@router.post("/plugins/install")
async def ui_plugin_install(body: PluginInstallBody):
    """Install a plugin package via pip.

    Validates the package name against a strict allowlist regex to prevent
    shell injection, runs pip install, then verifies the plugin signature.
    Returns {ok, package, signed} on success.
    """
    package_name = body.package_name.strip()
    if not _PACKAGE_NAME_RE.match(package_name):
        raise HTTPException(400, f"Invalid package name: {package_name!r}")

    def _install():
        pip_args = [_sys.executable, "-m", "pip", "install", "--no-cache-dir"]
        if body.upgrade:
            pip_args.append("--upgrade")
        pip_args.append(package_name)
        result = _subprocess.run(
            pip_args,
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"pip install failed (exit {result.returncode}): "
                f"{(result.stderr or result.stdout)[:500]}"
            )

        dist_name = package_name.split("==")[0]
        signed = False
        try:
            from verify import verify_plugin, PluginNotTrusted  # noqa: PLC0415
            verify_plugin(dist_name)
            signed = True
        except Exception:
            pass  # unsigned plugins install but are flagged

        return {"ok": True, "package": package_name, "dist_name": dist_name, "signed": signed}

    try:
        return await asyncio.to_thread(_install)
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@router.delete("/plugins/{name}")
async def ui_plugin_uninstall(
    name: str,
    dist_name: str = Query(..., description="pip distribution name"),
):
    """Uninstall a plugin package and remove its config directory.

    *name* is the plugin's NAME attribute; *dist_name* is the pip package
    name (e.g. chatwire-telegram). Confirm dialog on the frontend.
    """
    if not _PACKAGE_NAME_RE.match(dist_name):
        raise HTTPException(400, f"Invalid dist_name: {dist_name!r}")

    def _uninstall():
        result = _subprocess.run(
            [_sys.executable, "-m", "pip", "uninstall", "-y", dist_name],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode not in (0, 1):  # 1 = package not installed — OK
            raise RuntimeError(
                f"pip uninstall failed (exit {result.returncode}): "
                f"{(result.stderr or result.stdout)[:500]}"
            )

        from plugin_state import plugin_config_dir  # noqa: PLC0415
        config_dir = plugin_config_dir(name)
        if config_dir.exists():
            _shutil.rmtree(config_dir)

        return {"ok": True}

    try:
        return await asyncio.to_thread(_uninstall)
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


# ---------------------------------------------------------------------------
# Log viewer
# ---------------------------------------------------------------------------

import asyncio as _asyncio
from fastapi.responses import StreamingResponse


@router.get("/logs")
async def ui_logs_history(
    since: str = Query("", description="ISO timestamp; return only entries after this"),
    limit: int = Query(200, ge=1, le=1000),
    source: str = Query("", description="Filter by source name or 'all'"),
    level: str = Query("", description="Minimum level: info|warn|error"),
):
    """Return recent structured log entries from ~/.chatwire/chatwire.jsonl.

    Response::

        {"entries": [{"ts": "...", "source": "...", "level": "...", "msg": "..."}]}
    """
    def _read():
        from web.log_stream import read_history  # noqa: PLC0415
        return read_history(since=since, limit=limit, source=source, level=level)

    try:
        entries = await asyncio.to_thread(_read)
        return {"entries": entries}
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@router.get("/logs/stream")
async def ui_logs_stream(
    source: str = Query("", description="Filter by source or 'all'"),
    level: str = Query("", description="Minimum level: info|warn|error"),
):
    """Server-Sent Events stream of new log entries.

    Each SSE event carries a single JSON-encoded log line as its data.
    The client should reconnect automatically on disconnect (standard SSE
    behaviour).  Poll interval inside the generator is 1 second.
    """
    from web.log_stream import current_size, tail_from_offset  # noqa: PLC0415

    # Start from current end-of-file so we only stream *new* entries.
    offset = current_size()

    async def _generate():
        nonlocal offset
        heartbeat_counter = 0
        while True:
            entries, offset = tail_from_offset(offset, source=source, level=level)
            for entry in entries:
                import json as _json  # noqa: PLC0415
                yield f"data: {_json.dumps(entry, ensure_ascii=False)}\n\n"
                heartbeat_counter = 0  # reset after real data
            heartbeat_counter += 1
            # Send SSE comment as keepalive every 15s to prevent CF/proxy timeout
            if heartbeat_counter >= 15:
                yield ": heartbeat\n\n"
                heartbeat_counter = 0
            await _asyncio.sleep(1)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable Nginx buffering
        },
    )
