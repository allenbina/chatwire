"""Format inbound iMessage events for Telegram and parse reply targets back out.

The prefix shape is the only contract between relay-outbound and reply-inbound:
Telegram doesn't let us attach sidechannel metadata to text messages, so whatever
we need to route a reply back to the right place has to survive a round trip
through a plain string.

1:1 messages:   "From <name> (<handle>): <body>"
Group messages: "[<chat_name>] From <name> (<handle>): <body>"

For group messages the chat_name is a visible tag, not a GUID. The bridge
maintains a chat_name -> GUID map updated on every inbound; parse_reply_target
returns the tag and the caller resolves it. Unnamed groups are given a
synthetic short tag by the caller so they still fit this shape.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


PREFIX_RE = re.compile(
    r"^(?:\[(?P<chat>[^\]]+)\]\s+)?From\s+(?P<name>.+?)\s+\((?P<handle>[^)]+)\):\s?",
    re.DOTALL,
)


@dataclass
class ReplyTarget:
    handle: str
    # Chat-name tag when the replied-to message was from a group chat.
    # Empty for 1:1 messages. The caller must resolve this to a chat GUID.
    chat_name: str = ""

    @property
    def is_group(self) -> bool:
        return bool(self.chat_name)


def format_inbound(
    handle: str,
    display_name: str | None,
    body: str,
    chat_name: str | None = None,
) -> str:
    name = display_name or handle
    base = f"From {name} ({handle}): {body}"
    if chat_name:
        return f"[{chat_name}] {base}"
    return base


def parse_reply_target(replied_text: str) -> ReplyTarget | None:
    """Pull the iMessage handle (and group-chat tag, if any) out of a previously
    relayed inbound message.

    Returns None if the replied-to text was not a relayed inbound (e.g. a bot
    ack). For group messages, ReplyTarget.chat_name is set and the handle is
    still the sender — callers should prefer the chat when replying.
    """
    m = PREFIX_RE.match(replied_text or "")
    if not m:
        return None
    return ReplyTarget(handle=m.group("handle"), chat_name=m.group("chat") or "")
