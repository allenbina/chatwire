"""Optional cookie-session auth for the chatwire web UI.

Disabled by default — when no `web.auth` block is in config, every request
is allowed through (matching the historic "you can reach the box, you can
read messages" posture noted in `web/main.py`'s module docstring).

When enabled, requests outside a small public-paths whitelist (login,
logout, healthz, version, /static, favicons) need a valid signed session
cookie or they get redirected (HTML) or 401'd (htmx fragment, identified
by `HX-Request: true`).

Storage shape under `web.auth`:
  password_hash:    pbkdf2_sha256$rounds$salt_b64$hash_b64
  session_secret:   urlsafe_b64(32 random bytes)

Cookie format: `{issued_at}.{hex_sig}` where
  hex_sig = HMAC-SHA256(session_secret, str(issued_at)).
Sessions live `SESSION_TTL_S` and rotate when `session_secret` rotates.

Lockout escape hatch: stop the web agent, edit `~/.chatwire/config.json`
(already chmod 600), drop the `web.auth` block, restart. Auth is disabled
by absence — no separate "off" flag needed.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from collections import deque
from typing import Optional

PBKDF2_ROUNDS = 200_000
SESSION_TTL_S = 30 * 86_400
CSRF_TTL_S = 3600  # 1 hour — long enough to fill any form, short enough to limit replay
# Reissue the cookie when an authed request arrives with one older than this.
# Half of TTL gives an active user a rolling 30-day session while a user
# who's been idle for ~15 days still has to re-auth at SESSION_TTL_S.
SESSION_REFRESH_S = SESSION_TTL_S // 2
COOKIE_NAME = "chatwire_session"

# Failed-login throttle: lock a key out after this many fails inside the
# trailing window. Tuned for "annoy a human typo, frustrate a script" —
# a script grinding PBKDF2 at 200k rounds is already CPU-bound, this just
# caps the parallelism it can buy from a single source.
LOGIN_MAX_ATTEMPTS = 10
LOGIN_WINDOW_S = 15 * 60

# Anything matching these patterns bypasses the auth check. /login itself
# must be public (otherwise you can't ever log in); /healthz/version are
# probes the bridge process and update-check use; /static and the favicons
# are fetched before any login UI renders.
_PUBLIC_PATHS = frozenset({
    "/login", "/logout", "/healthz", "/version",
    "/favicon.ico", "/favicon.svg",
})
_PUBLIC_PREFIXES = ("/static/",)


def is_public_path(path: str) -> bool:
    if path in _PUBLIC_PATHS:
        return True
    return any(path.startswith(p) for p in _PUBLIC_PREFIXES)


# ---------- password hashing ----------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS,
    )
    return "pbkdf2_sha256${rounds}${salt}${hash}".format(
        rounds=PBKDF2_ROUNDS,
        salt=_b64e(salt),
        hash=_b64e(digest),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds_s, salt_b64, hash_b64 = stored.split("$", 3)
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    try:
        rounds = int(rounds_s)
        salt = _b64d(salt_b64)
        expected = _b64d(hash_b64)
    except (ValueError, _Base64Error):
        return False
    actual = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, rounds,
    )
    return hmac.compare_digest(actual, expected)


# ---------- session cookies ----------

def new_session_secret() -> str:
    return _b64e(secrets.token_bytes(32))


def issue_cookie(session_secret: str, *, now: Optional[int] = None) -> str:
    issued_at = int(time.time()) if now is None else int(now)
    sig = _sign(session_secret, str(issued_at))
    return f"{issued_at}.{sig}"


def verify_cookie(
    cookie: Optional[str], session_secret: str, *, now: Optional[int] = None,
) -> bool:
    return cookie_age(cookie, session_secret, now=now) is not None


def cookie_age(
    cookie: Optional[str], session_secret: str, *, now: Optional[int] = None,
) -> Optional[int]:
    """Seconds since this cookie was issued, or None if invalid/expired.

    Returning the age (rather than just bool) lets the middleware decide
    whether the cookie is old enough to warrant a sliding refresh, without
    re-parsing the value.
    """
    if not cookie or "." not in cookie:
        return None
    ts_s, sig = cookie.split(".", 1)
    if not ts_s.isdigit():
        return None
    expected = _sign(session_secret, ts_s)
    if not hmac.compare_digest(expected, sig):
        return None
    issued_at = int(ts_s)
    cur = int(time.time()) if now is None else int(now)
    if issued_at < cur - SESSION_TTL_S:
        return None
    # Generous clock-skew window: a cookie issued slightly in the future
    # (NTP nudge between issuer and verifier) is fine; a cookie far in the
    # future is bogus.
    if issued_at > cur + 60:
        return None
    return max(0, cur - issued_at)


# ---------- CSRF tokens ----------

def new_csrf_token(csrf_secret: str, *, now: Optional[int] = None) -> str:
    """Return a signed, time-limited CSRF token.

    Format: ``{timestamp}.{nonce}.{hmac}``

    ``csrf_secret`` should be an app-level secret generated at startup
    (separate from the per-user ``session_secret``).  Rotating on restart
    is intentional: in-flight forms older than a server restart become
    invalid, which is acceptable for a single-user home-server install.
    """
    ts = int(time.time()) if now is None else int(now)
    nonce = secrets.token_hex(8)
    payload = f"{ts}.{nonce}"
    sig = _sign(csrf_secret, payload)
    return f"{payload}.{sig}"


def verify_csrf_token(
    token: Optional[str],
    csrf_secret: str,
    *,
    now: Optional[int] = None,
) -> bool:
    """Return True iff ``token`` is structurally valid, correctly signed,
    and not expired (within ``CSRF_TTL_S`` seconds of issue)."""
    if not token:
        return False
    parts = token.split(".", 2)
    if len(parts) != 3:
        return False
    ts_s, nonce, sig = parts
    if not ts_s.isdigit():
        return False
    payload = f"{ts_s}.{nonce}"
    expected = _sign(csrf_secret, payload)
    if not hmac.compare_digest(expected, sig):
        return False
    ts = int(ts_s)
    cur = int(time.time()) if now is None else int(now)
    # Allow a small forward skew (NTP jitter); reject expired tokens.
    return cur - CSRF_TTL_S <= ts <= cur + 60


# ---------- config helpers ----------

def auth_block(cfg: dict) -> Optional[dict]:
    """Return the configured `web.auth` block iff fully populated.

    A half-populated block (one of the two fields missing) reads as
    "auth not configured" — same as a missing block. This protects
    against a partial write leaving the UI in an unrecoverable state.
    """
    auth = (cfg.get("web") or {}).get("auth") or {}
    pw = auth.get("password_hash")
    secret = auth.get("session_secret")
    if pw and secret:
        return {"password_hash": pw, "session_secret": secret}
    return None


def has_password(cfg: dict) -> bool:
    return auth_block(cfg) is not None


# ---------- login rate limiter ----------

class LoginRateLimiter:
    """Per-key sliding-window failure throttle.

    `key` is whatever string the caller wants to bucket on — typically the
    client IP. After `max_attempts` failures inside the trailing
    `window_s` from one key, that key is locked until the oldest failure
    in the window ages out. Successful login clears the bucket.

    This is in-memory only (resets on web-agent restart). For a
    single-process home install that's the right tradeoff: a persistent
    store would mean an attacker can lock the legitimate owner out of
    their own box just by hammering before they wake up. Restart-clears
    means the owner's recovery hatch (stop the agent, edit config) also
    clears any stuck lockout.

    Behind a reverse proxy `request.client.host` is the proxy IP, so all
    sources share one bucket. That's still useful — it caps the
    aggregate guess rate from any single transit — but a single attacker
    can lock out the owner. The README's deployment posture (LAN /
    Tailscale / CF Access) keeps that risk narrow; the lockout window is
    short enough (15 min) to be tolerable if it bites.
    """

    def __init__(
        self,
        max_attempts: int = LOGIN_MAX_ATTEMPTS,
        window_s: int = LOGIN_WINDOW_S,
    ):
        self.max_attempts = max_attempts
        self.window_s = window_s
        self._fails: dict[str, deque[float]] = {}

    def locked_for(self, key: str, *, now: Optional[float] = None) -> int:
        """Seconds until `key` may attempt again; 0 if not currently locked."""
        attempts = self._fails.get(key)
        if not attempts:
            return 0
        cur = time.time() if now is None else now
        while attempts and cur - attempts[0] > self.window_s:
            attempts.popleft()
        if not attempts:
            self._fails.pop(key, None)
            return 0
        if len(attempts) < self.max_attempts:
            return 0
        return int(self.window_s - (cur - attempts[0])) + 1

    def record_fail(self, key: str, *, now: Optional[float] = None) -> None:
        cur = time.time() if now is None else now
        attempts = self._fails.setdefault(key, deque())
        attempts.append(cur)
        # Cap deque so an attacker hammering during a lockout can't grow
        # memory; we only ever care about the most recent max_attempts.
        while len(attempts) > self.max_attempts:
            attempts.popleft()

    def record_success(self, key: str) -> None:
        self._fails.pop(key, None)


# ---------- internals ----------

class _Base64Error(Exception):
    pass


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    try:
        return base64.urlsafe_b64decode(s + pad)
    except Exception as e:  # pragma: no cover — surface as a typed error
        raise _Base64Error(str(e))


def _sign(session_secret: str, payload: str) -> str:
    return hmac.new(
        session_secret.encode("utf-8"),
        payload.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
