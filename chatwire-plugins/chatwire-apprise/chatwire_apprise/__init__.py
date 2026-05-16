"""chatwire-apprise — Multi-service push notifications for chatwire.

Delivers inbound message notifications via any Apprise-supported service:
ntfy.sh, Pushover, Slack, Gotify, Matrix, Discord, PushBullet, and 80+
others.  Replaces the narrower chatwire-ntfy plugin (ntfy users can migrate
by adding ``ntfy://<topic>`` to the URLs field).

Install with:
    pipx inject chatwire chatwire-apprise
    # or: pip install chatwire-apprise

Then enable via Settings → Plugins → Apprise, or add to config.json:

    {
      "integrations": {
        "chatwire_apprise": {
          "enabled": true,
          "urls": "ntfy://my-topic\\ndiscord://webhookid/webhooktoken"
        }
      }
    }

Each URL is on its own line.  Apprise URL format:
  https://github.com/caronc/apprise/wiki
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

log = logging.getLogger(__name__)

_MAX_BODY = 200  # max chars of preview text in notification body


class AppriseIntegration:
    """Send push notifications via Apprise for every inbound message.

    One ``apprise.Apprise`` instance is created at startup and reused for
    all ``on_notify`` calls; individual URL failures are logged but do not
    propagate.
    """

    NAME = "chatwire_apprise"
    TIER = "notify"
    DISPLAY_NAME = "Apprise notifications"
    DESCRIPTION = (
        "Push notifications via ntfy, Slack, Discord, Pushover, and 80+ services "
        "using Apprise URL format.  Replaces chatwire-ntfy."
    )
    ICON = "📣"

    SETTINGS_SCHEMA: dict[str, Any] = {
        "type": "object",
        "properties": {
            "enabled": {
                "type": "boolean",
                "default": False,
                "title": "Enable Apprise notifications",
                "x-ui-order": 0,
            },
            "urls": {
                "type": "string",
                "title": "Apprise URLs",
                "description": (
                    "One Apprise URL per line. Examples:\n"
                    "  ntfy://my-topic\n"
                    "  ntfy://user:password@ntfy.sh/my-topic\n"
                    "  discord://webhookid/webhooktoken\n"
                    "  slack://TokenA/TokenB/TokenC\n"
                    "Full list: https://github.com/caronc/apprise/wiki"
                ),
                "default": "",
                "x-ui-widget": "textarea",
                "x-ui-placeholder": "ntfy://my-imessages-abc123",
                "x-ui-order": 1,
            },
            "title_format": {
                "type": "string",
                "title": "Notification title",
                "description": (
                    "Template for the notification title.  "
                    "{sender} is replaced with the contact name."
                ),
                "default": "{sender}",
                "x-ui-order": 2,
            },
        },
        "required": [],
    }

    def __init__(self, config: dict[str, Any]) -> None:
        self._raw_urls: str = (config.get("urls") or "").strip()
        self._title_fmt: str = (config.get("title_format") or "{sender}").strip() or "{sender}"
        self._apprise: Any = None  # apprise.Apprise, set in start()
        self._loop: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self, ctx: Any) -> None:
        try:
            import apprise  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "chatwire-apprise requires the 'apprise' package. "
                "Install with: pipx inject chatwire apprise"
            ) from exc

        self._apprise = apprise.Apprise()
        loaded = 0
        for line in self._raw_urls.splitlines():
            url = line.strip()
            if url and not url.startswith("#"):
                self._apprise.add(url)
                loaded += 1
        self._loop = asyncio.get_event_loop()
        log.info("apprise integration started — %d URL(s) loaded", loaded)

    async def stop(self) -> None:
        self._apprise = None
        log.info("apprise integration stopped")

    # ------------------------------------------------------------------
    # Notification handler
    # ------------------------------------------------------------------

    async def on_notify(self, event: Any) -> None:
        """Send an Apprise push notification for each inbound event."""
        if self._apprise is None:
            return

        sender = getattr(event, "sender_display_name", None) or "iMessage"
        title = self._title_fmt.format(sender=sender)

        preview = getattr(event, "preview", None)
        has_att = getattr(event, "has_attachment", False)
        is_group = getattr(event, "is_group", False)
        group_name = getattr(event, "group_name", None)

        if preview:
            body = preview[:_MAX_BODY] + ("…" if len(preview) > _MAX_BODY else "")
        elif has_att:
            body = "[attachment]"
        else:
            body = "New message"

        if is_group and group_name:
            body = f"[{group_name}] {body}"

        try:
            await asyncio.to_thread(
                self._apprise.notify,
                body=body,
                title=title,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("apprise notify failed: %s: %s", type(exc).__name__, exc)
