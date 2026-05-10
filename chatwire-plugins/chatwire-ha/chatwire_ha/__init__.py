"""chatwire-ha — Home Assistant integration for chatwire.

Triggers HA automations/scenes/services via exact iMessage keyword matching.
Install with:
    pip install chatwire-ha

Then add to config.json:
    {
      "integrations": {
        "chatwire_ha": {
          "enabled": true,
          "ha_url": "http://homeassistant.local:8123",
          "access_token": "<long-lived token>",
          "commands": [
            {"keyword": "lights off", "domain": "light", "service": "turn_off",
             "entity_id": "light.living_room", "description": "Living room lights off"},
            {"keyword": "good night", "domain": "scene", "service": "turn_on",
             "entity_id": "scene.night_mode", "description": "Night mode scene"}
          ]
        }
      }
    }
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports: integrations.base is only available when installed inside the
# chatwire tree.  External packages reference it the same way; the bridge
# injects sys.path before loading entry-point plugins.
# ---------------------------------------------------------------------------
try:
    from integrations.base import BridgeContext, InboundMessage, SendTarget  # type: ignore[import]
except ImportError:  # pragma: no cover — only missing in isolated unit tests
    BridgeContext = object  # type: ignore[misc,assignment]
    InboundMessage = object  # type: ignore[misc,assignment]
    SendTarget = None  # type: ignore[misc,assignment]


class HAIntegration:
    """Trigger Home Assistant services via iMessage keyword commands.

    Each inbound message is checked against the configured keyword list
    (stripped, lowercased, exact match).  On a hit the integration POSTs to
    the HA services API and replies to the sender with "Done: <description>".
    """

    NAME = "chatwire_ha"
    TIER = "notify"  # Third-party; receives SanitizedEvent only (no message text).
    DISPLAY_NAME = "Home Assistant"
    DESCRIPTION = "Trigger HA automations/scenes via iMessage keywords."
    ICON = "🏠"

    SETTINGS_SCHEMA: dict[str, Any] = {
        "type": "object",
        "properties": {
            "enabled": {
                "type": "boolean",
                "default": False,
                "title": "Enable Home Assistant integration",
                "x-ui-order": 0,
            },
            "ha_url": {
                "type": "string",
                "title": "Home Assistant URL",
                "description": "Base URL of your HA instance, e.g. http://homeassistant.local:8123",
                "x-ui-placeholder": "http://homeassistant.local:8123",
                "x-ui-order": 1,
            },
            "access_token": {
                "type": "string",
                "title": "Long-lived access token",
                "description": (
                    "Create one in HA under Profile → Long-Lived Access Tokens."
                ),
                "x-ui-type": "password",
                "x-ui-order": 2,
            },
            "commands": {
                "type": "array",
                "title": "Command mappings",
                "description": (
                    "List of keyword → HA service mappings.  Each keyword is "
                    "matched case-insensitively against the full message text."
                ),
                "x-ui-order": 3,
                "items": {
                    "type": "object",
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "title": "Keyword",
                            "description": "Exact phrase the sender types (case-insensitive).",
                        },
                        "domain": {
                            "type": "string",
                            "title": "HA domain",
                            "description": "e.g. light, switch, scene, automation",
                        },
                        "service": {
                            "type": "string",
                            "title": "HA service",
                            "description": "e.g. turn_on, turn_off, trigger",
                        },
                        "entity_id": {
                            "type": "string",
                            "title": "Entity ID",
                            "description": "e.g. light.living_room, scene.night_mode",
                        },
                        "description": {
                            "type": "string",
                            "title": "Description",
                            "description": "Human-readable label sent back as the reply.",
                        },
                    },
                    "required": ["keyword", "domain", "service", "entity_id", "description"],
                },
                "default": [],
            },
        },
        "required": ["ha_url", "access_token"],
    }

    # ------------------------------------------------------------------

    def __init__(self, config: dict[str, Any]) -> None:
        self._ha_url: str = (config.get("ha_url") or "").rstrip("/")
        self._access_token: str = config.get("access_token") or ""
        commands_raw: list[dict] = config.get("commands") or []

        # Build lowercased-keyword → command mapping once at startup.
        self._commands: dict[str, dict[str, str]] = {}
        for cmd in commands_raw:
            kw = (cmd.get("keyword") or "").strip().lower()
            if kw:
                self._commands[kw] = {
                    "domain": cmd.get("domain", ""),
                    "service": cmd.get("service", ""),
                    "entity_id": cmd.get("entity_id", ""),
                    "description": cmd.get("description", ""),
                }

        self._ctx: Any = None
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Integration lifecycle
    # ------------------------------------------------------------------

    async def start(self, ctx: Any) -> None:
        if not self._ha_url:
            raise ValueError("chatwire_ha: 'ha_url' is required")
        if not self._access_token:
            raise ValueError("chatwire_ha: 'access_token' is required")

        self._ctx = ctx
        self._client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {self._access_token}"},
            timeout=10.0,
        )
        log.info(
            "home_assistant integration started; HA at %s, %d command(s) registered",
            self._ha_url,
            len(self._commands),
        )

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        log.info("home_assistant integration stopped")

    async def on_inbound(self, msg: Any) -> None:
        """Check for a keyword match and fire the corresponding HA service."""
        if self._client is None or self._ctx is None:
            return  # not started or already stopped — silently drop

        text = (msg.text or "").strip().lower()
        cmd = self._commands.get(text)
        if cmd is None:
            return  # not a recognised keyword

        domain = cmd["domain"]
        service = cmd["service"]
        entity_id = cmd["entity_id"]
        description = cmd["description"] or f"{domain}.{service}"

        url = f"{self._ha_url}/api/services/{domain}/{service}"
        try:
            r = await self._client.post(url, json={"entity_id": entity_id})
            if r.status_code >= 400:
                log.warning(
                    "HA service call %s -> HTTP %d: %s",
                    url, r.status_code, r.text[:200],
                )
                return
        except (httpx.HTTPError, asyncio.TimeoutError) as exc:
            log.warning(
                "HA service call failed: %s: %s", type(exc).__name__, exc
            )
            return

        # Reply to the sender (1:1 or group).
        if SendTarget is None:
            return  # pragma: no cover

        if msg.is_group:
            target = SendTarget(
                kind="chat",
                value=msg.chat_guid,
                label=msg.chat_name or msg.chat_identifier,
            )
        else:
            label = self._ctx.name_for(msg.handle) or msg.handle
            target = SendTarget(
                kind="handle",
                value=msg.handle,
                label=label,
            )

        await self._ctx.send_text(target, f"Done: {description}")
