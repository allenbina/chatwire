"""chatwire runtime core.

Responsibility breakdown:

  - **This file** owns the chat.db poll loop, the relay-scope filter (SELF +
    whitelist), bridge-echo dedup so our own outbound doesn't bounce back,
    the JSONL debug mirror, and the integration registry.
  - **`integrations/<name>/`** owns rendering inbound events on a specific
    surface (Telegram, webhook, …) and translating that surface's user
    actions into outbound iMessage sends. Integrations call back into this
    file via the `BridgeContext` they receive in `start()`.

Outbound is initiated by an integration via `ctx.send_text` / `ctx.send_file`;
the context wraps the AppleScript send and records the echo so the next poll
doesn't relay our own send back through every integration.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import deque
from dataclasses import replace as _dc_replace
from pathlib import Path

import importlib
import importlib.metadata
import inspect

import config as _bridge_config  # noqa: E402 — must run before env-consuming imports
CFG = _bridge_config.apply_to_environ()
from config import STATE_DIR  # noqa: E402

from chat_db import ChatDBReader, InboundMessage
from contacts import load_lookup as load_contacts
from echo_log import register as echo_register, seen_recently as echo_seen
from chat_send import (
    SendResult, send_file_confirm, send_file_to_chat_confirm,
    send_text_confirm, send_text_to_chat_confirm,
)
from whitelist import all_groups as wl_all_groups, all_handles as wl_all
from integrations.base import BridgeContext, SendOutcome, SendTarget
from verify import PluginNotTrusted, verify_plugin

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    level=logging.INFO,
)
# httpx at INFO prints the bot-token-bearing getUpdates URL every ~10s.
# Stderr is world-readable on this Mac; anything that leaks the token there
# owns the bot.
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("chatwire")

# ---------- core configuration ----------

SELF_HANDLES = {
    h.strip().lower()
    for h in os.environ.get("SELF_HANDLES", "").split(",")
    if h.strip()
}

POLL_INTERVAL_S = float(os.environ.get("POLL_INTERVAL_S", "2"))

# Optional observer/debug log: when set, every relayed inbound message and
# successful outbound send is appended as one JSONL line. Not touched by
# normal operation; safe to `tail -f` from a separate SSH session.
DEBUG_MIRROR_FILE = os.environ.get("DEBUG_MIRROR_FILE", "").strip() or None

STATE_DIR.mkdir(parents=True, exist_ok=True)
STATE_PATH = STATE_DIR / "state.json"

# ---------- relay scope ----------

def relay_handles() -> set[str]:
    """Live view: SELF (env) + whitelist (runtime-mutable file)."""
    return SELF_HANDLES | wl_all()


def relay_groups() -> set[str]:
    """Live view of whitelisted group-chat GUIDs. Groups are opt-in: none are
    seeded from env, they're added via inline search or /whitelist_add."""
    return wl_all_groups()


# ---------- mirror (debug JSONL) ----------

def mirror(event: str, **fields: object) -> None:
    """Append one JSONL line to DEBUG_MIRROR_FILE if set. Never raises."""
    if not DEBUG_MIRROR_FILE:
        return
    line = json.dumps(
        {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "event": event, **fields},
        ensure_ascii=False, default=str,
    )
    try:
        with open(DEBUG_MIRROR_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        log.exception("mirror append failed")


# ---------- bridge-echo dedup ----------
# Short-lived memory of what the bridge itself just sent, so we don't echo
# our own outbound through the inbound poll. Keyed by (handle, body, ts).
# iMessage records bridge sends as is_from_me=1 with handle == recipient, so
# without this every outbound send would bounce back to every integration.
SENT_ECHO_WINDOW_S = 30
_sent_recently: deque[tuple[str, str, float]] = deque(maxlen=64)
# Photos can't be deduped by body (chat.db records them with text="￼"), so
# track a separate "we just sent SOME photo to <handle>" memory.
_sent_photos_recently: deque[tuple[str, float]] = deque(maxlen=64)


def _record_text_send(handle: str, body: str) -> None:
    _sent_recently.append((handle.lower(), body.strip(), time.time()))
    echo_register(handle, "text", body)


def _record_photo_send(handle: str) -> None:
    _sent_photos_recently.append((handle.lower(), time.time()))
    echo_register(handle, "photo")


def _is_bridge_text_echo(handle: str, body: str) -> bool:
    now = time.time()
    target = (handle.lower(), body.strip())
    while _sent_recently and now - _sent_recently[0][2] > SENT_ECHO_WINDOW_S:
        _sent_recently.popleft()
    if any((h, b) == target for h, b, _ in _sent_recently):
        return True
    # Cross-process: web-originated text sends record into echo_log too.
    return echo_seen(handle, "text", body, SENT_ECHO_WINDOW_S)


def _is_bridge_photo_echo(handle: str) -> bool:
    now = time.time()
    target = handle.lower()
    while _sent_photos_recently and now - _sent_photos_recently[0][1] > SENT_ECHO_WINDOW_S:
        _sent_photos_recently.popleft()
    if any(h == target for h, _ in _sent_photos_recently):
        return True
    return echo_seen(handle, "photo", None, SENT_ECHO_WINDOW_S)


# ---------- inbound filter ----------

def _should_relay(msg: InboundMessage) -> bool:
    # Group-chat path: gate on the chat GUID, not the sender handle. Members
    # of a whitelisted group get relayed regardless of whether their own
    # handle is on the 1:1 whitelist — that's the whole point.
    if msg.is_group:
        if msg.chat_guid not in relay_groups():
            return False
        # Our own outgoing to group chats arrive with handle='' (handle_id is
        # NULL on outgoing group rows); don't relay those as incoming. Bridge
        # echoes on group sends are handled by the same handle=='' filter.
        if msg.is_from_me:
            return False
        return True

    h = msg.handle.lower()
    if h not in relay_handles():
        return False
    # Self-messages to your own Apple ID are recorded ONLY as is_from_me=1
    # in chat.db (there's no separate "received" row on the same account).
    # Relay those so the Phase A self-test actually produces traffic.
    if msg.is_from_me:
        if h not in SELF_HANDLES:
            return False  # bridge's own outbound to non-self contacts — skip
        if _is_bridge_text_echo(msg.handle, msg.text):
            return False  # we just sent this text from an integration; don't bounce
        if msg.attachments and _is_bridge_photo_echo(msg.handle):
            return False  # we just sent a photo from an integration; don't bounce
    return True


def _group_consecutive(messages: list[InboundMessage]) -> list[list[InboundMessage]]:
    """Collapse runs of relayable messages from the same handle AND chat into
    batches.

    Multi-line bursts ("yes\\nyes\\nlol") that arrive in one poll get rendered
    as a single message instead of N separate ones. We also key on chat_guid
    so an Eileen-in-Civi-kids message doesn't get merged with a Eileen-1:1
    message that happens to arrive in the same poll. Messages with
    attachments or threaded-reply context aren't merged because the
    integration's prefix/quote rendering makes mashing them visually messy.
    """
    batches: list[list[InboundMessage]] = []
    for m in messages:
        if not _should_relay(m):
            continue
        if (batches
                and batches[-1][-1].handle == m.handle
                and batches[-1][-1].chat_guid == m.chat_guid
                and not m.attachments
                and not (m.parent_text or m.parent_handle)
                and not batches[-1][-1].attachments
                and not (batches[-1][-1].parent_text or batches[-1][-1].parent_handle)):
            batches[-1].append(m)
        else:
            batches.append([m])
    return batches


# ---------- message transform pipeline ----------

def _scope_applies(integ: object, surface: str) -> bool:
    """Return True if the integration's TRANSFORM_SCOPE covers `surface`."""
    scope = getattr(integ, "TRANSFORM_SCOPE", "all")
    if scope == "all":
        return True
    if isinstance(scope, str):
        return scope == surface
    return surface in scope


def _run_transform_inbound(integrations: list, text: str, context: dict) -> str:
    """Chain all transform_inbound() hooks over `text` in load order.

    Only applies transforms whose TRANSFORM_SCOPE covers "bridge".
    Integrations without transform_inbound are skipped silently.
    Exceptions in a transform are logged and that transform is skipped;
    subsequent transforms still run on the last good text value.
    """
    for integ in integrations:
        fn = getattr(integ, "transform_inbound", None)
        if fn is None:
            continue
        if not _scope_applies(integ, "bridge"):
            continue
        try:
            text = fn(text, context)
        except Exception:
            log.exception(
                "integration %s transform_inbound failed",
                getattr(integ, "NAME", "?"),
            )
    return text


def _run_transform_outbound(integrations: list, text: str, target: "SendTarget") -> str:
    """Chain all transform_outbound() hooks over `text` in load order.

    Only applies transforms whose TRANSFORM_SCOPE covers "bridge".
    Integrations without transform_outbound are skipped silently.
    Exceptions are logged; subsequent transforms still run.
    """
    for integ in integrations:
        fn = getattr(integ, "transform_outbound", None)
        if fn is None:
            continue
        if not _scope_applies(integ, "bridge"):
            continue
        try:
            text = fn(text, target)
        except Exception:
            log.exception(
                "integration %s transform_outbound failed",
                getattr(integ, "NAME", "?"),
            )
    return text


# ---------- BridgeContext implementation ----------

def _to_outcome(r: SendResult) -> SendOutcome:
    """SendResult is the rich AppleScript-flavored shape; SendOutcome is the
    integration-friendly shape. The interesting fields line up 1:1."""
    return SendOutcome(
        status=r.status,
        hint=r.hint,
        service=r.service or "",
        fell_back_to_sms=r.fell_back_to_sms,
        error=r.error,
        original_error=r.original_error,
    )


class BridgeContextImpl:
    """Concrete BridgeContext passed to each integration's start().

    Implements the `integrations.base.BridgeContext` Protocol (send_text,
    send_file, name_for, mirror) plus a few in-repo extras consumed by the
    bundled Telegram (and future web) integrations:

      - `contacts`: shared handle_lc -> display_name dict (mutated by
        reload_contacts; integrations read from it directly for bulk lookup).
      - `chatdb`: the live ChatDBReader, for capability/group queries.
      - `reload_contacts()`: re-read Contacts.app and update the shared dict.
      - `relay_scope()`: SELF + whitelist + group GUIDs.

    Third-party integrations should type their `ctx` as the Protocol and
    only use the four declared methods. The extras are an in-repo
    convenience.
    """

    def __init__(self, contacts: dict[str, str], chatdb: ChatDBReader | None):
        self.contacts = contacts
        self.chatdb = chatdb
        # Set by amain() after _build_integrations(); holds the live integration
        # list so send_text/send_file can run transform_outbound() hooks.
        self.integrations: list = []

    async def send_text(self, target: SendTarget, body: str) -> SendOutcome:
        body = _run_transform_outbound(self.integrations, body, target)
        if target.is_group:
            r = await asyncio.to_thread(send_text_to_chat_confirm, target.value, body)
        else:
            r = await asyncio.to_thread(send_text_confirm, target.value, body)
            # Group outgoing rows have handle='' and are filtered by
            # _should_relay anyway; only 1:1 sends need echo registration.
            _record_text_send(target.value, body)
        return _to_outcome(r)

    async def send_file(self, target: SendTarget, path: Path) -> SendOutcome:
        # File transfers have no text body to transform; run the pipeline with
        # an empty string so transforms that inspect target still fire. We
        # discard the return value — send_file carries no text.
        _run_transform_outbound(self.integrations, "", target)
        if target.is_group:
            r = await asyncio.to_thread(send_file_to_chat_confirm, target.value, path)
        else:
            r = await asyncio.to_thread(send_file_confirm, target.value, path)
            _record_photo_send(target.value)
        return _to_outcome(r)

    def name_for(self, handle: str) -> str | None:
        return self.contacts.get(handle.lower())

    def mirror(self, event: str, **fields: object) -> None:
        mirror(event, **fields)

    def reload_contacts(self) -> int:
        new = load_contacts()
        self.contacts.clear()
        self.contacts.update(new)
        return len(self.contacts)

    def relay_scope(self) -> dict[str, frozenset[str]]:
        return {
            "self": frozenset(SELF_HANDLES),
            "handles": frozenset(relay_handles()),
            "groups": frozenset(relay_groups()),
        }

    @property
    def spam_whitelist(self) -> frozenset[str]:
        """Read-only view of the spam-detection name whitelist.

        Returns the names that are stripped from outbound text before
        broadcast-detection hashing.  Plugins may read this but cannot
        modify it — the whitelist lives in config.json and is only
        writable via the web settings route.
        """
        try:
            names = CFG.get("web", {}).get("spam_whitelist", [])
            if isinstance(names, list):
                return frozenset(n.strip() for n in names if n.strip())
        except Exception:
            pass
        return frozenset()

    def list_groups(self) -> list[dict]:
        if self.chatdb is None:
            return []
        return self.chatdb.list_groups()

    def services_for(self, handles: list[str]) -> dict[str, list[str]]:
        if self.chatdb is None:
            return {}
        return self.chatdb.services_for(handles)

    def outcomes_for(self, handles: list[str]) -> dict[str, object]:
        if self.chatdb is None:
            return {}
        return self.chatdb.outcomes_for(handles)


# ---------- integration registry ----------

INTEGRATIONS_DIR = Path(__file__).parent / "integrations"


def _looks_like_integration(cls: object) -> bool:
    """Structural check used to find Integration classes in a module.

    `runtime_checkable` Protocol's `isinstance` works on instances; we want
    to find classes before instantiating them. The two attributes that
    uniquely identify an Integration class are `NAME` and `SETTINGS_SCHEMA`.
    """
    return (
        inspect.isclass(cls)
        and isinstance(getattr(cls, "NAME", None), str)
        and isinstance(getattr(cls, "SETTINGS_SCHEMA", None), dict)
    )


def _classes_from_module(mod) -> list[type]:
    """Return Integration-shaped classes defined in `mod`. Skips re-exports
    (e.g. `from integrations.base import Integration`) by filtering on
    __module__."""
    out = []
    for cls in vars(mod).values():
        if _looks_like_integration(cls) and getattr(cls, "__module__", "") == mod.__name__:
            out.append(cls)
    return out


def _discover_integration_classes() -> dict[str, type]:
    """Find every Integration class available to this install.

    Two sources, merged with built-ins winning on name collisions:
      1. `integrations/<name>/` directories in this repo.
      2. `chatwire.integrations` entry points from pip-installed plugins.

    Failures in one integration don't take down the others — log and skip.
    """
    out: dict[str, type] = {}

    if INTEGRATIONS_DIR.is_dir():
        for child in sorted(INTEGRATIONS_DIR.iterdir()):
            if not child.is_dir() or child.name.startswith("_"):
                continue
            try:
                mod = importlib.import_module(f"integrations.{child.name}")
            except Exception:
                log.exception("integration %s failed to import; skipping", child.name)
                continue
            for cls in _classes_from_module(mod):
                out[cls.NAME] = cls

    try:
        eps = importlib.metadata.entry_points(group="chatwire.integrations")
    except Exception:
        eps = []
    for ep in eps:
        # Verify the plugin's signature before loading any of its code.
        # Built-ins (integrations/ directory) are trusted by construction;
        # only pip-installed entry-point plugins need a signature check.
        dist = getattr(ep, "dist", None)
        dist_name = dist.metadata["Name"] if dist is not None else ep.name
        try:
            verify_plugin(dist_name)
        except PluginNotTrusted as exc:
            log.warning("Refusing to load plugin '%s': %s", dist_name, exc)
            continue
        except Exception:
            log.exception(
                "Unexpected error verifying plugin '%s'; skipping", dist_name
            )
            continue

        try:
            cls = ep.load()
        except Exception:
            log.exception("entry point %s failed to load; skipping", ep.name)
            continue
        if not _looks_like_integration(cls):
            log.warning("entry point %s does not look like an Integration "
                        "(missing NAME/SETTINGS_SCHEMA); skipping", ep.name)
            continue
        if cls.NAME in out:
            log.info("entry point %s: %s already registered as built-in; skipping",
                     ep.name, cls.NAME)
            continue
        out[cls.NAME] = cls

    return out


def _validate_block(name: str, block: dict, schema: dict) -> None:
    """Validate `block` against `schema`. Fail fast at startup with a clear
    error — half-configured integrations cause baffling runtime crashes."""
    try:
        import jsonschema  # type: ignore
    except ImportError:
        log.warning("jsonschema not installed; skipping settings validation for %s", name)
        return
    try:
        jsonschema.validate(block, schema)
    except jsonschema.ValidationError as e:  # type: ignore[attr-defined]
        path = ".".join(str(p) for p in e.absolute_path) or "<root>"
        raise SystemExit(
            f"integration {name!r}: invalid config at {path}: {e.message}"
        ) from e


def _build_integrations(cfg: dict) -> list:
    """Instantiate every enabled integration found via discovery.

    `enabled: true` in the integration's config block opts it in. A class
    with no block in config (or `enabled: false`) is skipped silently — that
    way a third-party plugin's mere presence on disk doesn't run it.
    """
    classes = _discover_integration_classes()
    int_cfg = cfg.get("integrations") or {}
    out: list = []
    for name in sorted(classes):
        cls = classes[name]
        block = int_cfg.get(name) or {}
        if not block.get("enabled"):
            continue
        _validate_block(name, block, cls.SETTINGS_SCHEMA)
        try:
            out.append(cls(block))
        except Exception:
            log.exception("integration %s: failed to instantiate; skipping", name)
    return out


# ---------- poll loop ----------

async def poll_loop(reader: ChatDBReader, integrations: list) -> None:
    log.info("poll loop starting (interval=%.1fs, integrations=%s, relay_handles=%s)",
             POLL_INTERVAL_S,
             [getattr(i, "NAME", "?") for i in integrations],
             sorted(relay_handles()))
    while True:
        try:
            messages = reader.poll()
            for batch in _group_consecutive(messages):
                if len(batch) == 1:
                    msg = batch[0]
                else:
                    head = batch[0]
                    msg = InboundMessage(
                        rowid=batch[-1].rowid,
                        handle=head.handle,
                        text="\n".join(m.text.strip() for m in batch if m.text.strip()),
                        attachments=[],
                        is_from_me=head.is_from_me,
                        chat_guid=head.chat_guid,
                        chat_identifier=head.chat_identifier,
                        chat_name=head.chat_name,
                        is_group=head.is_group,
                    )
                # Mirror inbound centrally: integrations only mirror their
                # own outbound. Otherwise N integrations would each log the
                # same inbound row N times.
                mirror("inbound", handle=msg.handle, is_from_me=msg.is_from_me,
                       text=msg.text,
                       attachments=[str(a.path) for a in msg.attachments],
                       reply_to=msg.parent_handle or None,
                       chat_guid=msg.chat_guid or None,
                       chat_name=msg.chat_name or None)
                # Run inbound transform pipeline before fan-out.
                transform_context = {
                    "handle": msg.handle,
                    "is_from_me": msg.is_from_me,
                    "chat_guid": msg.chat_guid,
                }
                transformed_text = _run_transform_inbound(
                    integrations, msg.text, transform_context
                )
                if transformed_text != msg.text:
                    msg = _dc_replace(msg, text=transformed_text)
                for integ in integrations:
                    try:
                        await integ.on_inbound(msg)
                    except Exception:
                        log.exception("integration %s on_inbound failed",
                                      getattr(integ, "NAME", "?"))
        except Exception:
            log.exception("poll iteration failed; sleeping and retrying")
        await asyncio.sleep(POLL_INTERVAL_S)


# ---------- main ----------

async def amain() -> None:
    if not (SELF_HANDLES or wl_all()):
        raise SystemExit(
            "SELF_HANDLES or WHITELIST_HANDLES must contain at least one handle"
        )

    reader = ChatDBReader(STATE_PATH)
    reader.initialize_to_now()
    contacts = load_contacts()
    ctx = BridgeContextImpl(contacts=contacts, chatdb=reader)

    integrations = _build_integrations(CFG)
    ctx.integrations = integrations
    if not integrations:
        raise SystemExit(
            "No integrations enabled. Run `chatwire web` and walk the "
            "/setup wizard, or set integrations.<name>.enabled=true in "
            "~/.chatwire/config.json."
        )

    log.info("starting; integrations=%s relay=%s",
             [i.NAME for i in integrations], sorted(relay_handles()))

    started: list = []
    try:
        for integ in integrations:
            await integ.start(ctx)
            started.append(integ)
        await poll_loop(reader, integrations)
    finally:
        for integ in reversed(started):
            try:
                await integ.stop()
            except Exception:
                log.exception("integration %s stop failed",
                              getattr(integ, "NAME", "?"))


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
