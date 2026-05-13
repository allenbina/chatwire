"""chatwire-mqtt — Publish every inbound iMessage to an MQTT broker,
and optionally send iMessages via an outbound MQTT topic.

Useful for home-automation pipelines (Home Assistant, Node-RED, OpenHAB)
and any subscriber that can speak MQTT.

Install with:
    pipx inject chatwire chatwire-mqtt
    # or: pip install chatwire-mqtt

Then add to config.json:
    {
      "integrations": {
        "chatwire_mqtt": {
          "enabled": true,
          "host": "192.168.1.100",
          "port": 1883,
          "topic": "chatwire/messages",
          "username": "mqttuser",
          "password": "s3cr3t",
          "qos": 0,
          "use_tls": false,
          "ca_cert": "",
          "send_topic": "chatwire/send"
        }
      }
    }

TLS / encrypted brokers
-----------------------
Set ``use_tls: true`` to connect over TLS (typical port: 8883).
Leave ``ca_cert`` blank to verify with the system CA bundle, or set it to
the path of a PEM-formatted CA certificate file for self-signed brokers::

    "use_tls": true,
    "port": 8883,
    "ca_cert": "/etc/ssl/certs/my-broker-ca.pem"

Published topic layout
-----------------------
  1:1 message  →  <topic>/<sanitized_handle>
  Group chat   →  <topic>/group/<sanitized_chat_identifier>

The JSON payload (v=1) schema:
  {
    "v": 1,
    "rowid": 12345,
    "handle": "+15551234567",
    "text": "Hey!",
    "is_from_me": false,
    "chat": {
      "guid": "iMessage;-;+15551234567",
      "identifier": "+15551234567",
      "name": null,
      "is_group": false
    }
  }

Outbound relay (MQTT → iMessage)
---------------------------------
Set ``send_topic`` to a topic string (e.g. ``chatwire/send``) to subscribe
for outbound sends.  Publish a JSON payload to that topic and chatwire will
send an iMessage on your behalf::

  # 1:1 message
  {"handle": "+15551234567", "text": "Hello from Node-RED!"}

  # Group chat (use the chat GUID from the inbound payload's chat.guid)
  {"chat": "iMessage;+;chat629...", "text": "Hi group!", "label": "My Group"}

Both ``handle`` and ``text`` (or ``chat`` and ``text``) are required.
``label`` is optional and used only for logging.

Leave ``send_topic`` blank (the default) to disable inbound subscriptions.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports: integrations.base is only available inside the chatwire bridge.
# ---------------------------------------------------------------------------
try:
    from integrations.base import BridgeContext, InboundMessage, SendTarget  # type: ignore[import]
except ImportError:  # pragma: no cover
    BridgeContext = object  # type: ignore[misc,assignment]
    InboundMessage = object  # type: ignore[misc,assignment]
    SendTarget = None  # type: ignore[assignment]

# paho-mqtt is optional at import time so unit tests can import this module
# without the library installed.
try:
    import paho.mqtt.client as _paho  # type: ignore[import]
    _PAHO_AVAILABLE = True
except ImportError:  # pragma: no cover
    _paho = None  # type: ignore[assignment]
    _PAHO_AVAILABLE = False

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


# MQTT topic segments may not contain +, #, NUL, or /  (per spec §4.7).
_UNSAFE_TOPIC = re.compile(r'[+#/\x00]')


def _sanitize_topic_segment(s: str) -> str:
    """Replace MQTT-reserved characters with underscores for safe topic use."""
    return _UNSAFE_TOPIC.sub('_', s) or "_"


class MQTTIntegration:
    """Publish every inbound iMessage to an MQTT broker.

    Each message is serialised as JSON and published to:
      <topic>/<handle>           (1:1 conversations)
      <topic>/group/<chat_id>    (group chats)

    Handle and chat_id are sanitized to replace MQTT wildcard characters
    (+, #, /) with underscores.
    """

    NAME = "chatwire_mqtt"
    TIER = "official"
    DISPLAY_NAME = "MQTT"
    DESCRIPTION = "Publish every inbound iMessage to an MQTT broker (Home Assistant, Node-RED, etc.)"
    ICON = "📡"

    SETTINGS_SCHEMA: dict[str, Any] = {
        "type": "object",
        "properties": {
            "enabled": {
                "type": "boolean",
                "default": False,
                "title": "Enable MQTT integration",
                "x-ui-order": 0,
            },
            "host": {
                "type": "string",
                "title": "Broker host",
                "description": "Hostname or IP of your MQTT broker.",
                "x-ui-placeholder": "192.168.1.100",
                "x-ui-order": 1,
            },
            "port": {
                "type": "integer",
                "default": 1883,
                "minimum": 1,
                "maximum": 65535,
                "title": "Broker port",
                "x-ui-order": 2,
            },
            "topic": {
                "type": "string",
                "default": "chatwire/messages",
                "title": "Base topic",
                "description": (
                    "Messages are published to <topic>/<handle> (1:1) "
                    "or <topic>/group/<chat_id> (group)."
                ),
                "x-ui-order": 3,
            },
            "username": {
                "type": "string",
                "default": "",
                "title": "Username (optional)",
                "x-ui-order": 4,
            },
            "password": {
                "type": "string",
                "default": "",
                "title": "Password (optional)",
                "x-ui-type": "password",
                "x-ui-order": 5,
            },
            "qos": {
                "type": "integer",
                "default": 0,
                "enum": [0, 1, 2],
                "title": "QoS level",
                "description": "0 = at-most-once, 1 = at-least-once, 2 = exactly-once.",
                "x-ui-order": 6,
            },
            "client_id": {
                "type": "string",
                "default": "chatwire",
                "title": "Client ID (optional)",
                "description": "MQTT client identifier. Must be unique on the broker.",
                "x-ui-order": 7,
            },
            "use_tls": {
                "type": "boolean",
                "default": False,
                "title": "Use TLS/SSL",
                "description": (
                    "Encrypt the broker connection with TLS. "
                    "Set port to 8883 for standard MQTT-over-TLS."
                ),
                "x-ui-order": 8,
            },
            "ca_cert": {
                "type": "string",
                "default": "",
                "title": "CA certificate path (optional)",
                "description": (
                    "Absolute path to a PEM CA certificate file. "
                    "Leave blank to use the system CA bundle."
                ),
                "x-ui-placeholder": "/etc/ssl/certs/broker-ca.pem",
                "x-ui-order": 9,
            },
            "send_topic": {
                "type": "string",
                "default": "",
                "title": "Outbound send topic (optional)",
                "description": (
                    "Subscribe to this topic to send iMessages from automations. "
                    "Payload: {\"handle\": \"+1...\", \"text\": \"...\"} for 1:1, "
                    "or {\"chat\": \"iMessage;+;...\", \"text\": \"...\"} for groups. "
                    "Leave blank to disable."
                ),
                "x-ui-placeholder": "chatwire/send",
                "x-ui-order": 10,
            },
        },
        "required": ["host"],
    }

    def __init__(self, config: dict[str, Any]) -> None:
        self._host: str = config.get("host") or ""
        self._port: int = int(config.get("port") or 1883)
        self._topic: str = (config.get("topic") or "chatwire/messages").rstrip("/")
        self._username: str = config.get("username") or ""
        self._password: str = config.get("password") or ""
        self._qos: int = int(config.get("qos") or 0)
        self._client_id: str = config.get("client_id") or "chatwire"
        self._use_tls: bool = bool(config.get("use_tls", False))
        self._ca_cert: str = config.get("ca_cert") or ""
        self._send_topic: str = config.get("send_topic") or ""
        self._client: Any = None  # paho.mqtt.client.Client instance
        self._ctx: Any = None  # BridgeContext stashed in start()
        self._loop: asyncio.AbstractEventLoop | None = None  # bridge event loop

    async def start(self, ctx: Any) -> None:
        if not self._host:
            raise ValueError("chatwire_mqtt: 'host' is required")
        if not _PAHO_AVAILABLE:
            raise RuntimeError(
                "chatwire_mqtt: paho-mqtt is not installed.  "
                "Run: pip install paho-mqtt"
            )

        client = _paho.Client(client_id=self._client_id)
        if self._username:
            client.username_pw_set(self._username, self._password or None)

        if self._use_tls:
            try:
                client.tls_set(ca_certs=self._ca_cert or None)
            except Exception as exc:
                raise RuntimeError(
                    f"chatwire_mqtt: TLS setup failed: {exc}"
                ) from exc

        self._ctx = ctx
        self._loop = asyncio.get_event_loop()

        # on_connect / on_disconnect for logging.
        def _on_connect(c: Any, userdata: Any, flags: Any, rc: int) -> None:
            if rc == 0:
                log.info("mqtt: connected to %s:%d", self._host, self._port)
                _ls_info("mqtt", f"connected to {self._host}:{self._port}")
                if self._send_topic:
                    c.subscribe(self._send_topic)
                    log.info("mqtt: subscribed to send_topic=%s", self._send_topic)
                    _ls_info("mqtt", f"subscribed to send_topic={self._send_topic}")
            else:
                log.warning("mqtt: connect failed rc=%d", rc)
                _ls_warn("mqtt", f"connect failed rc={rc}")

        def _on_disconnect(c: Any, userdata: Any, rc: int) -> None:
            if rc != 0:
                log.warning("mqtt: unexpected disconnect rc=%d", rc)

        client.on_connect = _on_connect
        client.on_disconnect = _on_disconnect
        if self._send_topic:
            client.on_message = self._on_outbound_message

        try:
            client.connect(self._host, self._port, keepalive=60)
        except OSError as exc:
            raise RuntimeError(
                f"chatwire_mqtt: cannot connect to {self._host}:{self._port}: {exc}"
            ) from exc

        client.loop_start()
        self._client = client
        log.info(
            "mqtt integration started; broker=%s:%d topic=%s qos=%d tls=%s send_topic=%r",
            self._host, self._port, self._topic, self._qos, self._use_tls, self._send_topic,
        )

    async def stop(self) -> None:
        if self._client is not None:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass
            self._client = None
        self._ctx = None
        self._loop = None
        log.info("mqtt integration stopped")

    async def on_inbound(self, msg: Any) -> None:
        """Publish the inbound message as JSON to the configured MQTT topic."""
        if self._client is None:
            return

        is_group = bool(getattr(msg, "is_group", False))
        handle = getattr(msg, "handle", "") or ""
        chat_identifier = getattr(msg, "chat_identifier", "") or handle

        if is_group:
            seg = _sanitize_topic_segment(chat_identifier)
            full_topic = f"{self._topic}/group/{seg}"
        else:
            seg = _sanitize_topic_segment(handle)
            full_topic = f"{self._topic}/{seg}"

        payload = self._payload_for(msg)
        body = json.dumps(payload, ensure_ascii=False, default=str)

        try:
            result = self._client.publish(full_topic, body, qos=self._qos)
            # result.rc == 0 (MQTT_ERR_SUCCESS) on success.
            if result.rc != 0:
                log.warning("mqtt: publish to %s failed rc=%d", full_topic, result.rc)
                _ls_warn("mqtt", f"publish {full_topic} failed rc={result.rc}")
            else:
                _ls_info("mqtt", f"publish → {full_topic}")
        except Exception as exc:
            log.warning("mqtt: publish failed: %s: %s", type(exc).__name__, exc)
            _ls_error("mqtt", f"publish failed: {type(exc).__name__}: {exc}")

    def _on_outbound_message(self, client: Any, userdata: Any, message: Any) -> None:
        """Handle an MQTT message on send_topic and relay it as an iMessage.

        Called by paho on its network thread.  Parses the JSON payload,
        builds a SendTarget, and schedules ctx.send_text() on the bridge loop.

        Payload (1:1):  {"handle": "+15551234567", "text": "Hello!"}
        Payload (group): {"chat": "iMessage;+;chat123", "text": "Hi!", "label": "My Group"}

        ``text`` and either ``handle`` or ``chat`` are required.
        ``label`` is optional (used for logging only).
        """
        if self._ctx is None or SendTarget is None:
            return  # pragma: no cover

        try:
            payload = json.loads(message.payload)
        except (json.JSONDecodeError, Exception) as exc:
            log.warning("mqtt: bad outbound payload: %s", exc)
            _ls_warn("mqtt", f"bad outbound payload: {exc}")
            return

        text = (payload.get("text") or "").strip()
        if not text:
            log.debug("mqtt: outbound message has no text; ignored")
            return

        handle = (payload.get("handle") or "").strip()
        chat_guid = (payload.get("chat") or "").strip()
        label = (payload.get("label") or "").strip()

        if handle:
            target = SendTarget(
                kind="handle",
                value=handle,
                label=label or (self._ctx.name_for(handle) if hasattr(self._ctx, "name_for") else None) or handle,
            )
            log.debug("mqtt: outbound → handle=%s text=%r", handle, text[:80])
            _ls_info("mqtt", f"outbound → handle={handle}")
        elif chat_guid:
            target = SendTarget(
                kind="chat",
                value=chat_guid,
                label=label or chat_guid,
            )
            log.debug("mqtt: outbound → chat=%s text=%r", chat_guid, text[:80])
            _ls_info("mqtt", f"outbound → chat={chat_guid}")
        else:
            log.warning("mqtt: outbound payload missing 'handle' or 'chat'; ignored")
            _ls_warn("mqtt", "outbound payload missing 'handle' or 'chat'")
            return

        loop = self._loop or asyncio.get_event_loop()
        asyncio.run_coroutine_threadsafe(self._ctx.send_text(target, text), loop)

    @staticmethod
    def _payload_for(msg: Any) -> dict[str, Any]:
        """Serialise an InboundMessage to a stable, versioned dict (v=1)."""
        chat_guid = getattr(msg, "chat_guid", None)
        chat_identifier = getattr(msg, "chat_identifier", None)
        chat_name = getattr(msg, "chat_name", None)
        is_group = bool(getattr(msg, "is_group", False))

        return {
            "v": 1,
            "rowid": getattr(msg, "rowid", None),
            "handle": getattr(msg, "handle", "") or "",
            "text": getattr(msg, "text", "") or "",
            "is_from_me": bool(getattr(msg, "is_from_me", False)),
            "chat": (
                {
                    "guid": chat_guid,
                    "identifier": chat_identifier,
                    "name": chat_name,
                    "is_group": is_group,
                }
                if chat_guid
                else None
            ),
        }
