"""Plugin registry cache — fetches and caches plugins.json from GitHub.

Isolated from FastAPI so it can be imported in tests without the web app.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.request
from pathlib import Path

log = logging.getLogger("chatwire.registry")

PLUGIN_REGISTRY_URL = (
    "https://raw.githubusercontent.com/allenbina/chatwire-plugins/main/plugins.json"
)
_REGISTRY_CACHE_TTL = 86_400  # 24 hours


def fetch_registry(cache_path: Path) -> list[dict]:
    """Return the plugin registry, using a 24-hour on-disk cache.

    1. If *cache_path* exists and is < 24 h old, return the cached list.
    2. Otherwise, attempt to fetch from GitHub and update the cache.
    3. On network failure, return the stale cache if available, else [].
    """
    now = time.time()

    # Return fresh cache without hitting the network.
    if cache_path.exists():
        try:
            if now - cache_path.stat().st_mtime < _REGISTRY_CACHE_TTL:
                return json.loads(cache_path.read_text())
        except Exception:
            pass

    # Attempt network refresh.
    try:
        req = urllib.request.Request(
            PLUGIN_REGISTRY_URL,
            headers={"User-Agent": "chatwire/1 plugin-marketplace"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
        data = json.loads(raw)
        if isinstance(data, list):
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(raw)
            return data
    except Exception as exc:
        log.warning("plugin registry fetch failed: %s", exc)

    # Network failed — return stale cache or empty list.
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text())
        except Exception:
            pass
    return []
