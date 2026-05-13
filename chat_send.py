"""Send iMessages via AppleScript -> Messages.app.

Requires Automation permission for the running binary to control Messages.

Anti-spam guards (check_send_guard)
-------------------------------------
All outbound sends should call ``check_send_guard(recipient, body, source)``
before reaching the AppleScript layer.  The guard enforces:

1. **Global rate limit** — 20 messages / 60 s (token bucket).  Raises
   ``RateLimitError`` when exhausted.
2. **Broadcast detection** — maintains ``{hash → set(recipients)}`` with a
   1-hour rolling window.  At 3 unique recipients logs a warning.  At
   5 trips the global escalating fuse (5 min → 30 min → 2 h → 24 h → 24 h →
   permanent).  Fuse state is persisted to ``~/.chatwire/fuse_state.json``
   so restarts don't reset escalation.  On step 4+ a machine-bound unlock
   code is written to ``~/.chatwire/lockout.json``.
   Raises ``BroadcastBlockedError`` when the fuse is active.
3. **Audit log** — appends one TSV line per send to
   ``~/.chatwire/send_audit.log`` (timestamp, recipient, source, hash).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from chat_db import CHAT_DB
from web import log_stream as _ls

log = logging.getLogger("chat_send")

# ---------------------------------------------------------------------------
# Anti-spam constants
# ---------------------------------------------------------------------------

_RATE_LIMIT_COUNT = 20       # max messages per window
_RATE_LIMIT_WINDOW_S = 60.0  # window duration in seconds

_BROADCAST_WARN_AT = 3       # unique recipients → log warning
_BROADCAST_BLOCK_AT = 5      # unique recipients → trip global fuse
_BROADCAST_WINDOW_S = 3600   # rolling window (1 hour)

# Fuse cooldown steps in seconds (index 0 = step 1 … index 4 = step 5).
# Step 6 (index 5) is permanent (None).
_FUSE_STEPS_S: list[float | None] = [
    5 * 60,      # Step 1: 5 minutes
    30 * 60,     # Step 2: 30 minutes
    2 * 3600,    # Step 3: 2 hours
    24 * 3600,   # Step 4: 24 hours
    24 * 3600,   # Step 5: 24 hours
    None,        # Step 6: permanent
]

_FUSE_FILE  = Path.home() / ".chatwire" / "fuse_state.json"
_LOCKOUT_FILE = Path.home() / ".chatwire" / "lockout.json"
_AUDIT_LOG  = Path.home() / ".chatwire" / "send_audit.log"


# ---------------------------------------------------------------------------
# Anti-spam exceptions
# ---------------------------------------------------------------------------

class RateLimitError(Exception):
    """Raised when the global send rate limit (20/min) is exhausted."""


class BroadcastBlockedError(Exception):
    """Raised when the anti-spam fuse is currently active.

    Attributes:
        retry_after: seconds until the fuse expires, or None if permanent.
        step:        current fuse step (1-6).
    """

    def __init__(
        self, msg: str, retry_after: float | None = None, step: int = 0
    ) -> None:
        super().__init__(msg)
        self.retry_after = retry_after
        self.step = step


# ---------------------------------------------------------------------------
# Trigger-notify hook registry
# ---------------------------------------------------------------------------

# bridge.py registers a callback here after building integrations.
# Called (from a thread) whenever the fuse fires to notify all notify-tier
# plugins.  Callbacks must be synchronous and short; they schedule async
# work via the event loop.
_trigger_notify_hooks: list = []


def register_trigger_notify_hook(fn: object) -> None:
    """Register a sync callable to be invoked when the anti-spam fuse trips."""
    _trigger_notify_hooks.append(fn)


def _call_trigger_notify_hooks() -> None:
    """Invoke all registered trigger-notify hooks.  Never raises."""
    for hook in _trigger_notify_hooks:
        try:
            hook()  # type: ignore[operator]
        except Exception:
            log.exception("trigger notify hook failed")


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
# Global fuse state  (persisted to disk as wall-clock timestamps)
# ---------------------------------------------------------------------------

class _FuseState:
    """Global escalating fuse — single shared lock for all broadcast blocks.

    State file: ``~/.chatwire/fuse_state.json``::

        {"step": 0, "cooldown_until": null, "last_trigger": null}

    - ``step`` 0 = inactive; 1-5 = timed out; 6 = permanent.
    - ``cooldown_until`` is a UNIX wall-clock timestamp (null when inactive).
    - ``last_trigger`` tracks when the fuse was last tripped; if a second
      trigger happens within 1 hour the step counter is incremented by 2
      instead of 1 (rapid-re-offender fast-escalation).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._step: int = 0
        self._cooldown_until: float | None = None
        self._last_trigger: float | None = None
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(_FUSE_FILE.read_text())
            self._step = int(raw.get("step", 0))
            cu = raw.get("cooldown_until")
            self._cooldown_until = float(cu) if cu is not None else None
            lt = raw.get("last_trigger")
            self._last_trigger = float(lt) if lt is not None else None
        except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError):
            pass

    def _save(self) -> None:
        """Persist to disk; caller must hold self._lock."""
        try:
            _FUSE_FILE.parent.mkdir(parents=True, exist_ok=True)
            state = {
                "step": self._step,
                "cooldown_until": self._cooldown_until,
                "last_trigger": self._last_trigger,
            }
            tmp = _FUSE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(state, indent=2))
            tmp.replace(_FUSE_FILE)
        except Exception:
            log.exception("failed to save fuse_state.json")

    def check(self) -> None:
        """Raise BroadcastBlockedError if the fuse is currently active."""
        with self._lock:
            if self._step == 0:
                return
            if self._step >= 6:
                raise BroadcastBlockedError(
                    "Outbound sending is permanently locked. "
                    "Request an unlock code at chatwireapp@gmail.com.",
                    None,
                    step=self._step,
                )
            if self._cooldown_until is not None:
                remaining = self._cooldown_until - time.time()
                if remaining > 0:
                    raise BroadcastBlockedError(
                        f"Sends paused for {remaining / 60:.0f} min "
                        "— chatwire detected a broadcast pattern.",
                        remaining,
                        step=self._step,
                    )

    def trigger(self) -> float | None:
        """Trip the fuse; return cooldown seconds, or None if permanent.

        If the last trigger was within 1 hour, the step increments by 2
        (skip-a-step fast-escalation for rapid re-offenders).
        """
        with self._lock:
            now = time.time()
            rapid = (
                self._last_trigger is not None
                and now - self._last_trigger < 3600
            )
            increment = 2 if rapid else 1
            self._step = min(self._step + increment, 6)
            self._last_trigger = now

            step_s = _FUSE_STEPS_S[self._step - 1]
            if step_s is None:
                self._cooldown_until = None
            else:
                self._cooldown_until = now + step_s

            self._save()

            # Generate and persist unlock code on step 4+
            if self._step >= 4:
                _write_lockout(self._step)

            return step_s

    def status(self) -> dict:
        """Return a dict suitable for the /api/ui/fuse-status endpoint."""
        with self._lock:
            if self._step == 0:
                return {
                    "locked": False,
                    "step": 0,
                    "cooldown_remaining_s": None,
                    "unlock_code": None,
                }
            if self._step >= 6:
                return {
                    "locked": True,
                    "step": self._step,
                    "cooldown_remaining_s": None,
                    "unlock_code": _read_unlock_code(),
                }
            remaining: float | None = None
            locked = False
            if self._cooldown_until is not None:
                r = self._cooldown_until - time.time()
                if r > 0:
                    remaining = r
                    locked = True
            unlock_code = _read_unlock_code() if self._step >= 4 else None
            return {
                "locked": locked,
                "step": self._step,
                "cooldown_remaining_s": remaining,
                "unlock_code": unlock_code,
            }

    # --- for tests ---
    def _reset(self) -> None:
        with self._lock:
            self._step = 0
            self._cooldown_until = None
            self._last_trigger = None
            try:
                _FUSE_FILE.unlink(missing_ok=True)
                _LOCKOUT_FILE.unlink(missing_ok=True)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

_rate_bucket = _TokenBucket()
_broadcast   = _BroadcastTracker()
_fuse        = _FuseState()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_text(text: str) -> str:
    """Normalise text for broadcast-detection hashing.

    Steps: lowercase → strip punctuation → collapse whitespace.
    """
    t = text.lower()
    t = re.sub(r"[^\w\s]", "", t)
    return " ".join(t.split())


def _get_machine_id() -> str:
    """Return a machine-specific identifier for unlock-code binding.

    On macOS: reads IOPlatformUUID from ioreg.
    Fallback: SHA-256 of hostname + username.
    """
    try:
        result = subprocess.run(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            if "IOPlatformUUID" in line:
                m = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', line)
                if m:
                    return m.group(1)
    except Exception:
        pass
    import socket
    import os as _os
    return hashlib.sha256(
        f"{socket.gethostname()}{_os.getenv('USER', '')}".encode()
    ).hexdigest()


def _get_first_run_ts() -> str:
    """Return a persistent first-run timestamp string, creating it if needed."""
    try:
        from config import load_config as _load, save_config as _save
        cfg = _load()
        ts = cfg.get("_first_run_ts")
        if ts:
            return str(ts)
        ts = str(time.time())
        cfg["_first_run_ts"] = ts
        _save(cfg)
        return ts
    except Exception:
        return "0"


def _generate_unlock_code() -> str:
    """Generate a machine-bound unlock code: ``CW-XXXX-YYYY``.

    XXXX = first 4 hex chars of SHA-256(machine_id + first_run_ts).
    YYYY = 4 random hex chars unique per lockout event.
    """
    machine_id = _get_machine_id()
    first_run_ts = _get_first_run_ts()
    xxxx = hashlib.sha256(
        f"{machine_id}{first_run_ts}".encode()
    ).hexdigest()[:4].upper()
    yyyy = secrets.token_hex(2).upper()
    return f"CW-{xxxx}-{yyyy}"


def _write_lockout(step: int) -> None:
    """Persist lockout.json with unlock code (preserved across re-triggers)."""
    try:
        _LOCKOUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        existing: dict = {}
        try:
            existing = json.loads(_LOCKOUT_FILE.read_text())
        except Exception:
            pass
        if not existing.get("unlock_code"):
            existing["unlock_code"] = _generate_unlock_code()
        existing["step"] = step
        existing["locked_at"] = time.time()
        tmp = _LOCKOUT_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(existing, indent=2))
        tmp.replace(_LOCKOUT_FILE)
    except Exception:
        log.exception("failed to write lockout.json")


def _read_unlock_code() -> str | None:
    """Read the unlock code from lockout.json, or None if absent."""
    try:
        return json.loads(_LOCKOUT_FILE.read_text()).get("unlock_code")
    except Exception:
        return None


def _get_unlock_secret() -> str:
    """Return (or generate) the HMAC secret for unlock-code verification.

    Stored in ``~/.chatwire/config.json`` as ``unlock_secret`` (32-byte hex).
    Generated on first call and persisted immediately.
    """
    try:
        from config import load_config as _load, save_config as _save  # noqa: PLC0415
        cfg = _load()
        secret = cfg.get("unlock_secret")
        if secret:
            return str(secret)
        secret = secrets.token_hex(32)
        cfg["unlock_secret"] = secret
        _save(cfg)
        return secret
    except Exception:
        # Fallback: derive from machine ID so restarts stay consistent.
        return hashlib.sha256(_get_machine_id().encode()).hexdigest()


def _compute_unlock_response(cw_code: str, secret: str) -> str:
    """Compute the admin-issued unlock code for a given CW machine code.

    Algorithm: HMAC-SHA256(cw_code, secret) → first 8 hex chars → UL-XXXX-XXXX.
    The Apps Script in docs/admin/unlock-apps-script.js uses the same formula.
    """
    digest = hmac.new(
        secret.encode(), cw_code.encode(), hashlib.sha256
    ).hexdigest()
    return f"UL-{digest[:4].upper()}-{digest[4:8].upper()}"


def validate_and_reset_fuse(unlock_code: str) -> bool:
    """Validate an admin-issued unlock code and reset the fuse if correct.

    Returns True on success (fuse reset to step 0), False on failure.
    """
    cw_code = _read_unlock_code()
    if not cw_code:
        return False
    secret = _get_unlock_secret()
    expected = _compute_unlock_response(cw_code, secret)
    if not hmac.compare_digest(unlock_code.strip().upper(), expected.upper()):
        return False
    _fuse._reset()
    return True


def _msg_hash(normalized: str) -> str:
    return hashlib.sha256(normalized.encode()).hexdigest()




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
        RateLimitError:        Global rate limit exhausted.
        BroadcastBlockedError: Global fuse is active (broadcast detected).
    """
    # 1. Global fuse check — blocks ALL sends when active
    _fuse.check()

    # 2. Global rate limit
    if not _rate_bucket.consume():
        _ls.warn("anti_spam", "rate limit exceeded — send blocked (20 messages/minute)")
        raise RateLimitError(
            "Send rate limit exceeded (20 messages / minute). Try again shortly."
        )

    # 3. Broadcast detection (text-only; file sends pass an empty body)
    normalized = _normalize_text(body)
    h = _msg_hash(normalized)

    if body.strip():  # skip broadcast tracking for empty/file sends
        unique_count = _broadcast.record(h, recipient)

        if unique_count == _BROADCAST_WARN_AT:
            log.warning("broadcast warning: same message to %d recipients hash=%s",
                        unique_count, h[:8])
            _ls.warn("anti_spam", f"broadcast warning — same message to {unique_count} recipients")

        if unique_count >= _BROADCAST_BLOCK_AT:
            cooldown_s = _fuse.trigger()
            current_step = _fuse._step
            if cooldown_s is None:
                detail = "permanently locked — request an unlock code"
            else:
                detail = f"blocked for {cooldown_s / 60:.0f} min"
            log.warning("broadcast block: hash=%s unique=%d step=%d action=%s",
                        h[:8], unique_count, current_step, detail)
            _ls.error("anti_spam", f"broadcast blocked — {unique_count} recipients, step {current_step}: {detail}")
            _call_trigger_notify_hooks()
            raise BroadcastBlockedError(
                f"Broadcast detected ({unique_count} recipients). Sending {detail}.",
                cooldown_s,
                step=current_step,
            )

    # 4. Audit log
    _write_audit(recipient, source, h)
    return h


def _get_unlock_form_url() -> str | None:
    """Return the Google Form URL for unlock requests, or None if not configured.

    Reads (in priority order):
      1. CHATWIRE_UNLOCK_FORM_URL environment variable
      2. unlock_form_url key in ~/.chatwire/config.json
    """
    env_url = os.environ.get("CHATWIRE_UNLOCK_FORM_URL", "").strip()
    if env_url:
        return env_url
    try:
        from config import load_config as _load  # noqa: PLC0415
        cfg = _load()
        url = cfg.get("unlock_form_url", "")
        return str(url).strip() if url else None
    except Exception:
        return None


def get_fuse_status() -> dict:
    """Return the current fuse status dict for the /api/ui/fuse-status endpoint.

    Includes ``unlock_form_url`` so the frontend can link to the request form
    without hard-coding it.
    """
    status = _fuse.status()
    status["unlock_form_url"] = _get_unlock_form_url()
    return status


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
