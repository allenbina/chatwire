"""Tests for chunk 4: Home Assistant plugin (chatwire-ha).

Strategy
--------
- Import HAIntegration directly from the plugin source tree (sys.path insert).
- Mock httpx.AsyncClient to avoid real network calls.
- Mock BridgeContext / SendTarget to stay out of the bridge runtime.
- Use asyncio.run() for async tests (matches project pattern; no pytest-asyncio needed).

Covers:
  a. Keyword match triggers correct HA service call (POST URL + body).
  b. Non-matching text is silently ignored (no HTTP call, no reply).
  c. HA returns HTTP 4xx — integration logs warning, does not crash, no reply.
  d. httpx.HTTPError — integration logs warning, does not crash, no reply.
  e. Missing ha_url in config — start() raises ValueError.
  f. Missing access_token in config — start() raises ValueError.
  g. Keyword matching is case-insensitive (sender types "LIGHTS OFF").
  h. Group message reply uses chat_guid / kind="chat".
  i. 1:1 message reply uses handle / kind="handle".
  j. on_inbound() before start() (client=None) does nothing.
"""
from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# ---------------------------------------------------------------------------
# Make the plugin importable by inserting its src dir into sys.path.
# ---------------------------------------------------------------------------
_PLUGIN_ROOT = Path(__file__).resolve().parent.parent / "chatwire-plugins" / "chatwire-ha"
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from chatwire_ha import HAIntegration  # noqa: E402


# ---------------------------------------------------------------------------
# Minimal stubs for bridge types (not importing the full bridge)
# ---------------------------------------------------------------------------

@dataclass
class FakeSendTarget:
    kind: str
    value: str
    label: str

    @property
    def is_group(self) -> bool:
        return self.kind == "chat"


@dataclass
class FakeMsg:
    text: str
    handle: str = "+15551234567"
    is_group: bool = False
    chat_guid: str = ""
    chat_identifier: str = ""
    chat_name: str = ""


@dataclass
class FakeCtx:
    sent: list[tuple[Any, str]] = field(default_factory=list)

    async def send_text(self, target: Any, body: str) -> MagicMock:
        self.sent.append((target, body))
        return MagicMock(status="delivered")

    def name_for(self, handle: str) -> str | None:
        return None  # fallback to raw handle


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

BASE_CONFIG: dict[str, Any] = {
    "enabled": True,
    "ha_url": "http://ha.local:8123",
    "access_token": "tok_abc123",
    "commands": [
        {
            "keyword": "lights off",
            "domain": "light",
            "service": "turn_off",
            "entity_id": "light.living_room",
            "description": "Living room lights off",
        },
        {
            "keyword": "good night",
            "domain": "scene",
            "service": "turn_on",
            "entity_id": "scene.night_mode",
            "description": "Night mode activated",
        },
    ],
}


def _make_integration(config: dict | None = None) -> HAIntegration:
    return HAIntegration(config if config is not None else BASE_CONFIG)


async def _start(integ: HAIntegration, ctx: FakeCtx | None = None) -> FakeCtx:
    ctx = ctx or FakeCtx()
    import chatwire_ha as _mod
    _mod.SendTarget = FakeSendTarget  # type: ignore[attr-defined]
    await integ.start(ctx)
    return ctx


def _run(coro: Any) -> Any:
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestKeywordMatch:
    def test_keyword_triggers_ha_call(self) -> None:
        """a. Matching keyword fires POST to HA services endpoint."""
        async def _go() -> None:
            integ = _make_integration()
            ctx = await _start(integ)

            mock_resp = MagicMock()
            mock_resp.status_code = 200

            with patch.object(integ._client, "post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_resp
                await integ.on_inbound(FakeMsg(text="lights off"))

            mock_post.assert_awaited_once()
            call_args = mock_post.call_args
            assert call_args.args[0] == "http://ha.local:8123/api/services/light/turn_off"
            assert call_args.kwargs["json"] == {"entity_id": "light.living_room"}

            assert len(ctx.sent) == 1
            target, body = ctx.sent[0]
            assert body == "Done: Living room lights off"
            assert target.kind == "handle"
            assert target.value == "+15551234567"

            await integ.stop()

        _run(_go())

    def test_non_keyword_ignored(self) -> None:
        """b. Text that matches no keyword → no HTTP call, no reply."""
        async def _go() -> None:
            integ = _make_integration()
            ctx = await _start(integ)

            with patch.object(integ._client, "post", new_callable=AsyncMock) as mock_post:
                await integ.on_inbound(FakeMsg(text="hello world"))

            mock_post.assert_not_called()
            assert ctx.sent == []

            await integ.stop()

        _run(_go())

    def test_bad_ha_response_does_not_crash(self) -> None:
        """c. HA returns HTTP 4xx — logs warning, no exception, no reply."""
        async def _go() -> None:
            integ = _make_integration()
            ctx = await _start(integ)

            mock_resp = MagicMock()
            mock_resp.status_code = 401
            mock_resp.text = "Unauthorized"

            with patch.object(integ._client, "post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_resp
                await integ.on_inbound(FakeMsg(text="lights off"))  # must not raise

            assert ctx.sent == []

            await integ.stop()

        _run(_go())

    def test_httpx_error_does_not_crash(self) -> None:
        """d. httpx.ConnectError — logs warning, no exception, no reply."""
        async def _go() -> None:
            integ = _make_integration()
            ctx = await _start(integ)

            with patch.object(
                integ._client, "post", new_callable=AsyncMock,
                side_effect=httpx.ConnectError("connection refused"),
            ):
                await integ.on_inbound(FakeMsg(text="lights off"))  # must not raise

            assert ctx.sent == []

            await integ.stop()

        _run(_go())

    def test_timeout_error_does_not_crash(self) -> None:
        """d (variant). asyncio.TimeoutError — logs warning, no exception."""
        async def _go() -> None:
            integ = _make_integration()
            await _start(integ)

            with patch.object(
                integ._client, "post", new_callable=AsyncMock,
                side_effect=asyncio.TimeoutError(),
            ):
                await integ.on_inbound(FakeMsg(text="good night"))  # must not raise

            await integ.stop()

        _run(_go())


class TestMissingConfig:
    def test_missing_ha_url_raises(self) -> None:
        """e. ha_url absent in config → start() raises ValueError."""
        async def _go() -> None:
            integ = HAIntegration({"access_token": "tok"})
            with pytest.raises(ValueError, match="ha_url"):
                await integ.start(FakeCtx())

        _run(_go())

    def test_missing_access_token_raises(self) -> None:
        """f. access_token absent in config → start() raises ValueError."""
        async def _go() -> None:
            integ = HAIntegration({"ha_url": "http://ha.local:8123"})
            with pytest.raises(ValueError, match="access_token"):
                await integ.start(FakeCtx())

        _run(_go())

    def test_empty_commands_list_starts_ok(self) -> None:
        """Gracefully handles config with no commands (valid but no-op)."""
        async def _go() -> None:
            integ = HAIntegration({
                "ha_url": "http://ha.local:8123",
                "access_token": "tok",
                "commands": [],
            })
            ctx = FakeCtx()
            await integ.start(ctx)
            assert integ._commands == {}
            await integ.stop()

        _run(_go())


class TestCaseSensitivity:
    def test_keyword_match_is_case_insensitive(self) -> None:
        """g. Sender types "LIGHTS OFF" (uppercase) → still matches."""
        async def _go() -> None:
            integ = _make_integration()
            await _start(integ)

            mock_resp = MagicMock()
            mock_resp.status_code = 200

            with patch.object(integ._client, "post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_resp
                await integ.on_inbound(FakeMsg(text="LIGHTS OFF"))

            mock_post.assert_awaited_once()

            await integ.stop()

        _run(_go())

    def test_keyword_with_surrounding_whitespace(self) -> None:
        """g (variant). Sender types "  lights off  " (padded) → matches."""
        async def _go() -> None:
            integ = _make_integration()
            await _start(integ)

            mock_resp = MagicMock()
            mock_resp.status_code = 200

            with patch.object(integ._client, "post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_resp
                await integ.on_inbound(FakeMsg(text="  lights off  "))

            mock_post.assert_awaited_once()

            await integ.stop()

        _run(_go())


class TestGroupMessages:
    def test_group_message_reply_uses_chat_guid(self) -> None:
        """h. Group message reply target uses kind='chat' and chat_guid."""
        async def _go() -> None:
            integ = _make_integration()
            ctx = await _start(integ)

            mock_resp = MagicMock()
            mock_resp.status_code = 200

            group_msg = FakeMsg(
                text="lights off",
                is_group=True,
                chat_guid="iMessage;+;chat629",
                chat_name="Home Group",
            )

            with patch.object(integ._client, "post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_resp
                await integ.on_inbound(group_msg)

            assert len(ctx.sent) == 1
            target, body = ctx.sent[0]
            assert target.kind == "chat"
            assert target.value == "iMessage;+;chat629"
            assert body == "Done: Living room lights off"

            await integ.stop()

        _run(_go())

    def test_one_to_one_reply_uses_handle(self) -> None:
        """i. 1:1 message reply target uses kind='handle'."""
        async def _go() -> None:
            integ = _make_integration()
            ctx = await _start(integ)

            mock_resp = MagicMock()
            mock_resp.status_code = 200

            with patch.object(integ._client, "post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_resp
                await integ.on_inbound(FakeMsg(text="lights off", handle="+15559876543"))

            assert len(ctx.sent) == 1
            target, _ = ctx.sent[0]
            assert target.kind == "handle"
            assert target.value == "+15559876543"

            await integ.stop()

        _run(_go())


class TestAllowedSenders:
    """Tests for per-command allowed_senders filter."""

    def _config_with_senders(self, senders: list) -> dict:
        return {
            "enabled": True,
            "ha_url": "http://ha.local:8123",
            "access_token": "tok_abc123",
            "commands": [
                {
                    "keyword": "lights off",
                    "domain": "light",
                    "service": "turn_off",
                    "entity_id": "light.living_room",
                    "description": "Living room lights off",
                    "allowed_senders": senders,
                },
            ],
        }

    def test_allowed_sender_fires(self) -> None:
        """Handle in allowed_senders → command fires normally."""
        async def _go() -> None:
            integ = _make_integration(self._config_with_senders(["+15551234567"]))
            ctx = await _start(integ)

            mock_resp = MagicMock()
            mock_resp.status_code = 200

            with patch.object(integ._client, "post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_resp
                await integ.on_inbound(FakeMsg(text="lights off", handle="+15551234567"))

            mock_post.assert_awaited_once()
            assert len(ctx.sent) == 1

            await integ.stop()

        _run(_go())

    def test_disallowed_sender_skipped(self) -> None:
        """Handle NOT in allowed_senders → command is silently skipped."""
        async def _go() -> None:
            integ = _make_integration(self._config_with_senders(["+15551234567"]))
            ctx = await _start(integ)

            with patch.object(integ._client, "post", new_callable=AsyncMock) as mock_post:
                await integ.on_inbound(FakeMsg(text="lights off", handle="+19998887777"))

            mock_post.assert_not_called()
            assert ctx.sent == []

            await integ.stop()

        _run(_go())

    def test_empty_allowed_senders_fires_for_any_sender(self) -> None:
        """Empty allowed_senders list → any sender may trigger the command."""
        async def _go() -> None:
            integ = _make_integration(self._config_with_senders([]))
            ctx = await _start(integ)

            mock_resp = MagicMock()
            mock_resp.status_code = 200

            with patch.object(integ._client, "post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_resp
                await integ.on_inbound(FakeMsg(text="lights off", handle="+10000000000"))

            mock_post.assert_awaited_once()
            assert len(ctx.sent) == 1

            await integ.stop()

        _run(_go())

    def test_absent_allowed_senders_fires_for_any_sender(self) -> None:
        """Missing allowed_senders key → any sender may trigger (backward compat)."""
        async def _go() -> None:
            # BASE_CONFIG has no allowed_senders
            integ = _make_integration()
            ctx = await _start(integ)

            mock_resp = MagicMock()
            mock_resp.status_code = 200

            with patch.object(integ._client, "post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_resp
                await integ.on_inbound(FakeMsg(text="lights off", handle="+19990000001"))

            mock_post.assert_awaited_once()
            assert len(ctx.sent) == 1

            await integ.stop()

        _run(_go())

    def test_allowed_senders_case_insensitive(self) -> None:
        """Email-format handles match case-insensitively."""
        async def _go() -> None:
            integ = _make_integration(self._config_with_senders(["Alice@Example.com"]))
            ctx = await _start(integ)

            mock_resp = MagicMock()
            mock_resp.status_code = 200

            with patch.object(integ._client, "post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_resp
                # Sender arrives lowercase from bridge normalisation
                await integ.on_inbound(FakeMsg(text="lights off", handle="alice@example.com"))

            mock_post.assert_awaited_once()
            assert len(ctx.sent) == 1

            await integ.stop()

        _run(_go())

    def test_allowed_senders_multiple_handles(self) -> None:
        """Multiple handles in allowed_senders — each is permitted."""
        async def _go() -> None:
            integ = _make_integration(
                self._config_with_senders(["+15551111111", "+15552222222"])
            )
            ctx = await _start(integ)

            mock_resp = MagicMock()
            mock_resp.status_code = 200

            with patch.object(integ._client, "post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_resp
                await integ.on_inbound(FakeMsg(text="lights off", handle="+15552222222"))

            mock_post.assert_awaited_once()

            # Third handle not in list → skipped
            mock_post.reset_mock()
            ctx.sent.clear()
            with patch.object(integ._client, "post", new_callable=AsyncMock) as mock_post2:
                await integ.on_inbound(FakeMsg(text="lights off", handle="+15553333333"))

            mock_post2.assert_not_called()

            await integ.stop()

        _run(_go())

    def test_allowed_senders_stored_as_frozenset(self) -> None:
        """Internals: allowed_senders is a frozenset for O(1) lookup."""
        integ = _make_integration(self._config_with_senders(["+15551234567", "+15559876543"]))
        cmd = integ._commands.get("lights off")
        assert cmd is not None
        assert isinstance(cmd["allowed_senders"], frozenset)
        assert "+15551234567" in cmd["allowed_senders"]


class TestLifecycle:
    def test_on_inbound_before_start_does_nothing(self) -> None:
        """j. Calling on_inbound() before start() is a silent no-op."""
        async def _go() -> None:
            integ = _make_integration()
            await integ.on_inbound(FakeMsg(text="lights off"))  # must not raise

        _run(_go())

    def test_double_stop_is_idempotent(self) -> None:
        """stop() called twice should not raise."""
        async def _go() -> None:
            integ = _make_integration()
            await _start(integ)
            await integ.stop()
            await integ.stop()  # must not raise

        _run(_go())

    def test_authorization_header_set_on_client(self) -> None:
        """Bearer token is sent in Authorization header."""
        async def _go() -> None:
            integ = _make_integration()
            await _start(integ)
            assert integ._client is not None
            auth = dict(integ._client.headers).get("authorization", "")
            assert auth == "Bearer tok_abc123"
            await integ.stop()

        _run(_go())
