"""chatwire-sdk — Plugin SDK for building chatwire integrations.

This package provides the building blocks for third-party chatwire plugins:

- ``BaseIntegration``: Abstract base class with lifecycle hooks.
- ``PluginManifest``: Dataclass describing a plugin's identity and schema.
- ``@chatwire_plugin``: Class decorator that registers a class as a plugin.

Quick start::

    from chatwire_sdk import BaseIntegration, PluginManifest, chatwire_plugin

    @chatwire_plugin
    class GreeterIntegration(BaseIntegration):
        NAME = "greeter"
        DISPLAY_NAME = "Greeter"
        DESCRIPTION = "Sends a welcome message on startup."

        async def on_startup(self) -> None:
            print("Greeter plugin started!")

"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "BaseIntegration",
    "PluginManifest",
    "SanitizedEvent",
    "chatwire_plugin",
    "registry",
    "__version__",
]

__version__ = "0.1.0"

# ---------------------------------------------------------------------------
# SanitizedEvent — re-exported from integrations.sandbox when available,
# otherwise a local copy so the SDK works standalone.
# ---------------------------------------------------------------------------

try:
    from integrations.sandbox import SanitizedEvent  # noqa: F401 (re-export)
except ImportError:
    # Standalone SDK install: define a local copy with the same fields.
    @dataclass
    class SanitizedEvent:  # type: ignore[no-redef]
        """No-PII event delivered to ``notify``-tier plugins via ``on_notify()``.

        Fields
        ------
        event : str
            ``"message"`` or ``"reaction"``.
        sender_display_name : str | None
            Resolved display name (never a raw phone number or email).
            ``None`` when notification depth is ``"minimal"``.
        is_group : bool
        group_name : str | None
        has_attachment : bool
        timestamp : str
            ISO 8601 UTC string.
        preview : str | None
            First ~50 chars of message text — only set when notification
            depth is ``"preview"`` (opt-in by the user). Default ``None``.
        """
        event: str
        sender_display_name: str | None
        is_group: bool
        group_name: str | None
        has_attachment: bool
        timestamp: str
        preview: str | None = None

# ---------------------------------------------------------------------------
# Global plugin registry
# ---------------------------------------------------------------------------

registry: dict[str, type["BaseIntegration"]] = {}
"""Maps plugin NAME → class for every class decorated with @chatwire_plugin."""


# ---------------------------------------------------------------------------
# PluginManifest
# ---------------------------------------------------------------------------

@dataclass
class PluginManifest:
    """Describes a plugin's identity and configuration schema.

    This is automatically populated from the class attributes of a
    ``BaseIntegration`` subclass. Plugin authors typically don't construct
    this directly — use ``BaseIntegration.manifest()`` instead.
    """

    name: str
    """Stable short identifier (e.g. ``"greeter"``). Used as the config key."""

    version: str = "0.1.0"
    """Semantic version string (e.g. ``"1.2.3"``)."""

    author: str = ""
    """Plugin author / maintainer name."""

    description: str = ""
    """One-line description shown in the chatwire settings UI."""

    settings_schema: dict[str, Any] = field(default_factory=dict)
    """JSON Schema describing the plugin's config block.

    Follows the same convention as the built-in ``Integration.SETTINGS_SCHEMA``.
    The web settings page renders form controls from this schema.
    """


# ---------------------------------------------------------------------------
# BaseIntegration
# ---------------------------------------------------------------------------

class BaseIntegration(abc.ABC):
    """Abstract base class for chatwire plugins.

    Subclass this and implement the hook methods you need. All hooks have
    no-op default implementations so you only override what you use.

    Class variables to set on your subclass:

    - ``NAME`` (required): stable snake_case identifier
    - ``VERSION``: semver string (default ``"0.1.0"``)
    - ``AUTHOR``: author name (default ``""``)
    - ``DISPLAY_NAME``: human-readable label (default: ``NAME.title()``)
    - ``DESCRIPTION``: one-line description (default ``""``)
    - ``SETTINGS_SCHEMA``: JSON Schema dict (default ``{}``)

    Example::

        @chatwire_plugin
        class MyPlugin(BaseIntegration):
            NAME = "my_plugin"
            DISPLAY_NAME = "My Plugin"
            DESCRIPTION = "Does something useful."
            SETTINGS_SCHEMA = {
                "type": "object",
                "properties": {
                    "api_key": {"type": "string", "title": "API Key"},
                },
            }

            async def on_startup(self) -> None:
                print("My plugin started!")
    """

    NAME: str  # must be set by subclass
    TIER: str = "notify"
    """Sandbox tier — safe default for third-party plugins.

    New plugins start at ``"notify"`` so they never accidentally receive PII.
    Override to ``"official"`` only after the plugin has been reviewed and
    signed by the chatwire project maintainer.

    Values:
      ``"notify"``   — receives ``SanitizedEvent`` via ``on_notify()``.
                       No message text, no raw handles, no file paths.
      ``"official"`` — receives ``OfficialMessage`` via
                       ``on_official_message()``. Reviewed + signed only.
      ``"ui"``       — no bridge hooks at all (CSS/theme plugins).
    """
    VERSION: str = "0.1.0"
    AUTHOR: str = ""
    DISPLAY_NAME: str = ""
    DESCRIPTION: str = ""
    SETTINGS_SCHEMA: dict[str, Any] = {}

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config: dict[str, Any] = config or {}

    @property
    def config(self) -> dict[str, Any]:
        """The plugin's live config dict (read-only view)."""
        return self._config

    # ------------------------------------------------------------------
    # Lifecycle hooks — override as needed
    # ------------------------------------------------------------------

    async def on_startup(self) -> None:
        """Called once when the chatwire bridge starts up.

        Use this to open connections, register background tasks, etc.
        """

    async def on_shutdown(self) -> None:
        """Called once when the chatwire bridge shuts down.

        Use this to cancel tasks and release resources.
        """

    async def on_notify(self, event: "SanitizedEvent") -> None:
        """Called for ``notify``-tier plugins when a new message arrives.

        Receives a :class:`SanitizedEvent` with NO PII — sender display name,
        group info, attachment flag, and timestamp only.  Message text, phone
        numbers, email addresses, and file paths are never included.

        Override this to send push notifications, blink an LED, etc.
        The default implementation does nothing.
        """

    async def on_message_received(self, msg: Any) -> None:
        """Called for every inbound iMessage event delivered to this plugin.

        ``msg`` is an ``InboundMessage``-compatible object with at minimum:
        - ``text: str`` — message body
        - ``handle: str`` — sender handle (e.g. ``"+15551234567"``)
        - ``is_from_me: bool``
        - ``chat_guid: str | None``

        .. deprecated::
            New plugins should implement :meth:`on_notify` (for ``notify``
            tier) or ``on_official_message`` (for ``official`` tier) instead.
        """

    async def on_message_sent(self, msg: Any) -> None:
        """Called after an outbound message has been accepted by the bridge.

        ``msg`` carries the same fields as ``on_message_received`` plus
        ``outcome`` (a ``SendOutcome``-like object with ``status`` and ``hint``).
        """

    def settings_schema(self) -> dict[str, Any]:
        """Return the JSON Schema for this plugin's settings block.

        Defaults to the class-level ``SETTINGS_SCHEMA``. Override to build
        the schema dynamically if needed.
        """
        return self.__class__.SETTINGS_SCHEMA

    # ------------------------------------------------------------------
    # Compatibility shims for the existing Integration protocol
    # ------------------------------------------------------------------

    async def start(self, ctx: Any) -> None:
        """Bridge-facing lifecycle hook — delegates to ``on_startup``."""
        self._ctx = ctx
        await self.on_startup()

    async def stop(self) -> None:
        """Bridge-facing lifecycle hook — delegates to ``on_shutdown``."""
        await self.on_shutdown()

    async def on_inbound(self, msg: Any) -> None:
        """Bridge-facing event hook — delegates to ``on_message_received``.

        Called only by ``official``/``core`` tiers when ``on_official_message``
        is not defined (backward compat). ``notify``-tier plugins receive
        ``on_notify()`` instead and this is never called.
        """
        await self.on_message_received(msg)

    # ------------------------------------------------------------------
    # Manifest helper
    # ------------------------------------------------------------------

    @classmethod
    def manifest(cls) -> PluginManifest:
        """Return a ``PluginManifest`` populated from this class's attributes."""
        name = getattr(cls, "NAME", "unknown")
        display_name = getattr(cls, "DISPLAY_NAME", "") or name.replace("_", " ").title()
        return PluginManifest(
            name=name,
            version=getattr(cls, "VERSION", "0.1.0"),
            author=getattr(cls, "AUTHOR", ""),
            description=getattr(cls, "DESCRIPTION", display_name),
            settings_schema=getattr(cls, "SETTINGS_SCHEMA", {}),
        )


# ---------------------------------------------------------------------------
# @chatwire_plugin decorator
# ---------------------------------------------------------------------------

def chatwire_plugin(cls: type[BaseIntegration]) -> type[BaseIntegration]:
    """Class decorator that registers a ``BaseIntegration`` subclass.

    After decoration, the class is stored in ``chatwire_sdk.registry`` under
    its ``NAME``. This is how the chatwire runtime discovers installed plugins.

    Usage::

        @chatwire_plugin
        class MyPlugin(BaseIntegration):
            NAME = "my_plugin"
            ...

    The decorator is a no-op beyond registration — it returns the class
    unchanged, so normal inheritance and isinstance checks still work.
    """
    if not issubclass(cls, BaseIntegration):
        raise TypeError(
            f"@chatwire_plugin can only decorate BaseIntegration subclasses, "
            f"got {cls!r}"
        )
    name = getattr(cls, "NAME", None)
    if not name:
        raise ValueError(
            f"@chatwire_plugin: {cls.__name__} must define a non-empty NAME attribute"
        )
    registry[name] = cls
    return cls
