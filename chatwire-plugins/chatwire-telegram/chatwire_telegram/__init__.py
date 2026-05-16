"""chatwire-telegram — Two-way iMessage ↔ Telegram bridge.

Relays every inbound iMessage to a Telegram bot chat with "From <name>:" prefix.
Supports replying back via Telegram, /send <contact> <text>, and photo uploads.

Install with:
    pipx inject chatwire chatwire-telegram
    # or: pip install chatwire-telegram

Then add to config.json:
    {
      "integrations": {
        "chatwire_telegram": {
          "enabled": true,
          "bot_token": "123456:ABC-...",
          "allowed_user_ids": [12345678]
        }
      }
    }

The first entry in allowed_user_ids is the delivery target (the Telegram user or
group that receives all iMessages). Additional IDs may issue /send commands.
"""
from __future__ import annotations

import asyncio
import logging
import re
import tempfile
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports: core chatwire modules are only available when installed inside
# the chatwire bridge environment. The bridge injects sys.path before loading
# entry-point plugins so these imports succeed at runtime.
# ---------------------------------------------------------------------------
try:
    from integrations.base import BridgeContext, InboundMessage, SendTarget  # type: ignore[import]
except ImportError:  # pragma: no cover
    BridgeContext = object  # type: ignore[misc,assignment]
    InboundMessage = object  # type: ignore[misc,assignment]
    SendTarget = None  # type: ignore[misc,assignment]

try:
    from telegram import Update, BotCommand
    from telegram.ext import (
        Application, CommandHandler, ContextTypes, MessageHandler, filters,
    )
    _TELEGRAM_AVAILABLE = True
except ImportError:  # pragma: no cover
    _TELEGRAM_AVAILABLE = False

_CHUNK = 4096  # Telegram message length limit


def _chunk_text(text: str) -> list[str]:
    if not text:
        return ["(empty)"]
    parts: list[str] = []
    while len(text) > _CHUNK:
        split = text.rfind("\n", 0, _CHUNK)
        split = split if split > _CHUNK // 2 else _CHUNK
        parts.append(text[:split])
        text = text[split:].lstrip("\n")
    if text:
        parts.append(text)
    return parts


class TelegramIntegration:
    """Two-way iMessage ↔ Telegram bridge.

    Relays inbound iMessages to a Telegram chat; Telegram replies are sent
    back as iMessages to the most-recently-active conversation.
    """

    NAME = "chatwire_telegram"
    TIER = "official"
    DISPLAY_NAME = "Telegram bridge"
    DESCRIPTION = "Two-way relay: every iMessage appears in Telegram, replies go back as iMessages."
    ICON = "💬"

    SETTINGS_SCHEMA: dict[str, Any] = {
        "type": "object",
        "properties": {
            "enabled": {
                "type": "boolean",
                "default": False,
                "title": "Enable Telegram bridge",
                "x-ui-order": 0,
            },
            "bot_token": {
                "type": "string",
                "title": "Bot token",
                "description": (
                    "Obtain from @BotFather (/newbot). "
                    "Looks like '123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11'."
                ),
                "x-ui-type": "password",
                "x-ui-order": 1,
            },
            "allowed_user_ids": {
                "type": "array",
                "title": "Allowed Telegram user IDs",
                "description": (
                    "Numeric Telegram user IDs permitted to interact with the bot. "
                    "The first ID receives all inbound iMessage relays. "
                    "Use @userinfobot to find your ID."
                ),
                "items": {"type": "integer"},
                "default": [],
                "x-ui-order": 2,
            },
            "relay_prefix": {
                "type": "boolean",
                "title": "Show 'From <name>:' prefix",
                "description": "Prepend the sender name to each relayed message.",
                "default": True,
                "x-ui-order": 3,
            },
        },
        "required": ["bot_token", "allowed_user_ids"],
    }

    def __init__(self, config: dict[str, Any]) -> None:
        self._token: str = config.get("bot_token") or ""
        self._allowed: list[int] = [int(i) for i in (config.get("allowed_user_ids") or [])]
        self._relay_prefix: bool = bool(config.get("relay_prefix", True))
        self._ctx: Any = None
        self._app: Any = None
        # Track the last handle seen so free-text replies have a default target
        self._last_handle: str = ""
        self._last_group_guid: str = ""

    def _delivery_chat(self) -> int | None:
        return self._allowed[0] if self._allowed else None

    async def start(self, ctx: Any) -> None:
        if not _TELEGRAM_AVAILABLE:
            raise RuntimeError(
                "chatwire_telegram: python-telegram-bot is not installed. "
                "Run: pip install chatwire-telegram"
            )
        if not self._token:
            raise ValueError("chatwire_telegram: 'bot_token' is required")
        if not self._allowed:
            raise ValueError("chatwire_telegram: 'allowed_user_ids' must not be empty")

        self._ctx = ctx
        self._app = (
            Application.builder()
            .token(self._token)
            .build()
        )

        # Register handlers
        app = self._app
        allowed = set(self._allowed)

        async def _guard(update: Any, ctx_: Any) -> bool:
            uid = update.effective_user.id if update.effective_user else None
            return uid in allowed

        async def _reply_lockout_error(update: Any, exc: Exception) -> None:
            """Reply to the Telegram user with a human-readable lockout message."""
            try:
                from chat_send import BroadcastBlockedError, RateLimitError  # noqa: PLC0415
            except ImportError:
                return
            msg_obj = getattr(update, "message", None)
            if msg_obj is None:
                return
            if isinstance(exc, BroadcastBlockedError):
                await msg_obj.reply_text(f"Chatwire locked: {exc}")
            elif isinstance(exc, RateLimitError):
                await msg_obj.reply_text(f"Rate limit: {exc}")

        async def cmd_send(update: Any, ctx_: Any) -> None:
            if not await _guard(update, ctx_):
                return
            args = ctx_.args or []
            if len(args) < 2:
                await update.message.reply_text("Usage: /send <contact> <message>")
                return
            contact, text = args[0], " ".join(args[1:])
            if SendTarget is not None:
                target = SendTarget(kind="handle", value=contact, label=contact)
                try:
                    await self._ctx.send_text(target, text)
                except Exception as exc:
                    await _reply_lockout_error(update, exc)
                    raise

        async def on_message(update: Any, ctx_: Any) -> None:
            if not await _guard(update, ctx_):
                return
            msg = update.message
            if not msg or not msg.text:
                return
            text = msg.text.strip()
            # Default: reply to the last active conversation
            if self._last_handle and SendTarget is not None:
                target = SendTarget(kind="handle", value=self._last_handle, label=self._last_handle)
                try:
                    await self._ctx.send_text(target, text)
                except Exception as exc:
                    await _reply_lockout_error(update, exc)
                    raise
            elif self._last_group_guid and SendTarget is not None:
                target = SendTarget(kind="chat", value=self._last_group_guid, label="Group")
                try:
                    await self._ctx.send_text(target, text)
                except Exception as exc:
                    await _reply_lockout_error(update, exc)
                    raise
            else:
                await msg.reply_text("No active conversation — use /send <contact> <message>")

        app.add_handler(CommandHandler("send", cmd_send))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        log.info("telegram bridge started")

    async def stop(self) -> None:
        if self._app is not None:
            try:
                await self._app.updater.stop()
                await self._app.stop()
                await self._app.shutdown()
            except Exception as exc:
                log.warning("telegram stop error: %s", exc)
            self._app = None
        log.info("telegram bridge stopped")

    async def on_inbound(self, msg: Any) -> None:
        """Relay an inbound iMessage to the delivery Telegram chat."""
        if self._app is None:
            return
        chat_id = self._delivery_chat()
        if chat_id is None:
            return

        # Update last-active conversation for free-text replies
        if getattr(msg, "is_group", False):
            self._last_group_guid = getattr(msg, "chat_guid", "") or self._last_group_guid
            self._last_handle = ""
        else:
            self._last_handle = getattr(msg, "handle", "") or self._last_handle
            self._last_group_guid = ""

        sender = getattr(msg, "sender_name", None) or getattr(msg, "handle", "Unknown")
        text = (getattr(msg, "text", None) or "").strip()
        has_atts = getattr(msg, "has_attachments", False)

        if not text and has_atts:
            text = "[attachment]"

        body = f"From {sender}:\n{text}" if self._relay_prefix else text

        bot = self._app.bot
        for chunk in _chunk_text(body):
            try:
                await bot.send_message(chat_id=chat_id, text=chunk)
            except Exception as exc:
                log.warning("telegram send failed: %s", exc)
                break
