"""Repoint `debug.mirror_file` from the legacy state dir to the new one.

0.3.0 moves runtime state from `~/.imessage-tg/` to `~/.chatwire/` (see
`config.migrate_state_dir`). The mirror file is the one piece of state
whose location the user can override via config, so an explicit user
value at the legacy *default* gets bumped here. Anything pointed
elsewhere on purpose is left alone.

Pairs with the filesystem-level copy in `migrate_state_dir()` — that
moves the file's bytes; this updates the pointer in config.json.
"""
from __future__ import annotations

from pathlib import Path

target_version = 3


def migrate(cfg: dict) -> dict:
    debug = cfg.get("debug")
    if not isinstance(debug, dict):
        return cfg
    current = debug.get("mirror_file")
    if not isinstance(current, str):
        return cfg
    legacy_default = str(Path.home() / ".imessage-tg" / "mirror.jsonl")
    new_default = str(Path.home() / ".chatwire" / "mirror.jsonl")
    if current == legacy_default:
        debug["mirror_file"] = new_default
    return cfg
