"""Tiny shared file so the bridge (Telegram side) and the web frontend can
agree on "what we just sent" — used to suppress chat.db echoes of bridge-
originated outbound. Both processes append; the bridge consults on each poll.

Format: JSONL at ~/.chatwire/echo_log.jsonl
  {"t": <epoch>, "h": <handle_lc>, "k": "text"|"photo", "b": <body or null>}

Tail-only consumer: `seen_recently` reads the last ~200 lines and checks
matches within a window. Cheap enough at our message volume.
"""
from __future__ import annotations

import json
import time

from config import STATE_DIR

LOG = STATE_DIR / "echo_log.jsonl"
LOG.parent.mkdir(parents=True, exist_ok=True)
TAIL_LINES = 200


def register(handle: str, kind: str, body: str | None = None) -> None:
    entry = {"t": time.time(), "h": handle.lower(), "k": kind,
             "b": body.strip() if body else None}
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # never let the echo log break sending


def seen_recently(handle: str, kind: str, body: str | None = None,
                  window_s: float = 30.0) -> bool:
    if not LOG.exists():
        return False
    target_handle = handle.lower()
    target_body = body.strip() if body else None
    cutoff = time.time() - window_s
    try:
        with LOG.open("r", encoding="utf-8") as f:
            lines = f.readlines()[-TAIL_LINES:]
    except Exception:
        return False
    for line in lines:
        try:
            e = json.loads(line)
        except (ValueError, json.JSONDecodeError):
            continue
        if e.get("t", 0) < cutoff:
            continue
        if e.get("h") != target_handle:
            continue
        if e.get("k") != kind:
            continue
        if kind == "text":
            if e.get("b") == target_body:
                return True
        else:  # photo / file — just match handle+kind+window
            return True
    return False
