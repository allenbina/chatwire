"""Send iMessages via AppleScript -> Messages.app.

Requires Automation permission for the running binary to control Messages.

Anti-spam guards (check_send_guard)
-------------------------------------
All outbound sends should call ``check_send_guard(recipient, body, source)``
before reaching the AppleScript layer.  The guard enforces:

1. **Global rate limit** — 20 messages / 60 s (token bucket).  Raises
   ``RateLimitError`` when exhausted.
2. **Broadcast detection** — maintains ``{hash → set(recipients)}`` with a
   1-hour rolling window.  At 3 unique recipients sends an ntfy warning.  At
   5 starts escalating send-timeouts (5 min → 15 min → 60 min → 6 h →
   disabled).  Timeout state is persisted to
   ``~/.chatwire/rate_limit_state.json`` so restarts don't reset escalation.
   Raises ``BroadcastBlockedError`` when a timeout is active.
3. **Audit log** — appends one TSV line per send to
   ``~/.chatwire/send_audit.log`` (timestamp, recipient, source, hash).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from chat_db import CHAT_DB

log = logging.getLogger("chat_send")

# ---------------------------------------------------------------------------
# Anti-spam constants
# ---------------------------------------------------------------------------

_RATE_LIMIT_COUNT = 20       # max messages per window
_RATE_LIMIT_WINDOW_S = 60.0  # window duration in seconds

_BROADCAST_WARN_AT = 3       # unique recipients → ntfy warning
_BROADCAST_BLOCK_AT = 5      # unique recipients → escalating timeout
_BROADCAST_WINDOW_S = 3600   # rolling window (1 hour)

# Timeout steps in seconds; -1 means "disabled until manual re-enable"
_ESCALATION_STEPS = [5 * 60, 15 * 60, 60 * 60, 6 * 3600, -1]

_STATE_FILE = Path.home() / ".chatwire" / "rate_limit_state.json"
_AUDIT_LOG  = Path.home() / ".chatwire" / "send_audit.log"


# ---------------------------------------------------------------------------
# Anti-spam exceptions
# ---------------------------------------------------------------------------

class RateLimitError(Exception):
    """Raised when the global send rate limit (20/min) is exhausted."""


class BroadcastBlockedError(Exception):
    """Raised when a broadcast-detection timeout is currently active.

    Attributes:
        retry_after: seconds until the timeout expires, or None if disabled.
    """

    def __init__(self, msg: str, retry_after: float | None = None) -> None:
        super().__init__(msg)
        self.retry_after = retry_after


# ---------------------------------------------------------------------------
# Token-bucket rate limiter
# ---------------------------------------------------------------------------

class _TokenBucket:
    """Leaky-bucket rate limiter (refills proportionally over time)."""

    def __init__(self, rate: int = _RATE_LIMIT_COUNT,
                 window_s: float = _RATE_LIMIT_WINDOW_S) -> None:
        self._rate = rate
        self._window_s = window_s
        self._tokens = float(rate)
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def consume(self) -> bool:
        """Try to consume one token.  Returns True if allowed."""
        with self._lock:
            now = time.monotonic()
            self._tokens = min(
                float(self._rate),
                self._tokens + (now - self._last) / self._window_s * self._rate,
            )
            self._last = now
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False

    # --- for tests ---
    def _set_tokens(self, n: float) -> None:
        with self._lock:
            self._tokens = n


# ---------------------------------------------------------------------------
# Broadcast hash tracker  (in-memory, 1-hour rolling window)
# ---------------------------------------------------------------------------

class _BroadcastTracker:
    """Map {msg_hash → [(monotonic_ts, recipient)]} with rolling eviction."""

    def __init__(self, window_s: float = _BROADCAST_WINDOW_S) -> None:
        self._window = window_s
        self._lock = threading.Lock()
        self._records: dict[str, list[tuple[float, str]]] = {}

    def _evict(self, h: str, now: float) -> None:
        cutoff = now - self._window
        if h in self._records:
            self._records[h] = [(t, r) for t, r in self._records[h] if t >= cutoff]

    def record(self, msg_hash: str, recipient: str) -> int:
        """Record a send; return count of unique recipients for this hash in window."""
        with self._lock:
            now = time.monotonic()
            self._records.setdefault(msg_hash, [])
            self._evict(msg_hash, now)
            # Append to the (possibly newly-filtered) list after eviction
            self._records[msg_hash].append((now, recipient))
            return len({r for _, r in self._records[msg_hash]})

    # --- for tests ---
    def _reset(self) -> None:
        with self._lock:
            self._records.clear()


# ---------------------------------------------------------------------------
# Escalation state  (persisted to disk)
# ---------------------------------------------------------------------------

class _EscalationState:
    """Persistent escalating-timeout state for broadcast blocking.

    Persisted as JSON so restarts don't reset escalation level.
    Wall-clock expiry is stored; on load we convert back to monotonic.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # hash → {"level": int, "until_mono": float}
        # level is the index into _ESCALATION_STEPS that was last applied.
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(_STATE_FILE.read_text())
            now_wall = time.time()
            now_mono = time.monotonic()
            for h, v in raw.items():
                level = int(v.get("level", 0))
                until_wall = float(v.get("until_wall", 0))
                until_mono = now_mono + max(0.0, until_wall - now_wall)
                self._data[h] = {"level": level, "until_mono": until_mono}
        except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError):
            pass

    def _save(self) -> None:
        """Persist to disk; caller holds self._lock."""
        now_mono = time.monotonic()
        now_wall = time.time()
        out: dict[str, dict] = {}
        for h, v in self._data.items():
            remaining = v["until_mono"] - now_mono
            out[h] = {
                "level": v["level"],
                "until_wall": now_wall + max(0.0, remaining),
            }
        try:
            _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = _STATE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(out, indent=2))
            tmp.replace(_STATE_FILE)
        except Exception:
            log.exception("failed to save rate_limit_state.json")

    def check_blocked(self, msg_hash: str) -> tuple[bool, float | None]:
        """Return (is_blocked, seconds_remaining_or_None_if_disabled)."""
        with self._lock:
            st = self._data.get(msg_hash)
            if st is None:
                return False, None
            step = _ESCALATION_STEPS[st["level"]]
            if step == -1:
                return True, None
            remaining = st["until_mono"] - time.monotonic()
            return (remaining > 0, remaining if remaining > 0 else None)

    def escalate(self, msg_hash: str) -> float | None:
        """Move to next escalation level; return timeout seconds or None=disabled."""
        with self._lock:
            st = self._data.get(msg_hash)
            cur_level = st["level"] if st else -1
            next_level = min(cur_level + 1, len(_ESCALATION_STEPS) - 1)
            step = _ESCALATION_STEPS[next_level]
            now_mono = time.monotonic()
            self._data[msg_hash] = {
                "level": next_level,
                "until_mono": now_mono if step == -1 else now_mono + step,
            }
            self._save()
            return None if step == -1 else float(step)

    # --- for tests ---
    def _reset(self) -> None:
        with self._lock:
            self._data.clear()
            try:
                _STATE_FILE.unlink(missing_ok=True)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

_rate_bucket    = _TokenBucket()
_broadcast      = _BroadcastTracker()
_escalation     = _EscalationState()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_spam_whitelist() -> frozenset[str]:
    """Read spam_whitelist from config.  Graceful fallback to empty set."""
    try:
        from config import load_config as _load
        cfg = _load()
        names = cfg.get("web", {}).get("spam_whitelist", [])
        if isinstance(names, list):
            return frozenset(n.strip().lower() for n in names if n.strip())
    except Exception:
        pass
    return frozenset()


def _normalize_text(text: str, whitelist_names: frozenset[str]) -> str:
    """Normalise text for broadcast-detection hashing.

    Steps: lowercase → strip whitelisted names → strip punctuation →
    collapse whitespace.
    """
    t = text.lower()
    for name in whitelist_names:
        t = t.replace(name, "")
    t = re.sub(r"[^\w\s]", "", t)
    return " ".join(t.split())


def _msg_hash(normalized: str) -> str:
    return hashlib.sha256(normalized.encode()).hexdigest()


def _ntfy_warning(message: str) -> None:
    """Fire-and-forget ntfy notification.  Never raises."""
    try:
        from config import load_config as _load
        cfg = _load()
        topic = (cfg.get("web", {}).get("ntfy_topic") or
                 os.environ.get("NTFY_TOPIC", "")).strip()
        if not topic:
            log.warning("no ntfy_topic configured; dropping spam warning: %s", message)
            return
        import urllib.request
        req = urllib.request.Request(
            f"https://ntfy.sh/{topic}",
            data=message.encode(),
            method="POST",
            headers={"Content-Type": "text/plain"},
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        log.exception("ntfy warning failed")


def _write_audit(recipient: str, source: str, msg_hash: str) -> None:
    """Append one TSV line to send_audit.log.  Never raises."""
    try:
        _AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with open(_AUDIT_LOG, "a", encoding="utf-8") as fh:
            fh.write(f"{ts}\t{recipient}\t{source}\t{msg_hash}\n")
    except Exception:
        log.exception("audit log write failed")


# ---------------------------------------------------------------------------
# Public guard — callers MUST invoke this before any AppleScript send
# ---------------------------------------------------------------------------

def check_send_guard(recipient: str, body: str, source: str = "unknown") -> str:
    """Run all anti-spam checks before an outbound send.

    Args:
        recipient: The target handle or chat GUID.
        body:      The message text (empty string for file sends).
        source:    Attribution string for the audit log ("web", plugin name, …).

    Returns:
        The SHA-256 hex-digest of the normalised body (for callers that want
        to log it themselves).

    Raises:
        RateLimitError:       Global rate limit exhausted.
        BroadcastBlockedError: Broadcast timeout active for this message hash.
    """
    # 1. Global rate limit
    if not _rate_bucket.consume():
        raise RateLimitError(
            "Send rate limit exceeded (20 messages / minute). Try again shortly."
        )

    # 2. Broadcast detection (text-only; file sends pass an empty body)
    whitelist = _get_spam_whitelist()
    normalized = _normalize_text(body, whitelist)
    h = _msg_hash(normalized)

    if body.strip():  # skip broadcast tracking for empty/file sends
        blocked, remaining = _escalation.check_blocked(h)
        if blocked:
            if remaining is None:
                raise BroadcastBlockedError(
                    "Broadcast sending disabled — re-enable in settings.", None
                )
            raise BroadcastBlockedError(
                f"Broadcast timeout active ({remaining / 60:.0f} min remaining).",
                remaining,
            )

        unique_count = _broadcast.record(h, recipient)

        if unique_count == _BROADCAST_WARN_AT:
            log.warning("broadcast warning: same message to %d recipients hash=%s",
                        unique_count, h[:8])
            _ntfy_warning(
                f"chatwire anti-spam: same message sent to {unique_count} "
                f"different recipients. Possible broadcast spam."
            )

        if unique_count >= _BROADCAST_BLOCK_AT:
            timeout = _escalation.escalate(h)
            if timeout is None:
                detail = "disabled — re-enable in chatwire settings"
            else:
                detail = f"blocked for {timeout / 60:.0f} min"
            log.warning("broadcast block: hash=%s unique=%d action=%s",
                        h[:8], unique_count, detail)
            _ntfy_warning(
                f"chatwire anti-spam: broadcast blocked. Same message to "
                f"{unique_count} recipients. Sending {detail}."
            )
            raise BroadcastBlockedError(
                f"Broadcast detected ({unique_count} recipients). Sending {detail}.",
                timeout,
            )

    # 3. Audit log
    _write_audit(recipient, source, h)
    return h

OSASCRIPT_TIMEOUT_S = 30

# chat.db error codes we translate to human hints. Everything else surfaces
# as the bare integer so the UI tells you *something* meaningful to grep.
ERROR_HINTS = {
    0: "",
    3: "network error",
    22: "not registered on iMessage — try SMS / a different number",
    41: "blocked by recipient or invalid address",
    100: "delivery failed",
    102: "server rejected message",
}


@dataclass
class SendResult:
    """Outcome of a send attempt, enriched by reading chat.db after osascript.

    - osascript_ok: Messages.app accepted the send command.
    - rowid / service / is_sent / is_delivered / error: from the matching
      outgoing row in chat.db. None/False when we didn't find it in time.
    - fell_back_to_sms: the first iMessage attempt returned an identity error
      (22) and we auto-retried via SMS. The other fields describe the SMS
      attempt in that case; `original_error` carries the original iMessage code.
    """

    osascript_ok: bool = False
    rowid: int | None = None
    service: str | None = None
    is_sent: bool = False
    is_delivered: bool = False
    error: int = 0
    fell_back_to_sms: bool = False
    original_error: int = 0

    @property
    def delivered(self) -> bool:
        return self.error == 0 and self.is_delivered

    @property
    def failed(self) -> bool:
        return self.error != 0

    @property
    def hint(self) -> str:
        if self.error:
            base = ERROR_HINTS.get(self.error) or f"error {self.error}"
            if self.fell_back_to_sms:
                return f"iMessage err={self.original_error}, SMS also failed: {base}"
            return base
        if not self.osascript_ok:
            return "Messages.app rejected the send command"
        if self.rowid is None:
            return "no chat.db row after send — Messages.app may not have queued it"
        if self.is_delivered:
            return "delivered via SMS (iMessage unavailable)" if self.fell_back_to_sms else "delivered"
        if self.is_sent:
            return (
                "sent via SMS (iMessage unavailable), awaiting delivery receipt"
                if self.fell_back_to_sms
                else "sent, awaiting delivery receipt"
            )
        return "SMS fallback pending" if self.fell_back_to_sms else "pending"

    @property
    def status(self) -> str:
        """Short one-word status for UI badges."""
        if self.failed:
            return "failed"
        if self.delivered:
            return "delivered"
        if self.is_sent:
            return "sent"
        if self.osascript_ok:
            return "pending"
        return "failed"


def _run_osascript(script: str) -> None:
    proc = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=OSASCRIPT_TIMEOUT_S,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"osascript failed (exit {proc.returncode}): {proc.stderr.strip()}"
        )


def _escape(s: str) -> str:
    """Escape a string for embedding inside an AppleScript double-quoted literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _service_const(service: str) -> str:
    """Map caller-visible service name to the AppleScript identifier."""
    if service == "iMessage":
        return "iMessage"
    if service == "SMS":
        return "SMS"
    raise ValueError(f"unsupported service: {service!r}")


def send_text(handle: str, body: str, service: str = "iMessage") -> None:
    svc = _service_const(service)
    script = f'''
    tell application "Messages"
        set targetService to 1st service whose service type = {svc}
        set targetBuddy to buddy "{_escape(handle)}" of targetService
        send "{_escape(body)}" to targetBuddy
    end tell
    '''
    _run_osascript(script)
    log.info("sent text -> %s len=%d service=%s", handle, len(body), service)


def send_file(handle: str, path: Path, service: str = "iMessage") -> None:
    svc = _service_const(service)
    script = f'''
    tell application "Messages"
        set targetService to 1st service whose service type = {svc}
        set targetBuddy to buddy "{_escape(handle)}" of targetService
        send (POSIX file "{_escape(str(path))}") to targetBuddy
    end tell
    '''
    _run_osascript(script)
    log.info("sent file -> %s path=%s service=%s", handle, path, service)


# Group chats are addressed by chat GUID (e.g. "iMessage;+;chat629…"), not by
# a buddy. AppleScript accepts `chat id "<GUID>"` directly; no service lookup
# is needed because the service is embedded in the GUID itself. No SMS
# fallback for groups — the service is fixed by how the chat was created.

def send_text_to_chat(chat_guid: str, body: str) -> None:
    script = f'''
    tell application "Messages"
        set targetChat to chat id "{_escape(chat_guid)}"
        send "{_escape(body)}" to targetChat
    end tell
    '''
    _run_osascript(script)
    log.info("sent text -> chat=%s len=%d", chat_guid, len(body))


def send_file_to_chat(chat_guid: str, path: Path) -> None:
    script = f'''
    tell application "Messages"
        set targetChat to chat id "{_escape(chat_guid)}"
        send (POSIX file "{_escape(str(path))}") to targetChat
    end tell
    '''
    _run_osascript(script)
    log.info("sent file -> chat=%s path=%s", chat_guid, path)


# ------- chat.db confirmation -------
#
# Apple's `osascript … send` returns success the moment Messages.app accepts
# the command — that's many seconds before iMessage reports delivery or
# failure. To surface real outcomes we poll chat.db for the outgoing row
# Messages.app just wrote, then watch its is_sent / is_delivered / error
# fields update.

_confirm_src: sqlite3.Connection | None = None
_confirm_lock = threading.Lock()


def _confirm_snapshot() -> sqlite3.Connection:
    """Backup-snapshot of chat.db — same pattern as chat_db.ChatDBReader.

    A separate persistent source is kept here so confirmations don't contend
    with the bridge/web long-lived readers. (Each process opens its own; the
    module-global is per-process.)
    """
    global _confirm_src
    with _confirm_lock:
        if _confirm_src is None:
            _confirm_src = sqlite3.connect(
                f"file:{CHAT_DB}?mode=ro", uri=True, check_same_thread=False,
            )
        mem = sqlite3.connect(":memory:")
        mem.row_factory = sqlite3.Row
        _confirm_src.backup(mem)
        return mem


def _max_rowid() -> int:
    conn = _confirm_snapshot()
    try:
        return int(conn.execute(
            "SELECT COALESCE(MAX(ROWID), 0) FROM message"
        ).fetchone()[0])
    finally:
        conn.close()


def _find_outgoing(handle: str, after_rowid: int) -> sqlite3.Row | None:
    """First is_from_me row to `handle` with ROWID > after_rowid, if any."""
    conn = _confirm_snapshot()
    try:
        return conn.execute(
            """
            SELECT m.ROWID AS rowid, h.service AS service,
                   m.is_sent AS is_sent,
                   m.is_delivered AS is_delivered,
                   m.error AS error
            FROM message m LEFT JOIN handle h ON m.handle_id = h.ROWID
            WHERE m.is_from_me = 1
              AND LOWER(h.id) = ?
              AND m.ROWID > ?
            ORDER BY m.ROWID ASC LIMIT 1
            """,
            (handle.lower(), after_rowid),
        ).fetchone()
    finally:
        conn.close()


def _find_outgoing_in_chat(chat_guid: str, after_rowid: int) -> sqlite3.Row | None:
    """First is_from_me row in chat `chat_guid` with ROWID > after_rowid.

    Outgoing group messages have handle_id=NULL (the sender is us, not a peer),
    so the 1:1 matcher can't find them. Join chat_message_join instead. The
    service is derived from the chat's GUID prefix ("iMessage" / "SMS").
    """
    conn = _confirm_snapshot()
    try:
        return conn.execute(
            """
            SELECT m.ROWID AS rowid,
                   c.service_name AS service,
                   m.is_sent AS is_sent,
                   m.is_delivered AS is_delivered,
                   m.error AS error
            FROM message m
            JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
            JOIN chat c ON c.ROWID = cmj.chat_id
            WHERE m.is_from_me = 1
              AND c.guid = ?
              AND m.ROWID > ?
            ORDER BY m.ROWID ASC LIMIT 1
            """,
            (chat_guid, after_rowid),
        ).fetchone()
    finally:
        conn.close()


def _read_row(rowid: int) -> sqlite3.Row | None:
    conn = _confirm_snapshot()
    try:
        return conn.execute(
            """
            SELECT m.ROWID AS rowid, h.service AS service,
                   m.is_sent AS is_sent,
                   m.is_delivered AS is_delivered,
                   m.error AS error
            FROM message m LEFT JOIN handle h ON m.handle_id = h.ROWID
            WHERE m.ROWID = ?
            """,
            (rowid,),
        ).fetchone()
    finally:
        conn.close()


def _confirm(handle: str, after_rowid: int, timeout_s: float) -> SendResult:
    """Poll chat.db for up to timeout_s, reporting the richest state we see."""
    return _confirm_with(
        lambda: _find_outgoing(handle, after_rowid),
        timeout_s,
    )


def _confirm_in_chat(chat_guid: str, after_rowid: int, timeout_s: float) -> SendResult:
    """Same as _confirm but matches the outgoing row by chat GUID. Used for
    group sends where handle_id is NULL on the outgoing row."""
    return _confirm_with(
        lambda: _find_outgoing_in_chat(chat_guid, after_rowid),
        timeout_s,
    )


def _confirm_with(finder, timeout_s: float) -> SendResult:
    deadline = time.monotonic() + timeout_s
    r = SendResult(osascript_ok=True)

    # Phase 1: find the outgoing row Messages.app wrote for this send.
    while time.monotonic() < deadline and r.rowid is None:
        row = finder()
        if row is not None:
            r.rowid = int(row["rowid"])
            r.service = row["service"]
            r.is_sent = bool(row["is_sent"])
            r.is_delivered = bool(row["is_delivered"])
            r.error = int(row["error"] or 0)
            break
        time.sleep(0.3)

    # Phase 2: watch the row until delivered / errored / timed out.
    while r.rowid is not None and time.monotonic() < deadline:
        if r.failed or r.delivered:
            break
        time.sleep(0.5)
        row = _read_row(r.rowid)
        if row is None:
            break
        r.service = row["service"] or r.service
        r.is_sent = bool(row["is_sent"])
        r.is_delivered = bool(row["is_delivered"])
        r.error = int(row["error"] or 0)

    return r


def _should_fallback_to_sms(r: SendResult) -> bool:
    """Auto-retry via SMS only when the iMessage identity is permanently dead.

    Error 22 ("not registered on iMessage") is the one code where iMessage
    will never succeed for this recipient — safe to SMS now without risk of
    Apple later succeeding via iMessage and double-delivering. Other errors
    (3 network, 100 delivery-failed, 102 server-rejected) can be transient,
    so we don't auto-fallback on those.
    """
    return (
        r.osascript_ok
        and r.rowid is not None
        and r.service == "iMessage"
        and r.error == 22
    )


def _send_with_fallback(
    handle: str,
    send_fn,
    payload,
    timeout_s: float,
    kind: str,
) -> SendResult:
    """Run send_fn once as iMessage; on identity error (22) retry via SMS.

    send_fn must accept (handle, payload, service=<str>). Returned SendResult
    describes the SMS attempt when fallback triggered; fell_back_to_sms and
    original_error carry the iMessage error that justified the retry.
    """
    before = _max_rowid()
    try:
        send_fn(handle, payload)
    except Exception:
        log.exception("osascript %s failed", kind)
        return SendResult(osascript_ok=False)
    r = _confirm(handle, before, timeout_s)
    if not _should_fallback_to_sms(r):
        return r

    original_err = r.error
    log.info("iMessage err=%d for %s; retrying via SMS", original_err, handle)
    before2 = _max_rowid()
    try:
        send_fn(handle, payload, service="SMS")
    except Exception:
        log.exception("osascript %s SMS fallback failed", kind)
        r.fell_back_to_sms = True
        r.original_error = original_err
        r.osascript_ok = False
        return r
    r2 = _confirm(handle, before2, timeout_s)
    r2.fell_back_to_sms = True
    r2.original_error = original_err
    return r2


def send_text_confirm(handle: str, body: str, timeout_s: float = 8.0) -> SendResult:
    """send_text + poll chat.db for delivery. Always returns a SendResult.

    On iMessage error 22 (not registered) auto-retries via SMS and returns
    the SMS result with fell_back_to_sms=True.
    """
    return _send_with_fallback(handle, send_text, body, timeout_s, "send_text")


def send_file_confirm(handle: str, path: Path, timeout_s: float = 8.0) -> SendResult:
    return _send_with_fallback(handle, send_file, path, timeout_s, "send_file")


def _send_to_chat_confirm(
    chat_guid: str, send_fn, payload, timeout_s: float, kind: str
) -> SendResult:
    """Send to a group chat and report the outcome.

    No SMS fallback: the chat's service is fixed by its GUID and Messages.app
    handles retries within the chat itself. err=22 on a group iMessage is rare
    and wouldn't be fixable by switching to SMS without the user explicitly
    choosing to switch chat threads.
    """
    before = _max_rowid()
    try:
        send_fn(chat_guid, payload)
    except Exception:
        log.exception("osascript %s to chat failed", kind)
        return SendResult(osascript_ok=False)
    return _confirm_in_chat(chat_guid, before, timeout_s)


def send_text_to_chat_confirm(
    chat_guid: str, body: str, timeout_s: float = 8.0
) -> SendResult:
    return _send_to_chat_confirm(chat_guid, send_text_to_chat, body, timeout_s, "send_text")


def send_file_to_chat_confirm(
    chat_guid: str, path: Path, timeout_s: float = 8.0
) -> SendResult:
    return _send_to_chat_confirm(chat_guid, send_file_to_chat, path, timeout_s, "send_file")
