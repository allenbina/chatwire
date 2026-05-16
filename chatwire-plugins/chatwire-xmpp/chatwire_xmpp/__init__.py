"""chatwire-xmpp — XMPP relay integration for chatwire.

Bridges iMessage ↔ XMPP (Jabber) for whitelisted contacts (1:1 only, MVP).
Install with:
    pip install chatwire-xmpp

Then add to config.json:
    {
      "integrations": {
        "chatwire_xmpp": {
          "enabled": true,
          "jid": "bridge@example.com",
          "password": "s3cr3t",
          "server_url": "xmpp.example.com",   // optional; defaults to JID domain
          "contact_mappings": [
            {"imessage_handle": "+15551234567", "xmpp_jid": "alice@example.com"},
            {"imessage_handle": "bob@icloud.com", "xmpp_jid": "bob@example.com"}
          ]
        }
      }
    }

Messages flow:
  iMessage → on_inbound() → sends to mapped XMPP JID via slixmpp
  XMPP inbound handler → relays text to iMessage via ctx.send_text()

Only handles mapped (whitelisted) contacts; unknown senders are silently ignored.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Anti-spam error logging helper
# ---------------------------------------------------------------------------

def _log_send_future_error(fut: Any, label: str) -> None:
    """Done-callback for run_coroutine_threadsafe futures.

    Logs BroadcastBlockedError / RateLimitError so anti-spam blocks are not
    silently swallowed.  Never raises.
    """
    try:
        exc = fut.exception()
    except Exception:
        return
    if exc is None:
        return
    try:
        from chat_send import BroadcastBlockedError, RateLimitError  # noqa: PLC0415
    except ImportError:
        log.error("%s send failed: %s: %s", label, type(exc).__name__, exc)
        return
    if isinstance(exc, BroadcastBlockedError):
        log.error(
            "%s blocked by anti-spam fuse (step=%d): %s",
            label, exc.step, exc,
        )
    elif isinstance(exc, RateLimitError):
        log.warning("%s rate-limited: %s", label, exc)
    else:
        log.error("%s send failed: %s: %s", label, type(exc).__name__, exc)


# ---------------------------------------------------------------------------
# Lazy imports: integrations.base only available inside the chatwire install.
# ---------------------------------------------------------------------------
try:
    from integrations.base import BridgeContext, InboundMessage, SendTarget  # type: ignore[import]
except ImportError:  # pragma: no cover
    BridgeContext = object  # type: ignore[misc,assignment]
    InboundMessage = object  # type: ignore[misc,assignment]
    SendTarget = None  # type: ignore[misc,assignment]

# slixmpp is optional at import time so unit tests can import this module
# without the library installed.
try:
    import slixmpp  # type: ignore[import]
    from slixmpp import ClientXMPP  # type: ignore[import]
    _SLIXMPP_AVAILABLE = True
except ImportError:  # pragma: no cover
    slixmpp = None  # type: ignore[assignment]
    ClientXMPP = object  # type: ignore[misc,assignment]
    _SLIXMPP_AVAILABLE = False


class XMPPIntegration:
    """Bridge iMessage ↔ XMPP for a whitelisted set of contacts.

    Config keys
    -----------
    jid : str
        Full JID used by the bridge bot, e.g. ``bridge@example.com``.
    password : str
        Password for the XMPP account.
    server_url : str, optional
        XMPP server hostname.  Defaults to the domain part of *jid*.
    contact_mappings : list[dict]
        Each entry must have ``imessage_handle`` and ``xmpp_jid``.
    """

    NAME = "chatwire_xmpp"
    TIER = "official"  # Reviewed bridge; needs full message text for relay.
    DISPLAY_NAME = "XMPP Relay"
    DESCRIPTION = "Bridge iMessage ↔ XMPP (Jabber) for whitelisted contacts."
    ICON = "💬"

    SETTINGS_SCHEMA: dict[str, Any] = {
        "type": "object",
        "properties": {
            "enabled": {
                "type": "boolean",
                "default": False,
                "title": "Enable XMPP relay",
                "x-ui-order": 0,
            },
            "jid": {
                "type": "string",
                "title": "Bridge JID",
                "description": "Full JID for the bridge bot, e.g. bridge@example.com",
                "x-ui-placeholder": "bridge@example.com",
                "x-ui-order": 1,
            },
            "password": {
                "type": "string",
                "title": "Password",
                "description": "Password for the bridge XMPP account.",
                "x-ui-type": "password",
                "x-ui-order": 2,
            },
            "server_url": {
                "type": "string",
                "title": "XMPP server (optional)",
                "description": (
                    "Hostname of the XMPP server.  Leave blank to use the "
                    "domain part of the JID."
                ),
                "x-ui-placeholder": "xmpp.example.com",
                "x-ui-order": 3,
            },
            "contact_mappings": {
                "type": "array",
                "title": "Contact mappings",
                "description": (
                    "Map iMessage handles to XMPP JIDs.  Only mapped contacts "
                    "are relayed; all others are silently ignored."
                ),
                "x-ui-order": 4,
                "items": {
                    "type": "object",
                    "properties": {
                        "imessage_handle": {
                            "type": "string",
                            "title": "iMessage handle",
                            "description": "Phone number (+E.164) or email.",
                        },
                        "xmpp_jid": {
                            "type": "string",
                            "title": "XMPP JID",
                            "description": "Bare JID of the XMPP contact.",
                        },
                    },
                    "required": ["imessage_handle", "xmpp_jid"],
                },
                "default": [],
            },
        },
        "required": ["jid", "password"],
    }

    # ------------------------------------------------------------------

    def __init__(self, config: dict[str, Any]) -> None:
        self._jid: str = config.get("jid") or ""
        self._password: str = config.get("password") or ""
        self._server_url: str = config.get("server_url") or ""

        mappings_raw: list[dict] = config.get("contact_mappings") or []

        # imessage_handle → xmpp_jid  (for outbound relay)
        self._im_to_xmpp: dict[str, str] = {}
        # xmpp_jid (bare, lower) → imessage_handle  (for inbound relay)
        self._xmpp_to_im: dict[str, str] = {}
        for m in mappings_raw:
            handle = (m.get("imessage_handle") or "").strip()
            xjid = (m.get("xmpp_jid") or "").strip().lower()
            if handle and xjid:
                self._im_to_xmpp[handle] = xjid
                self._xmpp_to_im[xjid] = handle

        self._ctx: Any = None
        self._xmpp: Any = None  # slixmpp ClientXMPP instance

    # ------------------------------------------------------------------
    # Integration lifecycle
    # ------------------------------------------------------------------

    async def start(self, ctx: Any) -> None:
        if not self._jid:
            raise ValueError("chatwire_xmpp: 'jid' is required")
        if not self._password:
            raise ValueError("chatwire_xmpp: 'password' is required")
        if not _SLIXMPP_AVAILABLE:
            raise RuntimeError(
                "chatwire_xmpp: slixmpp is not installed.  "
                "Run: pip install slixmpp"
            )

        self._ctx = ctx

        # slixmpp uses its own asyncio event loop internally.  We run
        # connect/process on a dedicated thread so it doesn't block the
        # bridge's main loop.
        xmpp = ClientXMPP(self._jid, self._password)
        xmpp.add_event_handler("session_start", self._on_session_start)
        xmpp.add_event_handler("message", self._on_xmpp_message)
        self._xmpp = xmpp

        host = self._server_url or self._jid.split("@")[-1]
        xmpp.connect((host, 5222))

        # Run slixmpp's event loop in a background thread.
        t = threading.Thread(
            target=xmpp.process,
            kwargs={"forever": True},
            name="chatwire-xmpp-thread",
            daemon=True,
        )
        t.start()

        log.info(
            "xmpp integration started; JID=%s, %d mapping(s)",
            self._jid,
            len(self._im_to_xmpp),
        )

    async def stop(self) -> None:
        if self._xmpp is not None:
            try:
                self._xmpp.disconnect()
            except Exception:
                pass
            self._xmpp = None
        log.info("xmpp integration stopped")

    # ------------------------------------------------------------------
    # iMessage → XMPP
    # ------------------------------------------------------------------

    async def on_inbound(self, msg: Any) -> None:
        """Relay an inbound iMessage to the mapped XMPP JID."""
        if self._xmpp is None:
            return

        handle = getattr(msg, "handle", None) or ""
        xjid = self._im_to_xmpp.get(handle)
        if not xjid:
            return  # not a mapped contact; silently ignore

        text = (getattr(msg, "text", None) or "").strip()
        if not text:
            return  # no text to relay (photo-only messages unsupported in MVP)

        try:
            self._xmpp.send_message(mto=xjid, mbody=text, mtype="chat")
            log.debug("xmpp: relayed iMessage from %s → %s", handle, xjid)
        except Exception as exc:
            log.warning("xmpp: failed to relay message: %s", exc)

    # ------------------------------------------------------------------
    # XMPP → iMessage
    # ------------------------------------------------------------------

    def _on_session_start(self, event: Any) -> None:
        """Called by slixmpp when the XMPP session is established."""
        try:
            self._xmpp.send_presence()
            log.info("xmpp: session started, presence sent")
        except Exception as exc:
            log.warning("xmpp: error sending presence: %s", exc)

    def _on_xmpp_message(self, msg: Any) -> None:
        """Called by slixmpp for every incoming XMPP message."""
        if msg.get("type") not in ("chat", "normal"):
            return

        sender_jid = str(msg.get("from", "")).split("/")[0].lower()
        im_handle = self._xmpp_to_im.get(sender_jid)
        if not im_handle:
            return  # not a mapped contact

        body = str(msg.get("body") or "").strip()
        if not body:
            return

        if self._ctx is None or SendTarget is None:
            return  # pragma: no cover

        target = SendTarget(
            kind="handle",
            value=im_handle,
            label=self._ctx.name_for(im_handle) or im_handle,
        )

        # slixmpp runs in a thread; schedule the coroutine on the bridge loop.
        loop: asyncio.AbstractEventLoop | None = getattr(
            self._ctx, "_loop", None
        ) or asyncio.get_event_loop()
        fut = asyncio.run_coroutine_threadsafe(
            self._ctx.send_text(target, body), loop
        )
        label = f"xmpp:{sender_jid}"
        fut.add_done_callback(lambda f: _log_send_future_error(f, label))
        log.debug("xmpp: relayed XMPP from %s → iMessage %s", sender_jid, im_handle)
