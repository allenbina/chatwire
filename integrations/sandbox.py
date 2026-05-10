"""Plugin sandbox — PII firewall between the bridge core and third-party plugins.

Architecture
------------
Three public tiers define what data a plugin may receive:

  ui       — Nothing. CSS / theme / frontend slots only. No bridge hooks.
  notify   — SanitizedEvent: sender display name, is_group, group_name,
             has_attachment, timestamp. NO message text, phone, email,
             file paths.
  official — OfficialMessage: opaque conversation ID, display name, text,
             attachment bytes (NOT paths), send capability.
             NO raw phone/email, NO contact list, NO delivery stats, NO
             config secrets. Must be reviewed + signed by project maintainer.

A fourth internal tier:

  core     — Bypass sandboxing entirely. Only built-in components that ship
             with chatwire and are never installable separately (web UI,
             content_filter, anti_spam). They receive the real BridgeContext.

ConversationMap
---------------
Maps opaque UUID tokens ↔ real handles/GUIDs so official plugins can send
replies without ever learning the raw phone number or email address.

SandboxedContext
----------------
Wraps BridgeContextImpl. Allows only the two send methods for official tier;
blocks every other BridgeContext attribute via __getattr__.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Public data shapes
# ---------------------------------------------------------------------------

@dataclass
class SanitizedEvent:
    """Passed to ``on_notify()`` for ``notify``-tier plugins.

    Contains NO personally identifiable information: no message text,
    no phone numbers, no email addresses, no file paths.

    The optional ``preview`` field is only populated when the user has
    configured ``notification_depth = "preview"`` for this plugin (Chunk 6).
    At ``"sender"`` depth ``sender_display_name`` is set; at ``"minimal"``
    depth it is ``None``.
    """
    event: str                          # "message" | "reaction"
    sender_display_name: str | None     # resolved name, NOT phone/email
    is_group: bool
    group_name: str | None
    has_attachment: bool
    timestamp: str                      # ISO 8601
    preview: str | None = None          # first ~50 chars, only if depth="preview"
    # Explicitly absent: text, handle, attachments, chat_guid


@dataclass
class OfficialMessage:
    """Passed to ``on_official_message()`` for ``official``-tier plugins.

    Contains message text but NO raw identifiers. Plugins that need to reply
    use ``SandboxedContext.send_text(conversation_id, body)`` — the core
    resolves the opaque ID to the real handle internally.
    """
    conversation_id: str                # opaque UUID — only core knows the real handle
    sender_display_name: str            # display name, NOT phone/email
    text: str
    is_group: bool
    group_name: str | None
    attachments: list[dict]             # [{data: bytes, mime: str, filename: str}]
    timestamp: str                      # ISO 8601
    is_from_me: bool
    # Explicitly absent: handle, chat_guid, file paths, parent_handle


# ---------------------------------------------------------------------------
# Conversation ID mapping
# ---------------------------------------------------------------------------

class ConversationMap:
    """Bidirectional map: opaque UUID token ↔ real handle/GUID.

    Only the bridge core holds a ConversationMap instance. Plugins receive
    opaque UUIDs; the core resolves them internally when needed.
    """

    def __init__(self) -> None:
        self._to_real: dict[str, str] = {}
        self._to_opaque: dict[str, str] = {}

    def get_or_create(self, real_id: str) -> str:
        """Return (or create) the opaque UUID for ``real_id``."""
        if real_id not in self._to_opaque:
            opaque = str(uuid.uuid4())
            self._to_opaque[real_id] = opaque
            self._to_real[opaque] = real_id
        return self._to_opaque[real_id]

    def resolve(self, opaque_id: str) -> str | None:
        """Resolve an opaque UUID back to the real handle/GUID, or ``None``."""
        return self._to_real.get(opaque_id)


# ---------------------------------------------------------------------------
# Sandboxed context
# ---------------------------------------------------------------------------

class SandboxedContext:
    """Wraps BridgeContextImpl; enforces tier data restrictions.

    For ``official`` tier: exposes only ``send_text`` and ``send_file``
    (via opaque conversation ID) and ``mirror``.

    For ``notify`` and ``ui`` tiers: no methods are exposed.

    ``core`` tier bypasses this wrapper entirely — the real BridgeContextImpl
    is passed directly.
    """

    def __init__(self, real_ctx, tier: str, conv_map: ConversationMap) -> None:
        # Store on object __dict__ directly to avoid __getattr__ recursion.
        object.__setattr__(self, "_ctx", real_ctx)
        object.__setattr__(self, "_tier", tier)
        object.__setattr__(self, "_conv_map", conv_map)

    async def send_text(self, conversation_id: str, body: str):
        """Send text via an opaque conversation ID. Core resolves internally."""
        tier = object.__getattribute__(self, "_tier")
        if tier != "official":
            raise PermissionError(
                f"Tier '{tier}' cannot send messages. "
                "Only 'official' plugins may call send_text()."
            )
        ctx = object.__getattribute__(self, "_ctx")
        conv_map = object.__getattribute__(self, "_conv_map")
        real_id = conv_map.resolve(conversation_id)
        if not real_id:
            raise ValueError(f"Unknown conversation: {conversation_id}")
        from integrations.base import SendTarget
        kind = "chat" if ";" in real_id else "handle"
        label = ctx.name_for(real_id) or real_id
        target = SendTarget(kind=kind, value=real_id, label=label)
        return await ctx.send_text(target, body)

    async def send_file(self, conversation_id: str, data: bytes, mime_type: str):
        """Send file bytes via an opaque conversation ID. Core resolves internally."""
        tier = object.__getattribute__(self, "_tier")
        if tier != "official":
            raise PermissionError(
                f"Tier '{tier}' cannot send files. "
                "Only 'official' plugins may call send_file()."
            )
        ctx = object.__getattribute__(self, "_ctx")
        conv_map = object.__getattribute__(self, "_conv_map")
        real_id = conv_map.resolve(conversation_id)
        if not real_id:
            raise ValueError(f"Unknown conversation: {conversation_id}")
        import os
        import tempfile
        from pathlib import Path
        from integrations.base import SendTarget
        suffix = "." + mime_type.split("/")[-1] if "/" in mime_type else ""
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
            f.write(data)
            tmp_path = f.name
        try:
            kind = "chat" if ";" in real_id else "handle"
            label = ctx.name_for(real_id) or real_id
            target = SendTarget(kind=kind, value=real_id, label=label)
            return await ctx.send_file(target, Path(tmp_path))
        finally:
            os.unlink(tmp_path)

    def mirror(self, event: str, **fields):
        """Allow mirror calls for cross-integration echo (all tiers)."""
        ctx = object.__getattribute__(self, "_ctx")
        return ctx.mirror(event, **fields)

    def __getattr__(self, name: str):
        """Block every other BridgeContext attribute."""
        tier = object.__getattribute__(self, "_tier")
        raise PermissionError(
            f"Plugin tier '{tier}' cannot access BridgeContext.{name}. "
            f"Blocked attributes: contacts, name_for, relay_scope, list_groups, "
            f"services_for, outcomes_for, reload_contacts, spam_whitelist, chatdb."
        )
