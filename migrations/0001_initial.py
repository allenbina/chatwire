"""Initial schema marker.

v1 is the flat-keys-with-version-stamp shape that `config.migrate_legacy_env`
already produces, so this migration only matters for configs that somehow
landed without a version field — it stamps them as v1 without touching keys.

When v2 lands (Phase 4 — integration-namespaced reshape), it ships as
`0002_integration_split.py` and reads the v1 dict.
"""
from __future__ import annotations

target_version = 1


def migrate(cfg: dict) -> dict:
    return dict(cfg)
