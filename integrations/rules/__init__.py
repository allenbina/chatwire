"""chatwire_rules — built-in automation / rules engine.

Evaluates a declarative list of rules against every inbound iMessage (and
optionally outbound sends) and executes the configured actions (reply,
webhook, log) on a match.

Rule format (under ``integrations.chatwire_rules.rules`` in config.json):

    {
      "name": "greeting",
      "trigger": {"type": "text_contains", "pattern": "hello"},
      "conditions": {
        "from_handles": ["+15551234567"],
        "in_group": false
      },
      "actions": [
        {"type": "reply", "text": "Hi {name}! You said: {text}"}
      ]
    }

Trigger types
-------------
  text_exact    — stripped, lowercased exact match (inbound)
  text_contains — case-insensitive substring match (inbound)
  text_regex    — case-insensitive regex search (compiled at startup; inbound)
  always        — fires for every inbound message (regardless of text)
  dsl           — boolean expression grammar covering trigger + conditions
  on_send       — fires for every outbound text message the user (or any
                  integration) sends via the bridge

Condition keys (all absent = no restriction)
--------------------------------------------
  Inbound rules (text_exact / text_contains / text_regex / always / dsl):
    from_handles     — sender must be in list (lowercased, case-insensitive)
    not_from_handles — sender must NOT be in list (lowercased)
    in_group         — true → group only; false → 1:1 only
    group_guid       — must match this specific group chat GUID

  Outbound rules (on_send):
    to_handles       — recipient must be in list (1:1 sends; lowercased)
    not_to_handles   — recipient must NOT be in list (lowercased)
    in_group         — true → group sends only; false → 1:1 sends only
    group_guid       — must match this specific group chat GUID

Action types
------------
  reply   — send a text reply; supports {handle}, {name}, {text} templates
             (for on_send rules, {handle} is the recipient handle)
  webhook — HTTP POST (or configurable method) to a URL with JSON context
  log     — emit a log line at info/warning/debug/error level

Rule-level options
------------------
  stop_on_match (bool, default false) — when true, no subsequent rules are
      evaluated once this rule fires.

Template variables for ``reply`` and ``log`` actions
------------------------------------------------------
  {handle} — raw sender/recipient handle (e.g. "+15551234567")
  {name}   — contact display name, falls back to handle when not in address book
  {text}   — full message text (stripped)
"""
from __future__ import annotations

import logging
import re
from typing import Any

try:
    from integrations.rules.dsl import DSLError, parse_dsl  # type: ignore[import]
except ImportError:  # pragma: no cover — isolated test environments
    parse_dsl = None  # type: ignore[assignment]
    DSLError = ValueError  # type: ignore[misc,assignment]

log = logging.getLogger(__name__)

try:
    import httpx as _httpx
    _HTTPX_AVAILABLE = True
except ImportError:  # pragma: no cover
    _httpx = None  # type: ignore[assignment]
    _HTTPX_AVAILABLE = False

try:
    from integrations.base import BridgeContext, InboundMessage, OutboundEvent, SendTarget  # type: ignore[import]
except ImportError:  # pragma: no cover — only missing in isolated unit tests
    BridgeContext = object  # type: ignore[misc,assignment]
    InboundMessage = object  # type: ignore[misc,assignment]
    OutboundEvent = object  # type: ignore[misc,assignment]
    SendTarget = None  # type: ignore[misc,assignment]


# ---------------------------------------------------------------------------
# Safe string formatter — missing keys render as empty string
# ---------------------------------------------------------------------------

class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return ""


def _render(template: str, **kwargs: str) -> str:
    """Format *template* with keyword args; unknown keys become empty strings."""
    try:
        return template.format_map(_SafeDict(kwargs))
    except (ValueError, KeyError):
        return template  # malformed template → return as-is


# ---------------------------------------------------------------------------
# Pure rule evaluation engine (no async, no I/O — easy to unit-test)
# ---------------------------------------------------------------------------

class RulesEngine:
    """Compile and evaluate a list of automation rules.

    This class is intentionally pure: it performs no I/O, has no async
    methods, and carries no references to the bridge context.  The
    :class:`RulesIntegration` wrapper handles async dispatch.
    """

    def __init__(self, rules_config: list[dict]) -> None:
        self._rules: list[dict] = []
        for raw in rules_config:
            try:
                self._rules.append(self._compile(raw))
            except Exception as exc:
                name = raw.get("name", "<unnamed>")
                log.warning(
                    "chatwire_rules: skipping rule %r — compile error: %s",
                    name, exc,
                )

    @staticmethod
    def _compile(raw: dict) -> dict:
        """Validate and pre-compile one rule dict.  Raises on bad config."""
        name = str(raw.get("name") or "<unnamed>")

        trigger_raw: dict = raw.get("trigger") or {}
        trigger_type: str = trigger_raw.get("type") or "text_exact"
        pattern: str = trigger_raw.get("pattern") or ""

        compiled_regex = None
        compiled_dsl = None
        if trigger_type == "text_regex":
            compiled_regex = re.compile(pattern, re.IGNORECASE)
        elif trigger_type == "dsl":
            if parse_dsl is None:
                raise ValueError("dsl trigger requires the integrations.rules.dsl module")
            expr: str = trigger_raw.get("expr") or ""
            if not expr:
                raise ValueError("dsl trigger requires a non-empty 'expr' field")
            compiled_dsl = parse_dsl(expr)
        elif trigger_type not in ("text_exact", "text_contains", "always", "on_send"):
            raise ValueError("unknown trigger type: {!r}".format(trigger_type))

        conds: dict = raw.get("conditions") or {}
        from_handles = frozenset(
            h.lower() for h in (conds.get("from_handles") or []) if h
        )
        not_from_handles = frozenset(
            h.lower() for h in (conds.get("not_from_handles") or []) if h
        )
        # on_send-specific recipient filters
        to_handles = frozenset(
            h.lower() for h in (conds.get("to_handles") or []) if h
        )
        not_to_handles = frozenset(
            h.lower() for h in (conds.get("not_to_handles") or []) if h
        )
        # in_group: None = unrestricted; True = groups only; False = 1:1 only
        in_group = conds.get("in_group")
        group_guid = conds.get("group_guid")

        actions: list[dict] = list(raw.get("actions") or [])
        stop_on_match: bool = bool(raw.get("stop_on_match", False))

        return {
            "name": name,
            "trigger_type": trigger_type,
            # store lowercased for text_exact / text_contains comparisons
            "pattern": pattern.lower() if trigger_type != "text_regex" else pattern,
            "compiled_regex": compiled_regex,
            "compiled_dsl": compiled_dsl,
            "from_handles": from_handles,
            "not_from_handles": not_from_handles,
            "to_handles": to_handles,
            "not_to_handles": not_to_handles,
            "in_group": in_group,
            "group_guid": group_guid,
            "actions": actions,
            "stop_on_match": stop_on_match,
        }

    def evaluate(
        self,
        msg_text: str | None,
        msg_handle: str | None,
        msg_is_group: bool,
        msg_chat_guid: str | None,
    ) -> list[tuple[str, list[dict]]]:
        """Return (rule_name, actions) for every rule that matches this message.

        Rules are evaluated in declaration order.  A rule with
        ``stop_on_match: true`` halts evaluation after it fires.

        Args:
            msg_text:      inbound message text (may be None/empty)
            msg_handle:    sender handle, lowercased by the bridge
            msg_is_group:  True when the message arrived in a group chat
            msg_chat_guid: group GUID, or None for 1:1 messages

        Returns:
            List of ``(rule_name, actions)`` tuples, one per matching rule.
        """
        text = (msg_text or "").strip()
        text_lc = text.lower()
        handle_lc = (msg_handle or "").lower()
        results: list[tuple[str, list[dict]]] = []

        for rule in self._rules:
            tt = rule["trigger_type"]

            # on_send rules fire for outbound only — skip here
            if tt == "on_send":
                continue

            # ---- DSL rules: evaluator covers both trigger and conditions ----
            if tt == "dsl":
                if rule["compiled_dsl"] is None:
                    continue  # compile failed at startup; skip
                if rule["compiled_dsl"](text, handle_lc, msg_is_group, msg_chat_guid):
                    results.append((rule["name"], rule["actions"]))
                    if rule["stop_on_match"]:
                        break
                continue  # skip normal trigger + conditions block

            # ---- Trigger (non-DSL) ----
            if tt == "always":
                triggered = True
            elif tt == "text_exact":
                triggered = text_lc == rule["pattern"]
            elif tt == "text_contains":
                triggered = rule["pattern"] in text_lc
            elif tt == "text_regex":
                triggered = bool(rule["compiled_regex"].search(text))
            else:
                triggered = False  # shouldn't reach here after _compile

            if not triggered:
                continue

            # ---- Conditions ----
            if rule["from_handles"] and handle_lc not in rule["from_handles"]:
                continue
            if rule["not_from_handles"] and handle_lc in rule["not_from_handles"]:
                continue
            if rule["in_group"] is True and not msg_is_group:
                continue
            if rule["in_group"] is False and msg_is_group:
                continue
            if rule["group_guid"] is not None and msg_chat_guid != rule["group_guid"]:
                continue

            results.append((rule["name"], rule["actions"]))

            if rule["stop_on_match"]:
                break

        return results


    def evaluate_outbound(
        self,
        msg_text: str | None,
        to_handle: str | None,
        msg_is_group: bool,
        msg_chat_guid: str | None,
    ) -> list[tuple[str, list[dict]]]:
        """Return (rule_name, actions) for every ``on_send`` rule that matches.

        Evaluates only rules whose ``trigger.type`` is ``"on_send"``; all
        other rules are skipped.  Evaluation order and ``stop_on_match``
        behave identically to :meth:`evaluate`.

        Args:
            msg_text:      outbound message text (may be None/empty)
            to_handle:     recipient handle for 1:1 sends; '' for group sends
            msg_is_group:  True when sending to a group chat
            msg_chat_guid: group GUID ('' or None for 1:1 sends)

        Returns:
            List of ``(rule_name, actions)`` tuples, one per matching rule.
        """
        text = (msg_text or "").strip()
        text_lc = text.lower()
        handle_lc = (to_handle or "").lower()
        results: list[tuple[str, list[dict]]] = []

        for rule in self._rules:
            if rule["trigger_type"] != "on_send":
                continue

            # ---- Conditions for on_send ----
            if rule["to_handles"] and handle_lc not in rule["to_handles"]:
                continue
            if rule["not_to_handles"] and handle_lc in rule["not_to_handles"]:
                continue
            if rule["in_group"] is True and not msg_is_group:
                continue
            if rule["in_group"] is False and msg_is_group:
                continue
            if rule["group_guid"] is not None and msg_chat_guid != rule["group_guid"]:
                continue

            results.append((rule["name"], rule["actions"]))

            if rule["stop_on_match"]:
                break

        return results


# ---------------------------------------------------------------------------
# Integration wrapper
# ---------------------------------------------------------------------------

class RulesIntegration:
    """Built-in automation rules engine for chatwire.

    Reads a declarative list of rules from ``config.json`` and fires
    configured actions (reply, webhook, log) when an inbound iMessage
    matches a rule's trigger and conditions.

    See module docstring for the full rule format reference.
    """

    NAME = "chatwire_rules"
    TIER = "core"
    DISPLAY_NAME = "Automation rules"
    DESCRIPTION = "Declarative trigger → action rules evaluated on every inbound iMessage."
    ICON = "⚡"

    SETTINGS_SCHEMA: dict[str, Any] = {
        "type": "object",
        "properties": {
            "enabled": {
                "type": "boolean",
                "default": False,
                "title": "Enable automation rules",
                "x-ui-order": 0,
            },
            "rules": {
                "type": "array",
                "title": "Rules",
                "description": (
                    "List of trigger → action rules evaluated against every "
                    "inbound iMessage. Rules fire in order; set "
                    "stop_on_match: true to halt after the first match."
                ),
                "x-ui-order": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "title": "Rule name",
                            "description": "Unique label used in logs.",
                        },
                        "trigger": {
                            "type": "object",
                            "title": "Trigger",
                            "description": (
                                "When to fire: text_exact / text_contains / text_regex / always / dsl."
                            ),
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": [
                                        "text_exact",
                                        "text_contains",
                                        "text_regex",
                                        "always",
                                        "dsl",
                                        "on_send",
                                    ],
                                },
                                "pattern": {
                                    "type": "string",
                                    "description": "Text to match (text_exact / text_contains / text_regex).",
                                },
                                "expr": {
                                    "type": "string",
                                    "description": (
                                        "DSL expression (dsl trigger type only). "
                                        "Example: 'from:+15551234567 contains:\"hello\" AND in:group'"
                                    ),
                                },
                            },
                            "required": ["type"],
                        },
                        "conditions": {
                            "type": "object",
                            "title": "Conditions",
                            "description": "All conditions must pass. Absent = unrestricted.",
                            "properties": {
                                "from_handles": {
                                    "type": "array",
                                    "title": "From handles",
                                    "description": "Sender must be one of these handles (inbound rules).",
                                    "items": {"type": "string"},
                                    "default": [],
                                },
                                "not_from_handles": {
                                    "type": "array",
                                    "title": "Not from handles",
                                    "description": "Sender must NOT be one of these handles (inbound rules).",
                                    "items": {"type": "string"},
                                    "default": [],
                                },
                                "to_handles": {
                                    "type": "array",
                                    "title": "To handles",
                                    "description": "Recipient must be one of these handles (on_send rules).",
                                    "items": {"type": "string"},
                                    "default": [],
                                },
                                "not_to_handles": {
                                    "type": "array",
                                    "title": "Not to handles",
                                    "description": "Recipient must NOT be one of these handles (on_send rules).",
                                    "items": {"type": "string"},
                                    "default": [],
                                },
                                "in_group": {
                                    "type": "boolean",
                                    "title": "In group",
                                    "description": "true = group messages only; false = 1:1 only.",
                                },
                                "group_guid": {
                                    "type": "string",
                                    "title": "Group GUID",
                                    "description": "Must match this exact group chat GUID.",
                                },
                            },
                        },
                        "actions": {
                            "type": "array",
                            "title": "Actions",
                            "description": "Executed in order when the rule fires.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "type": {
                                        "type": "string",
                                        "enum": ["reply", "webhook", "log"],
                                    },
                                    "text": {
                                        "type": "string",
                                        "description": "Reply text (reply action). Supports {handle}, {name}, {text}.",
                                    },
                                    "url": {
                                        "type": "string",
                                        "description": "Webhook URL (webhook action).",
                                    },
                                    "method": {
                                        "type": "string",
                                        "default": "POST",
                                        "description": "HTTP method (webhook action).",
                                    },
                                    "headers": {
                                        "type": "object",
                                        "description": "Extra HTTP headers (webhook action).",
                                    },
                                    "level": {
                                        "type": "string",
                                        "default": "info",
                                        "description": "Log level: debug/info/warning/error (log action).",
                                    },
                                    "message": {
                                        "type": "string",
                                        "description": "Log message template (log action). Supports {handle}, {name}, {text}, {rule}.",
                                    },
                                },
                                "required": ["type"],
                            },
                            "default": [],
                        },
                        "stop_on_match": {
                            "type": "boolean",
                            "default": False,
                            "title": "Stop on match",
                            "description": "If true, no subsequent rules are evaluated when this rule fires.",
                        },
                    },
                    "required": ["name", "trigger", "actions"],
                },
                "default": [],
            },
        },
    }

    def __init__(self, config: dict[str, Any]) -> None:
        rules_raw: list[dict] = config.get("rules") or []
        self._engine = RulesEngine(rules_raw)
        self._ctx: Any = None
        self._client: Any = None  # httpx.AsyncClient — created lazily on first webhook

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self, ctx: Any) -> None:
        self._ctx = ctx
        log.info(
            "chatwire_rules: started; %d rule(s) loaded",
            len(self._engine._rules),
        )

    async def stop(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None
        self._ctx = None
        log.info("chatwire_rules: stopped")

    # ------------------------------------------------------------------
    # Bridge hook
    # ------------------------------------------------------------------

    async def on_inbound(self, msg: Any) -> None:
        if self._ctx is None:
            return

        matches = self._engine.evaluate(
            msg_text=msg.text,
            msg_handle=msg.handle,
            msg_is_group=getattr(msg, "is_group", False),
            msg_chat_guid=getattr(msg, "chat_guid", None),
        )

        for rule_name, actions in matches:
            for action in actions:
                try:
                    await self._dispatch(action, msg, rule_name)
                except Exception as exc:
                    log.warning(
                        "chatwire_rules: rule %r action %r raised: %s",
                        rule_name, action.get("type"), exc,
                    )

    async def on_outbound(self, event: Any) -> None:
        """Called by the bridge after each successful outbound send.

        Evaluates all ``on_send`` rules against the outbound message and
        dispatches matching actions.  ``reply`` actions in outbound rules send
        a follow-up iMessage back to the same recipient — use with care.
        """
        if self._ctx is None:
            return

        matches = self._engine.evaluate_outbound(
            msg_text=event.text,
            to_handle=event.handle,
            msg_is_group=getattr(event, "is_group", False),
            msg_chat_guid=getattr(event, "chat_guid", None),
        )

        for rule_name, actions in matches:
            for action in actions:
                try:
                    await self._dispatch(action, event, rule_name)
                except Exception as exc:
                    log.warning(
                        "chatwire_rules: on_send rule %r action %r raised: %s",
                        rule_name, action.get("type"), exc,
                    )

    # ------------------------------------------------------------------
    # Action dispatch
    # ------------------------------------------------------------------

    async def _dispatch(self, action: dict, msg: Any, rule_name: str) -> None:
        action_type = action.get("type") or ""

        if action_type == "reply":
            await self._do_reply(action, msg)
        elif action_type == "webhook":
            await self._do_webhook(action, msg, rule_name)
        elif action_type == "log":
            self._do_log(action, msg, rule_name)
        else:
            log.warning(
                "chatwire_rules: unknown action type %r in rule %r",
                action_type, rule_name,
            )

    async def _do_reply(self, action: dict, msg: Any) -> None:
        if SendTarget is None or self._ctx is None:
            return

        name = (self._ctx.name_for(msg.handle) if hasattr(self._ctx, "name_for") else None) or msg.handle or ""
        text = _render(
            action.get("text") or "",
            handle=msg.handle or "",
            name=name,
            text=(msg.text or "").strip(),
        )
        if not text:
            return

        if getattr(msg, "is_group", False) and getattr(msg, "chat_guid", None):
            target = SendTarget(
                kind="chat",
                value=msg.chat_guid,
                label=(
                    getattr(msg, "chat_name", None)
                    or getattr(msg, "chat_identifier", "")
                    or msg.chat_guid
                ),
            )
        else:
            target = SendTarget(
                kind="handle",
                value=msg.handle,
                label=name,
            )

        await self._ctx.send_text(target, text)

    async def _do_webhook(self, action: dict, msg: Any, rule_name: str) -> None:
        if not _HTTPX_AVAILABLE:
            log.warning(
                "chatwire_rules: webhook action in rule %r requires httpx",
                rule_name,
            )
            return

        url = (action.get("url") or "").strip()
        if not url:
            log.warning(
                "chatwire_rules: webhook action in rule %r has no url",
                rule_name,
            )
            return

        method = (action.get("method") or "POST").upper()
        headers = dict(action.get("headers") or {})
        payload = {
            "rule": rule_name,
            "handle": msg.handle or "",
            "text": msg.text or "",
            "is_group": getattr(msg, "is_group", False),
            "chat_guid": getattr(msg, "chat_guid", None) or "",
        }

        if self._client is None:
            self._client = _httpx.AsyncClient(timeout=10.0)

        try:
            r = await self._client.request(method, url, json=payload, headers=headers)
            if r.status_code >= 400:
                log.warning(
                    "chatwire_rules: webhook %s → HTTP %d: %s",
                    url, r.status_code, r.text[:200],
                )
        except Exception as exc:
            log.warning(
                "chatwire_rules: webhook %s failed: %s: %s",
                url, type(exc).__name__, exc,
            )

    def _do_log(self, action: dict, msg: Any, rule_name: str) -> None:
        level_str = (action.get("level") or "info").lower()
        level = level_str if level_str in ("debug", "info", "warning", "error") else "info"
        message = _render(
            action.get("message") or "rule fired",
            handle=msg.handle or "",
            name=(getattr(self._ctx, "name_for", lambda h: None)(msg.handle) or msg.handle or ""),
            text=(msg.text or "").strip(),
            rule=rule_name,
        )
        getattr(log, level)("chatwire_rules [%s]: %s", rule_name, message)
