"""Scoped API key management for the chatwire web UI.

Key format:  cwk_ + 32 random hex chars (68 chars total).
Storage:     ~/.chatwire/api_keys.json  (chmod 600)
Hashing:     PBKDF2-SHA256, same format as auth.py password hashes.

Scopes
------
  trigger_actions     POST /api/v1/actions/*
  read_conversations  GET /api/v1/conversations, GET /api/v1/messages
  send_messages       POST /api/v1/send, POST /send
  manage_settings     POST /api/ui/settings/*

Each key carries an explicit list of scopes.  A request carrying a
``Authorization: Bearer cwk_...`` header is checked against this list in
the auth-gate middleware (web/main.py).  Cookie auth is unchanged.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

# Mirrors config.STATE_DIR to avoid a circular import.
_STATE_DIR = Path.home() / ".chatwire"
KEYS_FILE = _STATE_DIR / "api_keys.json"

PBKDF2_ROUNDS = 200_000

ALL_SCOPES: tuple[str, ...] = (
    "trigger_actions",
    "read_conversations",
    "send_messages",
    "manage_settings",
    "mcp",
)

# (method, path_prefix_or_exact, scope)
_ROUTE_SCOPES: list[tuple[str, str, str]] = [
    ("POST", "/api/v1/actions/",           "trigger_actions"),
    ("GET",  "/api/v1/conversations",      "read_conversations"),
    ("GET",  "/api/v1/messages",           "read_conversations"),
    ("POST", "/api/v1/send",               "send_messages"),
    ("POST", "/send",                      "send_messages"),
    ("POST", "/api/ui/settings/",          "manage_settings"),
    ("GET",  "/mcp/",                      "mcp"),
    ("POST", "/mcp/",                      "mcp"),
]


@dataclass
class APIKey:
    name: str
    key_hash: str
    scopes: list[str]
    created_at: str
    # First 8 hex chars after the cwk_ prefix — shown in the UI as a hint.
    prefix: str = ""

    def to_display(self) -> dict:
        """Return a safe dict for JSON responses (no hash)."""
        return {
            "name": self.name,
            "prefix": self.prefix,
            "scopes": self.scopes,
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# Key lifecycle
# ---------------------------------------------------------------------------

def generate_key() -> str:
    """Return a fresh plaintext cwk_ key. Hash before storing."""
    return "cwk_" + secrets.token_hex(32)


def hash_key(key: str) -> str:
    """PBKDF2-SHA256 hash in the same format as auth.py."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", key.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return "pbkdf2_sha256${rounds}${salt}${hash}".format(
        rounds=PBKDF2_ROUNDS,
        salt=_b64e(salt),
        hash=_b64e(digest),
    )


def verify_key(key: str, key_hash: str) -> bool:
    """Return True iff the plaintext key matches the stored PBKDF2 hash."""
    try:
        algo, rounds_s, salt_b64, hash_b64 = key_hash.split("$", 3)
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    try:
        rounds = int(rounds_s)
        salt = _b64d(salt_b64)
        expected = _b64d(hash_b64)
    except Exception:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", key.encode("utf-8"), salt, rounds)
    return hmac.compare_digest(actual, expected)


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def load_keys() -> list[APIKey]:
    """Load API keys from disk. Returns [] if the file is missing or corrupt."""
    if not KEYS_FILE.exists():
        return []
    try:
        raw = json.loads(KEYS_FILE.read_text("utf-8"))
        return [
            APIKey(
                name=entry["name"],
                key_hash=entry["key_hash"],
                scopes=list(entry.get("scopes", [])),
                created_at=entry.get("created_at", ""),
                prefix=entry.get("prefix", ""),
            )
            for entry in raw
        ]
    except Exception:
        return []


def save_keys(keys: list[APIKey]) -> None:
    """Persist the key list. Creates the state dir if needed; chmod 600."""
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    KEYS_FILE.write_text(
        json.dumps([asdict(k) for k in keys], indent=2),
        encoding="utf-8",
    )
    try:
        KEYS_FILE.chmod(0o600)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def check_scope(key: str, required_scope: str) -> bool:
    """Return True iff the key is valid and includes required_scope."""
    if not key.startswith("cwk_"):
        return False
    for entry in load_keys():
        if verify_key(key, entry.key_hash):
            return required_scope in entry.scopes
    return False


def authenticate_bearer(key: str) -> Optional[APIKey]:
    """Return the matching APIKey entry if the key is valid, else None.

    Does NOT check scope — the caller must do that separately via
    ``scope_for_request`` + the returned entry's ``scopes`` list.
    """
    if not key.startswith("cwk_"):
        return None
    for entry in load_keys():
        if verify_key(key, entry.key_hash):
            return entry
    return None


def scope_for_request(method: str, path: str) -> Optional[str]:
    """Return the scope that guards this method+path, or None for unguarded routes."""
    for req_method, prefix, scope in _ROUTE_SCOPES:
        if method == req_method and path.startswith(prefix):
            return scope
    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)
