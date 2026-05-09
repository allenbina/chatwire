"""Config-schema migrations.

Each module in this package is named `NNNN_short_description.py` and exposes:

    target_version: int          # the schema version this migration produces
    def migrate(cfg: dict) -> dict: ...

`config.load_config()` walks every migration with `target_version > cfg["version"]`
in NNNN order, applying each one and persisting the result. Migrations must be
deterministic and idempotent.

This is the same shape Django/Alembic use, scaled down. Each phase that
changes the on-disk shape ships a new migration; users never edit
`config.json` by hand to upgrade.

The framework is intentionally tiny — there's no rollback. If a migration is
wrong, ship a new one that fixes the damage.
"""
from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import Callable

log = logging.getLogger("chatwire.migrations")


def discover() -> list[tuple[int, Callable[[dict], dict], str]]:
    """Return [(target_version, migrate_fn, name), ...] sorted by version."""
    out = []
    for _, name, _ in pkgutil.iter_modules(__path__):
        if not name[:4].isdigit():
            continue
        mod = importlib.import_module(f"{__name__}.{name}")
        target = getattr(mod, "target_version", None)
        fn = getattr(mod, "migrate", None)
        if target is None or fn is None:
            log.warning("migration %s missing target_version or migrate()", name)
            continue
        out.append((int(target), fn, name))
    out.sort(key=lambda x: x[0])
    return out


def apply_pending(cfg: dict) -> tuple[dict, list[str]]:
    """Apply every migration whose target_version exceeds cfg['version'].

    Returns the (possibly-mutated) cfg and the list of migration names that
    ran. Caller decides whether to persist.
    """
    current = int(cfg.get("version") or 0)
    ran: list[str] = []
    for target, fn, name in discover():
        if target <= current:
            continue
        log.info("running migration %s (→ v%d)", name, target)
        cfg = fn(cfg)
        cfg["version"] = target
        current = target
        ran.append(name)
    return cfg, ran
