"""Stats integration — built-in messaging analytics.

Web-only plugin: no bridge connection, no background tasks. Exposes
a date_range setting that the /plugins/stats/report route reads when
generating the analytics page.

Config block (under ``integrations.stats`` in config.json):

    {
        "enabled": true,
        "date_range": "30d"
    }
"""
from __future__ import annotations

from typing import Any


class StatsIntegration:
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
        self._config = config or {}

    async def start(self, ctx: object) -> None:  # no-op: web-only plugin
        pass

    async def stop(self) -> None:  # no-op
        pass

    async def on_inbound(self, msg: object) -> None:  # no-op
        pass
