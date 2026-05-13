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
import atexit
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

from web import log_stream as _ls

from chat_db import ChatDBReader, InboundMessage
from contacts import load_lookup as load_contacts
from echo_log import register as echo_register, seen_recently as echo_seen
from chat_send import (
    BroadcastBlockedError, RateLimitError,
    SendResult, check_send_guard,
    send_file_confirm, send_file_to_chat_confirm,
    send_text_confirm, send_text_to_chat_confirm,
    register_trigger_notify_hook,
)
from whitelist import all_groups as wl_all_groups, all_handles as wl_all
from integrations.base import BridgeContext, SendOutcome, SendTarget
from integrations.sandbox import ConversationMap, OfficialMessage, SanitizedEvent, SandboxedContext
from verify import PluginNotTrusted, verify_plugin
from web.plugin_audit import log_event as _audit_log

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
_PID_LOCK_PATH = STATE_DIR / "bridge.pid"


# ---------- single-instance lock ----------

def acquire_pid_lock(lock_path: Path = _PID_LOCK_PATH) -> None:
    """Ensure only one bridge process runs at a time.

    Writes the current PID to *lock_path*. If a lock file already exists and
    the recorded PID is alive, exit with a human-readable error. Stale lock
    files (process dead or PID recycled) are silently replaced.

    Registers ``release_pid_lock`` via ``atexit`` so the file is removed on
    clean exit and on most unhandled-exception exits.
    """
    pid = os.getpid()

    if lock_path.exists():
        try:
            old_pid = int(lock_path.read_text().strip())
        except (ValueError, OSError):
            old_pid = None

        if old_pid is not None and old_pid != pid:
            try:
                os.kill(old_pid, 0)  # signal 0 = existence check, no signal sent
                alive = True
            except ProcessLookupError:
                alive = False
            except PermissionError:
                # Process exists but belongs to another user — treat as alive.
                alive = True

            if alive:
                raise SystemExit(
                    f"chatwire bridge is already running (PID {old_pid}).\n"
                    f"Stop the existing instance before starting a new one, or\n"
                    f"remove {lock_path} if the process is genuinely gone."
                )

    lock_path.write_text(str(pid))
    atexit.register(release_pid_lock, lock_path)


def release_pid_lock(lock_path: Path = _PID_LOCK_PATH) -> None:
    """Remove the PID lock file if it still contains our own PID."""
    try:
        if lock_path.exists() and lock_path.read_text().strip() == str(os.getpid()):
            lock_path.unlink(missing_ok=True)
    except OSError:
        pass


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
        # Anti-spam guard — raises RateLimitError / BroadcastBlockedError if blocked.
        await asyncio.to_thread(check_send_guard, target.value, body, "integration")
        if target.is_group:
            r = await asyncio.to_thread(send_text_to_chat_confirm, target.value, body)
        else:
            r = await asyncio.to_thread(send_text_confirm, target.value, body)
            # Group outgoing rows have handle='' and are filtered by
            # _should_relay anyway; only 1:1 sends need echo registration.
            _record_text_send(target.value, body)
        outcome = _to_outcome(r)
        # Fire on_outbound hooks (fire-and-forget; errors are logged, not raised).
        await _fan_out_outbound(self.integrations, target, body)
        return outcome

    async def send_file(self, target: SendTarget, path: Path) -> SendOutcome:
        # File transfers have no text body to transform; run the pipeline with
        # an empty string so transforms that inspect target still fire. We
        # discard the return value — send_file carries no text.
        _run_transform_outbound(self.integrations, "", target)
        # Anti-spam guard — file sends pass empty body; still subject to fuse.
        await asyncio.to_thread(check_send_guard, target.value, "", "integration-file")
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

def _notification_depth_for(plugin_name: str, cfg: dict) -> str:
    """Return the notification depth level for a given plugin name.

    Reads from config: notifications.notification_depth.<plugin_name> with
    fallback to notifications.notification_depth.default, then "sender".

    Three levels:
      "minimal"  — no sender name, no text ("New message")
      "sender"   — sender display name only (default for third-party)
      "preview"  — sender name + first ~50 chars of message text (opt-in)
    """
    notif = cfg.get("notifications") or {}
    depth_map = notif.get("notification_depth") or {}
    return depth_map.get(plugin_name) or depth_map.get("default") or "sender"


def _build_sanitized_event(
    msg: InboundMessage,
    display_name: str | None,
    depth: str = "sender",
) -> SanitizedEvent:
    """Build a SanitizedEvent from a raw InboundMessage.

    The ``depth`` parameter controls how much information is populated:
      "minimal"  — sender_display_name=None, preview=None
      "sender"   — sender_display_name=display_name, preview=None (default)
      "preview"  — sender_display_name=display_name, preview=first 50 chars
    """
    import datetime
    sender = None if depth == "minimal" else display_name
    preview: str | None = None
    if depth == "preview" and msg.text:
        preview = msg.text[:50]
    return SanitizedEvent(
        event="message",
        sender_display_name=sender,
        is_group=msg.is_group,
        group_name=msg.chat_name if msg.is_group else None,
        has_attachment=bool(msg.attachments),
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        preview=preview,
    )


def _build_official_message(
    msg: InboundMessage,
    display_name: str,
    conv_map: ConversationMap,
) -> OfficialMessage:
    """Build an OfficialMessage from a raw InboundMessage.
    Attachment file paths are read as bytes; raw handles are never exposed."""
    import datetime
    real_id = msg.chat_guid if msg.is_group else msg.handle
    conversation_id = conv_map.get_or_create(real_id)

    attachments = []
    for att in msg.attachments:
        try:
            mime = getattr(att, "mime_type", None) or "application/octet-stream"
            filename = getattr(att, "filename", None) or ""
            data = att.path.read_bytes() if att.path and att.path.exists() else b""
            attachments.append({"data": data, "mime": mime, "filename": filename})
        except Exception:
            log.exception("failed to read attachment bytes for official plugin")

    return OfficialMessage(
        conversation_id=conversation_id,
        sender_display_name=display_name,
        text=msg.text,
        is_group=msg.is_group,
        group_name=msg.chat_name if msg.is_group else None,
        attachments=attachments,
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        is_from_me=msg.is_from_me,
    )


async def _fan_out(
    integrations: list,
    msg: InboundMessage,
    conv_map: ConversationMap,
    contacts: dict[str, str],
    cfg: dict | None = None,
) -> None:
    """Dispatch one inbound message to all integrations, gated by tier.

    Tier routing:
      "ui"       — skip entirely (no bridge hooks for UI plugins)
      "notify"   — call on_notify(SanitizedEvent) if defined; skipped when
                   message is already seen (read_state) by any interface
      "official" — call on_official_message(OfficialMessage) if defined,
                   else fall back to on_inbound(msg) for backward compat
      "core"     — call on_inbound(msg) directly (full access, no sandbox)

    For "notify" tier, the per-plugin notification depth is read from config
    (notifications.notification_depth.<plugin_name>) and used to gate what
    fields are populated in the SanitizedEvent.
    """
    if cfg is None:
        cfg = {}

    # Resolve display name once; used by both notify and official paths.
    handle_lc = msg.handle.lower()
    display_name = contacts.get(handle_lc) or msg.handle

    # For the notify tier we need the conversation_id to check read state.
    # Use the same ID scheme as read_state: group chat GUID or handle.
    conv_id_for_read_state = msg.chat_guid if msg.is_group else msg.handle

    for integ in integrations:
        tier = getattr(integ, "TIER", "official")
        name = getattr(integ, "NAME", "?")
        _ran = False
        _success = False
        _error_msg: str | None = None
        try:
            if tier == "ui":
                # UI plugins get no bridge hooks at all.
                continue
            elif tier == "notify":
                fn = getattr(integ, "on_notify", None)
                if fn is not None:
                    # Skip-if-seen: suppress the notification when the
                    # conversation has already been acknowledged by any
                    # interface (web UI, XMPP, …) up to or past this rowid.
                    try:
                        from read_state import get_last_seen as _get_last_seen
                        last_seen = _get_last_seen(conv_id_for_read_state)
                        if last_seen >= msg.rowid:
                            continue
                    except Exception:
                        log.exception(
                            "read_state check failed for notify plugin %s; proceeding", name
                        )
                    depth = _notification_depth_for(name, cfg)
                    event = _build_sanitized_event(msg, display_name, depth)
                    _ran = True
                    await fn(event)
                    _success = True
            elif tier == "official":
                fn = getattr(integ, "on_official_message", None)
                _ran = True
                if fn is not None:
                    official_msg = _build_official_message(msg, display_name, conv_map)
                    await fn(official_msg)
                else:
                    # Backward-compat: official plugins that still use on_inbound().
                    await integ.on_inbound(msg)
                _success = True
            else:
                # "core" or anything unrecognised: full access, on_inbound().
                _ran = True
                await integ.on_inbound(msg)
                _success = True
        except PermissionError as exc:
            log.warning("integration %s tier violation (tier=%s): %s", name, tier, exc)
            _audit_log("tier_violation", plugin=name, tier=tier, detail=str(exc))
            _ls.warn("bridge", f"plugin {name}: tier violation — {exc}")
            _error_msg = str(exc)
        except Exception as exc:
            log.exception("integration %s fan-out failed (tier=%s)", name, tier)
            _ls.error("bridge", f"plugin {name}: fan-out error — {exc}")
            _error_msg = str(exc)
        finally:
            if _ran:
                try:
                    from plugin_state import record_plugin_run  # noqa: PLC0415
                    record_plugin_run(name, _success, _error_msg)
                except Exception:
                    log.exception("health tracking failed for %s", name)


async def _fan_out_outbound(integrations: list, target: "SendTarget", body: str) -> None:
    """Call ``on_outbound(event)`` on every integration that defines the hook.

    Errors are caught and logged per-integration; a failing hook never
    interrupts the caller's send flow.
    """
    from integrations.base import OutboundEvent  # local import avoids circularity
    event = OutboundEvent(
        handle=target.value if not target.is_group else "",
        text=body,
        is_group=target.is_group,
        chat_guid=target.value if target.is_group else "",
    )
    for integ in integrations:
        fn = getattr(integ, "on_outbound", None)
        if fn is None:
            continue
        name = getattr(integ, "NAME", "?")
        try:
            await fn(event)
        except Exception as exc:
            log.warning("integration %s on_outbound failed: %s", name, exc)


async def poll_loop(reader: ChatDBReader, integrations: list, conv_map: ConversationMap) -> None:
    log.info("poll loop starting (interval=%.1fs, integrations=%s, relay_handles=%s)",
             POLL_INTERVAL_S,
             [getattr(i, "NAME", "?") for i in integrations],
             sorted(relay_handles()))

    # Build a live contacts reference from the first core-tier integration's
    # context or fall back to an empty dict. In practice BridgeContextImpl
    # exposes .contacts directly — we reach it via the poll_loop caller (amain).
    # Pass contacts separately to _fan_out via a closure over the BridgeContextImpl
    # reference stored here. We resolve it once per batch (contacts is mutable).
    # Actually, we stored contacts in ctx.contacts; pass ctx into poll_loop.
    # Refactored: poll_loop receives the real ctx for name resolution only.
    # (poll_loop itself never exposes ctx to plugins — _fan_out does the gating.)

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
                # Structured log: inbound message (sender name only, no content).
                _sender_name = _contacts_ref.get(msg.handle.lower()) or msg.handle
                if msg.is_group:
                    _ls.info("bridge", f"inbound message — group: {msg.chat_name or msg.chat_guid}")
                else:
                    _ls.info("bridge", f"inbound message — from: {_sender_name}")
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
                await _fan_out(integrations, msg, conv_map, _contacts_ref, CFG)
        except Exception:
            log.exception("poll iteration failed; sleeping and retrying")
        await asyncio.sleep(POLL_INTERVAL_S)


# Module-level mutable reference so poll_loop can reach contacts without
# holding a direct ctx reference. Set by amain() after building ctx.
_contacts_ref: dict[str, str] = {}


def _register_anti_spam_notifier(
    loop: asyncio.AbstractEventLoop, integrations: list
) -> None:
    """Register a trigger hook that fans out anti_spam_triggered to notify plugins.

    The hook is called from a worker thread (inside asyncio.to_thread), so it
    schedules the async notification coroutine on the bridge's event loop via
    ``call_soon_threadsafe``.
    """
    import datetime as _dt  # noqa: PLC0415

    async def _notify_coro() -> None:
        from integrations.sandbox import SanitizedEvent  # noqa: PLC0415
        event = SanitizedEvent(
            event="anti_spam_triggered",
            sender_display_name=None,
            is_group=False,
            group_name=None,
            has_attachment=False,
            timestamp=_dt.datetime.now(_dt.timezone.utc).isoformat(),
        )
        for integ in integrations:
            if getattr(integ, "TIER", "") == "notify":
                fn = getattr(integ, "on_notify", None)
                if fn is not None:
                    try:
                        await fn(event)
                    except Exception:
                        log.exception(
                            "notify plugin %s failed on anti_spam_triggered",
                            getattr(integ, "NAME", "?"),
                        )

    def _sync_hook() -> None:
        try:
            loop.call_soon_threadsafe(
                lambda: asyncio.ensure_future(_notify_coro(), loop=loop)
            )
        except Exception:
            log.exception("failed to schedule anti_spam_triggered notification")

    register_trigger_notify_hook(_sync_hook)


# ---------- main ----------

async def amain() -> None:
    acquire_pid_lock()

    if not (SELF_HANDLES or wl_all()):
        raise SystemExit(
            "SELF_HANDLES or WHITELIST_HANDLES must contain at least one handle"
        )

    reader = ChatDBReader(STATE_PATH)
    reader.initialize_to_now()
    contacts = load_contacts()
    ctx = BridgeContextImpl(contacts=contacts, chatdb=reader)

    # One ConversationMap per bridge process lifetime. Maps opaque UUIDs ↔
    # real handles so official plugins can send replies without seeing raw
    # phone numbers or email addresses.
    conv_map = ConversationMap()

    integrations = _build_integrations(CFG)
    ctx.integrations = integrations
    _register_anti_spam_notifier(asyncio.get_event_loop(), integrations)
    if not integrations:
        raise SystemExit(
            "No integrations enabled. Run `chatwire web` and walk the "
            "/setup wizard, or set integrations.<name>.enabled=true in "
            "~/.chatwire/config.json."
        )

    log.info("starting; integrations=%s relay=%s",
             [i.NAME for i in integrations], sorted(relay_handles()))
    _ls.info("bridge", f"bridge started — integrations: {[i.NAME for i in integrations]}")

    # Wire the contacts dict into the module-level reference so poll_loop's
    # _fan_out() can resolve display names without holding a ctx reference.
    global _contacts_ref
    _contacts_ref = ctx.contacts

    started: list = []
    try:
        for integ in integrations:
            tier = getattr(integ, "TIER", "official")
            name = getattr(integ, "NAME", "")
            # core tier: pass real context unchanged.
            # All other tiers: wrap in SandboxedContext so the plugin can
            # access its own isolated config via ctx.plugin_config.
            if tier == "core":
                start_ctx = ctx
            else:
                logs_visible = bool(getattr(integ, "LOGS_VISIBLE", True))
                start_ctx = SandboxedContext(ctx, tier, conv_map, plugin_name=name, logs_visible=logs_visible)
            await integ.start(start_ctx)
            started.append(integ)
        await poll_loop(reader, integrations, conv_map)
    finally:
        _ls.info("bridge", "bridge shutting down")
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
