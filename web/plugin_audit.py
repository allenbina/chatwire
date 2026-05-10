"""Plugin audit log — append-only JSONL at ~/.chatwire/plugin-audit.jsonl.

Events written here:
  plugin_enable     — a plugin is enabled (official/core tier logged; all tiers written)
  plugin_disable    — a plugin is disabled
  tier_violation    — a sandboxed plugin attempted to access a blocked BridgeContext attr

Rotates to plugin-audit.jsonl.1 when the file exceeds 1 MB.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Resolve STATE_DIR without importing the full config module so this file
# can be imported from both web/ (PYTHONPATH includes project root) and
# bridge.py (project root is sys.path[0]).
_here = Path(__file__).resolve().parent
_project_root = _here.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

try:
    from config import STATE_DIR
except ImportError:
    STATE_DIR = Path("~/.chatwire").expanduser()

AUDIT_FILE = STATE_DIR / "plugin-audit.jsonl"
MAX_BYTES = 1_000_000  # rotate at 1 MB


def log_event(event: str, plugin: str, **extra) -> None:
    """Append one audit event (fire-and-forget; errors are silently swallowed).

    Args:
        event:  Event name string (e.g. "plugin_enable", "tier_violation").
        plugin: Plugin NAME attribute (e.g. "chatwire-ntfy").
        **extra: Arbitrary key=value pairs serialised alongside the record.
    """
    entry: dict = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": event,
        "plugin": plugin,
    }
    for k, v in extra.items():
        if v is not None:
            entry[k] = v

    _append(json.dumps(entry, separators=(",", ":")) + "\n")


def _append(line: str) -> None:
    try:
        AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Rotate if the current file is over the size limit.
        if AUDIT_FILE.exists() and AUDIT_FILE.stat().st_size >= MAX_BYTES:
            rotated = AUDIT_FILE.with_suffix(".jsonl.1")
            AUDIT_FILE.rename(rotated)
        # O_APPEND write is atomic on POSIX for writes ≤ PIPE_BUF (~4 KB).
        # JSON audit lines are tiny, so this is safe without a lock file.
        with AUDIT_FILE.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        pass  # Audit failure must never crash the calling process.
