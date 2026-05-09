"""PyPI version checks for plugins and chatwire core.

Isolated from FastAPI so tests can import this without the web stack.

Cache format (on disk):
  {package_name: {"version": "x.y.z", "ts": <unix timestamp float>}}

Stored at STATE_DIR/plugin_version_cache.json.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.request
from pathlib import Path

log = logging.getLogger("chatwire.version_check")

PYPI_JSON_URL = "https://pypi.org/pypi/{package}/json"
_CACHE_TTL = 86_400  # 24 hours


def fetch_pypi_version(package: str, mem_cache: dict, now: float) -> str | None:
    """Return the latest PyPI version for *package*.

    Uses *mem_cache* (a mutable dict) as an in-memory layer.  Callers
    should load it from disk before iterating and persist it afterwards.

    Returns None if the fetch fails and no cached value is available.
    """
    entry = mem_cache.get(package)
    if entry and now - entry.get("ts", 0) < _CACHE_TTL:
        return entry["version"]

    url = PYPI_JSON_URL.format(package=package)
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "chatwire/1 version-check"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        version: str = data["info"]["version"]
        mem_cache[package] = {"version": version, "ts": now}
        return version
    except Exception as exc:
        log.debug("PyPI version fetch failed for %s: %s", package, exc)

    # Network failed — return stale cached value if we have one.
    if entry:
        return entry["version"]
    return None


def load_version_cache(cache_path: Path) -> dict:
    """Load the on-disk version cache dict, or return {} on any error."""
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text())
        except Exception:
            pass
    return {}


def save_version_cache(cache_path: Path, mem_cache: dict) -> None:
    """Persist *mem_cache* to *cache_path*, silently ignoring errors."""
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(mem_cache))
    except Exception as exc:
        log.warning("Failed to save version cache: %s", exc)


def check_updates(
    dist_map: dict[str, str],
    cache_path: Path,
) -> dict[str, str]:
    """Check PyPI for newer versions of the given distributions.

    *dist_map*: ``{dist_name: installed_version}``

    Returns ``{dist_name: latest_pypi_version}`` for packages where a
    newer version is available (latest != installed, both non-None).

    Side-effect: updates the on-disk cache at *cache_path*.
    """
    if not dist_map:
        return {}

    mem_cache = load_version_cache(cache_path)
    now = time.time()
    updates: dict[str, str] = {}

    for dist, current in dist_map.items():
        if not current:
            continue
        latest = fetch_pypi_version(dist, mem_cache, now)
        if latest and latest != current:
            updates[dist] = latest

    save_version_cache(cache_path, mem_cache)
    return updates
