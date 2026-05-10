"""Read new iMessage rows from ~/Library/Messages/chat.db.

Requires Full Disk Access granted to the python binary running this code.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

# chat.db timestamps: nanoseconds since 2001-01-01 UTC (Apple epoch).
APPLE_EPOCH_OFFSET = 978307200

log = logging.getLogger("chat_db")

CHAT_DB = Path.home() / "Library" / "Messages" / "chat.db"

# Attachments downloaded successfully have transfer_state = 5.
ATTACHMENT_READY = 5

# A message belongs to exactly one chat via chat_message_join (INSERT/DELETE
# triggers maintain this invariant). For 1:1 chats style=45 and chat_identifier
# is the peer handle; for groups style=43 and chat_identifier is like
# "chat629180424750381661". display_name is the user-set group name (may be
# empty). chat.guid is the full AppleScript-addressable form, e.g.
# "iMessage;+;chat629180424750381661" — use this for `chat id` sends.
NEW_MESSAGES_SQL = """
SELECT
    m.ROWID                                    AS rowid,
    COALESCE(h.id, '')                         AS handle,
    m.is_from_me                               AS is_from_me,
    COALESCE(m.text, '')                       AS text,
    m.cache_has_attachments                    AS has_attachments,
    COALESCE(parent.text, '')                  AS parent_text,
    COALESCE(parent_h.id, '')                  AS parent_handle,
    COALESCE(parent.is_from_me, 0)             AS parent_is_from_me,
    COALESCE(c.guid, '')                       AS chat_guid,
    COALESCE(c.chat_identifier, '')            AS chat_identifier,
    COALESCE(c.display_name, '')               AS chat_display_name,
    COALESCE(c.style, 0)                       AS chat_style
FROM message m
LEFT JOIN handle h ON m.handle_id = h.ROWID
LEFT JOIN message parent ON parent.guid = m.thread_originator_guid
LEFT JOIN handle parent_h ON parent.handle_id = parent_h.ROWID
LEFT JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
LEFT JOIN chat c ON c.ROWID = cmj.chat_id
WHERE m.ROWID > ?
ORDER BY m.ROWID ASC
"""

ATTACHMENTS_SQL = """
SELECT
    a.filename       AS filename,
    a.mime_type      AS mime_type,
    a.transfer_state AS transfer_state
FROM message_attachment_join maj
JOIN attachment a ON a.ROWID = maj.attachment_id
WHERE maj.message_id = ?
"""


# chat.style values we care about. Apple has other values for abandoned
# chats etc., but the only useful distinction is group vs 1:1.
CHAT_STYLE_GROUP = 43
CHAT_STYLE_DIRECT = 45


@dataclass
class InboundMessage:
    rowid: int
    handle: str          # e.g. '+15551234567' or 'foo@example.com'
    text: str
    attachments: list["InboundAttachment"]
    is_from_me: bool     # 1 when this device (or an iCloud-synced device of the same account) sent it
    parent_text: str = ""
    parent_handle: str = ""
    parent_is_from_me: bool = False
    # Source chat context. chat_guid is the AppleScript-addressable ID
    # ("iMessage;+;chat…"); chat_identifier is the short form the `handle`
    # table stores; chat_name is the group's display_name (empty for 1:1 and
    # for unnamed groups). is_group tracks style=43.
    chat_guid: str = ""
    chat_identifier: str = ""
    chat_name: str = ""
    is_group: bool = False


@dataclass
class InboundAttachment:
    path: Path           # local filesystem path (HEIC may be converted)
    mime_type: str
    ready: bool          # False if Apple hasn't finished downloading from iCloud yet


def _expand(p: str | None) -> Path | None:
    if not p:
        return None
    return Path(p).expanduser()


def _maybe_convert_heic(src: Path) -> Path:
    """Convert HEIC to JPEG via macOS `sips`. Returns original path if not HEIC."""
    if src.suffix.lower() not in {".heic", ".heif"}:
        return src
    dst = src.with_suffix(".jpg")
    if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        return dst
    try:
        subprocess.run(
            ["sips", "-s", "format", "jpeg", str(src), "--out", str(dst)],
            check=True, capture_output=True, timeout=30,
        )
        return dst
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        log.warning("sips HEIC convert failed for %s: %s", src, e)
        return src


class ChatDBReader:
    """Read chat.db through a stable TCC-warm connection, then snapshot-via-backup
    for fresh data each poll.

    Observed constraints on macOS 12 / launchd user agent:
      - FRESH `sqlite3.connect(chat.db)` calls succeed for the first ~4 minutes
        after process start, then TCC starts denying with "unable to open
        database file". Reason unclear — suspected responsibility-process cache
        TTL.
      - A persistent read-only connection does NOT see WAL frames Messages.app
        appends after open (likely because the `chat.db-shm` index isn't
        accessible the same way), so `MAX(ROWID)` stays stale.
      - `conn.backup(target)` uses the already-open source connection and
        correctly copies the latest committed state including WAL frames.

    Strategy: open ONCE at startup (TCC is hot), then every poll `backup()`
    the current state into a fresh in-memory db and query that.
    """

    def __init__(self, state_path: Path):
        self.state_path = state_path
        self.last_seen = self._load_state()
        self._src: sqlite3.Connection | None = None

    def _load_state(self) -> int:
        if self.state_path.exists():
            try:
                return int(json.loads(self.state_path.read_text()).get("last_seen_rowid", 0))
            except (json.JSONDecodeError, ValueError):
                log.exception("state file corrupt; resetting last_seen=0")
        return 0

    def _save_state(self) -> None:
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"last_seen_rowid": self.last_seen}, indent=2))
        tmp.replace(self.state_path)

    def _src_conn(self) -> sqlite3.Connection:
        """Long-lived source connection, opened once while TCC is hot."""
        if self._src is None:
            self._src = sqlite3.connect(f"file:{CHAT_DB}?mode=ro", uri=True)
        return self._src

    def _fresh_snapshot(self) -> sqlite3.Connection:
        """Copy the live chat.db into an in-memory db via sqlite backup.

        Uses the warm source connection (no new chat.db open, so TCC stays
        happy) and produces an in-memory db that reflects the latest committed
        state — including WAL frames the persistent source cursor would miss
        if we queried it directly.
        """
        src = self._src_conn()
        mem = sqlite3.connect(":memory:")
        mem.row_factory = sqlite3.Row
        src.backup(mem)
        return mem

    def initialize_to_now(self) -> None:
        """Open chat.db once (TCC is hot) and seed last_seen on first run."""
        snap = self._fresh_snapshot()
        try:
            current_max = int(snap.execute("SELECT COALESCE(MAX(ROWID), 0) FROM message").fetchone()[0])
        finally:
            snap.close()
        if self.last_seen == 0:
            self.last_seen = current_max
            self._save_state()
            log.info("first run: seeded last_seen_rowid=%d (skipping history)", self.last_seen)
        else:
            log.info("resuming from last_seen_rowid=%d (current max=%d)",
                     self.last_seen, current_max)

    def list_groups(self) -> list[dict]:
        """Return group chats visible in chat.db, most-recently-active first.
        Each dict: {guid, chat_identifier, name, last_rowid, participants}.

        Used to populate the inline whitelist search with groups alongside
        handles. Only groups we've actually exchanged messages in show up —
        abandoned/empty chats are skipped via the chat_message_join filter.
        Unnamed groups get a synthetic name from participants so they're
        still findable.
        """
        conn = self._fresh_snapshot()
        try:
            rows = conn.execute(
                """
                SELECT c.guid AS guid,
                       c.chat_identifier AS chat_identifier,
                       COALESCE(c.display_name, '') AS name,
                       MAX(cmj.message_id) AS last_rowid
                FROM chat c
                JOIN chat_message_join cmj ON cmj.chat_id = c.ROWID
                WHERE c.style = ?
                GROUP BY c.ROWID
                ORDER BY last_rowid DESC
                """,
                (CHAT_STYLE_GROUP,),
            ).fetchall()
            out: list[dict] = []
            for r in rows:
                participants = [
                    row["id"] for row in conn.execute(
                        """
                        SELECT h.id AS id FROM chat_handle_join chj
                        JOIN handle h ON h.ROWID = chj.handle_id
                        JOIN chat c ON c.ROWID = chj.chat_id
                        WHERE c.guid = ?
                        """,
                        (r["guid"],),
                    ).fetchall()
                ]
                out.append({
                    "guid": r["guid"],
                    "chat_identifier": r["chat_identifier"],
                    "name": r["name"],
                    "last_rowid": int(r["last_rowid"] or 0),
                    "participants": participants,
                })
            return out
        finally:
            conn.close()

    def services_for(self, handles: list[str]) -> dict[str, list[str]]:
        """Return {handle_lc: [services]} — e.g. {"+19805858391": ["SMS", "iMessage"]}.

        Apple stores one handle row per (id, service) pair. A phone number
        that has an iMessage identity AND has been SMS'd will appear twice;
        a number you've only ever iMessaged will appear once; a number never
        messaged won't appear at all (empty list in the result).

        Used to tell the user BEFORE whitelisting whether a candidate is
        iMessage-capable from this Mac.
        """
        if not handles:
            return {}
        lows = [h.lower() for h in handles]
        placeholders = ",".join("?" * len(lows))
        out: dict[str, list[str]] = {h: [] for h in lows}
        conn = self._fresh_snapshot()
        try:
            rows = conn.execute(
                f"SELECT LOWER(id) AS id, service FROM handle WHERE LOWER(id) IN ({placeholders})",
                lows,
            ).fetchall()
            for r in rows:
                out.setdefault(r["id"], []).append(r["service"])
        finally:
            conn.close()
        return out

    def outcomes_for(
        self, handles: list[str], window_days: int = 30
    ) -> dict[str, dict[str, dict]]:
        """Per-handle-per-service outgoing delivery stats.

        A handle row in chat.db tells you what's *configured* (e.g. an iMessage
        identity exists) but not whether iMessage still works — Apple leaves
        stale handle rows around after the recipient deregisters, which is the
        whole reason `error=22` exists. These aggregates surface actual
        recent-reachability so /check can say "deregistered → SMS" instead of
        "iMessage" when the last real attempt failed.

        Returns `{handle_lc: {service: stats}}` where stats is:
            total             — outgoing message rows in the window
            delivered         — rows with is_delivered=1
            err22             — rows with error=22 ("not registered on iMessage")
            latest_error      — error code of the *most recent ever* outgoing row
            latest_delivered  — is_delivered of the most recent ever row
            latest_rowid      — ROWID of the most recent ever row

        Latest-* fields ignore the window so stale err=22 signals still surface
        even if the last iMessage attempt was months ago. A service absent from
        the inner dict means we've never sent via it to that handle.
        """
        if not handles:
            return {}
        lows = [h.lower() for h in handles]
        placeholders = ",".join("?" * len(lows))
        cutoff_apple_ns = int(
            (time.time() - window_days * 86400 - APPLE_EPOCH_OFFSET) * 1_000_000_000
        )
        out: dict[str, dict[str, dict]] = {h: {} for h in lows}
        conn = self._fresh_snapshot()
        try:
            agg_sql = f"""
                SELECT LOWER(h.id) AS handle, h.service AS service,
                       COUNT(*) AS total,
                       COALESCE(SUM(m.is_delivered), 0) AS delivered,
                       COALESCE(SUM(CASE WHEN m.error = 22 THEN 1 ELSE 0 END), 0) AS err22
                FROM message m JOIN handle h ON m.handle_id = h.ROWID
                WHERE m.is_from_me = 1
                  AND LOWER(h.id) IN ({placeholders})
                  AND m.date >= ?
                GROUP BY LOWER(h.id), h.service
            """
            for r in conn.execute(agg_sql, [*lows, cutoff_apple_ns]).fetchall():
                out[r["handle"]][r["service"]] = {
                    "total": int(r["total"]),
                    "delivered": int(r["delivered"]),
                    "err22": int(r["err22"]),
                }
            # Latest row per (handle, service) across all time — so a stale
            # err=22 still tells the truth even if nothing was sent recently.
            latest_sql = f"""
                SELECT LOWER(h.id) AS handle, h.service AS service,
                       m.error AS error, m.is_delivered AS is_delivered, m.ROWID AS rowid
                FROM message m JOIN handle h ON m.handle_id = h.ROWID
                WHERE m.is_from_me = 1
                  AND LOWER(h.id) IN ({placeholders})
                  AND m.ROWID IN (
                      SELECT MAX(m2.ROWID) FROM message m2
                      JOIN handle h2 ON m2.handle_id = h2.ROWID
                      WHERE m2.is_from_me = 1
                        AND LOWER(h2.id) IN ({placeholders})
                      GROUP BY LOWER(h2.id), h2.service
                  )
            """
            for r in conn.execute(latest_sql, [*lows, *lows]).fetchall():
                stats = out[r["handle"]].setdefault(
                    r["service"], {"total": 0, "delivered": 0, "err22": 0}
                )
                stats["latest_error"] = int(r["error"] or 0)
                stats["latest_delivered"] = bool(r["is_delivered"])
                stats["latest_rowid"] = int(r["rowid"])
        finally:
            conn.close()
        return out

    def poll(self) -> list[InboundMessage]:
        """Return new INCOMING messages since last poll."""
        out: list[InboundMessage] = []
        conn = self._fresh_snapshot()
        try:
            rows = conn.execute(NEW_MESSAGES_SQL, (self.last_seen,)).fetchall()
            for r in rows:
                self.last_seen = int(r["rowid"])
                attachments: list[InboundAttachment] = []
                if r["has_attachments"]:
                    for a in conn.execute(ATTACHMENTS_SQL, (r["rowid"],)).fetchall():
                        path = _expand(a["filename"])
                        if not path:
                            continue
                        # Trust the filesystem: if the file is there, we can
                        # send it. transfer_state lags behind iCloud sync.
                        ready = path.exists()
                        if ready:
                            path = _maybe_convert_heic(path)
                        attachments.append(InboundAttachment(
                            path=path,
                            mime_type=a["mime_type"] or "application/octet-stream",
                            ready=ready,
                        ))
                out.append(InboundMessage(
                    rowid=int(r["rowid"]),
                    handle=r["handle"],
                    text=r["text"],
                    attachments=attachments,
                    is_from_me=bool(r["is_from_me"]),
                    parent_text=r["parent_text"],
                    parent_handle=r["parent_handle"],
                    parent_is_from_me=bool(r["parent_is_from_me"]),
                    chat_guid=r["chat_guid"],
                    chat_identifier=r["chat_identifier"],
                    chat_name=r["chat_display_name"],
                    is_group=(int(r["chat_style"]) == CHAT_STYLE_GROUP),
                ))
        finally:
            conn.close()
        if rows:
            self._save_state()
        return out
