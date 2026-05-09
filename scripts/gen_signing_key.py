#!/usr/bin/env python3
"""gen_signing_key.py — Ed25519 keypair generation and plugin signing helper.

This script is NOT installed as a console command.  Allen runs it manually
from the repo root.

Usage
-----
Generate a new keypair (admin only — run once, keep the private key offline)::

    python scripts/gen_signing_key.py --keygen

Sign a plugin release (produces the base64 string to put in CHATWIRE_SIGNATURE)::

    python scripts/gen_signing_key.py --sign <dist_name> <version>
    # e.g.
    python scripts/gen_signing_key.py --sign chatwire-ntfy 0.2.0

Both commands read the private key from CHATWIRE_PRIVATE_KEY env var
(base64-encoded raw bytes, 32 bytes / 44 base64 chars).

Example end-to-end for a new plugin release
--------------------------------------------
1. Set the private key in your environment (never hardcode it)::

       export CHATWIRE_PRIVATE_KEY='<base64 private key>'

2. Sign::

       python scripts/gen_signing_key.py --sign chatwire-ntfy 0.1.0
       # Output: nFJ+Qh3mRHT7...

3. Create a file called ``CHATWIRE_SIGNATURE`` in the plugin's package root
   containing that one-line base64 string.

4. Add to the plugin's ``pyproject.toml`` so it ships in the wheel::

       [tool.setuptools.package-data]
       chatwire_ntfy = ["CHATWIRE_SIGNATURE"]

   Or if using MANIFEST.in::

       include CHATWIRE_SIGNATURE

5. Rebuild and publish.

Key rotation
------------
If the private key is lost or compromised:
1. Run ``--keygen`` to produce a new pair.
2. Replace ``CHATWIRE_SIGNING_PUBLIC_KEY_B64`` in ``verify.py``.
3. Bump chatwire to a new minor version.
4. Re-sign all official plugins with the new key.
5. Commit and push.
"""

from __future__ import annotations

import argparse
import base64
import os
import sys

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
        PublicFormat,
    )
except ImportError:
    print("ERROR: 'cryptography' package is required.  pip install cryptography")
    sys.exit(1)

# Import the canonical payload formula so we sign the same bytes verify.py checks.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from verify import canonical_payload  # noqa: E402


def _load_private_key() -> Ed25519PrivateKey:
    raw_b64 = os.environ.get("CHATWIRE_PRIVATE_KEY", "").strip()
    if not raw_b64:
        print(
            "ERROR: CHATWIRE_PRIVATE_KEY env var is not set.\n"
            "Export the base64-encoded private key before running this script."
        )
        sys.exit(1)
    try:
        raw = base64.b64decode(raw_b64)
    except Exception as exc:
        print(f"ERROR: CHATWIRE_PRIVATE_KEY is not valid base64: {exc}")
        sys.exit(1)
    return Ed25519PrivateKey.from_private_bytes(raw)


def cmd_keygen() -> None:
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()
    priv_bytes = priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    pub_bytes = pub.public_bytes(Encoding.Raw, PublicFormat.Raw)
    priv_b64 = base64.b64encode(priv_bytes).decode()
    pub_b64 = base64.b64encode(pub_bytes).decode()
    print("=" * 60)
    print("NEW Ed25519 KEYPAIR — keep the private key offline!")
    print("=" * 60)
    print()
    print("PRIVATE KEY (base64) — NEVER commit this:")
    print(priv_b64)
    print()
    print("PUBLIC KEY (base64) — paste into verify.py:")
    print(pub_b64)
    print()
    print("To use:")
    print(f"  export CHATWIRE_PRIVATE_KEY='{priv_b64}'")
    print("  python scripts/gen_signing_key.py --sign <dist_name> <version>")


def cmd_sign(dist_name: str, version: str) -> None:
    priv = _load_private_key()
    payload = canonical_payload(dist_name, version)
    sig_bytes = priv.sign(payload)
    sig_b64 = base64.b64encode(sig_bytes).decode()
    print("CHATWIRE_SIGNATURE for dist '{}' version '{}'".format(dist_name, version))
    print("=" * 60)
    print(sig_b64)
    print("=" * 60)
    print()
    print("Place this single line in a file named CHATWIRE_SIGNATURE")
    print("in the plugin package's distribution (wheel / sdist).")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="chatwire Ed25519 key generation and plugin signing helper"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--keygen",
        action="store_true",
        help="Generate a new Ed25519 keypair and print both keys",
    )
    group.add_argument(
        "--sign",
        nargs=2,
        metavar=("DIST_NAME", "VERSION"),
        help="Sign a plugin release (reads private key from CHATWIRE_PRIVATE_KEY env)",
    )
    args = parser.parse_args()

    if args.keygen:
        cmd_keygen()
    elif args.sign:
        cmd_sign(args.sign[0], args.sign[1])


if __name__ == "__main__":
    main()
