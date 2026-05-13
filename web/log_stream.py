"""Structured JSONL logger for chatwire.

All log output is written to ~/.chatwire/chatwire.jsonl.
Each line is a JSON object::

    {"ts": "2026-05-10T18:00:00Z", "source": "core", "level": "info", "msg": "..."}

The file auto-rotates when it exceeds LOG_MAX_BYTES (10 MB).  The previous
file is renamed to chatwire.1.jsonl and the rotated log list is kept to one
backup (the oldest is discarded).

Consumers (SSE endpoint, history endpoint) read the file directly as plain
text so there's no shared queue or thread needed.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path.home() / ".chatwire" / "chatwire.jsonl"
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_BACKUP_PATH = LOG_PATH.parent / "chatwire.1.jsonl"

_write_lock = threading.Lock()
_python_log = logging.getLogger("chatwire.log_stream")


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rotate_if_needed() -> None:
    """Rotate chatwire.jsonl → chatwire.1.jsonl when it exceeds LOG_MAX_BYTES."""
    try:
        if LOG_PATH.exists() and LOG_PATH.stat().st_size >= LOG_MAX_BYTES:
            if _BACKUP_PATH.exists():
                _BACKUP_PATH.unlink()
            LOG_PATH.rename(_BACKUP_PATH)
    except Exception:
        _python_log.exception("log rotation failed")


def write_log(source: str, level: str, msg: str) -> None:
    """Append one structured log entry to chatwire.jsonl.

    *source* — ``"core"`` or a plugin name.
    *level*  — ``"info"``, ``"warn"``, or ``"error"``.
    *msg*    — the log message (single line preferred).
    """
    entry = json.dumps({
        "ts": _now_iso(),
        "source": source,
        "level": level,
        "msg": str(msg),
    }, ensure_ascii=False)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _write_lock:
        _rotate_if_needed()
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(entry + "\n")


def info(source: str, msg: str) -> None:
    write_log(source, "info", msg)


def warn(source: str, msg: str) -> None:
    write_log(source, "warn", msg)


def error(source: str, msg: str) -> None:
    write_log(source, "error", msg)


# ---------------------------------------------------------------------------
# Read helpers (for HTTP endpoints)
# ---------------------------------------------------------------------------

def _parse_entry(line: str) -> dict | None:
    """Parse one JSONL line. Returns None if unparseable."""
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
        if not isinstance(obj, dict):
            return None
        return obj
    except Exception:
        return None


def _passes_filter(entry: dict, source: str, level: str) -> bool:
    """Return True if *entry* matches the requested filters."""
    _LEVEL_ORDER = {"info": 0, "warn": 1, "error": 2}
    if source and source != "all" and entry.get("source") != source:
        return False
    if level and level != "all":
        entry_level = _LEVEL_ORDER.get(entry.get("level", "info"), 0)
        min_level = _LEVEL_ORDER.get(level, 0)
        if entry_level < min_level:
            return False
    return True


def read_history(
    *,
    since: str = "",
    limit: int = 200,
    source: str = "",
    level: str = "",
) -> list[dict]:
    """Return recent log entries from chatwire.jsonl (newest-last).

    *since* — ISO timestamp; only entries *after* this time are returned.
    *limit* — maximum number of entries to return (applied after filtering).
    """
    if not LOG_PATH.exists():
        return []

    try:
        lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []

    entries = []
    for line in lines:
        entry = _parse_entry(line)
        if entry is None:
            continue
        if since and entry.get("ts", "") <= since:
            continue
        if not _passes_filter(entry, source, level):
            continue
        entries.append(entry)

    return entries[-limit:]


def tail_from_offset(
    byte_offset: int,
    source: str = "",
    level: str = "",
) -> tuple[list[dict], int]:
    """Return new entries since *byte_offset* and the new file offset.

    Used by the SSE endpoint to efficiently stream only new lines.
    Returns (entries, new_offset).
    """
    if not LOG_PATH.exists():
        return [], byte_offset

    try:
        size = LOG_PATH.stat().st_size
    except Exception:
        return [], byte_offset

    # File was rotated (shrunk) — reset to end so we don't re-emit everything.
    if byte_offset > size:
        return [], size

    if byte_offset == size:
        return [], byte_offset

    try:
        with LOG_PATH.open("rb") as fh:
            fh.seek(byte_offset)
            raw = fh.read()
        new_offset = byte_offset + len(raw)
    except Exception:
        return [], byte_offset

    entries = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        entry = _parse_entry(line)
        if entry and _passes_filter(entry, source, level):
            entries.append(entry)

    return entries, new_offset


def current_size() -> int:
    """Return current byte size of the log file (0 if not yet created)."""
    try:
        return LOG_PATH.stat().st_size if LOG_PATH.exists() else 0
    except Exception:
        return 0
