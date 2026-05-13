"""The Integration interface.

A chatwire integration is anything that wants to receive iMessage events
or send iMessages: a Telegram bot, the web UI, a generic webhook poster, an
ntfy push notifier, an SMTP-mirror, etc. Each lives in `integrations/<name>/`
and exposes a class satisfying the `Integration` Protocol below.

The runtime contract:
  - On startup the bridge core builds a `BridgeContext` and calls
    `Integration.start(ctx)` on every enabled integration.
  - Inbound iMessage events (read from chat.db) are pushed to every
    integration via `Integration.on_inbound(msg)`.
  - Outbound is initiated by the integration itself via `ctx.send_text` or
    `ctx.send_file`. The integration owns the trigger (Telegram callback,
    HTTP form submit, etc.); the context handles the iMessage send and
    the cross-integration echo dedup.
  - On shutdown `Integration.stop()` is called.

This module imports nothing integration-specific so it's safe to import from
anywhere — including from a third-party package whose entry-point declares
the integration class.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from chat_db import InboundMessage  # re-export for integrations to type against

__all__ = [
    "BridgeContext",
    "InboundMessage",
    "Integration",
    "OfficialMessage",
    "SanitizedEvent",
    "SendOutcome",
    "SendTarget",
]

# Re-export sandbox types so integrations can import from one place.
from integrations.sandbox import OfficialMessage, SanitizedEvent  # noqa: E402


@dataclass
class SendTarget:
    """Where an outbound iMessage is going. Either a 1:1 handle (kind="handle",
    value is e.g. "+15551234567") or a group chat (kind="chat", value is the
    AppleScript GUID like "iMessage;+;chat629…").
    """
    kind: str   # "handle" or "chat"
    value: str
    label: str  # human-readable — contact name or group display_name

    @property
    def is_group(self) -> bool:
        return self.kind == "chat"


@dataclass
class SendOutcome:
    """Outcome of an outbound send, in integration-friendly shape.

    `status` is one of "delivered", "sent", "pending", "failed":
      - delivered: peer confirmed receipt (iMessage only; SMS never returns
        a delivery receipt to Messages.app, so successful SMS sends report
        "sent" not "delivered").
      - sent: Messages.app accepted the send but no delivery receipt yet.
      - pending: AppleScript hasn't confirmed even acceptance — usually a
        race with Messages.app's outgoing queue.
      - failed: Messages.app reported an error code; `hint` carries the
        human-readable reason.

    `service` is "iMessage", "SMS", or "" if not yet known.
    `fell_back_to_sms` is True when iMessage was tried first and failed.
    `error` is the Messages.app error code from chat.db (0 on success).
    `original_error` carries the *initial* iMessage error code when
    `fell_back_to_sms` is True; otherwise 0. UI surfaces both so users
    can distinguish "iMessage deregistered, SMS worked" (success with
    diagnostic) from "everything failed" (true failure).
    """
    status: str
    hint: str
    service: str
    fell_back_to_sms: bool
    error: int = 0
    original_error: int = 0


class BridgeContext(Protocol):
    """Surface the bridge core exposes to each integration.

    Integrations don't construct this themselves — the core builds it once
    and passes it to `Integration.start()`. Stash it on `self` if you need
    it later.

    The four core methods (`send_text`, `send_file`, `name_for`, `mirror`)
    are the stable, minimal API for third-party integrations. The six
    extended members below (`contacts`, `reload_contacts`, `relay_scope`,
    `list_groups`, `services_for`, `outcomes_for`) are also part of the
    declared contract so that typed integrations can reference them without
    needing to cast through a concrete implementation.
    """

    async def send_text(self, target: SendTarget, body: str) -> SendOutcome:
        """Send a text iMessage to `target`. Returns once Messages.app has
        either accepted, rejected, or timed out the send."""
        ...

    async def send_file(self, target: SendTarget, path: Path) -> SendOutcome:
        """Send a file (image / video / arbitrary) to `target`."""
        ...

    def name_for(self, handle: str) -> str | None:
        """Resolve a handle ('+15551234567' or 'name@example.com') to its
        Contacts.app display name. Returns None if the handle isn't in the
        user's address book."""
        ...

    def mirror(self, event: str, **fields: object) -> None:
        """Append one JSONL line to the debug mirror file, if enabled.

        Integrations should call this for outbound sends they originate, so
        cross-integration consumers (notifications, the web UI's SSE feed)
        see them. Inbound mirroring is done by the core before it fans out.
        """
        ...

    # --- extended members (in-repo and plugin integrations) ---

    contacts: dict[str, str]
    """Live handle_lc → display-name mapping. Mutated by `reload_contacts`;
    integrations read from it directly for bulk lookups (e.g. inline search,
    slug-command generation). External plugins should prefer `name_for` for
    single-handle lookups and treat this dict as read-only."""

    def reload_contacts(self) -> int:
        """Re-read Contacts.app and refresh the shared `contacts` mapping.
        Returns the number of handles now in the mapping."""
        ...

    def relay_scope(self) -> dict[str, set[str]]:
        """Return the live relay scope: a dict with three keys —
        ``'self'``, ``'handles'``, and ``'groups'`` — each a set of strings
        (SELF handles, whitelisted 1:1 handles, whitelisted group GUIDs)."""
        ...

    def list_groups(self) -> list[dict]:
        """Return group chats visible in chat.db, most-recently-active first.
        Each dict: ``{guid, chat_identifier, name, last_rowid, participants}``.
        Returns an empty list when chat.db is unavailable."""
        ...

    def services_for(self, handles: list[str]) -> dict[str, list[str]]:
        """iMessage/SMS capability per handle from chat.db.
        Returns ``{handle_lc: ['iMessage', 'SMS', …]}``. Handles with no
        recorded messages return an empty list. Returns ``{}`` when chat.db
        is unavailable."""
        ...

    def outcomes_for(self, handles: list[str]) -> dict[str, object]:
        """Most-recent outgoing send stats per handle from chat.db.
        Returns ``{handle_lc: {service: stats}}``.  Returns ``{}`` when
        chat.db is unavailable."""
        ...

def integration_ui_meta(cls: type) -> dict:
    """Extract UI metadata from an integration class with sensible defaults.

    Returns a dict with keys: display_name, description, icon. These are
    optional class variables that integration authors can set for richer
    settings UI rendering. If absent, defaults are derived from NAME.

    Optional class variables:
        DISPLAY_NAME: str — Human-readable name (default: NAME.title())
        DESCRIPTION: str  — One-line description for the settings accordion
        ICON: str         — Emoji or short label (default: "")
    """
    name = getattr(cls, "NAME", "unknown")
    return {
        "display_name": getattr(cls, "DISPLAY_NAME", name.replace("_", " ").title()),
        "description": getattr(cls, "DESCRIPTION", ""),
        "icon": getattr(cls, "ICON", ""),
    }


@runtime_checkable
class Integration(Protocol):
    """The contract every integration satisfies.

    Implement this as a regular class — `runtime_checkable` Protocols don't
    require explicit inheritance, but doing so (e.g. `class TelegramIntegration:`
    with no base) is fine and is what the auto-discovery walker expects.

    Optional class variables for UI display (not part of the Protocol since
    they're optional — use `integration_ui_meta(cls)` to read with defaults):

        DISPLAY_NAME: str  — "ntfy notifications"
        DESCRIPTION: str   — "Push notifications via ntfy.sh"
        ICON: str          — "🔔"
    """

    NAME: str
    """Stable short name. Used as the config key and for log lines.
    Examples: "telegram", "webhook", "web", "slack". Must be a valid
    Python identifier so it can also be a module name."""

    TIER: str
    """Sandbox tier. Controls what data this integration may receive.

    Values:
      "ui"       — No data access. CSS/theme/frontend slots only.
      "notify"   — SanitizedEvent only (sender display name, no text/PII).
      "official" — OfficialMessage (text + opaque conv ID). Must be reviewed
                   and signed by project maintainer.
      "core"     — Built-in component; bypasses sandboxing entirely. Never
                   installable separately.

    Default for backward compatibility: ``"official"``.
    Third-party plugins built with the SDK default to ``"notify"`` (safe by
    default — see ``packages/sdk/``).
    """

    SETTINGS_SCHEMA: dict
    """JSON Schema describing this integration's config block. The web UI's
    settings page renders form controls from this; the core uses it to
    validate config.json before start(). May be empty `{}` if the
    integration has no settings.

    Schema properties may include standard JSON Schema fields (``title``,
    ``description``, ``enum``, ``default``, ``minimum``, ``maximum``) plus
    chatwire-specific ``x-ui-*`` extensions:

        x-ui-type: "password"   — render as password input
        x-ui-placeholder: str   — placeholder text for inputs
        x-ui-order: int         — field render order (lower first)
    """

    async def start(self, ctx: BridgeContext) -> None:
        """Begin running. Connect to the remote service, register handlers,
        spawn background tasks. Should not return until the integration is
        fully ready to receive inbound calls; long-running loops belong in
        tasks spawned here, not in the body of start()."""
        ...

    async def stop(self) -> None:
        """Shut down cleanly. Cancel background tasks, close connections,
        flush state. Called on bridge shutdown and on config reload."""
        ...

    async def on_inbound(self, msg: InboundMessage) -> None:
        """Handle one inbound iMessage event.

        The bridge has already filtered for whitelist scope and bridge-
        echo dedup; the integration just decides how to render this event
        on its surface (post to Telegram, push to a webhook, store in a
        DB, etc.).

        Called only for ``"official"`` tier plugins that do NOT implement
        ``on_official_message()``.  New official plugins should implement
        ``on_official_message()`` instead; ``on_inbound()`` is kept for
        backward compatibility.

        ``"notify"`` tier plugins receive ``on_notify()`` instead.
        ``"ui"`` tier plugins receive no bridge hooks at all.
        """
        ...

    # ------------------------------------------------------------------
    # Optional sandbox hooks — NOT required Protocol members.
    # The bridge calls these (when present) instead of on_inbound() for
    # sandboxed tiers. Integrations that omit them are skipped silently.
    #
    # async def on_notify(self, event: SanitizedEvent) -> None:
    #     """Called for 'notify'-tier integrations. No PII — sender display
    #     name, is_group, group_name, has_attachment, timestamp only."""
    #
    # async def on_official_message(self, msg: OfficialMessage) -> None:
    #     """Called for 'official'-tier integrations instead of on_inbound().
    #     Receives text + opaque conversation ID. No raw handles/paths."""
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Optional transform hooks — NOT required Protocol members.
    # Integrations that want to mutate message text implement these.
    # The bridge checks for their presence with getattr() and calls them
    # only when present; integrations that omit them are skipped silently.
    #
    # TRANSFORM_SCOPE (optional class variable, default "all"):
    #   Controls which surfaces the transform is applied to.
    #   "all"                    — every surface (default)
    #   "bridge"                 — bridge relay / outbound only
    #   "web"                    — web UI rendering only
    #   ["web", "telegram"]      — explicit allowlist
    #
    # def transform_inbound(self, text: str, context: dict) -> str:
    #     """Modify inbound message text before integrations render it.
    #
    #     Called by the bridge relay loop after reading from chat.db and
    #     before dispatching to on_inbound(). `context` carries at minimum:
    #       handle     — sender handle (lowercase)
    #       is_from_me — bool
    #       chat_guid  — str or None
    #     Returns the (possibly modified) text.
    #     """
    #
    # def transform_outbound(self, text: str, target: SendTarget) -> str:
    #     """Modify outbound text before sending via iMessage AppleScript.
    #
    #     Called by BridgeContext.send_text() before the AppleScript call.
    #     `target` is the SendTarget (handle or group). Returns the
    #     (possibly modified) text.
    #     """
    # ------------------------------------------------------------------
