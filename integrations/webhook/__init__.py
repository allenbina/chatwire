"""Webhook-out integration.

POSTs every inbound iMessage event to a user-configured URL. The simplest
possible third-party-shaped integration — no SDK, no long-lived connection,
no callback routing. Useful as:

  - A bridge to Zapier / n8n / Make / Pipedream without writing per-service
    code.
  - A poor-man's audit log: point it at a server you control and you have a
    JSONL feed of every relayed message.
  - The reference for what an integration looks like end-to-end.

Outbound (webhook -> iMessage) is intentionally not implemented in this
direction. A future inbound-webhook integration could accept POSTs and call
ctx.send_text, but that needs auth and lives in its own module.

Config block (under `integrations.webhook` in config.json):

    {
        "enabled": true,
        "url": "https://example.com/hooks/imessage",
        "secret": "optional shared secret",
        "timeout_s": 10
    }

If `secret` is set, requests carry an `X-Chatwire-Signature: sha256=<hex>`
header containing HMAC-SHA256(secret, body). Receivers should reject
mismatches.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from typing import Any

import httpx

from integrations.base import BridgeContext, InboundMessage

log = logging.getLogger("chatwire.webhook")


class WebhookIntegration:
    NAME = "webhook"
    DISPLAY_NAME = "Webhook"
    DESCRIPTION = "POST every inbound iMessage to a URL"
    ICON = "🔗"

    SETTINGS_SCHEMA = {
        "type": "object",
        "properties": {
            "enabled": {
                "type": "boolean",
                "default": False,
                "title": "Enable webhook integration",
            },
            "url": {
                "type": "string",
                "format": "uri",
                "title": "Webhook URL",
                "description": "Each inbound iMessage is POSTed here as JSON.",
            },
            "secret": {
                "type": "string",
                "title": "Shared secret (optional)",
                "description": (
                    "If set, requests carry X-Chatwire-Signature: "
                    "sha256=<hmac> so the receiver can verify the sender."
                ),
            },
            "timeout_s": {
                "type": "number",
                "default": 10,
                "minimum": 1,
                "maximum": 60,
                "title": "Request timeout (seconds)",
            },
        },
        "required": ["url"],
    }

    def __init__(self, config: dict[str, Any]):
        self._config = config
        self._url: str = config.get("url", "")
        self._secret: str = config.get("secret", "") or ""
        self._timeout_s: float = float(config.get("timeout_s", 10))
        self._ctx: BridgeContext | None = None
        self._client: httpx.AsyncClient | None = None

    async def start(self, ctx: BridgeContext) -> None:
        if not self._url:
            raise ValueError("webhook integration: 'url' is required")
        self._ctx = ctx
        self._client = httpx.AsyncClient(timeout=self._timeout_s)
        log.info("webhook integration started; posting to %s", self._url)

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        log.info("webhook integration stopped")

    async def on_inbound(self, msg: InboundMessage) -> None:
        if self._client is None:
            return  # not started, or already stopped — silently drop

        payload = self._payload_for(msg)
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._secret:
            sig = hmac.new(
                self._secret.encode("utf-8"),
                body,
                hashlib.sha256,
            ).hexdigest()
            headers["X-Chatwire-Signature"] = f"sha256={sig}"

        try:
            r = await self._client.post(self._url, content=body, headers=headers)
            if r.status_code >= 400:
                log.warning("webhook POST %s -> %d %s",
                            self._url, r.status_code, r.text[:200])
        except (httpx.HTTPError, asyncio.TimeoutError) as e:
            # Don't re-raise: a flaky webhook receiver shouldn't take the
            # whole bridge down or stall the inbound poll loop.
            log.warning("webhook POST failed: %s: %s", type(e).__name__, e)

    @staticmethod
    def _payload_for(msg: InboundMessage) -> dict[str, Any]:
        """Render an InboundMessage as a JSON-friendly dict.

        Stable shape — third-party receivers pin to this. Bumping `v` is the
        signal that fields changed in a non-additive way; additive changes
        keep `v` the same.
        """
        return {
            "v": 1,
            "rowid": msg.rowid,
            "handle": msg.handle,
            "text": msg.text,
            "is_from_me": bool(msg.is_from_me),
            "attachments": [
                {
                    "path": str(a.path),
                    "mime_type": a.mime_type,
                    "ready": bool(a.ready),
                }
                for a in msg.attachments
            ],
            "parent": (
                {
                    "handle": msg.parent_handle,
                    "text": msg.parent_text,
                    "is_from_me": bool(msg.parent_is_from_me),
                }
                if msg.parent_handle or msg.parent_text
                else None
            ),
            "chat": (
                {
                    "guid": msg.chat_guid,
                    "identifier": msg.chat_identifier,
                    "name": msg.chat_name,
                    "is_group": bool(msg.is_group),
                }
                if msg.chat_guid
                else None
            ),
        }
