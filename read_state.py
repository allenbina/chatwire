"""Cross-interface read-state tracking.

Stores the highest message rowid each interface (web, xmpp, telegram, …) has
acknowledged for each conversation.  The "last seen" for a conversation is the
MAX across all interfaces — so opening a chat in the web UI suppresses the
notification badge on XMPP and vice versa.

conversation_id:
  - 1:1 handles:  the raw handle string, e.g. "+15550001111"
  - group chats:  the iMessage GUID, e.g. "chat00112233-4455-..."
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path("~/.chatwire/read_state.db").expanduser()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE IF NOT EXISTS read_state (
        conversation_id TEXT NOT NULL,
        interface       TEXT NOT NULL,
        last_seen_rowid INTEGER NOT NULL,
        updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (conversation_id, interface)
    )""")
    db.commit()
    return db


def mark_seen(conversation_id: str, interface: str, last_rowid: int) -> None:
    """Record that `interface` has seen up to `last_rowid` in this conversation."""
    db = _connect()
    try:
        db.execute(
            "INSERT OR REPLACE INTO read_state VALUES (?, ?, ?, datetime('now'))",
            (conversation_id, interface, last_rowid),
        )
        db.commit()
    finally:
        db.close()


def get_last_seen(conversation_id: str) -> int:
    """Highest seen rowid across ALL interfaces for this conversation.

    Returns 0 if the conversation has never been marked seen.
    """
    db = _connect()
    try:
        row = db.execute(
            "SELECT MAX(last_seen_rowid) FROM read_state WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    finally:
        db.close()


def get_all_last_seen() -> dict[str, int]:
    """Return {conversation_id: max_last_seen_rowid} for all tracked conversations."""
    db = _connect()
    try:
        rows = db.execute(
            "SELECT conversation_id, MAX(last_seen_rowid) AS m FROM read_state GROUP BY conversation_id"
        ).fetchall()
        return {r["conversation_id"]: int(r["m"]) for r in rows}
    finally:
        db.close()


def mark_all_seen(interface: str, conversations: list[dict]) -> None:
    """Mark all conversations as seen up to their latest message rowid."""
    db = _connect()
    try:
        for c in conversations:
            conv_id = c.get("handle") or c.get("guid") or ""
            last_rowid = c.get("last_rowid", 0)
            if conv_id and last_rowid:
                db.execute(
                    "INSERT OR REPLACE INTO read_state VALUES (?, ?, ?, datetime('now'))",
                    (conv_id, interface, last_rowid),
                )
        db.commit()
    finally:
        db.close()
