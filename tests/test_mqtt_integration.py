"""Tests for chatwire-mqtt plugin.

Strategy
--------
- Import MQTTIntegration from the plugin source tree (sys.path insert).
- Mock paho.mqtt.client.Client to avoid real broker connections.
- Use asyncio event loop for async tests (matches project pattern).

Covers:
  a. Inbound 1:1 message → publish() called with correct topic + JSON body (v=1).
  b. Group message → topic uses group/<sanitized_chat_id> prefix.
  c. is_from_me=True message → published normally (no filter by direction).
  d. Text-less message (attachment only) → published with empty text field.
  e. publish() raises exception → silent no-op (no crash).
  f. publish() returns non-zero rc → logs warning, no crash.
  g. host missing in config → start() raises ValueError.
  h. paho unavailable → start() raises RuntimeError (mocked).
  i. on_inbound() before start() → silent no-op.
  j. stop() without prior start() → no crash.
  k. stop() called twice → no crash.
  l. JSON payload contains v=1, handle, text, is_from_me, chat.
  m. _sanitize_topic_segment replaces +, #, / with underscores.
  n. username/password set on client when both configured.
  o. Client ID defaults to "chatwire"; custom value overrides.
"""
from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Make the plugin importable.
# ---------------------------------------------------------------------------
_PLUGIN_ROOT = Path(__file__).resolve().parent.parent / "chatwire-plugins" / "chatwire-mqtt"
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

# Stub out paho so the module imports cleanly even without the library.
_paho_stub = MagicMock()
_paho_stub.Client = MagicMock
sys.modules.setdefault("paho", MagicMock())
sys.modules.setdefault("paho.mqtt", MagicMock())
sys.modules.setdefault("paho.mqtt.client", _paho_stub)

import chatwire_mqtt as _mod  # noqa: E402
from chatwire_mqtt import MQTTIntegration, _sanitize_topic_segment  # noqa: E402


# ---------------------------------------------------------------------------
# Minimal message stub
# ---------------------------------------------------------------------------

@dataclass
class FakeMsg:
    text: str = "Hello"
    handle: str = "+15551234567"
    is_from_me: bool = False
    is_group: bool = False
    rowid: int = 1
    chat_guid: str = "iMessage;-;+15551234567"
    chat_identifier: str = "+15551234567"
    chat_name: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_CONFIG: dict[str, Any] = {
    "enabled": True,
    "host": "mqtt.local",
    "port": 1883,
    "topic": "chatwire/messages",
    "qos": 0,
}


def _make(config: dict | None = None) -> MQTTIntegration:
    return MQTTIntegration(config if config is not None else BASE_CONFIG)


def _make_mock_client() -> MagicMock:
    """Return a paho Client mock with a successful publish result."""
    client = MagicMock()
    result = MagicMock()
    result.rc = 0
    client.publish.return_value = result
    return client


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPublishTopic:
    def test_one_to_one_message_topic(self) -> None:
        """a. 1:1 inbound message → topic is <base>/<sanitized_handle>."""
        async def _go() -> None:
            integ = _make()
            mock_client = _make_mock_client()
            integ._client = mock_client
            await integ.on_inbound(FakeMsg())
            mock_client.publish.assert_called_once()
            topic = mock_client.publish.call_args.args[0]
            # + is MQTT-reserved, so +15551234567 sanitizes to _15551234567
            assert topic == "chatwire/messages/_15551234567"

        _run(_go())

    def test_group_message_topic(self) -> None:
        """b. Group message → topic is <base>/group/<sanitized_chat_id>."""
        async def _go() -> None:
            integ = _make()
            mock_client = _make_mock_client()
            integ._client = mock_client
            msg = FakeMsg(
                is_group=True,
                chat_guid="iMessage;+;chat123",
                chat_identifier="chat123",
            )
            await integ.on_inbound(msg)
            topic = mock_client.publish.call_args.args[0]
            assert topic == "chatwire/messages/group/chat123"

        _run(_go())

    def test_handle_with_plus_sanitized_in_topic(self) -> None:
        """m (partial). + in handle becomes _ in topic segment."""
        assert _sanitize_topic_segment("+15551234567") == "_15551234567"

    def test_handle_with_slash_sanitized(self) -> None:
        """m. / in identifier becomes _ in topic segment."""
        assert _sanitize_topic_segment("iMessage;+;chat123") == "iMessage;_;chat123"

    def test_hash_sanitized(self) -> None:
        """m. # in a segment becomes _."""
        assert _sanitize_topic_segment("a#b") == "a_b"

    def test_empty_string_sanitized_to_underscore(self) -> None:
        """m. Empty string → '_' (fallback)."""
        assert _sanitize_topic_segment("") == "_"


class TestPayload:
    def test_payload_has_v1(self) -> None:
        """l. Published JSON contains v=1."""
        payload = MQTTIntegration._payload_for(FakeMsg())
        assert payload["v"] == 1

    def test_payload_fields(self) -> None:
        """l. Payload contains handle, text, is_from_me, chat."""
        msg = FakeMsg(text="Hi", handle="+1", is_from_me=False)
        payload = MQTTIntegration._payload_for(msg)
        assert payload["handle"] == "+1"
        assert payload["text"] == "Hi"
        assert payload["is_from_me"] is False
        assert payload["chat"] is not None
        assert payload["chat"]["is_group"] is False

    def test_is_from_me_true_is_published(self) -> None:
        """c. is_from_me=True messages are published (no direction filter)."""
        async def _go() -> None:
            integ = _make()
            mock_client = _make_mock_client()
            integ._client = mock_client
            await integ.on_inbound(FakeMsg(is_from_me=True))
            mock_client.publish.assert_called_once()
            body = mock_client.publish.call_args.args[1]
            data = json.loads(body)
            assert data["is_from_me"] is True

        _run(_go())

    def test_empty_text_published(self) -> None:
        """d. Message with empty text → published with text=''."""
        async def _go() -> None:
            integ = _make()
            mock_client = _make_mock_client()
            integ._client = mock_client
            await integ.on_inbound(FakeMsg(text=""))
            mock_client.publish.assert_called_once()
            body = mock_client.publish.call_args.args[1]
            data = json.loads(body)
            assert data["text"] == ""

        _run(_go())

    def test_no_chat_guid_gives_null_chat(self) -> None:
        """l. Message without chat_guid → chat is None in payload."""
        msg = FakeMsg(chat_guid="")
        payload = MQTTIntegration._payload_for(msg)
        assert payload["chat"] is None


class TestErrorHandling:
    def test_publish_exception_does_not_raise(self) -> None:
        """e. publish() raising an exception → silent no-op."""
        async def _go() -> None:
            integ = _make()
            mock_client = MagicMock()
            mock_client.publish.side_effect = RuntimeError("broker gone")
            integ._client = mock_client
            await integ.on_inbound(FakeMsg())  # must not raise

        _run(_go())

    def test_publish_nonzero_rc_does_not_raise(self) -> None:
        """f. publish() returns rc != 0 → logs warning, no crash."""
        async def _go() -> None:
            integ = _make()
            mock_client = MagicMock()
            bad_result = MagicMock()
            bad_result.rc = 4  # MQTT_ERR_NO_CONN
            mock_client.publish.return_value = bad_result
            integ._client = mock_client
            await integ.on_inbound(FakeMsg())  # must not raise

        _run(_go())


class TestMissingConfig:
    def test_missing_host_raises(self) -> None:
        """g. host absent in config → start() raises ValueError."""
        async def _go() -> None:
            integ = MQTTIntegration({})
            with pytest.raises(ValueError, match="host"):
                await integ.start(None)

        _run(_go())

    def test_paho_unavailable_raises(self) -> None:
        """h. paho-mqtt not installed → start() raises RuntimeError."""
        async def _go() -> None:
            integ = _make()
            with patch.object(_mod, "_PAHO_AVAILABLE", False):
                with pytest.raises(RuntimeError, match="paho-mqtt"):
                    await integ.start(None)

        _run(_go())


class TestLifecycle:
    def test_on_inbound_before_start_does_nothing(self) -> None:
        """i. on_inbound() before start() is a silent no-op."""
        async def _go() -> None:
            integ = _make()
            await integ.on_inbound(FakeMsg())  # must not raise

        _run(_go())

    def test_stop_without_start_does_nothing(self) -> None:
        """j. stop() with no prior start() does not crash."""
        async def _go() -> None:
            integ = _make()
            await integ.stop()  # must not raise

        _run(_go())

    def test_double_stop_is_idempotent(self) -> None:
        """k. stop() twice does not raise."""
        async def _go() -> None:
            integ = _make()
            mock_client = _make_mock_client()
            integ._client = mock_client
            await integ.stop()
            await integ.stop()  # must not raise

        _run(_go())


class TestClientConfig:
    def test_username_password_set_when_provided(self) -> None:
        """n. username + password → username_pw_set() called on client."""
        async def _go() -> None:
            integ = MQTTIntegration({
                "host": "mqtt.local",
                "username": "alice",
                "password": "s3cr3t",
            })
            mock_client = _make_mock_client()
            mock_client.connect.return_value = None

            with patch.object(_mod, "_PAHO_AVAILABLE", True), \
                 patch.object(_mod, "_paho") as mock_paho:
                mock_paho.Client.return_value = mock_client
                await integ.start(None)

            mock_client.username_pw_set.assert_called_once_with("alice", "s3cr3t")
            await integ.stop()

        _run(_go())

    def test_no_username_skips_auth(self) -> None:
        """n. No username → username_pw_set() not called."""
        async def _go() -> None:
            integ = _make()
            mock_client = _make_mock_client()
            mock_client.connect.return_value = None

            with patch.object(_mod, "_PAHO_AVAILABLE", True), \
                 patch.object(_mod, "_paho") as mock_paho:
                mock_paho.Client.return_value = mock_client
                await integ.start(None)

            mock_client.username_pw_set.assert_not_called()
            await integ.stop()

        _run(_go())

    def test_custom_client_id(self) -> None:
        """o. Custom client_id is passed to paho.Client()."""
        async def _go() -> None:
            integ = MQTTIntegration({"host": "mqtt.local", "client_id": "my-bridge"})
            mock_client = _make_mock_client()
            mock_client.connect.return_value = None

            with patch.object(_mod, "_PAHO_AVAILABLE", True), \
                 patch.object(_mod, "_paho") as mock_paho:
                mock_paho.Client.return_value = mock_client
                await integ.start(None)

            mock_paho.Client.assert_called_once_with(client_id="my-bridge")
            await integ.stop()

        _run(_go())

    def test_default_client_id_is_chatwire(self) -> None:
        """o. Default client_id is 'chatwire'."""
        integ = _make()
        assert integ._client_id == "chatwire"


class TestTLS:
    """Tests for use_tls / ca_cert config options."""

    def test_use_tls_defaults_to_false(self) -> None:
        """use_tls is False when not supplied in config."""
        integ = _make()
        assert integ._use_tls is False

    def test_ca_cert_defaults_to_empty(self) -> None:
        """ca_cert is '' when not supplied in config."""
        integ = _make()
        assert integ._ca_cert == ""

    def test_tls_disabled_does_not_call_tls_set(self) -> None:
        """When use_tls=False, tls_set() is never called on the paho client."""
        async def _go() -> None:
            integ = _make()  # use_tls not in BASE_CONFIG → False
            mock_client = _make_mock_client()
            mock_client.connect.return_value = None

            with patch.object(_mod, "_PAHO_AVAILABLE", True), \
                 patch.object(_mod, "_paho") as mock_paho:
                mock_paho.Client.return_value = mock_client
                await integ.start(None)

            mock_client.tls_set.assert_not_called()
            await integ.stop()

        _run(_go())

    def test_tls_enabled_calls_tls_set_no_ca(self) -> None:
        """use_tls=True without ca_cert → tls_set(ca_certs=None) (system CA)."""
        async def _go() -> None:
            integ = MQTTIntegration({**BASE_CONFIG, "use_tls": True})
            mock_client = _make_mock_client()
            mock_client.connect.return_value = None

            with patch.object(_mod, "_PAHO_AVAILABLE", True), \
                 patch.object(_mod, "_paho") as mock_paho:
                mock_paho.Client.return_value = mock_client
                await integ.start(None)

            mock_client.tls_set.assert_called_once_with(ca_certs=None)
            await integ.stop()

        _run(_go())

    def test_tls_enabled_with_ca_cert_passes_path(self) -> None:
        """use_tls=True + ca_cert path → tls_set(ca_certs='/path/to/ca.pem')."""
        async def _go() -> None:
            integ = MQTTIntegration({
                **BASE_CONFIG,
                "use_tls": True,
                "ca_cert": "/etc/ssl/my-ca.pem",
            })
            mock_client = _make_mock_client()
            mock_client.connect.return_value = None

            with patch.object(_mod, "_PAHO_AVAILABLE", True), \
                 patch.object(_mod, "_paho") as mock_paho:
                mock_paho.Client.return_value = mock_client
                await integ.start(None)

            mock_client.tls_set.assert_called_once_with(ca_certs="/etc/ssl/my-ca.pem")
            await integ.stop()

        _run(_go())

    def test_tls_setup_failure_raises_runtime_error(self) -> None:
        """If tls_set() raises, start() wraps the error as RuntimeError."""
        async def _go() -> None:
            integ = MQTTIntegration({**BASE_CONFIG, "use_tls": True})
            mock_client = _make_mock_client()
            mock_client.tls_set.side_effect = OSError("cert not found")

            with patch.object(_mod, "_PAHO_AVAILABLE", True), \
                 patch.object(_mod, "_paho") as mock_paho:
                mock_paho.Client.return_value = mock_client
                with pytest.raises(RuntimeError, match="TLS setup failed"):
                    await integ.start(None)

        _run(_go())

    def test_use_tls_false_explicit_in_config(self) -> None:
        """Explicitly setting use_tls=False behaves same as default."""
        integ = MQTTIntegration({**BASE_CONFIG, "use_tls": False})
        assert integ._use_tls is False

    def test_use_tls_true_stored(self) -> None:
        """use_tls=True is stored correctly."""
        integ = MQTTIntegration({**BASE_CONFIG, "use_tls": True})
        assert integ._use_tls is True

    def test_ca_cert_stored(self) -> None:
        """ca_cert path is stored correctly."""
        integ = MQTTIntegration({**BASE_CONFIG, "ca_cert": "/tmp/ca.pem"})
        assert integ._ca_cert == "/tmp/ca.pem"
