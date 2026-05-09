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

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
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
