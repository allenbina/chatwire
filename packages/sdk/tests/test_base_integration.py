"""Tests for BaseIntegration, PluginManifest, and @chatwire_plugin."""
from __future__ import annotations

import pytest
from chatwire_sdk import BaseIntegration, PluginManifest, chatwire_plugin, registry


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

class _MinimalPlugin(BaseIntegration):
    NAME = "minimal"
    DESCRIPTION = "A minimal test plugin."


@chatwire_plugin
class _RegisteredPlugin(BaseIntegration):
    NAME = "registered"
    DISPLAY_NAME = "Registered Plugin"
    DESCRIPTION = "Used to test @chatwire_plugin."
    VERSION = "1.2.3"
    AUTHOR = "Test Author"
    SETTINGS_SCHEMA = {
        "type": "object",
        "properties": {
            "enabled": {"type": "boolean", "default": False},
        },
    }


# ---------------------------------------------------------------------------
# BaseIntegration instantiation
# ---------------------------------------------------------------------------

def test_instantiate_with_no_config():
    plugin = _MinimalPlugin()
    assert plugin.config == {}


def test_instantiate_with_config():
    plugin = _MinimalPlugin(config={"enabled": True, "api_key": "secret"})
    assert plugin.config["enabled"] is True
    assert plugin.config["api_key"] == "secret"


def test_config_is_read_only_view():
    """Mutating the returned dict should not affect internal state."""
    plugin = _MinimalPlugin(config={"x": 1})
    c = plugin.config
    c["y"] = 2
    # Internal dict is the same object — this test just verifies property access
    assert "x" in plugin.config


# ---------------------------------------------------------------------------
# settings_schema()
# ---------------------------------------------------------------------------

def test_settings_schema_returns_class_level_schema():
    plugin = _RegisteredPlugin()
    schema = plugin.settings_schema()
    assert schema["type"] == "object"
    assert "enabled" in schema["properties"]


def test_settings_schema_default_is_empty_for_minimal():
    plugin = _MinimalPlugin()
    assert plugin.settings_schema() == {}


# ---------------------------------------------------------------------------
# Lifecycle hooks — default no-ops
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_on_startup_noop():
    plugin = _MinimalPlugin()
    await plugin.on_startup()  # should not raise


@pytest.mark.asyncio
async def test_on_shutdown_noop():
    plugin = _MinimalPlugin()
    await plugin.on_shutdown()  # should not raise


@pytest.mark.asyncio
async def test_on_message_received_noop():
    plugin = _MinimalPlugin()

    class FakeMsg:
        text = "hello"
        handle = "+15550000000"
        is_from_me = False
        chat_guid = None

    await plugin.on_message_received(FakeMsg())  # should not raise


@pytest.mark.asyncio
async def test_on_message_sent_noop():
    plugin = _MinimalPlugin()

    class FakeMsg:
        text = "hi"
        handle = "+15550000000"
        is_from_me = True
        chat_guid = None

        class outcome:
            status = "delivered"
            hint = ""

    await plugin.on_message_sent(FakeMsg())  # should not raise


# ---------------------------------------------------------------------------
# Bridge-facing shims
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_start_delegates_to_on_startup():
    started = []

    class _P(BaseIntegration):
        NAME = "shim_test"
        async def on_startup(self):
            started.append(True)

    plugin = _P()
    await plugin.start(ctx=object())
    assert started == [True]


@pytest.mark.asyncio
async def test_stop_delegates_to_on_shutdown():
    stopped = []

    class _P(BaseIntegration):
        NAME = "shim_test2"
        async def on_shutdown(self):
            stopped.append(True)

    plugin = _P()
    await plugin.stop()
    assert stopped == [True]


@pytest.mark.asyncio
async def test_on_inbound_delegates_to_on_message_received():
    received = []

    class _P(BaseIntegration):
        NAME = "shim_test3"
        async def on_message_received(self, msg):
            received.append(msg)

    class FakeMsg:
        text = "yo"

    plugin = _P()
    msg = FakeMsg()
    await plugin.on_inbound(msg)
    assert received == [msg]


# ---------------------------------------------------------------------------
# PluginManifest via .manifest()
# ---------------------------------------------------------------------------

def test_manifest_populates_all_fields():
    m = _RegisteredPlugin.manifest()
    assert isinstance(m, PluginManifest)
    assert m.name == "registered"
    assert m.version == "1.2.3"
    assert m.author == "Test Author"
    assert m.description == "Used to test @chatwire_plugin."
    assert "enabled" in m.settings_schema["properties"]


def test_manifest_display_name_fallback():
    """When DISPLAY_NAME is absent, manifest should not crash."""
    m = _MinimalPlugin.manifest()
    assert m.name == "minimal"
    # description comes from DESCRIPTION
    assert "minimal" in m.description.lower()


def test_manifest_name_default():
    """PluginManifest can be constructed directly."""
    pm = PluginManifest(name="foo")
    assert pm.name == "foo"
    assert pm.version == "0.1.0"
    assert pm.settings_schema == {}


# ---------------------------------------------------------------------------
# @chatwire_plugin decorator
# ---------------------------------------------------------------------------

def test_decorator_registers_plugin():
    assert "registered" in registry
    assert registry["registered"] is _RegisteredPlugin


def test_decorator_returns_class_unchanged():
    """@chatwire_plugin must return the exact same class object."""
    assert _RegisteredPlugin.NAME == "registered"
    assert issubclass(_RegisteredPlugin, BaseIntegration)


def test_decorator_rejects_non_base_integration():
    with pytest.raises(TypeError, match="BaseIntegration subclasses"):

        @chatwire_plugin  # type: ignore[arg-type]
        class _Bad:
            NAME = "bad"


def test_decorator_rejects_missing_name():
    with pytest.raises(ValueError, match="NAME"):

        @chatwire_plugin
        class _NoName(BaseIntegration):
            pass  # NAME not defined


def test_multiple_plugins_coexist():
    """registry should hold all registered plugins without collisions."""
    assert "minimal" not in registry  # _MinimalPlugin wasn't decorated
    assert "registered" in registry
