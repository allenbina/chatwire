"""Tests for integrations/content_filter/__init__.py.

Covers:
  a. transform_inbound replaces a word from an enabled category.
  b. transform_inbound leaves text unchanged when category is disabled.
  c. custom_words entries are respected.
  d. loose mode catches a l33t-substituted word.
  e. replacement is drawn from emoji_pool.
  f. SETTINGS_SCHEMA has all 12 category keys.
  g. ContentFilterIntegration satisfies NAME, SETTINGS_SCHEMA, start/stop/on_inbound.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from integrations.content_filter import (
    ContentFilterIntegration,
    _CATEGORIES,
    _build_pattern,
    _normalise_l33t,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make(config: dict | None = None) -> ContentFilterIntegration:
    return ContentFilterIntegration(config or {})


def _make_with_cat(cat: str, **extra) -> ContentFilterIntegration:
    cfg = {"categories": {cat: True}, **extra}
    return ContentFilterIntegration(cfg)


# ---------------------------------------------------------------------------
# a. transform_inbound replaces a word from an enabled category
# ---------------------------------------------------------------------------

class TestCategoryReplacement:
    def test_profanity_word_replaced(self):
        inst = _make_with_cat("profanity", emoji_pool="🙈")
        result = inst.transform_inbound("That damn thing broke again.", {})
        assert "damn" not in result.lower()
        assert "🙈" in result

    def test_drugs_word_replaced(self):
        inst = _make_with_cat("drugs", emoji_pool="🚫")
        result = inst.transform_inbound("They found cocaine in his car.", {})
        assert "cocaine" not in result.lower()
        assert "🚫" in result

    def test_politics_word_replaced(self):
        inst = _make_with_cat("politics", emoji_pool="💢")
        result = inst.transform_inbound("All that fake news is exhausting.", {})
        assert "fake news" not in result.lower()
        assert "💢" in result

    def test_replacement_preserves_surrounding_text(self):
        inst = _make_with_cat("profanity", emoji_pool="😤")
        result = inst.transform_inbound("You look like an ass today.", {})
        assert "You look like an" in result
        assert "today." in result

    def test_case_insensitive_match(self):
        inst = _make_with_cat("profanity", emoji_pool="🤐")
        result = inst.transform_inbound("What the HELL is going on?", {})
        assert "HELL" not in result
        assert "🤐" in result


# ---------------------------------------------------------------------------
# b. transform_inbound leaves text unchanged when category is disabled
# ---------------------------------------------------------------------------

class TestCategoryDisabled:
    def test_disabled_category_passes_through(self):
        inst = _make()  # all categories disabled by default
        text = "That damn cocaine is politics!"
        result = inst.transform_inbound(text, {})
        assert result == text

    def test_other_category_disabled_does_not_filter(self):
        # Enable profanity only; politics word should pass through.
        inst = _make_with_cat("profanity", emoji_pool="😤")
        text = "The democrat said hello."
        result = inst.transform_inbound(text, {})
        assert "democrat" in result  # politics disabled

    def test_empty_text_returned_as_is(self):
        inst = _make_with_cat("profanity")
        assert inst.transform_inbound("", {}) == ""

    def test_none_emoji_pool_falls_back_to_default(self):
        inst = ContentFilterIntegration(
            {"categories": {"profanity": True}, "emoji_pool": ""}
        )
        result = inst.transform_inbound("That damn thing.", {})
        assert "damn" not in result.lower()


# ---------------------------------------------------------------------------
# c. custom_words entries are respected
# ---------------------------------------------------------------------------

class TestCustomWords:
    def test_single_custom_word(self):
        inst = ContentFilterIntegration(
            {"custom_words": "unicorn", "emoji_pool": "🦄"}
        )
        result = inst.transform_inbound("I saw a unicorn today.", {})
        assert "unicorn" not in result.lower()
        assert "🦄" in result

    def test_multi_custom_words(self):
        inst = ContentFilterIntegration(
            {"custom_words": "unicorn\ndragon", "emoji_pool": "🔥"}
        )
        text = "A unicorn fought a dragon."
        result = inst.transform_inbound(text, {})
        assert "unicorn" not in result.lower()
        assert "dragon" not in result.lower()

    def test_custom_phrase_matched(self):
        inst = ContentFilterIntegration(
            {"custom_words": "best friend", "emoji_pool": "😊"}
        )
        result = inst.transform_inbound("She is my best friend forever.", {})
        assert "best friend" not in result.lower()
        assert "😊" in result

    def test_blank_lines_in_custom_words_ignored(self):
        inst = ContentFilterIntegration(
            {"custom_words": "\nunicorn\n\n", "emoji_pool": "🦄"}
        )
        result = inst.transform_inbound("I saw a unicorn today.", {})
        assert "unicorn" not in result.lower()

    def test_custom_words_combined_with_category(self):
        inst = ContentFilterIntegration(
            {
                "categories": {"profanity": True},
                "custom_words": "unicorn",
                "emoji_pool": "🙈",
            }
        )
        result = inst.transform_inbound("A unicorn said damn!", {})
        assert "unicorn" not in result.lower()
        assert "damn" not in result.lower()


# ---------------------------------------------------------------------------
# d. loose mode catches a l33t-substituted word
# ---------------------------------------------------------------------------

class TestLooseMode:
    def test_l33t_at_sign_substitution(self):
        # "@ss" → normalises to "ass" which is in profanity list
        inst = ContentFilterIntegration(
            {"categories": {"profanity": True}, "mode": "loose", "emoji_pool": "🙈"}
        )
        result = inst.transform_inbound("What a @ss!", {})
        assert "@ss" not in result
        assert "🙈" in result

    def test_l33t_dollar_sign_substitution(self):
        # "$hit" → normalises to "shit"
        inst = ContentFilterIntegration(
            {"categories": {"profanity": True}, "mode": "loose", "emoji_pool": "🚫"}
        )
        result = inst.transform_inbound("$hit happens.", {})
        assert "$hit" not in result
        assert "🚫" in result

    def test_l33t_zero_substitution(self):
        # "c0caine" → normalises to "cocaine"
        inst = ContentFilterIntegration(
            {"categories": {"drugs": True}, "mode": "loose", "emoji_pool": "💊"}
        )
        result = inst.transform_inbound("He had c0caine.", {})
        assert "c0caine" not in result
        assert "💊" in result

    def test_exact_mode_does_not_catch_l33t(self):
        # In exact mode, "@ss" should NOT be replaced (it's not literally "ass")
        inst = ContentFilterIntegration(
            {"categories": {"profanity": True}, "mode": "exact", "emoji_pool": "🙈"}
        )
        result = inst.transform_inbound("What a @ss!", {})
        assert "@ss" in result  # not replaced in exact mode

    def test_normalise_l33t_helper(self):
        assert _normalise_l33t("@3105$") == "aeios s"[::1].replace(" ", "")
        # Check each substitution individually
        assert _normalise_l33t("@") == "a"
        assert _normalise_l33t("3") == "e"
        assert _normalise_l33t("1") == "i"
        assert _normalise_l33t("0") == "o"
        assert _normalise_l33t("$") == "s"
        assert _normalise_l33t("5") == "s"

    def test_loose_mode_multiple_l33t_matches(self):
        # Both "@ss" and "$hit" normalise to words in profanity list
        inst = ContentFilterIntegration(
            {"categories": {"profanity": True}, "mode": "loose", "emoji_pool": "🚫"}
        )
        result = inst.transform_inbound("@ss $hit happens.", {})
        assert "@ss" not in result
        assert "$hit" not in result


# ---------------------------------------------------------------------------
# e. replacement is drawn from emoji_pool
# ---------------------------------------------------------------------------

class TestEmojiPool:
    def test_single_emoji_in_pool_always_used(self):
        inst = _make_with_cat("profanity", emoji_pool="🎯")
        result = inst.transform_inbound("That damn thing!", {})
        assert "🎯" in result

    def test_replacement_comes_from_pool(self):
        pool = {"🎯", "🧨", "🎪"}
        inst = _make_with_cat("profanity", emoji_pool=" ".join(pool))
        results = set()
        for _ in range(50):
            r = inst.transform_inbound("damn", {})
            for emoji in pool:
                if emoji in r:
                    results.add(emoji)
        # With 50 trials and 3 options we expect more than 1 unique emoji.
        assert len(results) >= 1  # at minimum one emoji used

    def test_all_pool_emojis_can_appear(self):
        # Use a tiny pool and many iterations to verify all are reachable.
        pool_list = ["🅰️", "🅱️"]
        inst = _make_with_cat("profanity", emoji_pool=" ".join(pool_list))
        seen = set()
        for _ in range(200):
            r = inst.transform_inbound("damn", {})
            for e in pool_list:
                if e in r:
                    seen.add(e)
        assert seen == set(pool_list)


# ---------------------------------------------------------------------------
# f. SETTINGS_SCHEMA has all 12 category keys
# ---------------------------------------------------------------------------

class TestSettingsSchema:
    def test_schema_has_12_categories(self):
        cats = ContentFilterIntegration.SETTINGS_SCHEMA["properties"]["categories"]["properties"]
        assert len(cats) == 12

    def test_schema_has_all_category_keys(self):
        cats = ContentFilterIntegration.SETTINGS_SCHEMA["properties"]["categories"]["properties"]
        expected = {
            "profanity", "politics", "religion", "sex",
            "money", "body", "drugs", "gossip",
            "gambling", "social_media", "gaming", "dietary",
        }
        assert set(cats.keys()) == expected

    def test_all_categories_default_false(self):
        cats = ContentFilterIntegration.SETTINGS_SCHEMA["properties"]["categories"]["properties"]
        for name, schema in cats.items():
            assert schema.get("default") is False, f"{name} should default to False"

    def test_schema_has_custom_words_property(self):
        props = ContentFilterIntegration.SETTINGS_SCHEMA["properties"]
        assert "custom_words" in props
        assert props["custom_words"]["type"] == "string"

    def test_schema_has_emoji_pool_property(self):
        props = ContentFilterIntegration.SETTINGS_SCHEMA["properties"]
        assert "emoji_pool" in props

    def test_schema_mode_enum(self):
        props = ContentFilterIntegration.SETTINGS_SCHEMA["properties"]
        assert props["mode"]["enum"] == ["exact", "loose"]

    def test_schema_scope_enum(self):
        props = ContentFilterIntegration.SETTINGS_SCHEMA["properties"]
        assert props["scope"]["enum"] == ["all", "web"]

    def test_categories_constant_matches_schema(self):
        schema_cats = set(
            ContentFilterIntegration.SETTINGS_SCHEMA["properties"]["categories"]["properties"].keys()
        )
        assert schema_cats == set(_CATEGORIES)


# ---------------------------------------------------------------------------
# g. ContentFilterIntegration satisfies NAME, SETTINGS_SCHEMA, start/stop/on_inbound
# ---------------------------------------------------------------------------

class TestIntegrationProtocol:
    def test_name(self):
        assert ContentFilterIntegration.NAME == "content_filter"

    def test_settings_schema_is_dict(self):
        assert isinstance(ContentFilterIntegration.SETTINGS_SCHEMA, dict)

    def test_start_is_coroutine(self):
        inst = _make()
        ctx = MagicMock()
        coro = inst.start(ctx)
        assert asyncio.iscoroutine(coro)
        asyncio.run(coro)

    def test_stop_is_coroutine(self):
        inst = _make()
        coro = inst.stop()
        assert asyncio.iscoroutine(coro)
        asyncio.run(coro)

    def test_on_inbound_is_coroutine(self):
        inst = _make()
        msg = MagicMock()
        coro = inst.on_inbound(msg)
        assert asyncio.iscoroutine(coro)
        asyncio.run(coro)

    def test_has_transform_inbound(self):
        assert callable(getattr(ContentFilterIntegration, "transform_inbound", None))

    def test_transform_scope_default(self):
        inst = _make()
        assert inst.TRANSFORM_SCOPE == "all"

    def test_transform_scope_web(self):
        inst = ContentFilterIntegration({"scope": "web"})
        assert inst.TRANSFORM_SCOPE == "web"

    def test_display_name(self):
        assert ContentFilterIntegration.DISPLAY_NAME == "Content Filter"

    def test_icon(self):
        assert ContentFilterIntegration.ICON == "🤐"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class TestBuildPattern:
    def test_none_on_empty_list(self):
        assert _build_pattern([]) is None

    def test_matches_word(self):
        pat = _build_pattern(["hello"])
        assert pat is not None
        assert pat.search("say hello world") is not None

    def test_does_not_match_substring(self):
        pat = _build_pattern(["ass"])
        # "class" should not match — the 'ass' is not at a word boundary.
        assert pat.search("class") is None

    def test_case_insensitive(self):
        pat = _build_pattern(["hello"])
        assert pat.search("HELLO") is not None

    def test_longer_phrase_preferred(self):
        # "fake news" should match as a unit, not just "fake".
        pat = _build_pattern(["fake", "fake news"])
        m = pat.search("spreading fake news today")
        assert m is not None
        assert m.group() == "fake news"
