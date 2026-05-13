"""Tests for edited-message detection (_fetch_edited_flags) in web/main.py.

Strategy: mirror the _fetch_edited_flags logic locally so we can test it
without importing web/main.py (which has module-level side-effects and
Python-3.10+ type-annotation syntax incompatible with Python 3.8).

The local mirror must be kept in sync with web/main.py if that function
ever changes.

Covers:
  a. Returns True for rows with date_edited != 0.
  b. Returns False for rows with date_edited == 0.
  c. Returns False for rows with date_edited NULL (COALESCE fallback).
  d. Returns {} for an empty rowid list.
  e. Returns {} gracefully when date_edited column is absent
     (pre-macOS-13 chat.db schema).
  f. Rows not in the DB are absent from the result dict.
  g. Handles a mixed batch (edited + not edited + NULL).
"""
from __future__ import annotations

import sqlite3


# ---------------------------------------------------------------------------
# Local mirror of web.main._fetch_edited_flags
# ---------------------------------------------------------------------------

def _fetch_edited_flags(conn, rowids: list[int]) -> dict[int, bool]:
    """Mirror of web.main._fetch_edited_flags — keep in sync."""
    if not rowids:
        return {}
    placeholders = ",".join("?" * len(rowids))
    sql = (
        f"SELECT ROWID, COALESCE(date_edited, 0) AS date_edited "
        f"FROM message WHERE ROWID IN ({placeholders})"
    )
    try:
        rows = conn.execute(sql, rowids).fetchall()
    except Exception:
        return {}
    return {int(row["ROWID"]): bool(row["date_edited"]) for row in rows}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_conn(has_date_edited: bool = True) -> sqlite3.Connection:
    """In-memory SQLite DB with a minimal message table.

    If ``has_date_edited`` is False the column is omitted, simulating a
    pre-macOS-13 chat.db where the column does not exist.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    if has_date_edited:
        conn.execute("""
            CREATE TABLE message (
                ROWID INTEGER PRIMARY KEY,
                text TEXT,
                date_edited INTEGER DEFAULT 0
            )
        """)
        conn.executemany(
            "INSERT INTO message (ROWID, text, date_edited) VALUES (?,?,?)",
            [
                (1, "hello",  0),            # not edited
                (2, "world",  123456789),     # edited
                (3, "again",  None),          # NULL — treat as not edited
                (4, "latest", 987654321),     # edited
            ],
        )
    else:
        conn.execute("""
            CREATE TABLE message (
                ROWID INTEGER PRIMARY KEY,
                text TEXT
            )
        """)
        conn.executemany(
            "INSERT INTO message (ROWID, text) VALUES (?,?)",
            [(1, "hello"), (2, "world")],
        )
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFetchEditedFlags:
    def test_empty_rowids_returns_empty_dict(self):
        conn = _make_conn()
        result = _fetch_edited_flags(conn, [])
        assert result == {}
        conn.close()

    def test_unedited_message_returns_false(self):
        conn = _make_conn()
        result = _fetch_edited_flags(conn, [1])
        assert result == {1: False}
        conn.close()

    def test_edited_message_returns_true(self):
        conn = _make_conn()
        result = _fetch_edited_flags(conn, [2])
        assert result == {2: True}
        conn.close()

    def test_null_date_edited_treated_as_not_edited(self):
        conn = _make_conn()
        result = _fetch_edited_flags(conn, [3])
        assert result == {3: False}
        conn.close()

    def test_mixed_batch(self):
        conn = _make_conn()
        result = _fetch_edited_flags(conn, [1, 2, 3, 4])
        assert result == {1: False, 2: True, 3: False, 4: True}
        conn.close()

    def test_missing_column_returns_empty_dict(self):
        """Pre-macOS-13 databases don't have date_edited — must not crash."""
        conn = _make_conn(has_date_edited=False)
        result = _fetch_edited_flags(conn, [1, 2])
        assert result == {}
        conn.close()

    def test_rowids_not_in_db_absent_from_result(self):
        conn = _make_conn()
        result = _fetch_edited_flags(conn, [999])
        assert result == {}
        conn.close()

    def test_subset_of_rowids(self):
        conn = _make_conn()
        result = _fetch_edited_flags(conn, [2, 4])
        assert result[2] is True
        assert result[4] is True
        assert 1 not in result
        assert 3 not in result
        conn.close()
