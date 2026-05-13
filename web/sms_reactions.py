"""SMS text-pattern reaction detection.

Standalone module so it can be unit-tested without importing the heavy
web/main.py dependency tree (FastAPI app, pydantic models, chat.db, etc.).
"""
from __future__ import annotations

import re
from typing import Optional

_SMS_REACTION_RE = re.compile(
    r'^(Liked|Loved|Laughed at|Emphasized|Questioned|Disliked|👍|❤️|😂|😢|‼️|❓|👎)\s+(?:to\s+)?["\u201c](.+)["\u201d]$',
    re.DOTALL,
)
_SMS_MEDIA_REACTION_RE = re.compile(
    r'^(Liked|Loved|Laughed at|Emphasized|Questioned|Disliked|👍|❤️|😂|😢|‼️|❓|👎)'
    r'\s+(?:to\s+)?an?\s+(image|photo|picture|video|gif|sticker|audio|voice\s+message|attachment|file|link)$',
    re.IGNORECASE | re.DOTALL,
)
_SMS_REACTION_EMOJI: dict = {
    "Liked": "👍",
    "Loved": "❤️",
    "Laughed at": "😂",
    "Emphasized": "‼️",
    "Questioned": "❓",
    "Disliked": "👎",
    "😢": "😢",
}
# Maps the media noun from _SMS_MEDIA_REACTION_RE → attachment kind.
# None means "any attachment"; a string means a specific kind.
_SMS_MEDIA_KIND_MAP: dict = {
    "image": "image",
    "photo": "image",
    "picture": "image",
    "gif": "image",
    "sticker": "image",
    "video": "video",
    "audio": "audio",
    "voice message": "audio",
    "attachment": None,
    "file": None,
    "link": None,
}


def _sender_of(msg: dict) -> dict:
    """Build a tapback sender entry from a reaction message dict."""
    if msg.get("from_me"):
        name = "You"
    else:
        name = msg.get("sender_name") or msg.get("sender_handle") or "Unknown"
    time_val = msg.get("ts") or ""
    return {"name": name, "time": str(time_val) if time_val else ""}


def apply_sms_reactions(msgs: list) -> list:
    """Detect Android SMS text-pattern reactions and convert them to tapbacks.

    Handles two reaction forms that Android contacts send when reacting to
    iMessages:

    Text reactions (quoted original text):
      👍 "original message text"
      Liked "some text"
      Loved to "some text"

    Media reactions (no quoted text — reacting to an attachment):
      Loved an image
      Liked a video
      😢 to a photo

    For text reactions we search backward for the first message whose text
    contains the quoted string and attach a synthetic tapback.

    For media reactions we search backward for the first message that has
    attachments whose kind matches the media noun (image, video, etc.).

    In both cases if no match is found the message is left as-is (plain text).
    """
    suppress: set = set()
    for i, entry in enumerate(msgs):
        raw = entry.get("text") or ""
        # Strip zero-width spaces/hair spaces that Android wraps around emojis
        text = re.sub(r'[\u200a\u200b\u200c\u200d\ufeff]', '', raw).strip()

        # --- text reaction ---
        m = _SMS_REACTION_RE.match(text)
        if m:
            verb, quoted = m.group(1), m.group(2)
            emoji = _SMS_REACTION_EMOJI.get(verb, verb)
            for j in range(i - 1, max(i - 51, -1), -1):
                if j in suppress:
                    continue
                target = msgs[j]
                t_text = target.get("text") or ""
                if t_text and (quoted in t_text or t_text in quoted):
                    existing = next(
                        (tb for tb in target.setdefault("tapbacks", []) if tb["type"] == emoji),
                        None,
                    )
                    sender = _sender_of(entry)
                    if existing:
                        existing["senders"].append(sender)
                    else:
                        target["tapbacks"].append({"type": emoji, "senders": [sender]})
                    suppress.add(i)
                    break
            continue

        # --- media reaction ---
        mm = _SMS_MEDIA_REACTION_RE.match(text)
        if mm:
            verb = mm.group(1)
            media_noun = mm.group(2).lower().strip()
            # Normalise multi-word nouns ("voice message" captured as "voice  message")
            media_noun = re.sub(r'\s+', ' ', media_noun)
            emoji = _SMS_REACTION_EMOJI.get(verb, verb)
            want_kind: Optional[str] = _SMS_MEDIA_KIND_MAP.get(media_noun)
            # want_kind is None → matches any attachment; str → specific kind
            for j in range(i - 1, max(i - 51, -1), -1):
                target = msgs[j]
                atts = target.get("attachments") or []
                if not atts:
                    continue
                matched = (
                    want_kind is None
                    or any(a.get("kind") == want_kind for a in atts)
                )
                if matched:
                    existing = next(
                        (tb for tb in target.setdefault("tapbacks", []) if tb["type"] == emoji),
                        None,
                    )
                    sender = _sender_of(entry)
                    if existing:
                        existing["senders"].append(sender)
                    else:
                        target["tapbacks"].append({"type": emoji, "senders": [sender]})
                    suppress.add(i)
                    break

    return [entry for i, entry in enumerate(msgs) if i not in suppress]
