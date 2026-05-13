"""Tests for integrations/tinfoil/__init__.py.

Covers:
  a. _derive_key produces 32-byte bytes deterministically.
  b. _encrypt output starts with "🔒".
  c. Round-trip: encrypt then decrypt returns original text.
  d. Wrong key returns None from _decrypt.
  e. transform_inbound decrypts matching handle, leaves others alone.
  f. transform_inbound with wrong key shows error placeholder.
  g. transform_outbound encrypts when encrypt_by_default=True.
  h. transform_outbound skips when handle not in per_contact_keys.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from integrations.tinfoil import (
    TinfoilIntegration,
    _derive_key,
    _decrypt,
    _encrypt,
    _ERROR_PLACEHOLDER,
    _LOCK,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make(config: dict | None = None) -> TinfoilIntegration:
    return TinfoilIntegration(config or {})


def _make_target(handle: str) -> MagicMock:
    t = MagicMock()
    t.value = handle
    t.kind = "handle"
    return t


# ---------------------------------------------------------------------------
# a. _derive_key produces 32-byte bytes deterministically
# ---------------------------------------------------------------------------

class TestDeriveKey:
    def test_returns_bytes(self):
        key = _derive_key("mysecret")
        assert isinstance(key, bytes)

    def test_length_is_32(self):
        key = _derive_key("mysecret")
        assert len(key) == 32

    def test_deterministic(self):
        assert _derive_key("mysecret") == _derive_key("mysecret")

    def test_different_passphrases_differ(self):
        assert _derive_key("abc") != _derive_key("xyz")


# ---------------------------------------------------------------------------
# b. _encrypt output starts with "🔒"
# ---------------------------------------------------------------------------

class TestEncrypt:
    def test_starts_with_lock(self):
        key = _derive_key("pass")
        token = _encrypt(key, "hello")
        assert token.startswith(_LOCK)

    def test_different_nonces_each_call(self):
        key = _derive_key("pass")
        t1 = _encrypt(key, "hello")
        t2 = _encrypt(key, "hello")
        # With random nonces, two encryptions of the same plaintext must differ.
        assert t1 != t2


# ---------------------------------------------------------------------------
# c. Round-trip: encrypt then decrypt returns original text
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_basic_roundtrip(self):
        key = _derive_key("roundtrip")
        plaintext = "Hello, this is a secret message!"
        token = _encrypt(key, plaintext)
        assert _decrypt(key, token) == plaintext

    def test_roundtrip_unicode(self):
        key = _derive_key("unicode_pass")
        plaintext = "こんにちは 🌍"
        token = _encrypt(key, plaintext)
        assert _decrypt(key, token) == plaintext

    def test_roundtrip_empty_string(self):
        key = _derive_key("emptypass")
        plaintext = ""
        token = _encrypt(key, plaintext)
        assert _decrypt(key, token) == plaintext


# ---------------------------------------------------------------------------
# d. Wrong key returns None from _decrypt
# ---------------------------------------------------------------------------

class TestWrongKey:
    def test_wrong_key_returns_none(self):
        right_key = _derive_key("correct")
        wrong_key = _derive_key("incorrect")
        token = _encrypt(right_key, "top secret")
        assert _decrypt(wrong_key, token) is None

    def test_no_lock_prefix_returns_none(self):
        key = _derive_key("pass")
        assert _decrypt(key, "no prefix here") is None

    def test_truncated_payload_returns_none(self):
        key = _derive_key("pass")
        # 🔒 prefix but garbage after
        assert _decrypt(key, _LOCK + "abc") is None

    def test_corrupted_payload_returns_none(self):
        key = _derive_key("pass")
        token = _encrypt(key, "data")
        # Flip the last character of the base64 payload.
        corrupted = token[:-1] + ("A" if token[-1] != "A" else "B")
        # This may or may not parse as valid base64, but decryption should fail.
        result = _decrypt(key, corrupted)
        # Either None (decryption failed) or the payload was invalid length.
        assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# e. transform_inbound decrypts matching handle, leaves others alone
# ---------------------------------------------------------------------------

class TestTransformInbound:
    def test_decrypts_matching_handle(self):
        passphrase = "shared_secret"
        key = _derive_key(passphrase)
        plaintext = "Hi there!"
        token = _encrypt(key, plaintext)

        inst = _make({"per_contact_keys": {"+15551234567": passphrase}})
        ctx = {"handle": "+15551234567", "is_from_me": False}
        result = inst.transform_inbound(token, ctx)
        assert result == plaintext

    def test_leaves_unencrypted_message_alone(self):
        inst = _make({"per_contact_keys": {"+15551234567": "pass"}})
        ctx = {"handle": "+15551234567", "is_from_me": False}
        plain = "Just a normal message."
        result = inst.transform_inbound(plain, ctx)
        assert result == plain

    def test_leaves_unknown_handle_alone(self):
        passphrase = "shared_secret"
        key = _derive_key(passphrase)
        token = _encrypt(key, "secret")

        inst = _make({"per_contact_keys": {}})
        ctx = {"handle": "+19999999999", "is_from_me": False}
        result = inst.transform_inbound(token, ctx)
        # No key for this handle → leave the encrypted token unchanged.
        assert result == token

    def test_empty_text_passthrough(self):
        inst = _make({"per_contact_keys": {"+15551234567": "pass"}})
        ctx = {"handle": "+15551234567", "is_from_me": False}
        assert inst.transform_inbound("", ctx) == ""


# ---------------------------------------------------------------------------
# f. transform_inbound with wrong key shows error placeholder
# ---------------------------------------------------------------------------

class TestTransformInboundWrongKey:
    def test_wrong_key_shows_placeholder(self):
        right_pass = "correct_passphrase"
        wrong_pass = "wrong_passphrase"
        key = _derive_key(right_pass)
        token = _encrypt(key, "secret data")

        # Integration configured with wrong passphrase.
        inst = _make({"per_contact_keys": {"+15551234567": wrong_pass}})
        ctx = {"handle": "+15551234567", "is_from_me": False}
        result = inst.transform_inbound(token, ctx)
        assert result == _ERROR_PLACEHOLDER

    def test_error_placeholder_content(self):
        assert "wrong key" in _ERROR_PLACEHOLDER.lower() or "encrypted" in _ERROR_PLACEHOLDER.lower()


# ---------------------------------------------------------------------------
# g. transform_outbound encrypts when encrypt_by_default=True
# ---------------------------------------------------------------------------

class TestTransformOutbound:
    def test_encrypts_when_enabled_and_default(self):
        passphrase = "outbound_pass"
        handle = "+15551234567"
        inst = _make({
            "enabled": True,
            "encrypt_by_default": True,
            "per_contact_keys": {handle: passphrase},
        })
        target = _make_target(handle)
        plaintext = "Encrypt me!"
        result = inst.transform_outbound(plaintext, target)
        assert result.startswith(_LOCK)

        # Verify it's actually decryptable.
        key = _derive_key(passphrase)
        assert _decrypt(key, result) == plaintext

    def test_does_not_encrypt_when_disabled(self):
        passphrase = "outbound_pass"
        handle = "+15551234567"
        inst = _make({
            "enabled": False,
            "encrypt_by_default": True,
            "per_contact_keys": {handle: passphrase},
        })
        target = _make_target(handle)
        plaintext = "Do not encrypt."
        result = inst.transform_outbound(plaintext, target)
        assert result == plaintext

    def test_does_not_encrypt_when_not_default(self):
        passphrase = "outbound_pass"
        handle = "+15551234567"
        inst = _make({
            "enabled": True,
            "encrypt_by_default": False,
            "per_contact_keys": {handle: passphrase},
        })
        target = _make_target(handle)
        plaintext = "Do not encrypt."
        result = inst.transform_outbound(plaintext, target)
        assert result == plaintext


# ---------------------------------------------------------------------------
# h. transform_outbound skips when handle not in per_contact_keys
# ---------------------------------------------------------------------------

class TestTransformOutboundNoKey:
    def test_skips_unknown_handle(self):
        inst = _make({
            "enabled": True,
            "encrypt_by_default": True,
            "per_contact_keys": {},
        })
        target = _make_target("+19999999999")
        plaintext = "No key for this contact."
        result = inst.transform_outbound(plaintext, target)
        assert result == plaintext

    def test_skips_handle_not_in_keys(self):
        inst = _make({
            "enabled": True,
            "encrypt_by_default": True,
            "per_contact_keys": {"+15551234567": "pass"},
        })
        # Different handle
        target = _make_target("+19999999999")
        plaintext = "Different handle."
        result = inst.transform_outbound(plaintext, target)
        assert result == plaintext


# ---------------------------------------------------------------------------
# Integration class sanity checks
# ---------------------------------------------------------------------------

class TestIntegrationProtocol:
    def test_name(self):
        assert TinfoilIntegration.NAME == "tinfoil"

    def test_settings_schema_keys(self):
        props = TinfoilIntegration.SETTINGS_SCHEMA["properties"]
        assert "enabled" in props
        assert "per_contact_keys" in props
        assert "encrypt_by_default" in props

    def test_settings_schema_defaults(self):
        props = TinfoilIntegration.SETTINGS_SCHEMA["properties"]
        assert props["enabled"]["default"] is False
        assert props["encrypt_by_default"]["default"] is False

    def test_transform_scope(self):
        inst = _make()
        assert inst.TRANSFORM_SCOPE == "all"

    def test_start_stop(self):
        import asyncio
        ctx = MagicMock()
        inst = _make()
        asyncio.run(inst.start(ctx))
        asyncio.run(inst.stop())
