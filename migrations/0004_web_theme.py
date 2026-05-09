"""Default `web.theme` to "default" so older configs render under the new
theme-aware templates without an explicit pick.

Phase 2 of the redesign moves theme selection out of hardcoded template
links into a `web.theme` config key. Existing 0.3+ configs don't have
that key; this migration plants the default value so `selected_theme()`
finds something on its first read.

Idempotent: only writes the key when it's missing. A user who already
edited `web.theme` by hand (e.g. to "dracula") is left alone.
"""
from __future__ import annotations

target_version = 4


def migrate(cfg: dict) -> dict:
    web = cfg.setdefault("web", {})
    web.setdefault("theme", "default")
    return cfg
