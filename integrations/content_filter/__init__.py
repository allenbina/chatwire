"""Content filter integration.

Filters inbound message text by replacing matched words/phrases with a
randomly-chosen emoji from an configurable pool.  The filter runs as a
display-only transform — chat.db is never modified.

Categories ship as JSON word lists in ``integrations/content_filter/data/``.
All categories are disabled by default; the user enables them in Settings.

Supports two matching modes:
  exact — whole-word, case-insensitive (\b boundaries).
  loose — additionally normalises l33tspeak before matching.

``TRANSFORM_SCOPE`` is set from the ``scope`` config key (default "all"),
so the transform can be restricted to the web UI only.
"""
from __future__ import annotations

import json
import logging
import random
import re
from pathlib import Path
from typing import Any

from integrations.base import BridgeContext, InboundMessage
from web import log_stream as _ls

log = logging.getLogger("chatwire.content_filter")

_DATA_DIR = Path(__file__).parent / "data"

_CATEGORIES = [
    "profanity",
    "politics",
    "religion",
    "sex",
    "money",
    "body",
    "drugs",
    "gossip",
    "gambling",
    "social_media",
    "gaming",
    "dietary",
]

_DEFAULT_EMOJI_POOL = "😤 🤬 💢 🙈 🚫 ⚠️ 🤐"

# l33tspeak → canonical character substitutions used in loose mode.
_L33T_MAP: list[tuple[str, str]] = [
    ("@", "a"),
    ("3", "e"),
    ("1", "i"),
    ("0", "o"),
    ("$", "s"),
    ("5", "s"),
]


def _load_category(name: str) -> list[str]:
    """Load word list for *name* from the bundled JSON data file."""
    path = _DATA_DIR / f"{name}.json"
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return [str(w) for w in data if w]
        log.warning("content_filter: %s.json is not a list, skipping", name)
        return []
    except FileNotFoundError:
        log.warning("content_filter: data file not found: %s", path)
        return []
    except json.JSONDecodeError as exc:
        log.warning("content_filter: bad JSON in %s: %s", path, exc)
        return []


def _normalise_l33t(text: str) -> str:
    """Substitute common l33tspeak characters so the normalised form can be
    matched against plain-text word lists."""
    for src, dst in _L33T_MAP:
        text = text.replace(src, dst)
    return text


def _build_pattern(words: list[str]) -> re.Pattern | None:
    """Build a compiled regex that matches any word in *words* as a whole
    word (case-insensitive).  Returns None when *words* is empty."""
    if not words:
        return None
    # Sort longest-first so multi-word phrases match before their sub-words.
    sorted_words = sorted(words, key=len, reverse=True)
    # Escape each entry and wrap in word boundaries.
    # For phrases (containing spaces) \b on each end is still correct because
    # spaces are non-word chars, so the boundary fires before/after the phrase.
    alternation = "|".join(re.escape(w) for w in sorted_words)
    return re.compile(r"\b(?:" + alternation + r")\b", re.IGNORECASE)


class ContentFilterIntegration:
    """Built-in integration that replaces filtered words with emoji."""

    NAME = "content_filter"
    TIER = "core"  # Built-in anti-abuse; needs raw text; bypasses sandboxing.
    DISPLAY_NAME = "Content Filter"
    DESCRIPTION = (
        "Replace words/phrases in inbound messages with emoji. "
        "Categories and custom words are fully configurable."
    )
    ICON = "🤐"

    SETTINGS_SCHEMA: dict[str, Any] = {
        "type": "object",
        "properties": {
            "categories": {
                "type": "object",
                "title": "Filter categories",
                "description": "Enable one or more categories to filter.",
                "properties": {cat: {"type": "boolean", "default": False, "title": cat.replace("_", " ").title()} for cat in _CATEGORIES},
                "default": {cat: False for cat in _CATEGORIES},
            },
            "custom_words": {
                "type": "string",
                "title": "Custom words",
                "description": "Newline-separated words or phrases to filter.",
                "default": "",
                "x-ui-type": "textarea",
                "x-ui-placeholder": "one word or phrase per line",
            },
            "emoji_pool": {
                "type": "string",
                "title": "Emoji pool",
                "description": "Space-separated emoji that replacements are drawn from.",
                "default": _DEFAULT_EMOJI_POOL,
            },
            "mode": {
                "type": "string",
                "title": "Matching mode",
                "description": (
                    "exact — whole-word match only. "
                    "loose — also catches l33tspeak substitutions (@ → a, 3 → e, etc.)."
                ),
                "enum": ["exact", "loose"],
                "default": "exact",
            },
            "scope": {
                "type": "string",
                "title": "Apply to",
                "description": "Which surfaces the filter is applied to.",
                "enum": ["all", "web"],
                "default": "all",
            },
        },
    }

    # Set by __init__ so the bridge can read TRANSFORM_SCOPE as an instance attr.
    TRANSFORM_SCOPE: str = "all"

    def __init__(self, config: dict[str, Any]) -> None:
        cats_cfg: dict[str, bool] = config.get("categories") or {}
        self._enabled_cats: list[str] = [c for c in _CATEGORIES if cats_cfg.get(c, False)]

        raw_custom: str = config.get("custom_words") or ""
        self._custom_words: list[str] = [
            line.strip() for line in raw_custom.splitlines() if line.strip()
        ]

        raw_pool: str = config.get("emoji_pool") or _DEFAULT_EMOJI_POOL
        self._emoji_pool: list[str] = raw_pool.split()
        if not self._emoji_pool:
            self._emoji_pool = _DEFAULT_EMOJI_POOL.split()

        self._mode: str = config.get("mode", "exact")
        self._scope: str = config.get("scope", "all")
        # Expose as instance attribute so the bridge relay can read it.
        self.TRANSFORM_SCOPE = self._scope

        # Pre-load word lists (cached at start-time for performance).
        self._word_lists: dict[str, list[str]] = {
            cat: _load_category(cat) for cat in _CATEGORIES
        }

    # ------------------------------------------------------------------
    # Integration Protocol
    # ------------------------------------------------------------------

    async def start(self, ctx: BridgeContext) -> None:
        log.info(
            "content_filter started — mode=%s scope=%s enabled=%s custom=%d",
            self._mode,
            self._scope,
            self._enabled_cats or "none",
            len(self._custom_words),
        )

    async def stop(self) -> None:
        pass

    async def on_inbound(self, msg: InboundMessage) -> None:
        # Transform is applied by the bridge relay via transform_inbound();
        # on_inbound() is a no-op for this integration.
        pass

    # ------------------------------------------------------------------
    # Transform hook
    # ------------------------------------------------------------------

    def transform_inbound(self, text: str, context: dict) -> str:
        """Replace filtered words in *text* with a random emoji.

        Called by the bridge relay loop before dispatching to on_inbound().
        Returns the (possibly modified) text.  The original message in
        chat.db is never touched.
        """
        if not text:
            return text

        # Collect all active words from enabled categories + custom list.
        active_words: list[str] = list(self._custom_words)
        for cat in self._enabled_cats:
            active_words.extend(self._word_lists.get(cat, []))

        if not active_words:
            return text

        pattern = _build_pattern(active_words)
        if pattern is None:
            return text

        if self._mode == "loose":
            result = self._replace_loose(text, pattern)
        else:
            result = self._replace_exact(text, pattern)
        if result != text:
            _ls.info("content_filter", "filter match — message content replaced")
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _pick_emoji(self) -> str:
        return random.choice(self._emoji_pool)  # noqa: S311

    def _replace_exact(self, text: str, pattern: re.Pattern) -> str:
        return pattern.sub(lambda _: self._pick_emoji(), text)

    def _replace_loose(self, text: str, pattern: re.Pattern) -> str:
        """Loose mode: apply the word pattern to the l33t-normalised text and
        replace the corresponding spans in the *original* text.

        We collect all match spans first (from right to left) and splice them
        into the original string so that earlier replacements don't shift the
        indices of later ones.
        """
        normalised = _normalise_l33t(text)
        # Collect all non-overlapping matches, reversed so we splice right→left.
        matches = list(pattern.finditer(normalised))
        if not matches:
            return text
        result = text
        for m in reversed(matches):
            start, end = m.start(), m.end()
            result = result[:start] + self._pick_emoji() + result[end:]
        return result
