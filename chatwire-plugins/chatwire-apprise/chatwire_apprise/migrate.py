"""Migration helper: convert chatwire-ntfy config → chatwire-apprise URLs.

Usage (run once after installing chatwire-apprise):
    python -m chatwire_apprise.migrate

Reads ~/.chatwire/config.json, converts any chatwire_ntfy settings to an
Apprise ntfy:// URL, and writes the result into chatwire_apprise.urls.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _state_dir() -> Path:
    return Path(os.environ.get("CHATWIRE_STATE_DIR", Path.home() / ".chatwire"))


def migrate() -> int:
    """Migrate ntfy config to Apprise config.

    Returns:
        0  — migrated successfully or nothing to migrate
        1  — config file not found or not parseable
    """
    cfg_path = _state_dir() / "config.json"
    if not cfg_path.exists():
        print(f"[migrate] config file not found: {cfg_path}", file=sys.stderr)
        return 1

    try:
        cfg: dict = json.loads(cfg_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[migrate] could not read config: {exc}", file=sys.stderr)
        return 1

    integrations: dict = cfg.setdefault("integrations", {})
    ntfy_cfg: dict = integrations.get("chatwire_ntfy") or {}
    apprise_cfg: dict = integrations.get("chatwire_apprise") or {}

    # Nothing to migrate
    if not ntfy_cfg.get("topic"):
        print("[migrate] no chatwire_ntfy topic found — nothing to migrate")
        return 0

    # Already has Apprise config
    if apprise_cfg.get("urls"):
        print("[migrate] chatwire_apprise.urls already set — skipping migration")
        return 0

    topic = ntfy_cfg["topic"].strip()
    server = (ntfy_cfg.get("server") or "https://ntfy.sh").rstrip("/")
    username = (ntfy_cfg.get("username") or "").strip()
    password = (ntfy_cfg.get("password") or "").strip()

    # Build ntfy Apprise URL: ntfy://[user:pass@]host/topic
    # Strip https:// from server to get hostname
    hostname = server.removeprefix("https://").removeprefix("http://")
    if username and password:
        ntfy_url = f"ntfy://{username}:{password}@{hostname}/{topic}"
    else:
        ntfy_url = f"ntfy://{hostname}/{topic}"

    # For the default public server (ntfy.sh) the short form works too.
    # Apprise recognises "ntfy://<topic>" when no host is given but let's
    # be explicit to avoid ambiguity.

    integrations["chatwire_apprise"] = {
        "enabled": bool(ntfy_cfg.get("enabled", False)),
        "urls": ntfy_url,
        "title_format": "{sender}",
    }

    # Write back (pretty-print, preserve structure)
    tmp = cfg_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
    tmp.replace(cfg_path)

    print(f"[migrate] chatwire_ntfy → chatwire_apprise: {ntfy_url}")
    print("[migrate] Done.  You can now disable chatwire_ntfy or uninstall chatwire-ntfy.")
    return 0


if __name__ == "__main__":
    sys.exit(migrate())
