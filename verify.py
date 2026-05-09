"""verify.py — Plugin signature verification for chatwire.

Every pip-installed plugin that declares a ``chatwire.integrations`` entry
point must be signed with the chatwire Ed25519 private key before it will
load.  Built-in integrations (under ``integrations/``) ship in the wheel and
are trusted by construction; they are never passed through this module.

Signing workflow (Allen only)
------------------------------
1. Build and publish the plugin wheel to PyPI as normal.
2. Determine ``dist_name`` (PyPI package name, e.g. ``chatwire-ntfy``) and
   ``version`` (e.g. ``0.1.0``).
3. Compute the canonical payload::

       payload = f"{dist_name}:{version}".encode()

4. Sign with the private key::

       python scripts/gen_signing_key.py --sign chatwire-ntfy 0.1.0

   This prints a base64 signature string.
5. Place that string as a single line in the package's dist-info directory
   as ``CHATWIRE_SIGNATURE`` (add it to ``MANIFEST.in`` / ``package_data``
   so it ships in the wheel).

Key management
--------------
- Private key: held offline by Allen Bina.  Generated 2026-05-08.
  *Never commit the private key.*  If lost or compromised, rotate:
    1. Run ``scripts/gen_signing_key.py --keygen`` to get a new pair.
    2. Replace CHATWIRE_SIGNING_PUBLIC_KEY_B64 below.
    3. Bump chatwire version and re-sign all official plugins.
- Public key: baked into this module (CHATWIRE_SIGNING_PUBLIC_KEY_B64).

Bypass
------
Set ``CHATWIRE_TRUST_UNSIGNED=1`` to skip verification.  Intended for local
plugin development only.  Never set this in production.
"""

from __future__ import annotations

import base64
import importlib.metadata
import logging
import os

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

log = logging.getLogger(__name__)

# Ed25519 public key for chatwire plugin signing (base64-encoded raw bytes).
# Generated 2026-05-08.  Rotate via key management procedure above.
CHATWIRE_SIGNING_PUBLIC_KEY_B64 = "NBYf1ow8qExZtCren5TsQXMEEIyIXtdfX6ZRCmb5EuY="


class PluginNotTrusted(Exception):
    """Raised when a plugin cannot be verified against the trusted signing key."""


def _get_public_key() -> Ed25519PublicKey:
    raw = base64.b64decode(CHATWIRE_SIGNING_PUBLIC_KEY_B64)
    return Ed25519PublicKey.from_public_bytes(raw)


def canonical_payload(dist_name: str, version: str) -> bytes:
    """Return the exact bytes that are signed for a given dist+version.

    Exported so ``gen_signing_key.py`` and tests use the same formula.
    """
    return f"{dist_name}:{version}".encode()


def verify_plugin(dist_name: str) -> None:
    """Verify *dist_name* carries a valid chatwire signature.

    Raises :class:`PluginNotTrusted` if:

    * The package is not installed (shouldn't happen in normal use, but
      guards against stale entry points).
    * No ``CHATWIRE_SIGNATURE`` file is present in the dist-info directory.
    * The signature does not verify against the baked-in public key.

    Silently returns if ``CHATWIRE_TRUST_UNSIGNED=1`` is set in the
    environment (development bypass).
    """
    if os.environ.get("CHATWIRE_TRUST_UNSIGNED", "").strip() == "1":
        log.debug(
            "CHATWIRE_TRUST_UNSIGNED set — skipping signature check for %s",
            dist_name,
        )
        return

    try:
        dist = importlib.metadata.distribution(dist_name)
    except importlib.metadata.PackageNotFoundError:
        raise PluginNotTrusted(
            f"Plugin package '{dist_name}' is not installed; cannot verify signature."
        )

    version = dist.metadata["Version"]

    sig_text = dist.read_text("CHATWIRE_SIGNATURE")
    if sig_text is None:
        raise PluginNotTrusted(
            f"Plugin '{dist_name}' ({version}) is unsigned. "
            "Only officially signed chatwire plugins are loaded by default. "
            "Set CHATWIRE_TRUST_UNSIGNED=1 to load unsigned plugins (development only)."
        )

    try:
        sig_bytes = base64.b64decode(sig_text.strip())
    except Exception as exc:
        raise PluginNotTrusted(
            f"Plugin '{dist_name}' ({version}) has a malformed CHATWIRE_SIGNATURE "
            f"(not valid base64): {exc}"
        ) from exc

    payload = canonical_payload(dist_name, version)

    try:
        _get_public_key().verify(sig_bytes, payload)
    except InvalidSignature:
        raise PluginNotTrusted(
            f"Plugin '{dist_name}' ({version}) signature is invalid. "
            "The plugin may have been tampered with or signed with an unknown key."
        )

    log.debug("Plugin %s (%s) signature verified OK", dist_name, version)
