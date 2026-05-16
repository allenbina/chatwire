"""FTS5 sidecar index for MCP search_messages.

Maintains a persistent SQLite FTS5 index at ~/.chatwire/search_fts.db
that mirrors the text content of chat.db. Syncs incrementally on each
search call (only new rows since last sync).

First build on a large DB (~500k messages) takes a few seconds.
Subsequent syncs are near-instant (only new messages since last call).
FTS5 MATCH queries return in <10ms regardless of DB size.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path

log = logging.getLogger("chatwire.mcp.fts")

_lock = threading.Lock()

# Default location — tests can override via patch
_INDEX_PATH: Path | None = None


def _index_db_path() -> Path:
    """Return the path to the FTS5 sidecar DB."""
    global _INDEX_PATH
    if _INDEX_PATH is not None:
        return _INDEX_PATH
    from config import STATE_DIR  # noqa: PLC0415
    return STATE_DIR / "search_fts.db"


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the FTS5 table and sync state table if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sync_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            last_rowid INTEGER NOT NULL DEFAULT 0
        );
        INSERT OR IGNORE INTO sync_state (id, last_rowid) VALUES (1, 0);
        CREATE VIRTUAL TABLE IF NOT EXISTS fts_messages USING fts5(
            rowid_orig UNINDEXED,
            handle UNINDEXED,
            is_from_me UNINDEXED,
            date_val UNINDEXED,
            text,
            content='',
            contentless_delete=1
        );
    """)


def _sync(index_conn: sqlite3.Connection, chat_db: Path) -> int:
    """Incrementally sync new messages from chat.db into the FTS5 index.

    Returns the number of new rows indexed.
    """
    row = index_conn.execute("SELECT last_rowid FROM sync_state WHERE id = 1").fetchone()
    last_rowid = row[0] if row else 0

    # Open chat.db read-only
    src = sqlite3.connect(f"file:{chat_db}?mode=ro", uri=True)
    try:
        rows = src.execute(
            "SELECT m.ROWID, COALESCE(h.id, ''), m.is_from_me, m.date, m.text "
            "FROM message m "
            "LEFT JOIN handle h ON m.handle_id = h.ROWID "
            "WHERE m.ROWID > ? AND m.text IS NOT NULL AND m.text != '' "
            "ORDER BY m.ROWID",
            (last_rowid,),
        ).fetchall()
    finally:
        src.close()

    if not rows:
        return 0

    # Batch insert into FTS5
    index_conn.executemany(
        "INSERT INTO fts_messages (rowid_orig, handle, is_from_me, date_val, text) "
        "VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    new_last = rows[-1][0]
    index_conn.execute("UPDATE sync_state SET last_rowid = ? WHERE id = 1", (new_last,))
    index_conn.commit()
    log.info("FTS5 sync: indexed %d new messages (up to rowid %d)", len(rows), new_last)
    return len(rows)


def search(query: str, chat_db: Path, handle: str = "", limit: int = 100) -> list[dict]:
    """Search messages using FTS5 MATCH. Syncs index first if needed.

    Returns list of {rowid, date, from_me, text, handle} dicts.
    """
    with _lock:
        db_path = _index_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(db_path))
        try:
            _ensure_schema(conn)
            _sync(conn, chat_db)

            # FTS5 query — escape special characters for safety
            # Use double-quotes to treat the query as a phrase
            safe_query = query.replace('"', '""')
            fts_query = f'"{safe_query}"'

            if handle:
                sql = (
                    "SELECT rowid_orig, date_val, is_from_me, text, handle "
                    "FROM fts_messages WHERE fts_messages MATCH ? "
                    "AND lower(handle) = lower(?) "
                    "ORDER BY rowid_orig DESC LIMIT ?"
                )
                rows = conn.execute(sql, (fts_query, handle, limit)).fetchall()
            else:
                sql = (
                    "SELECT rowid_orig, date_val, is_from_me, text, handle "
                    "FROM fts_messages WHERE fts_messages MATCH ? "
                    "ORDER BY rowid_orig DESC LIMIT ?"
                )
                rows = conn.execute(sql, (fts_query, limit)).fetchall()
        finally:
            conn.close()

    return [
        {
            "rowid": row[0],
            "date": row[1],
            "from_me": bool(row[2]),
            "text": row[3] or "",
            "handle": row[4],
        }
        for row in rows
    ]
