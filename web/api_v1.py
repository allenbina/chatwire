"""REST API v1 — programmatic access to chatwire.

FastAPI APIRouter mounted at /api/v1 in web/main.py.

Auth: X-API-Key header. Key stored hashed (SHA-256 hex) in
config.json under web.api_key_hash.  The plaintext key is returned
exactly once (on generation) and is never stored.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import functools
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Optional

# asyncio.to_thread was added in Python 3.9; polyfill for 3.8.
if not hasattr(asyncio, "to_thread"):
    _pool = concurrent.futures.ThreadPoolExecutor()

    async def _to_thread(func, *args, **kwargs):  # type: ignore[misc]
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_pool, functools.partial(func, *args, **kwargs))

    asyncio.to_thread = _to_thread  # type: ignore[attr-defined]

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Ensure chatwire root is on sys.path (already done by web/main.py in
# production, but needed when the module is imported standalone in tests).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as _bridge_config  # noqa: E402
from chat_send import (  # noqa: E402
    BroadcastBlockedError,
    RateLimitError,
    check_send_guard,
    send_text_confirm,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Config helpers — module-level functions so tests can patch without
# importing web.main.
# ---------------------------------------------------------------------------

def _api_key_hash() -> Optional[str]:
    """Return the stored SHA-256 hex hash, or None if not configured."""
    return _bridge_config.load_config().get("web", {}).get("api_key_hash") or None


# ---------------------------------------------------------------------------
# web.main adapters — imported lazily to avoid circular import.
# Defined as module-level wrapper functions so tests can patch them
# without triggering web.main's side-effectful module-level code.
# ---------------------------------------------------------------------------

def _relay_handles() -> set:
    from web.main import relay_handles  # noqa: PLC0415
    return relay_handles()


def _history_for(handle: str):
    from web.main import history_for  # noqa: PLC0415
    return history_for(handle)


def _list_conversations() -> list:
    from web.main import list_conversations  # noqa: PLC0415
    return list_conversations()


def _mirror_file() -> Path:
    from web.main import MIRROR_FILE  # noqa: PLC0415
    return MIRROR_FILE


def _enrich_name(h: str) -> str:
    from web.main import _name  # noqa: PLC0415
    return _name(h)


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

async def require_api_key(request: Request) -> None:
    """FastAPI dependency: validate X-API-Key header against stored hash."""
    stored = _api_key_hash()
    if not stored:
        raise HTTPException(status_code=401, detail="API key not configured")
    provided = request.headers.get("X-API-Key", "")
    if not provided:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    given_hash = hashlib.sha256(provided.encode()).hexdigest()
    if given_hash != stored:
        raise HTTPException(status_code=401, detail="Invalid API key")


_AUTH = Depends(require_api_key)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class SendRequest(BaseModel):
    handle: str
    text: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/send")
async def api_send(body: SendRequest, _auth: None = _AUTH):
    """Send a message.  Goes through anti-spam guardrails before sending."""
    if body.handle.lower() not in _relay_handles():
        raise HTTPException(403, "handle not in relay scope")
    try:
        await asyncio.to_thread(check_send_guard, body.handle, body.text, "api")
    except RateLimitError as exc:
        raise HTTPException(
            429, {"message": str(exc), "cooldown_remaining": None, "step": 0}
        ) from exc
    except BroadcastBlockedError as exc:
        raise HTTPException(
            429, {"message": str(exc), "cooldown_remaining": exc.retry_after, "step": exc.step}
        ) from exc
    result = await asyncio.to_thread(send_text_confirm, body.handle, body.text)
    return {"status": result.status, "hint": result.hint, "service": result.service}


@router.get("/messages")
async def api_messages(
    handle: str = Query(...),
    since: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    _auth: None = _AUTH,
):
    """Return recent messages for a 1:1 conversation.

    `since` filters to rows with ROWID > since.
    `limit` caps the number of returned messages (newest-last, same as UI).
    """
    if handle.lower() not in _relay_handles():
        raise HTTPException(403, "handle not in relay scope")
    msgs, has_more = await asyncio.to_thread(_history_for, handle)
    if since:
        msgs = [m for m in msgs if m["rowid"] > since]
    msgs = msgs[-limit:]
    return {"handle": handle, "messages": msgs, "has_more": has_more}


@router.get("/conversations")
async def api_conversations(_auth: None = _AUTH):
    """List conversations in sidebar shape.

    Each entry: {handle, name, last_text, last_ts, unread_count}.
    """
    convos = await asyncio.to_thread(_list_conversations)
    return {
        "conversations": [
            {
                "handle": c.get("handle") or c.get("guid", ""),
                "name": c.get("name", ""),
                "last_text": c.get("preview", ""),
                "last_ts": c.get("last_dt", 0),
                "unread_count": c.get("n", 0),
            }
            for c in convos
        ]
    }


@router.get("/events")
async def api_events(_auth: None = _AUTH):
    """SSE stream of inbound events, gated on the API key.

    Same event shape as the browser-facing /events endpoint.
    """
    async def gen():
        mirror = _mirror_file()
        if not mirror.exists():
            yield "event: ping\ndata: {}\n\n"
        try:
            f = open(mirror, "r", encoding="utf-8")
        except FileNotFoundError:
            return
        f.seek(0, 2)
        last_ping = time.time()
        try:
            while True:
                line = f.readline()
                if line:
                    out = line.strip()
                    try:
                        evt = json.loads(out)
                        h = evt.get("handle")
                        if h and "name" not in evt:
                            evt["name"] = _enrich_name(h)
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


# ---------------------------------------------------------------------------
# Automation rules CRUD — /api/v1/automations
# ---------------------------------------------------------------------------

def _load_rules() -> list:
    """Read the chatwire_rules rules list from config."""
    cfg = _bridge_config.load_config()
    return list(
        cfg.get("integrations", {}).get("chatwire_rules", {}).get("rules", [])
    )


def _save_rules(rules: list) -> None:
    """Persist the rules list back to config."""
    cfg = _bridge_config.load_config()
    cfg.setdefault("integrations", {}).setdefault("chatwire_rules", {})["rules"] = rules
    _bridge_config.save_config(cfg)


def _validate_rule_body(body: object) -> dict:
    """Basic structural validation of a rule object.  Raises HTTPException on error."""
    if not isinstance(body, dict):
        raise HTTPException(400, "body must be an object")
    if not body.get("name"):
        raise HTTPException(400, "name is required")
    trigger = body.get("trigger")
    if not isinstance(trigger, dict) or not trigger.get("type"):
        raise HTTPException(400, "trigger.type is required")
    valid_triggers = {"text_exact", "text_contains", "text_regex", "always"}
    if trigger["type"] not in valid_triggers:
        raise HTTPException(400, f"trigger.type must be one of: {', '.join(sorted(valid_triggers))}")
    if not isinstance(body.get("actions"), list):
        raise HTTPException(400, "actions must be a list")
    return body  # type: ignore[return-value]


@router.get("/automations")
async def api_automations_list(_auth: None = _AUTH):
    """Return all automation rules."""
    rules = await asyncio.to_thread(_load_rules)
    return {"rules": rules}


@router.post("/automations")
async def api_automations_create(request: Request, _auth: None = _AUTH):
    """Append a new automation rule.  Returns the index of the created rule."""
    body = await request.json()
    _validate_rule_body(body)

    def _add(rule: dict) -> int:
        rules = _load_rules()
        rules.append(rule)
        _save_rules(rules)
        return len(rules) - 1

    idx = await asyncio.to_thread(_add, body)
    return {"ok": True, "index": idx}


@router.put("/automations/{rule_index}")
async def api_automations_update(rule_index: int, request: Request, _auth: None = _AUTH):
    """Replace the automation rule at *rule_index* (0-based)."""
    body = await request.json()
    _validate_rule_body(body)

    def _update(idx: int, rule: dict) -> bool:
        rules = _load_rules()
        if idx < 0 or idx >= len(rules):
            return False
        rules[idx] = rule
        _save_rules(rules)
        return True

    ok = await asyncio.to_thread(_update, rule_index, body)
    if not ok:
        raise HTTPException(404, "Rule not found")
    return {"ok": True}


@router.delete("/automations/{rule_index}")
async def api_automations_delete(rule_index: int, _auth: None = _AUTH):
    """Delete the automation rule at *rule_index* (0-based)."""
    def _remove(idx: int) -> bool:
        rules = _load_rules()
        if idx < 0 or idx >= len(rules):
            return False
        rules.pop(idx)
        _save_rules(rules)
        return True

    ok = await asyncio.to_thread(_remove, rule_index)
    if not ok:
        raise HTTPException(404, "Rule not found")
    return {"ok": True}


@router.post("/automations/reorder")
async def api_automations_reorder(request: Request, _auth: None = _AUTH):
    """Reorder automation rules.

    Body: ``{"order": [2, 0, 1]}`` — a permutation of ``range(len(rules))``
    that specifies the new position of each rule.  ``order[i]`` is the old
    index of the rule that should end up at position *i*.
    """
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(400, "body must be an object")
    order = body.get("order")
    if not isinstance(order, list):
        raise HTTPException(400, "order must be a list")

    def _reorder(new_order: list) -> str:
        rules = _load_rules()
        n = len(rules)
        if sorted(new_order) != list(range(n)):
            return "order must be a permutation of rule indices"
        reordered = [rules[i] for i in new_order]
        _save_rules(reordered)
        return ""

    err = await asyncio.to_thread(_reorder, order)
    if err:
        raise HTTPException(400, err)
    return {"ok": True}
