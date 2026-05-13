"""Tinfoil hat integration — AES-256-GCM end-to-end encryption.

Encrypts and decrypts message text using a shared passphrase per contact.
Key derivation: PBKDF2-SHA256, salt=b"chatwire", 100 000 iterations, 32 bytes.
Wire format:  🔒 + base64url(nonce[12] + tag[16] + ciphertext).

On inbound: if the message text starts with 🔒 and the sender handle has a
  configured passphrase, attempt decryption.  Success → plaintext shown.
  Failure → "[Encrypted message — wrong key or not for you]".

On outbound: if enabled, encrypt_by_default is set, and the recipient handle
  has a configured passphrase, encrypt the text before sending.
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Any

from web import log_stream as _ls

log = logging.getLogger("chatwire.tinfoil")

_LOCK = "🔒"
_PBKDF2_ITERS = 100_000
_SALT = b"chatwire"
_KEY_LEN = 32
_NONCE_LEN = 12
_TAG_LEN = 16
_ERROR_PLACEHOLDER = "[Encrypted message — wrong key or not for you]"


# ---------------------------------------------------------------------------
# Pure crypto helpers (no self — easy to unit-test)
# ---------------------------------------------------------------------------

def _derive_key(passphrase: str) -> bytes:
    """Derive a 32-byte AES key from *passphrase* via PBKDF2-SHA256."""
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=_KEY_LEN,
        salt=_SALT,
        iterations=_PBKDF2_ITERS,
        backend=default_backend(),
    )
    return kdf.derive(passphrase.encode())


def _encrypt(key: bytes, plaintext: str) -> str:
    """Encrypt *plaintext* with AES-256-GCM.

    Returns 🔒 + base64url(nonce[12] || tag[16] || ciphertext).
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(_NONCE_LEN)
    aesgcm = AESGCM(key)
    # AESGCM.encrypt() appends the 16-byte tag to the ciphertext.
    ct_and_tag = aesgcm.encrypt(nonce, plaintext.encode(), None)
    # ct_and_tag = ciphertext + tag (last 16 bytes)
    ciphertext = ct_and_tag[:-_TAG_LEN]
    tag = ct_and_tag[-_TAG_LEN:]
    payload = nonce + tag + ciphertext
    return _LOCK + base64.urlsafe_b64encode(payload).decode()


def _decrypt(key: bytes, token: str) -> str | None:
    """Decrypt a token produced by _encrypt().

    Returns the plaintext string, or None on any failure (wrong key, bad
    format, corrupted ciphertext).
    """
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not token.startswith(_LOCK):
        return None
    try:
        payload = base64.urlsafe_b64decode(token[len(_LOCK):] + "==")
    except Exception:
        return None

    if len(payload) < _NONCE_LEN + _TAG_LEN:
        return None

    nonce = payload[:_NONCE_LEN]
    tag = payload[_NONCE_LEN: _NONCE_LEN + _TAG_LEN]
    ciphertext = payload[_NONCE_LEN + _TAG_LEN:]

    aesgcm = AESGCM(key)
    try:
        # AESGCM.decrypt() expects ciphertext + tag concatenated.
        plaintext_bytes = aesgcm.decrypt(nonce, ciphertext + tag, None)
        return plaintext_bytes.decode()
    except (InvalidTag, Exception):
        return None


# ---------------------------------------------------------------------------
# Integration class
# ---------------------------------------------------------------------------

class TinfoilIntegration:
    """Built-in integration for AES-256-GCM symmetric message encryption."""

    NAME = "tinfoil"
    TIER = "official"  # Reviewed built-in; needs raw text for encryption.
    DISPLAY_NAME = "Tinfoil Hat"
    DESCRIPTION = (
        "End-to-end encrypt messages with a shared passphrase. "
        "Uses AES-256-GCM with per-contact keys derived via PBKDF2."
    )
    ICON = "🔒"

    SETTINGS_SCHEMA: dict[str, Any] = {
        "type": "object",
        "properties": {
            "enabled": {
                "type": "boolean",
                "title": "Enable tinfoil hat",
                "description": "Master switch for encryption/decryption.",
                "default": False,
            },
            "per_contact_keys": {
                "type": "object",
                "title": "Per-contact passphrases",
                "description": (
                    "Map of handle (phone/email) → shared passphrase. "
                    "Both parties must use the same passphrase."
                ),
                "additionalProperties": {"type": "string"},
                "default": {},
            },
            "encrypt_by_default": {
                "type": "boolean",
                "title": "Encrypt by default",
                "description": (
                    "Automatically encrypt all outbound messages to contacts "
                    "that have a configured passphrase."
                ),
                "default": False,
            },
        },
    }

    TRANSFORM_SCOPE: str = "all"

    def __init__(self, config: dict[str, Any]) -> None:
        self._enabled: bool = bool(config.get("enabled", False))
        self._per_contact_keys: dict[str, str] = dict(
            config.get("per_contact_keys") or {}
        )
        self._encrypt_by_default: bool = bool(
            config.get("encrypt_by_default", False)
        )

    # ------------------------------------------------------------------
    # Integration Protocol
    # ------------------------------------------------------------------

    async def start(self, ctx: Any) -> None:
        log.info(
            "tinfoil started — enabled=%s encrypt_by_default=%s contacts=%d",
            self._enabled,
            self._encrypt_by_default,
            len(self._per_contact_keys),
        )

    async def stop(self) -> None:
        pass

    async def on_inbound(self, msg: Any) -> None:
        # Transform is applied by the bridge relay via transform_inbound().
        pass

    # ------------------------------------------------------------------
    # Transform hooks
    # ------------------------------------------------------------------

    def transform_inbound(self, text: str, context: dict) -> str:
        """Decrypt inbound messages that start with the lock marker.

        Called by the bridge relay before fan-out to on_inbound() hooks.
        The original message in chat.db is never modified.
        """
        if not text or not text.startswith(_LOCK):
            return text

        handle: str = context.get("handle", "")
        passphrase = self._per_contact_keys.get(handle)
        if passphrase is None:
            # No key configured for this contact — leave as-is.
            return text

        key = _derive_key(passphrase)
        result = _decrypt(key, text)
        if result is None:
            log.warning(
                "tinfoil: decryption failed for handle=%s (wrong key or corrupted)",
                handle,
            )
            _ls.warn("tinfoil", "decryption failed — wrong key or corrupted message")
            return _ERROR_PLACEHOLDER
        _ls.info("tinfoil", "inbound message decrypted")
        return result

    def transform_outbound(self, text: str, target: Any) -> str:
        """Encrypt outbound messages when tinfoil is active for the target.

        Called by the bridge relay before the AppleScript send.
        """
        if not self._enabled or not self._encrypt_by_default:
            return text

        # target is a SendTarget dataclass with a .value attribute (the handle).
        handle: str = getattr(target, "value", "")
        passphrase = self._per_contact_keys.get(handle)
        if passphrase is None:
            return text

        key = _derive_key(passphrase)
        encrypted = _encrypt(key, text)
        _ls.info("tinfoil", "outbound message encrypted")
        return encrypted
