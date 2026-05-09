"""Tests for verify.py — plugin signature verification.

Strategy:
  - Generate a fresh Ed25519 test keypair per module (not per test).
  - Monkeypatch verify._get_public_key() so tests are independent of the
    production key baked into verify.CHATWIRE_SIGNING_PUBLIC_KEY_B64.
  - Mock importlib.metadata.distribution() to avoid needing real installed
    packages in the test environment.
  - Cover: unsigned (raises), valid sig (passes), bad sig (raises),
    CHATWIRE_TRUST_UNSIGNED=1 bypass, missing package, malformed sig.
  - Also test bridge._discover_integration_classes() integration (mocked).
"""
from __future__ import annotations

import base64
import importlib.metadata
from unittest.mock import MagicMock, patch

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

import verify as _verify_mod
from verify import PluginNotTrusted, canonical_payload, verify_plugin


# ---------------------------------------------------------------------------
# Test keypair — generated once per module run, never the production key.
# ---------------------------------------------------------------------------

_TEST_PRIVATE_KEY = Ed25519PrivateKey.generate()
_TEST_PUBLIC_KEY = _TEST_PRIVATE_KEY.public_key()
_TEST_PUBLIC_KEY_BYTES = _TEST_PUBLIC_KEY.public_bytes(Encoding.Raw, PublicFormat.Raw)


def _sign(dist_name: str, version: str) -> str:
    """Return a base64 signature string using the test private key."""
    payload = canonical_payload(dist_name, version)
    sig_bytes = _TEST_PRIVATE_KEY.sign(payload)
    return base64.b64encode(sig_bytes).decode()


def _make_dist(name: str, version: str, signature: str | None) -> MagicMock:
    """Build a mock Distribution object as returned by importlib.metadata."""
    dist = MagicMock()
    dist.metadata = {"Name": name, "Version": version}
    dist.read_text.return_value = signature
    return dist


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_public_key(monkeypatch):
    """Replace the production public key with the test key for every test."""
    monkeypatch.setattr(
        _verify_mod,
        "_get_public_key",
        lambda: _TEST_PUBLIC_KEY,
    )


@pytest.fixture(autouse=True)
def _clear_trust_env(monkeypatch):
    """Ensure CHATWIRE_TRUST_UNSIGNED is unset by default."""
    monkeypatch.delenv("CHATWIRE_TRUST_UNSIGNED", raising=False)


# ---------------------------------------------------------------------------
# verify_plugin — core scenarios
# ---------------------------------------------------------------------------

class TestVerifyPlugin:

    def test_valid_signature_passes(self):
        sig = _sign("chatwire-ntfy", "0.1.0")
        dist = _make_dist("chatwire-ntfy", "0.1.0", sig)
        with patch("importlib.metadata.distribution", return_value=dist):
            verify_plugin("chatwire-ntfy")  # must not raise

    def test_unsigned_raises_plugin_not_trusted(self):
        dist = _make_dist("chatwire-foo", "1.0.0", None)
        with patch("importlib.metadata.distribution", return_value=dist):
            with pytest.raises(PluginNotTrusted) as exc_info:
                verify_plugin("chatwire-foo")
        assert "unsigned" in str(exc_info.value).lower()
        assert "chatwire-foo" in str(exc_info.value)

    def test_unsigned_error_mentions_trust_unsigned(self):
        dist = _make_dist("chatwire-foo", "1.0.0", None)
        with patch("importlib.metadata.distribution", return_value=dist):
            with pytest.raises(PluginNotTrusted) as exc_info:
                verify_plugin("chatwire-foo")
        assert "CHATWIRE_TRUST_UNSIGNED" in str(exc_info.value)

    def test_wrong_version_signature_raises(self):
        sig = _sign("chatwire-ntfy", "0.1.0")
        dist = _make_dist("chatwire-ntfy", "0.2.0", sig)  # version mismatch
        with patch("importlib.metadata.distribution", return_value=dist):
            with pytest.raises(PluginNotTrusted) as exc_info:
                verify_plugin("chatwire-ntfy")
        assert "invalid" in str(exc_info.value).lower()

    def test_wrong_dist_name_signature_raises(self):
        sig = _sign("chatwire-ntfy", "0.1.0")
        dist = _make_dist("chatwire-evil", "0.1.0", sig)  # name mismatch
        with patch("importlib.metadata.distribution", return_value=dist):
            with pytest.raises(PluginNotTrusted) as exc_info:
                verify_plugin("chatwire-evil")
        assert "invalid" in str(exc_info.value).lower()

    def test_malformed_base64_signature_raises(self):
        dist = _make_dist("chatwire-ntfy", "0.1.0", "not-valid-base64!!!")
        with patch("importlib.metadata.distribution", return_value=dist):
            with pytest.raises(PluginNotTrusted) as exc_info:
                verify_plugin("chatwire-ntfy")
        assert "malformed" in str(exc_info.value).lower()

    def test_package_not_installed_raises(self):
        with patch(
            "importlib.metadata.distribution",
            side_effect=importlib.metadata.PackageNotFoundError("chatwire-ghost"),
        ):
            with pytest.raises(PluginNotTrusted) as exc_info:
                verify_plugin("chatwire-ghost")
        assert "not installed" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# CHATWIRE_TRUST_UNSIGNED bypass
# ---------------------------------------------------------------------------

class TestTrustUnsigned:

    def test_bypass_skips_unsigned_check(self, monkeypatch):
        monkeypatch.setenv("CHATWIRE_TRUST_UNSIGNED", "1")
        dist = _make_dist("chatwire-foo", "1.0.0", None)
        with patch("importlib.metadata.distribution", return_value=dist):
            verify_plugin("chatwire-foo")  # must not raise

    def test_bypass_skips_even_missing_package(self, monkeypatch):
        monkeypatch.setenv("CHATWIRE_TRUST_UNSIGNED", "1")
        with patch(
            "importlib.metadata.distribution",
            side_effect=importlib.metadata.PackageNotFoundError("x"),
        ):
            verify_plugin("chatwire-x")  # must not raise

    def test_bypass_does_not_trigger_on_zero(self, monkeypatch):
        monkeypatch.setenv("CHATWIRE_TRUST_UNSIGNED", "0")
        dist = _make_dist("chatwire-foo", "1.0.0", None)
        with patch("importlib.metadata.distribution", return_value=dist):
            with pytest.raises(PluginNotTrusted):
                verify_plugin("chatwire-foo")

    def test_bypass_does_not_trigger_on_empty_string(self, monkeypatch):
        monkeypatch.setenv("CHATWIRE_TRUST_UNSIGNED", "")
        dist = _make_dist("chatwire-foo", "1.0.0", None)
        with patch("importlib.metadata.distribution", return_value=dist):
            with pytest.raises(PluginNotTrusted):
                verify_plugin("chatwire-foo")

    def test_bypass_with_surrounding_whitespace(self, monkeypatch):
        monkeypatch.setenv("CHATWIRE_TRUST_UNSIGNED", "  1  ")
        dist = _make_dist("chatwire-foo", "1.0.0", None)
        with patch("importlib.metadata.distribution", return_value=dist):
            verify_plugin("chatwire-foo")  # must not raise


# ---------------------------------------------------------------------------
# canonical_payload
# ---------------------------------------------------------------------------

class TestCanonicalPayload:

    def test_returns_bytes(self):
        assert isinstance(canonical_payload("chatwire-ntfy", "0.1.0"), bytes)

    def test_includes_dist_name_and_version(self):
        p = canonical_payload("chatwire-ntfy", "0.1.0")
        assert b"chatwire-ntfy" in p
        assert b"0.1.0" in p

    def test_different_versions_different_payload(self):
        assert canonical_payload("chatwire-ntfy", "0.1.0") != canonical_payload(
            "chatwire-ntfy", "0.2.0"
        )

    def test_different_names_different_payload(self):
        assert canonical_payload("chatwire-ntfy", "0.1.0") != canonical_payload(
            "chatwire-other", "0.1.0"
        )


# ---------------------------------------------------------------------------
# bridge._discover_integration_classes — signature gate integration test
# ---------------------------------------------------------------------------

class TestBridgeDiscovery:
    """Verify that _discover_integration_classes() refuses unsigned plugins
    and loads signed ones correctly."""

    def _make_ep(self, dist_name: str, version: str, signature: str | None):
        """Build a mock EntryPoint with a mock .dist."""
        dist = _make_dist(dist_name, version, signature)
        ep = MagicMock()
        ep.name = dist_name.replace("chatwire-", "")
        ep.dist = dist
        ep.dist.metadata = {"Name": dist_name, "Version": version}
        return ep, dist

    def _make_integration_cls(self, name: str):
        """Return a minimal Integration-shaped class."""
        return type(
            f"{name.title()}Integration",
            (),
            {"NAME": name, "SETTINGS_SCHEMA": {}},
        )

    def test_unsigned_plugin_not_loaded(self, monkeypatch):
        """An unsigned entry-point plugin must not appear in the registry."""
        from bridge import _discover_integration_classes

        ep, dist = self._make_ep("chatwire-foo", "1.0.0", None)
        ep.load.return_value = self._make_integration_cls("foo")

        with patch("importlib.metadata.entry_points", return_value=[ep]):
            with patch("importlib.metadata.distribution", return_value=dist):
                # Also patch away the integrations/ directory scan.
                with patch("bridge.INTEGRATIONS_DIR") as mock_dir:
                    mock_dir.is_dir.return_value = False
                    result = _discover_integration_classes()

        assert "foo" not in result

    def test_signed_plugin_is_loaded(self, monkeypatch):
        """A properly signed entry-point plugin must appear in the registry."""
        from bridge import _discover_integration_classes

        sig = _sign("chatwire-bar", "2.0.0")
        ep, dist = self._make_ep("chatwire-bar", "2.0.0", sig)
        cls = self._make_integration_cls("bar")
        ep.load.return_value = cls

        with patch("importlib.metadata.entry_points", return_value=[ep]):
            with patch("importlib.metadata.distribution", return_value=dist):
                with patch("bridge.INTEGRATIONS_DIR") as mock_dir:
                    mock_dir.is_dir.return_value = False
                    result = _discover_integration_classes()

        assert "bar" in result
        assert result["bar"] is cls

    def test_trust_unsigned_allows_unsigned_plugin(self, monkeypatch):
        """CHATWIRE_TRUST_UNSIGNED=1 must allow unsigned plugins to load."""
        monkeypatch.setenv("CHATWIRE_TRUST_UNSIGNED", "1")
        from bridge import _discover_integration_classes

        ep, dist = self._make_ep("chatwire-baz", "0.5.0", None)
        cls = self._make_integration_cls("baz")
        ep.load.return_value = cls

        with patch("importlib.metadata.entry_points", return_value=[ep]):
            with patch("importlib.metadata.distribution", return_value=dist):
                with patch("bridge.INTEGRATIONS_DIR") as mock_dir:
                    mock_dir.is_dir.return_value = False
                    result = _discover_integration_classes()

        assert "baz" in result
