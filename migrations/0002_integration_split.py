"""Reshape v1 flat config into v2 with `integrations: {<name>: {...}}`.

v1 was the .env-shaped flat dict — a holdover from when there was only one
integration (Telegram) and the whole bridge read env vars. v2 namespaces
per-integration settings under `integrations.<name>`, web settings under
`web`, debug knobs under `debug`, and lifts `SELF_HANDLES` to a real list.

The runtime still reads env vars (the rest of the codebase hasn't been
ported yet); `config.apply_to_environ()` flattens v2 → env on load so
`web/main.py` and `whitelist.py` see the legacy names. That's intentional
back-compat — full env-var removal lands in Phase 5.
"""
from __future__ import annotations

target_version = 2

# Keys that move from a flat root entry to a nested location. The value is
# the (path, transform) pair; transform=None means "copy as-is".
def _split_csv(s: object) -> list[str]:
    if not isinstance(s, str):
        return []
    return [x.strip() for x in s.split(",") if x.strip()]


def _split_csv_int(s: object) -> list[int]:
    return [int(x) for x in _split_csv(s) if x.lstrip("-").isdigit()]


def _to_float(v: object) -> float:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 10.0


def migrate(cfg: dict) -> dict:
    out: dict = {}

    # Top-level: self_handles list.
    if "SELF_HANDLES" in cfg:
        out["self_handles"] = _split_csv(cfg["SELF_HANDLES"])

    # Telegram block.
    tg: dict = {}
    if "TELEGRAM_BOT_TOKEN" in cfg:
        tg["bot_token"] = cfg["TELEGRAM_BOT_TOKEN"]
    if "TELEGRAM_ALLOWED_USER_IDS" in cfg:
        tg["allowed_user_ids"] = _split_csv_int(cfg["TELEGRAM_ALLOWED_USER_IDS"])
    if tg:
        # Enabled iff a token is present — a token-less Telegram block is a
        # half-migrated install and not actually runnable.
        tg["enabled"] = bool(tg.get("bot_token"))

    # Webhook block.
    wh: dict = {}
    if "WEBHOOK_URL" in cfg:
        wh["url"] = cfg["WEBHOOK_URL"]
        wh["enabled"] = True
    if "WEBHOOK_SECRET" in cfg:
        wh["secret"] = cfg["WEBHOOK_SECRET"]
    if "WEBHOOK_TIMEOUT_S" in cfg:
        wh["timeout_s"] = _to_float(cfg["WEBHOOK_TIMEOUT_S"])

    integrations: dict = {}
    if tg:
        integrations["telegram"] = tg
    if wh:
        integrations["webhook"] = wh
    if integrations:
        out["integrations"] = integrations

    # Web block (port, vapid).
    web: dict = {}
    if "WEB_PORT" in cfg:
        try:
            web["port"] = int(cfg["WEB_PORT"])
        except (TypeError, ValueError):
            pass
    vapid: dict = {}
    if "VAPID_PUBLIC_KEY" in cfg:
        vapid["public"] = cfg["VAPID_PUBLIC_KEY"]
    if "VAPID_PRIVATE_KEY" in cfg:
        vapid["private"] = cfg["VAPID_PRIVATE_KEY"]
    if "VAPID_CONTACT" in cfg:
        vapid["contact"] = cfg["VAPID_CONTACT"]
    if vapid:
        web["vapid"] = vapid
    if web:
        out["web"] = web

    # Debug block.
    if "DEBUG_MIRROR_FILE" in cfg:
        out["debug"] = {"mirror_file": cfg["DEBUG_MIRROR_FILE"]}

    # Preserve anything we didn't recognize — better to leak forward than
    # silently drop a key the user manually added. The flatten step in
    # apply_to_environ() will ignore them.
    known_flat = {
        "SELF_HANDLES",
        "TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_USER_IDS",
        "WEBHOOK_URL", "WEBHOOK_SECRET", "WEBHOOK_TIMEOUT_S",
        "WEB_PORT",
        "VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY", "VAPID_CONTACT",
        "DEBUG_MIRROR_FILE",
        "version",
    }
    leftover = {k: v for k, v in cfg.items() if k not in known_flat}
    # If the input is already v2-shaped (re-running the migration on a v2
    # dict that somehow lost its version stamp), don't double-wrap.
    for nested_key in ("integrations", "web", "debug", "self_handles"):
        if nested_key in leftover:
            out.setdefault(nested_key, leftover.pop(nested_key))
    out.update(leftover)

    return out
