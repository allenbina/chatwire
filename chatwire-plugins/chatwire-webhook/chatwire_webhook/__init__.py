"""chatwire-webhook — POST every inbound iMessage to a webhook URL.

The simplest possible integration — no SDK, no long-lived connection. Useful as:
  - A bridge to Zapier / n8n / Make / Pipedream without writing per-service code.
  - An audit log: point at a server you control for a JSONL feed of every message.
  - The reference implementation for what a chatwire integration looks like.

Install with:
    pipx inject chatwire chatwire-webhook
    # or: pip install chatwire-webhook

Then add to config.json:
    {
      "integrations": {
        "chatwire_webhook": {
          "enabled": true,
          "url": "https://example.com/hooks/imessage",
          "secret": "optional-shared-secret",
          "timeout_s": 10
        }
      }
    }

If `secret` is set, requests carry an X-Chatwire-Signature: sha256=<hex> header
containing HMAC-SHA256(secret, body). Receivers should verify the signature.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports: integrations.base is only available inside the chatwire bridge.
# The bridge injects sys.path before loading plugins so these work at runtime.
# ---------------------------------------------------------------------------
try:
    from integrations.base import BridgeContext, InboundMessage  # type: ignore[import]
except ImportError:  # pragma: no cover
    BridgeContext = object  # type: ignore[misc,assignment]
    InboundMessage = object  # type: ignore[misc,assignment]

try:
    from web import log_stream as _ls  # type: ignore[import]
    _HAS_LOG_STREAM = True
except ImportError:  # pragma: no cover
    _ls = None  # type: ignore[assignment]
    _HAS_LOG_STREAM = False


def _ls_info(tag: str, msg: str) -> None:
    if _HAS_LOG_STREAM and _ls is not None:
        _ls.info(tag, msg)


def _ls_warn(tag: str, msg: str) -> None:
    if _HAS_LOG_STREAM and _ls is not None:
        _ls.warn(tag, msg)


def _ls_error(tag: str, msg: str) -> None:
    if _HAS_LOG_STREAM and _ls is not None:
        _ls.error(tag, msg)


class WebhookIntegration:
    """POST every inbound iMessage to a configured webhook URL.

    POSTs a stable JSON payload (v=1) for every message. If a shared secret
    is configured, requests include an HMAC-SHA256 signature header so the
    receiver can verify authenticity.
    """

    NAME = "chatwire_webhook"
    TIER = "official"
    DISPLAY_NAME = "Webhook"
    DESCRIPTION = "POST every inbound iMessage to a URL (Zapier, n8n, Make, etc.)"
    ICON = "🔗"

    SETTINGS_SCHEMA: dict[str, Any] = {
        "type": "object",
        "properties": {
            "enabled": {
                "type": "boolean",
                "default": False,
                "title": "Enable webhook integration",
                "x-ui-order": 0,
            },
            "url": {
                "type": "string",
                "format": "uri",
                "title": "Webhook URL",
                "description": "Each inbound iMessage is POSTed here as JSON.",
                "x-ui-placeholder": "https://example.com/hooks/imessage",
                "x-ui-order": 1,
            },
            "secret": {
                "type": "string",
                "title": "Shared secret (optional)",
                "description": (
                    "If set, requests carry X-Chatwire-Signature: sha256=<hmac> "
                    "so the receiver can verify the sender."
                ),
                "default": "",
                "x-ui-type": "password",
                "x-ui-order": 2,
            },
            "timeout_s": {
                "type": "number",
                "default": 10,
                "minimum": 1,
                "maximum": 60,
                "title": "Request timeout (seconds)",
                "x-ui-order": 3,
            },
        },
        "required": ["url"],
    }

    def __init__(self, config: dict[str, Any]) -> None:
        self._url: str = config.get("url") or ""
        self._secret: str = config.get("secret") or ""
        self._timeout_s: float = float(config.get("timeout_s") or 10)
        self._client: httpx.AsyncClient | None = None

    async def start(self, ctx: Any) -> None:
        if not self._url:
            raise ValueError("chatwire_webhook: 'url' is required")
        self._client = httpx.AsyncClient(timeout=self._timeout_s)
        log.info("webhook integration started; posting to %s", self._url)

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        log.info("webhook integration stopped")

    async def on_inbound(self, msg: Any) -> None:
        """POST the inbound message as JSON to the configured URL."""
        if self._client is None:
            return

        payload = self._payload_for(msg)
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        headers: dict[str, str] = {"Content-Type": "application/json"}
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
                log.warning("webhook POST %s -> %d %s", self._url, r.status_code, r.text[:200])
                _ls_warn("webhook", f"POST {self._url} → {r.status_code}")
            else:
                _ls_info("webhook", f"POST {self._url} → {r.status_code}")
        except (httpx.HTTPError, asyncio.TimeoutError) as exc:
            log.warning("webhook POST failed: %s: %s", type(exc).__name__, exc)
            _ls_error("webhook", f"POST {self._url} failed: {type(exc).__name__}: {exc}")

    @staticmethod
    def _payload_for(msg: Any) -> dict[str, Any]:
        """Render an InboundMessage as a stable JSON-friendly dict.

        Shape is versioned (v=1). Additive changes keep v=1; breaking changes
        increment it so receivers can detect incompatible updates.
        """
        attachments = []
        for a in (getattr(msg, "attachments", None) or []):
            attachments.append({
                "path": str(getattr(a, "path", "")),
                "mime_type": getattr(a, "mime_type", ""),
                "ready": bool(getattr(a, "ready", False)),
            })

        parent_handle = getattr(msg, "parent_handle", None)
        parent_text = getattr(msg, "parent_text", None)
        parent_is_from_me = getattr(msg, "parent_is_from_me", None)

        chat_guid = getattr(msg, "chat_guid", None)
        chat_identifier = getattr(msg, "chat_identifier", None)
        chat_name = getattr(msg, "chat_name", None)
        is_group = getattr(msg, "is_group", False)

        return {
            "v": 1,
            "rowid": getattr(msg, "rowid", None),
            "handle": getattr(msg, "handle", ""),
            "text": getattr(msg, "text", ""),
            "is_from_me": bool(getattr(msg, "is_from_me", False)),
            "attachments": attachments,
            "parent": (
                {
                    "handle": parent_handle,
                    "text": parent_text,
                    "is_from_me": bool(parent_is_from_me),
                }
                if parent_handle or parent_text
                else None
            ),
            "chat": (
                {
                    "guid": chat_guid,
                    "identifier": chat_identifier,
                    "name": chat_name,
                    "is_group": bool(is_group),
                }
                if chat_guid
                else None
            ),
        }
