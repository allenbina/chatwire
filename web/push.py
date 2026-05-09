"""Web-push payload helpers — pure functions with no FastAPI/form dependencies.

Extracted so tests can import these without triggering web/main.py's
side-effectful startup (DB open, contact load, FastAPI Form registration).
"""
from __future__ import annotations

import json

_VALID_NOTIFICATION_DETAILS = ("rich", "sender_only", "private")


def build_push_payload(
    evt: dict,
    detail: str,
    muted: list,
    name_fn=None,
    notify_mode: str = "all",
    selected_contacts: "list | None" = None,
) -> "str | None":
    """Build a JSON push payload string from a mirror event.

    Returns None if the event should be suppressed — wrong event type,
    self-sent message, muted contact, or not in the selected-contacts list.

    Args:
        evt:               A decoded mirror.jsonl event dict.
        detail:            One of 'rich', 'sender_only', 'private'.
        muted:             List of handle strings that should produce no push.
        name_fn:           Callable(handle) -> display name.  Defaults to identity.
        notify_mode:       'all' (default) or 'selected'.
        selected_contacts: List of handles to notify when mode='selected'.
    """
    if evt.get("event") != "inbound" or evt.get("is_from_me"):
        return None

    if name_fn is None:
        name_fn = lambda h: h  # noqa: E731

    handle = evt.get("handle", "")
    chat_guid = evt.get("chat_guid", "")

    # Mute check (case-insensitive).
    if handle and any(handle.lower() == m.lower() for m in muted):
        return None

    # Selected-contacts mode: only notify for explicitly chosen contacts.
    if notify_mode == "selected" and selected_contacts is not None:
        sel_lower = {s.lower() for s in selected_contacts}
        if handle and handle.lower() not in sel_lower:
            return None

    text_raw = (evt.get("text") or "").replace("\ufffc", "").strip() or "(photo)"

    if detail == "private":
        if chat_guid:
            return json.dumps({
                "title": "iMessage",
                "body": "New iMessage received",
                "chat": chat_guid,
                "tag": chat_guid,
            })
        return json.dumps({
            "title": "iMessage",
            "body": "New iMessage received",
            "handle": handle,
            "tag": handle,
        })

    if chat_guid:
        group = evt.get("chat_name") or "Group"
        sender = name_fn(handle) if handle else ""
        if detail == "sender_only":
            body_text = f"Message from {sender}" if sender else "New group message"
        else:  # rich
            body_text = (f"{sender}: " if sender else "") + text_raw
        return json.dumps({
            "title": f"iMessage [{group}]",
            "body": body_text[:140],
            "chat": chat_guid,
            "tag": chat_guid,
        })

    # 1-to-1
    display = name_fn(handle)
    if detail == "sender_only":
        return json.dumps({
            "title": f"iMessage from {display}",
            "body": f"Message from {display}",
            "handle": handle,
            "tag": handle,
        })
    # rich
    return json.dumps({
        "title": f"iMessage from {display}",
        "body": text_raw[:140],
        "handle": handle,
        "tag": handle,
    })
