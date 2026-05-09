"""Config loader for the bridge.

Source-of-truth precedence (highest first):
  1. process environment (already-set env vars win)
  2. ~/.chatwire/config.json          (current home)
  3. ~/.chat-bridge/config.json       (v0.1.0 location, pre-chatwire rename)
  4. ~/.imessage-bridge/config.json   (Phase 1 / pre-chat-bridge-rename)
  5. ~/.imessage-tg/.env              (pre-Phase-1)

Both bridge.py and web/main.py call `apply_to_environ()` once at startup.
This populates `os.environ` (via setdefault) so the rest of the codebase
keeps reading config the way it always has — no per-call refactor needed
in Phase 1. The shape revisits in Phase 4 when integrations get factored.

config.json is flat in v1: same keys as the legacy .env, JSON-shaped.
A v2 reshuffle into `{integrations: {...}, web: {...}}` ships with the
integration interface in Phase 4 and runs through the same migrator
mechanism that took us from .env to v1 here.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import stat
from pathlib import Path

log = logging.getLogger("chatwire.config")

CONFIG_DIR = Path.home() / ".chatwire"
CONFIG_PATH = CONFIG_DIR / "config.json"

# Runtime state files (state.json, whitelist.json, echo_log.jsonl, mirror.jsonl,
# push_subs.json, thumb_cache/) live alongside config under the same dir.
# Same path as CONFIG_DIR by design — exposing it as its own name lets state
# consumers (bridge.py, whitelist.py, echo_log.py, web/main.py) import the
# concept without pretending they're reading config.
STATE_DIR = CONFIG_DIR

# Read-only fallbacks for prior config locations. First save under the new
# CONFIG_PATH migrates a user off the legacy path. Order matters: most
# recent first, so a user mid-rename gets the freshest snapshot.
LEGACY_CONFIG_PATHS: list[Path] = [
    Path.home() / ".chat-bridge" / "config.json",      # v0.1.0
    Path.home() / ".imessage-bridge" / "config.json",  # Phase 1
]

LEGACY_ENV_DIR = Path.home() / ".imessage-tg"
LEGACY_ENV_PATH = LEGACY_ENV_DIR / ".env"

# Pre-0.3.0 the runtime state lived alongside the legacy .env in this dir.
# `migrate_state_dir()` copies these into STATE_DIR on first 0.3.0 boot.
LEGACY_STATE_DIR = LEGACY_ENV_DIR
STATE_FILES = (
    "state.json",
    "whitelist.json",
    "echo_log.jsonl",
    "mirror.jsonl",
    "push_subs.json",
    "thumb_cache",  # directory
)

CURRENT_VERSION = 4


def _read_legacy_env() -> dict[str, str]:
    """Parse the legacy ~/.imessage-tg/.env if present. Returns empty dict if not."""
    out: dict[str, str] = {}
    if not LEGACY_ENV_PATH.exists():
        return out
    for line in LEGACY_ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


def _read_config_json() -> dict | None:
    """Read config.json from the current path, falling back to legacy
    locations if the current one doesn't exist. Returns the parsed dict
    on first successful read; None if no config file exists anywhere."""
    for path in [CONFIG_PATH, *LEGACY_CONFIG_PATHS]:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            log.exception("%s is invalid JSON; trying next fallback", path)
            continue
        if path != CONFIG_PATH:
            log.info("read config from legacy %s; will migrate to %s on next save",
                     path, CONFIG_PATH)
        return data
    return None


def _ensure_secure(path: Path) -> None:
    """Refuse to load a config that's group/world readable. Telegram tokens
    live here — anyone with read on this file can take over the bot."""
    if not path.exists():
        return
    mode = path.stat().st_mode & 0o777
    if mode & 0o077:
        raise SystemExit(
            f"refusing to load {path}: permissions {oct(mode)} are too open. "
            f"run `chmod 600 {path}` and retry."
        )


def load_config() -> dict:
    """Return the merged config dict. Does not touch os.environ."""
    cfg = _read_config_json()
    if cfg is None:
        # Fall back to legacy .env, mapped into the same flat shape.
        legacy = _read_legacy_env()
        if legacy:
            return {"version": 1, **legacy}
        return {"version": CURRENT_VERSION}
    return cfg


def apply_to_environ() -> dict:
    """Populate os.environ from config (without overwriting already-set vars).

    Call this once at process start. Mirrors the legacy `.env` loader in
    bridge.py / web/main.py, just with config.json as primary source. Runs
    pending schema migrations before populating env so callers see the latest
    shape.

    Since v2, config is nested. `bridge.py` reads the dict directly for
    integration registration; everything else (web/main.py, whitelist.py,
    chatwire_cli.py) still reads the legacy flat env names. We flatten
    v2 → env on load so those readers don't need to change. Full env-var
    removal is Phase 5.
    """
    # Validate permissions on whichever config file actually exists,
    # whether that's the current path or a legacy fallback.
    for path in [CONFIG_PATH, *LEGACY_CONFIG_PATHS]:
        if path.exists():
            _ensure_secure(path)
            break
    migrate_state_dir()
    cfg = load_config()
    cfg = _run_migrations(cfg)
    for k, v in _flatten_v2_to_env(cfg).items():
        os.environ.setdefault(k, v)
    return cfg


def _flatten_v2_to_env(cfg: dict) -> dict[str, str]:
    """Project a v2 nested config back to the v1 flat env names.

    The inverse of migrations/0002_integration_split.py. List values become
    comma-joined strings (matching the historical .env format). Anything
    that isn't part of the legacy contract is skipped — env-var consumers
    only care about the keys they used to read.
    """
    out: dict[str, str] = {}

    self_handles = cfg.get("self_handles") or []
    if isinstance(self_handles, list) and self_handles:
        out["SELF_HANDLES"] = ",".join(str(h) for h in self_handles)

    integrations = cfg.get("integrations") or {}
    tg = integrations.get("telegram") or {}
    if tg.get("enabled") and tg.get("bot_token"):
        out["TELEGRAM_BOT_TOKEN"] = str(tg["bot_token"])
        ids = tg.get("allowed_user_ids") or []
        if isinstance(ids, list):
            out["TELEGRAM_ALLOWED_USER_IDS"] = ",".join(str(i) for i in ids)
    wh = integrations.get("webhook") or {}
    if wh.get("enabled") and wh.get("url"):
        out["WEBHOOK_URL"] = str(wh["url"])
        if wh.get("secret"):
            out["WEBHOOK_SECRET"] = str(wh["secret"])
        if "timeout_s" in wh:
            out["WEBHOOK_TIMEOUT_S"] = str(wh["timeout_s"])

    web = cfg.get("web") or {}
    if "port" in web:
        out["WEB_PORT"] = str(web["port"])
    if web.get("secure_cookie"):
        out["WEB_SECURE_COOKIE"] = "true"
    vapid = web.get("vapid") or {}
    if vapid.get("public"):
        out["VAPID_PUBLIC_KEY"] = str(vapid["public"])
    if vapid.get("private"):
        out["VAPID_PRIVATE_KEY"] = str(vapid["private"])
    if vapid.get("contact"):
        out["VAPID_CONTACT"] = str(vapid["contact"])

    debug = cfg.get("debug") or {}
    if debug.get("mirror_file"):
        out["DEBUG_MIRROR_FILE"] = str(debug["mirror_file"])

    # Forward any leftover scalar root keys (e.g., POLL_INTERVAL_S,
    # WHITELIST_HANDLES, UPDATE_CHECK_REPO) that the migration left at the
    # root because we never claimed them. This keeps escape-hatch keys the
    # user dropped in by hand working.
    nested_consumed = {"version", "self_handles", "integrations", "web", "debug"}
    for k, v in cfg.items():
        if k in nested_consumed:
            continue
        if isinstance(v, (str, int, float, bool)):
            out.setdefault(k, str(v))
    return out


def _run_migrations(cfg: dict) -> dict:
    """Apply pending migrations and persist if any ran. Best-effort: import
    failures are logged but don't block startup (the fallback flat-dict shape
    keeps working)."""
    try:
        import migrations
    except ImportError:
        return cfg
    cfg, ran = migrations.apply_pending(cfg)
    # Persist if migrations ran AND the data didn't come from thin air.
    # Includes legacy locations: a config read from a legacy dotfile dir
    # (~/.chat-bridge or ~/.imessage-bridge) that's been migrated should
    # be written to the new ~/.chatwire/ path, completing the dotfile-dir
    # migration on first run.
    config_existed_somewhere = CONFIG_PATH.exists() or any(p.exists() for p in LEGACY_CONFIG_PATHS)
    if ran and config_existed_somewhere:
        log.info("applied %d migration(s); saving config to %s", len(ran), CONFIG_PATH)
        save_config(cfg)
    return cfg


def save_config(cfg: dict) -> None:
    """Write config.json atomically with chmod 600."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cfg = {"version": CURRENT_VERSION, **{k: v for k, v in cfg.items() if k != "version"}}
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, indent=2, sort_keys=True))
    os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    tmp.replace(CONFIG_PATH)


def migrate_state_dir() -> list[str]:
    """Copy any pre-0.3.0 state files from LEGACY_STATE_DIR into STATE_DIR.

    Idempotent by file-existence check: a file is only copied when the
    destination doesn't already exist. The legacy dir is left in place so
    the operator can verify and remove it manually.

    Returns the list of file/dir names that were copied (empty list = no-op).
    """
    if not LEGACY_STATE_DIR.exists() or LEGACY_STATE_DIR == STATE_DIR:
        return []
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for name in STATE_FILES:
        src = LEGACY_STATE_DIR / name
        dst = STATE_DIR / name
        if not src.exists() or dst.exists():
            continue
        try:
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
        except OSError:
            log.exception("failed to copy %s → %s", src, dst)
            continue
        copied.append(name)
    if copied:
        log.info("migrated %d state file(s) from %s → %s: %s",
                 len(copied), LEGACY_STATE_DIR, STATE_DIR, ", ".join(copied))
    return copied


def migrate_legacy_env() -> bool:
    """If config.json is absent and a legacy .env exists, write config.json
    from it. Returns True if a migration ran. Idempotent: a no-op once
    config.json exists.

    The legacy .env is v1-flat (TELEGRAM_BOT_TOKEN at the root, etc.). We
    apply the schema migrations before saving so the on-disk file is the
    current shape — otherwise save_config would stamp version=CURRENT_VERSION
    over v1-flat content, the load-time `apply_pending` would skip (version
    already current), and the bridge would see a v2 schema with empty
    `integrations` and refuse to start.
    """
    if CONFIG_PATH.exists():
        return False
    legacy = _read_legacy_env()
    if not legacy:
        return False
    log.info("migrating %s → %s (%d keys)",
             LEGACY_ENV_PATH, CONFIG_PATH, len(legacy))
    cfg = {"version": 1, **{k: v for k, v in legacy.items() if k != "version"}}
    try:
        import migrations
        cfg, _ = migrations.apply_pending(cfg)
    except ImportError:
        log.warning("migrations module unavailable; saving as v1")
    save_config(cfg)
    return True
