"""Runtime-mutable whitelist of what the bridge will relay.

Two independent sets live in whitelist.json:
  - handles: iMessage handles (phone/email) — matched against direct messages
    and (historically) against the sender of any relayed message.
  - groups:  iMessage chat GUIDs (e.g. "iMessage;+;chat629…") — matched
    against the source chat of a group message so group chats are relayed as
    distinct threads, not collapsed onto the 1:1 with whichever member sent.

Seeded from WHITELIST_HANDLES env on first load if the file is missing.
After that, whitelist.json is the source of truth — mutations (add/remove)
persist there and env is only consulted when the file doesn't exist.
Groups are never seeded from env; they're added at runtime via inline search.

SELF_HANDLES stays env-only (your own Apple IDs don't change at runtime).
"""
from __future__ import annotations

import json
import logging
import os
import threading

from config import STATE_DIR

log = logging.getLogger("whitelist")

WHITELIST_FILE = STATE_DIR / "whitelist.json"

_lock = threading.Lock()
_cached_handles: set[str] = set()
_cached_groups: set[str] = set()
_cached_mtime: float = -1.0


def _seed_from_env_if_missing() -> None:
    if WHITELIST_FILE.exists():
        return
    seed = {h.strip().lower() for h in os.environ.get("WHITELIST_HANDLES", "").split(",") if h.strip()}
    WHITELIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = WHITELIST_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"handles": sorted(seed), "groups": []}, indent=2))
    tmp.replace(WHITELIST_FILE)
    log.info("seeded whitelist.json with %d handles from env", len(seed))


def _read_file() -> tuple[set[str], set[str]]:
    try:
        data = json.loads(WHITELIST_FILE.read_text())
        handles = {h.lower() for h in data.get("handles", [])}
        # Group GUIDs are case-sensitive (they carry a service prefix like
        # "iMessage;+;" and an opaque chat ID); don't lowercase them.
        groups = {g for g in data.get("groups", []) if g}
        return handles, groups
    except (json.JSONDecodeError, FileNotFoundError):
        return set(), set()


def _refresh() -> None:
    """Reload cache if the file has changed. Caller holds _lock."""
    global _cached_handles, _cached_groups, _cached_mtime
    _seed_from_env_if_missing()
    try:
        mtime = WHITELIST_FILE.stat().st_mtime
    except FileNotFoundError:
        _cached_handles, _cached_groups, _cached_mtime = set(), set(), -1.0
        return
    if mtime != _cached_mtime:
        _cached_handles, _cached_groups = _read_file()
        _cached_mtime = mtime


def all_handles() -> set[str]:
    """Return the current handle whitelist, reloading on file mtime change."""
    with _lock:
        _refresh()
        return set(_cached_handles)


def all_groups() -> set[str]:
    """Return the current group-chat GUID whitelist."""
    with _lock:
        _refresh()
        return set(_cached_groups)


def _write(handles: set[str], groups: set[str]) -> None:
    global _cached_handles, _cached_groups, _cached_mtime
    tmp = WHITELIST_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(
        {"handles": sorted(handles), "groups": sorted(groups)}, indent=2,
    ))
    tmp.replace(WHITELIST_FILE)
    _cached_handles = set(handles)
    _cached_groups = set(groups)
    _cached_mtime = WHITELIST_FILE.stat().st_mtime


def add(handle: str) -> bool:
    """Add one handle. True if newly added, False if already present."""
    h = handle.strip().lower()
    if not h:
        return False
    with _lock:
        _seed_from_env_if_missing()
        handles, groups = _read_file()
        if h in handles:
            return False
        handles.add(h)
        _write(handles, groups)
        return True


def remove(handle: str) -> bool:
    """Remove one handle. True if it was present, False otherwise."""
    h = handle.strip().lower()
    with _lock:
        handles, groups = _read_file()
        if h not in handles:
            return False
        handles.discard(h)
        _write(handles, groups)
        return True


def add_group(guid: str) -> bool:
    """Add one group chat GUID. True if newly added, False if already present."""
    g = guid.strip()
    if not g:
        return False
    with _lock:
        _seed_from_env_if_missing()
        handles, groups = _read_file()
        if g in groups:
            return False
        groups.add(g)
        _write(handles, groups)
        return True


def remove_group(guid: str) -> bool:
    """Remove one group chat GUID. True if it was present, False otherwise."""
    g = guid.strip()
    with _lock:
        handles, groups = _read_file()
        if g not in groups:
            return False
        groups.discard(g)
        _write(handles, groups)
        return True
