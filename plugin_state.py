"""Plugin state management — per-plugin config isolation and health tracking.

Directory structure:
    ~/.chatwire/plugins/<name>/
        config.json   — plugin-specific settings (isolated per-plugin)
        state.json    — health data (last run, error count, consecutive fails)
    ~/.chatwire/plugin-updates.json — cached update-check results (24 h TTL)

Health status derivation:
    healthy   — 0 errors in last 24 h
    degraded  — 1–5 errors in last 24 h
    failing   — 5+ errors in last 24 h  OR  last 3 consecutive runs failed
"""
from __future__ import annotations

import importlib
import importlib.metadata
import inspect
import json
import logging
import os
import re
import stat
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("chatwire.plugin_state")

_PLUGINS_DIR = Path.home() / ".chatwire" / "plugins"
_UPDATES_CACHE = Path.home() / ".chatwire" / "plugin-updates.json"
_UPDATES_TTL = 86_400  # 24 hours

_FAILING_CONSEC = 3   # consecutive failures → failing
_FAILING_24H = 5      # errors in 24 h → failing
_DEGRADED_24H = 1     # errors in 24 h → degraded (below _FAILING_24H)
_WINDOW_S = 86_400    # 24 hours in seconds

try:
    from _version import __version__ as _CHATWIRE_VERSION  # noqa: PLC0415
except ImportError:
    _CHATWIRE_VERSION = "0.0.0"


# ---------------------------------------------------------------------------
# Version comparison utilities
# ---------------------------------------------------------------------------

def _parse_version(v: str) -> tuple[int, ...]:
    """Parse a semver-ish string to a comparable int tuple.

    Examples: "1.12.0" → (1, 12, 0), "2.0.0-beta" → (2, 0, 0).
    Returns (0,) for unparseable strings.
    """
    try:
        parts = re.split(r"[.\-]", v)
        return tuple(int(p) for p in parts if p.isdigit())
    except Exception:
        return (0,)


def _version_gt(a: str, b: str) -> bool:
    """Return True if version string a is strictly greater than b."""
    return _parse_version(a) > _parse_version(b)


def _version_lt(a: str, b: str) -> bool:
    """Return True if version string a is strictly less than b."""
    return _parse_version(a) < _parse_version(b)


# ---------------------------------------------------------------------------
# SDK compatibility check
# ---------------------------------------------------------------------------

def _sdk_compat(cls: type, current_version: str) -> tuple[bool, str | None]:
    """Check whether a plugin's MIN_SDK / MAX_SDK allows *current_version*.

    Returns (compatible: bool, warning_message: str | None).
    """
    min_sdk = getattr(cls, "MIN_SDK", None)
    max_sdk = getattr(cls, "MAX_SDK", None)

    if min_sdk and _version_lt(current_version, min_sdk):
        return False, f"Requires chatwire >= {min_sdk} (installed: {current_version})"
    if max_sdk and _version_gt(current_version, max_sdk):
        return False, f"Requires chatwire <= {max_sdk} (installed: {current_version})"
    return True, None


# ---------------------------------------------------------------------------
# Directory helpers
# ---------------------------------------------------------------------------

def plugin_config_dir(name: str) -> Path:
    """Return (and create) the isolated config dir for plugin *name*."""
    d = _PLUGINS_DIR / name
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Per-plugin config (isolated settings)
# ---------------------------------------------------------------------------

def load_plugin_config(name: str) -> dict:
    """Load plugin's config.json. Returns {} if not yet written."""
    path = plugin_config_dir(name) / "config.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        log.exception("plugin %s: failed to read config.json", name)
        return {}


def save_plugin_config(name: str, data: dict) -> None:
    """Write plugin's config.json atomically with chmod 600."""
    path = plugin_config_dir(name) / "config.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Health tracking
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_state(name: str) -> dict:
    path = plugin_config_dir(name) / "state.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        log.exception("plugin %s: failed to read state.json", name)
        return {}


def _save_state(name: str, state: dict) -> None:
    path = plugin_config_dir(name) / "state.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp.replace(path)


def _parse_ts(ts: str) -> float:
    """Parse an ISO timestamp (ending in Z) to a Unix float. Returns 0 on error."""
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _derive_status(errors_24h: int, consecutive_errors: int) -> str:
    if errors_24h >= _FAILING_24H or consecutive_errors >= _FAILING_CONSEC:
        return "failing"
    if errors_24h >= _DEGRADED_24H:
        return "degraded"
    return "healthy"


def record_plugin_run(name: str, success: bool, error_msg: str | None = None) -> None:
    """Update health state after a plugin invocation.

    Reads the current state.json, updates counters, and writes it back.
    Best-effort: exceptions are logged and suppressed so health tracking
    never takes down a plugin.
    """
    try:
        now = _now_iso()
        state = _load_state(name)

        total_runs = state.get("total_runs", 0) + 1
        consecutive_errors = state.get("consecutive_errors", 0)

        # Rolling error list: trim entries older than 24 h on each write.
        error_timestamps: list[str] = state.get("error_timestamps", [])
        cutoff = datetime.now(timezone.utc).timestamp() - _WINDOW_S
        error_timestamps = [
            ts for ts in error_timestamps
            if _parse_ts(ts) >= cutoff
        ]

        if success:
            consecutive_errors = 0
            last_success = now
            last_error = state.get("last_error")
        else:
            consecutive_errors += 1
            last_success = state.get("last_success")
            last_error = error_msg or "unknown error"
            error_timestamps.append(now)

        errors_24h = len(error_timestamps)
        status = _derive_status(errors_24h, consecutive_errors)

        _save_state(name, {
            "last_run": now,
            "last_success": last_success,
            "last_error": last_error,
            "errors_24h": errors_24h,
            "consecutive_errors": consecutive_errors,
            "total_runs": total_runs,
            "status": status,
            "error_timestamps": error_timestamps,
        })
    except Exception:
        log.exception("record_plugin_run failed for %s", name)


def get_plugin_health(name: str) -> dict:
    """Return health status and stats for plugin *name*.

    Returns a dict with the same shape as state.json but without the
    internal error_timestamps list.
    """
    state = _load_state(name)
    if not state:
        return {
            "last_run": None,
            "last_success": None,
            "last_error": None,
            "errors_24h": 0,
            "total_runs": 0,
            "status": "healthy",
        }
    return {
        "last_run": state.get("last_run"),
        "last_success": state.get("last_success"),
        "last_error": state.get("last_error"),
        "errors_24h": state.get("errors_24h", 0),
        "total_runs": state.get("total_runs", 0),
        "status": state.get("status", "healthy"),
    }


def get_all_plugin_health() -> dict[str, dict]:
    """Return health dicts for all plugins that have a state.json."""
    if not _PLUGINS_DIR.exists():
        return {}
    out: dict[str, dict] = {}
    for child in _PLUGINS_DIR.iterdir():
        if child.is_dir() and (child / "state.json").exists():
            out[child.name] = get_plugin_health(child.name)
    return out


# ---------------------------------------------------------------------------
# Plugin update checking (compare installed vs PyPI latest)
# ---------------------------------------------------------------------------

def _pypi_latest_version(dist_name: str, timeout: int = 10) -> str | None:
    """Fetch the latest release version of *dist_name* from PyPI.

    Returns the version string on success, None on any error.
    """
    try:
        url = f"https://pypi.org/pypi/{dist_name}/json"
        req = urllib.request.Request(
            url, headers={"User-Agent": "chatwire/1 update-check"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
        version: str = data["info"]["version"]
        return version
    except Exception as exc:
        log.debug("update check: PyPI fetch failed for %s: %s", dist_name, exc)
        return None


def check_plugin_updates(classes: dict | None = None) -> list[dict]:
    """Compare installed pip-plugin versions against PyPI latest releases.

    Returns a list of dicts for plugins where an update is available::

        [{"name": "...", "dist_name": "...", "current_version": "...", "latest_version": "..."}]

    Built-in (non-pip) plugins are skipped. Network errors are silently
    skipped per-plugin so a single bad lookup never blocks the rest.
    """
    if classes is None:
        classes = discover_plugin_classes()

    updates = []
    for name, (cls, dist_name) in sorted(classes.items()):
        if dist_name is None:
            continue  # built-in — not pip-installed
        current = getattr(cls, "VERSION", None)
        if not current:
            continue
        latest = _pypi_latest_version(dist_name)
        if latest and _version_gt(latest, current):
            updates.append({
                "name": name,
                "dist_name": dist_name,
                "current_version": current,
                "latest_version": latest,
            })
    return updates


def save_plugin_updates(updates: list[dict]) -> None:
    """Persist update-check results to ~/.chatwire/plugin-updates.json."""
    _UPDATES_CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _UPDATES_CACHE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(updates, indent=2, sort_keys=True))
    tmp.replace(_UPDATES_CACHE)


def load_plugin_updates() -> list[dict]:
    """Load cached update-check results. Returns [] if not yet written."""
    if not _UPDATES_CACHE.exists():
        return []
    try:
        data = json.loads(_UPDATES_CACHE.read_text())
        return data if isinstance(data, list) else []
    except Exception:
        log.exception("failed to read plugin-updates.json")
        return []


def get_plugin_updates(force: bool = False) -> list[dict]:
    """Return plugin update info, refreshing from PyPI if the cache is stale.

    The cache file (~/.chatwire/plugin-updates.json) is considered fresh for
    24 hours. Pass ``force=True`` to bypass the TTL and always re-fetch.
    """
    if not force and _UPDATES_CACHE.exists():
        try:
            age = time.time() - _UPDATES_CACHE.stat().st_mtime
            if age < _UPDATES_TTL:
                return load_plugin_updates()
        except Exception:
            pass

    updates = check_plugin_updates()
    try:
        save_plugin_updates(updates)
    except Exception:
        log.exception("failed to save plugin-updates.json")
    return updates


# ---------------------------------------------------------------------------
# Integration class discovery (for the web UI plugin list)
# ---------------------------------------------------------------------------

def _looks_like_integration(cls: object) -> bool:
    return (
        inspect.isclass(cls)
        and isinstance(getattr(cls, "NAME", None), str)
        and isinstance(getattr(cls, "SETTINGS_SCHEMA", None), dict)
    )


def discover_plugin_classes() -> dict[str, tuple[type, str | None]]:
    """Find every Integration class available to this install.

    Mirrors bridge._discover_integration_classes() but without signature
    verification (verification happens at bridge startup). Safe to call
    from the web process.

    Returns a dict mapping plugin NAME → (cls, dist_name_or_None).
    dist_name is the pip distribution name for pip-installed plugins;
    None for built-in integrations that are part of the chatwire package.
    """
    out: dict[str, tuple[type, str | None]] = {}

    integrations_dir = Path(__file__).parent / "integrations"
    if integrations_dir.is_dir():
        for child in sorted(integrations_dir.iterdir()):
            if not child.is_dir() or child.name.startswith("_"):
                continue
            try:
                mod = importlib.import_module(f"integrations.{child.name}")
                for cls in vars(mod).values():
                    if (_looks_like_integration(cls)
                            and getattr(cls, "__module__", "") == mod.__name__):
                        out[cls.NAME] = (cls, None)  # built-in, no dist_name
            except Exception:
                log.exception("plugin discovery: failed to import integrations.%s", child.name)

    try:
        eps = importlib.metadata.entry_points(group="chatwire.integrations")
    except Exception:
        eps = []
    for ep in eps:
        try:
            cls = ep.load()
        except Exception:
            log.exception("plugin discovery: failed to load entry point %s", ep.name)
            continue
        if not _looks_like_integration(cls):
            continue
        if cls.NAME in out:
            continue
        dist = getattr(ep, "dist", None)
        dist_name = dist.metadata["Name"] if dist is not None else ep.name
        out[cls.NAME] = (cls, dist_name)

    return out


def build_plugin_list(cfg: dict) -> list[dict]:
    """Return a list of plugin dicts for the UI, merging class metadata,
    config (enabled/disabled), and health stats.

    Each dict shape:
        name, display_name, description, icon, tier, version,
        tags, settings_schema, enabled, health, needs_config, dist_name
    """
    classes = discover_plugin_classes()
    int_cfg = cfg.get("integrations") or {}

    out = []
    for name, (cls, dist_name) in sorted(classes.items()):
        block = int_cfg.get(name) or {}
        plugin_cfg = load_plugin_config(name)
        health = get_plugin_health(name)

        # Detect missing required settings.
        # Supports two schema shapes:
        #   1. JSON Schema: {"type": "object", "properties": {...}, "required": [...]}
        #   2. Custom manifest: {"field": {"type": "text", "required": True}, ...}
        schema = getattr(cls, "SETTINGS_SCHEMA", {})
        if schema.get("type") == "object":
            # JSON Schema format — required is a top-level list of field names.
            required_fields = schema.get("required") or []
        else:
            # Custom manifest format — each field dict may have "required": True.
            required_fields = [
                fname
                for fname, fdef in schema.items()
                if isinstance(fdef, dict) and fdef.get("required")
            ]
        needs_config = any(
            not block.get(f) and not plugin_cfg.get(f)
            for f in required_fields
        )

        compat, sdk_warning = _sdk_compat(cls, _CHATWIRE_VERSION)

        out.append({
            "name": name,
            "display_name": getattr(cls, "DISPLAY_NAME", name),
            "description": getattr(cls, "DESCRIPTION", ""),
            "icon": getattr(cls, "ICON", None),
            "tier": getattr(cls, "TIER", "official"),
            "version": getattr(cls, "VERSION", None),
            "min_sdk": getattr(cls, "MIN_SDK", None),
            "max_sdk": getattr(cls, "MAX_SDK", None),
            "tags": list(getattr(cls, "TAGS", [])),
            "settings_schema": schema,
            "enabled": bool(block.get("enabled")),
            "health": health,
            "needs_config": needs_config,
            "dist_name": dist_name,  # pip distribution name, None for built-ins
            "sdk_compat": compat,
            "sdk_warning": sdk_warning,
        })
    return out
