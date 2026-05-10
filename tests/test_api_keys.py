"""Tests for web/api_keys.py — key lifecycle, hashing, scope routing."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from web.api_keys import (
    ALL_SCOPES,
    APIKey,
    authenticate_bearer,
    check_scope,
    generate_key,
    hash_key,
    load_keys,
    save_keys,
    scope_for_request,
    verify_key,
)


# ---------------------------------------------------------------------------
# generate_key
# ---------------------------------------------------------------------------

class TestGenerateKey:
    def test_starts_with_cwk_(self):
        k = generate_key()
        assert k.startswith("cwk_")

    def test_length_is_68(self):
        # cwk_ (4) + 64 hex chars = 68
        k = generate_key()
        assert len(k) == 68, f"Expected 68, got {len(k)}: {k!r}"

    def test_hex_part_is_valid(self):
        k = generate_key()
        hex_part = k[4:]
        assert all(c in "0123456789abcdef" for c in hex_part)

    def test_uniqueness(self):
        keys = {generate_key() for _ in range(20)}
        assert len(keys) == 20


# ---------------------------------------------------------------------------
# hash_key / verify_key
# ---------------------------------------------------------------------------

class TestHashVerify:
    def test_verify_correct_key(self):
        k = generate_key()
        h = hash_key(k)
        assert verify_key(k, h) is True

    def test_reject_wrong_key(self):
        k = generate_key()
        h = hash_key(k)
        assert verify_key("cwk_" + "0" * 64, h) is False

    def test_hash_format(self):
        k = generate_key()
        h = hash_key(k)
        parts = h.split("$")
        assert len(parts) == 4
        assert parts[0] == "pbkdf2_sha256"
        assert parts[1] == "200000"

    def test_different_hashes_for_same_key(self):
        # Each call generates a fresh salt → different stored hash.
        k = generate_key()
        h1 = hash_key(k)
        h2 = hash_key(k)
        assert h1 != h2
        # Both should verify correctly.
        assert verify_key(k, h1)
        assert verify_key(k, h2)

    def test_reject_malformed_hash(self):
        k = generate_key()
        assert verify_key(k, "not-a-hash") is False
        assert verify_key(k, "") is False
        assert verify_key(k, "x$y$z") is False

    def test_reject_non_cwk_key(self):
        h = hash_key(generate_key())
        assert verify_key("plaintext", h) is False


# ---------------------------------------------------------------------------
# load_keys / save_keys
# ---------------------------------------------------------------------------

class TestLoadSave:
    def test_load_missing_file_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr("web.api_keys.KEYS_FILE", tmp_path / "api_keys.json")
        assert load_keys() == []

    def test_round_trip(self, tmp_path, monkeypatch):
        monkeypatch.setattr("web.api_keys.KEYS_FILE", tmp_path / "api_keys.json")
        k = generate_key()
        entry = APIKey(
            name="test",
            key_hash=hash_key(k),
            scopes=["read_conversations"],
            created_at="2026-01-01T00:00:00Z",
            prefix=k[4:12],
        )
        save_keys([entry])
        loaded = load_keys()
        assert len(loaded) == 1
        assert loaded[0].name == "test"
        assert loaded[0].scopes == ["read_conversations"]
        assert loaded[0].prefix == k[4:12]

    def test_load_corrupt_returns_empty(self, tmp_path, monkeypatch):
        f = tmp_path / "api_keys.json"
        f.write_text("not valid json")
        monkeypatch.setattr("web.api_keys.KEYS_FILE", f)
        assert load_keys() == []

    def test_file_chmod_600(self, tmp_path, monkeypatch):
        f = tmp_path / "api_keys.json"
        monkeypatch.setattr("web.api_keys.KEYS_FILE", f)
        monkeypatch.setattr("web.api_keys._STATE_DIR", tmp_path)
        save_keys([])
        import stat
        mode = f.stat().st_mode & 0o777
        assert mode == 0o600, f"Expected 0o600, got 0o{mode:03o}"


# ---------------------------------------------------------------------------
# check_scope
# ---------------------------------------------------------------------------

class TestCheckScope:
    def _setup(self, tmp_path, monkeypatch, scopes):
        monkeypatch.setattr("web.api_keys.KEYS_FILE", tmp_path / "api_keys.json")
        k = generate_key()
        entry = APIKey(
            name="test",
            key_hash=hash_key(k),
            scopes=list(scopes),
            created_at="2026-01-01T00:00:00Z",
            prefix=k[4:12],
        )
        save_keys([entry])
        return k

    def test_valid_key_with_matching_scope(self, tmp_path, monkeypatch):
        k = self._setup(tmp_path, monkeypatch, ["send_messages"])
        assert check_scope(k, "send_messages") is True

    def test_valid_key_wrong_scope(self, tmp_path, monkeypatch):
        k = self._setup(tmp_path, monkeypatch, ["read_conversations"])
        assert check_scope(k, "send_messages") is False

    def test_unknown_key(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch, ["send_messages"])
        assert check_scope(generate_key(), "send_messages") is False

    def test_non_cwk_prefix_rejected_fast(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch, ["send_messages"])
        assert check_scope("plaintext", "send_messages") is False


# ---------------------------------------------------------------------------
# authenticate_bearer
# ---------------------------------------------------------------------------

class TestAuthenticateBearer:
    def test_valid_key_returns_entry(self, tmp_path, monkeypatch):
        monkeypatch.setattr("web.api_keys.KEYS_FILE", tmp_path / "api_keys.json")
        k = generate_key()
        entry = APIKey(
            name="home",
            key_hash=hash_key(k),
            scopes=["trigger_actions"],
            created_at="2026-01-01T00:00:00Z",
            prefix=k[4:12],
        )
        save_keys([entry])
        result = authenticate_bearer(k)
        assert result is not None
        assert result.name == "home"

    def test_invalid_key_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr("web.api_keys.KEYS_FILE", tmp_path / "api_keys.json")
        save_keys([])
        assert authenticate_bearer(generate_key()) is None

    def test_non_cwk_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr("web.api_keys.KEYS_FILE", tmp_path / "api_keys.json")
        assert authenticate_bearer("not-a-cwk-key") is None


# ---------------------------------------------------------------------------
# scope_for_request
# ---------------------------------------------------------------------------

class TestScopeForRequest:
    def test_post_actions(self):
        assert scope_for_request("POST", "/api/v1/actions/send") == "trigger_actions"

    def test_get_conversations(self):
        assert scope_for_request("GET", "/api/v1/conversations") == "read_conversations"

    def test_get_messages(self):
        assert scope_for_request("GET", "/api/v1/messages") == "read_conversations"

    def test_post_send_v1(self):
        assert scope_for_request("POST", "/api/v1/send") == "send_messages"

    def test_post_send_legacy(self):
        assert scope_for_request("POST", "/send") == "send_messages"

    def test_post_settings(self):
        assert scope_for_request("POST", "/api/ui/settings/theme") == "manage_settings"

    def test_get_settings_unguarded(self):
        # GET /api/ui/settings/* is read-only — not in the scope map.
        assert scope_for_request("GET", "/api/ui/settings/theme") is None

    def test_public_path_unguarded(self):
        assert scope_for_request("GET", "/healthz") is None
        assert scope_for_request("GET", "/static/app.js") is None

    def test_wrong_method_unguarded(self):
        # Only POST to /api/v1/actions is gated — GET is not.
        assert scope_for_request("GET", "/api/v1/actions/list") is None
