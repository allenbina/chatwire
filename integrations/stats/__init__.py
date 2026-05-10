"""Stats integration — built-in messaging analytics.

Web-only plugin: no bridge connection, no background tasks. Exposes
a date_range setting that the /plugins/stats/report route reads when
generating the analytics page.

Ported to BaseIntegration (chatwire-sdk) in Phase 4 as a proof-of-concept
end-to-end demonstration of the Plugin SDK.

Config block (under ``integrations.stats`` in config.json):

    {
        "enabled": true,
        "date_range": "30d"
    }
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Bootstrap: make chatwire_sdk importable even when running in-tree.
# packages/sdk is a sibling of the repo root so we add it to sys.path
# if it isn't already installed as a package.
# ---------------------------------------------------------------------------
_sdk_path = Path(__file__).resolve().parents[2] / "packages" / "sdk"
if str(_sdk_path) not in sys.path:
    sys.path.insert(0, str(_sdk_path))

try:
    from chatwire_sdk import BaseIntegration, chatwire_plugin
except ImportError:  # fallback if SDK isn't on path at all
    BaseIntegration = object  # type: ignore[assignment,misc]
    def chatwire_plugin(cls):  # type: ignore[misc]
        return cls


@chatwire_plugin
class StatsIntegration(BaseIntegration):
    NAME = "stats"
    DISPLAY_NAME = "Message statistics"
    DESCRIPTION = "Messaging analytics computed locally from your chat.db."
    ICON = "📊"

    SETTINGS_SCHEMA = {
        "type": "object",
        "properties": {
            "enabled": {
                "type": "boolean",
                "default": False,
                "title": "Enable stats",
            },
            "date_range": {
                "type": "string",
                "enum": ["30d", "90d", "365d", "all"],
                "default": "30d",
                "title": "Date range",
                "description": "How far back to include messages in the report.",
            },
        },
    }

    def __init__(self, config: dict[str, Any] | None = None):
        # Call BaseIntegration.__init__ when available (SDK installed)
        if hasattr(super(), "__init__"):
            try:
                super().__init__(config)
            except TypeError:
                self._config = config or {}
        else:
            self._config = config or {}

    # Web-only plugin — no bridge tasks needed.
    async def on_startup(self) -> None:
        pass

    async def on_shutdown(self) -> None:
        pass

    async def on_message_received(self, msg: Any) -> None:
        pass

    # Compat shims for the original Integration protocol (pre-SDK).
    async def start(self, ctx: object) -> None:
        await self.on_startup()

    async def stop(self) -> None:
        await self.on_shutdown()

    async def on_inbound(self, msg: object) -> None:
        await self.on_message_received(msg)
