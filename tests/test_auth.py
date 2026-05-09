"""Tests for web/auth.py — CSRF token helpers.

All pure-function: no subprocess, no file I/O, no FastAPI app needed.
The cookie and password helpers were already exercised implicitly by the
integration paths; these tests focus on the new CSRF surface area.
"""
from __future__ import annotations

import pytest

from web.auth import (
    CSRF_TTL_S,
    new_csrf_token,
    verify_csrf_token,
)

SECRET = "test-secret-xyzzy-123"
OTHER = "different-secret"


# ---------------------------------------------------------------------------
# new_csrf_token — structure
# ---------------------------------------------------------------------------

class TestNewCsrfToken:
    def test_returns_string(self):
        tok = new_csrf_token(SECRET)
        assert isinstance(tok, str)

    def test_three_dot_separated_parts(self):
        tok = new_csrf_token(SECRET)
        parts = tok.split(".")
        assert len(parts) == 3, f"Expected 3 parts, got {parts!r}"

    def test_timestamp_is_integer(self):
        ts_s, _nonce, _sig = new_csrf_token(SECRET).split(".", 2)
        assert ts_s.isdigit()

    def test_timestamp_reflects_now(self):
        import time
        before = int(time.time())
        ts_s, _, _ = new_csrf_token(SECRET).split(".", 2)
        after = int(time.time())
        ts = int(ts_s)
        assert before <= ts <= after + 1

    def test_different_tokens_each_call(self):
        # Nonce ensures uniqueness even within the same second.
        t1 = new_csrf_token(SECRET)
        t2 = new_csrf_token(SECRET)
        assert t1 != t2

    def test_different_secrets_different_sigs(self):
        now = 1_700_000_000
        # Force same timestamp; nonces will differ so compare sig prefix is wrong.
        # Instead, verify cross-secret: a token signed with SECRET won't verify with OTHER.
        tok = new_csrf_token(SECRET, now=now)
        assert not verify_csrf_token(tok, OTHER, now=now)


# ---------------------------------------------------------------------------
# verify_csrf_token — valid cases
# ---------------------------------------------------------------------------

class TestVerifyCsrfTokenValid:
    def test_fresh_token_verifies(self):
        tok = new_csrf_token(SECRET)
        assert verify_csrf_token(tok, SECRET)

    def test_token_at_exact_issue_time(self):
        now = 1_700_000_000
        tok = new_csrf_token(SECRET, now=now)
        assert verify_csrf_token(tok, SECRET, now=now)

    def test_token_just_before_expiry(self):
        now = 1_700_000_000
        tok = new_csrf_token(SECRET, now=now)
        # One second before expiry — should still be valid.
        assert verify_csrf_token(tok, SECRET, now=now + CSRF_TTL_S - 1)

    def test_small_forward_skew_allowed(self):
        # Token timestamped 30 s in the future (NTP jitter) should still verify.
        now = 1_700_000_000
        tok = new_csrf_token(SECRET, now=now + 30)
        assert verify_csrf_token(tok, SECRET, now=now)


# ---------------------------------------------------------------------------
# verify_csrf_token — rejection cases
# ---------------------------------------------------------------------------

class TestVerifyCsrfTokenReject:
    def test_none_token(self):
        assert not verify_csrf_token(None, SECRET)

    def test_empty_string(self):
        assert not verify_csrf_token("", SECRET)

    def test_expired_token(self):
        now = 1_700_000_000
        tok = new_csrf_token(SECRET, now=now)
        assert not verify_csrf_token(tok, SECRET, now=now + CSRF_TTL_S + 1)

    def test_wrong_secret(self):
        tok = new_csrf_token(SECRET)
        assert not verify_csrf_token(tok, OTHER)

    def test_tampered_sig(self):
        ts_s, nonce, sig = new_csrf_token(SECRET).split(".", 2)
        bad = f"{ts_s}.{nonce}.{'x' * len(sig)}"
        assert not verify_csrf_token(bad, SECRET)

    def test_tampered_timestamp(self):
        ts_s, nonce, sig = new_csrf_token(SECRET).split(".", 2)
        new_ts = str(int(ts_s) - 9999)
        bad = f"{new_ts}.{nonce}.{sig}"
        assert not verify_csrf_token(bad, SECRET)

    def test_tampered_nonce(self):
        ts_s, nonce, sig = new_csrf_token(SECRET).split(".", 2)
        bad = f"{ts_s}.XXXXXXXXXXXXXXXX.{sig}"
        assert not verify_csrf_token(bad, SECRET)

    def test_too_far_future(self):
        # Token issued 120 s in the future — beyond the 60 s skew window.
        now = 1_700_000_000
        tok = new_csrf_token(SECRET, now=now + 120)
        assert not verify_csrf_token(tok, SECRET, now=now)

    def test_missing_parts(self):
        assert not verify_csrf_token("only.two", SECRET)

    def test_non_digit_timestamp(self):
        assert not verify_csrf_token("abc.nonce.sig", SECRET)

    def test_extra_dots(self):
        # Extra dots in the sig field — the split(".", 2) means the sig part
        # contains all remaining content. This shouldn't crash.
        tok = new_csrf_token(SECRET)
        bad = tok + ".extra"
        assert not verify_csrf_token(bad, SECRET)
