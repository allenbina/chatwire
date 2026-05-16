"""Tests for apply_sms_reactions in web/sms_reactions.py.

Covers:
  - Text reactions (quoted original text) — existing behaviour
  - Media reactions (attachment-based) — new in Phase 29
  - 😢 emoji reaction
  - Fallback: no match → message kept as plain text
  - Sender accumulation when multiple reactions target the same message
  - Tapback format: {type, senders: [{name, time}]} (updated Phase 33)
"""
from __future__ import annotations

import copy
import pytest

from web.sms_reactions import apply_sms_reactions as _apply_sms_reactions

# Sender entry produced for messages with no sender_name and from_me=False
_ANON = {"name": "Unknown", "time": ""}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _msg(text: str, from_me: bool = False, atts: list[dict] | None = None,
         sender_name: str | None = None) -> dict:
    m: dict = {"text": text, "from_me": from_me, "ts": 0}
    if atts is not None:
        m["attachments"] = atts
    if sender_name is not None:
        m["sender_name"] = sender_name
    return m


def _img_msg(from_me: bool = False) -> dict:
    return _msg("", from_me=from_me, atts=[{"kind": "image", "ready": True}])


def _video_msg(from_me: bool = False) -> dict:
    return _msg("", from_me=from_me, atts=[{"kind": "video", "ready": True}])


def _audio_msg(from_me: bool = False) -> dict:
    return _msg("", from_me=from_me, atts=[{"kind": "audio", "ready": True}])


def _tb_counts(tapbacks: list[dict]) -> dict:
    """Helper: {emoji: sender_count} for quick multi-reaction assertions."""
    return {t["type"]: len(t["senders"]) for t in tapbacks}


# ---------------------------------------------------------------------------
# Text reactions (verb + "quoted text")
# ---------------------------------------------------------------------------

class TestTextReactions:
    def test_liked_verb_matches_and_suppresses(self):
        msgs = [_msg("hello"), _msg('Liked "hello"')]
        out = _apply_sms_reactions(msgs)
        assert len(out) == 1
        assert out[0]["tapbacks"] == [{"type": "👍", "senders": [_ANON]}]

    def test_loved_verb(self):
        msgs = [_msg("hi there"), _msg('Loved "hi there"')]
        out = _apply_sms_reactions(msgs)
        assert out[0]["tapbacks"] == [{"type": "❤️", "senders": [_ANON]}]

    def test_laughed_at_verb(self):
        msgs = [_msg("joke"), _msg('Laughed at "joke"')]
        out = _apply_sms_reactions(msgs)
        assert out[0]["tapbacks"] == [{"type": "😂", "senders": [_ANON]}]

    def test_disliked_verb(self):
        msgs = [_msg("bad idea"), _msg('Disliked "bad idea"')]
        out = _apply_sms_reactions(msgs)
        assert out[0]["tapbacks"] == [{"type": "👎", "senders": [_ANON]}]

    def test_emphasized_verb(self):
        msgs = [_msg("wow"), _msg('Emphasized "wow"')]
        out = _apply_sms_reactions(msgs)
        assert out[0]["tapbacks"] == [{"type": "‼️", "senders": [_ANON]}]

    def test_questioned_verb(self):
        msgs = [_msg("really?"), _msg('Questioned "really?"')]
        out = _apply_sms_reactions(msgs)
        assert out[0]["tapbacks"] == [{"type": "❓", "senders": [_ANON]}]

    def test_emoji_verb_thumbsup(self):
        msgs = [_msg("nice"), _msg('👍 "nice"')]
        out = _apply_sms_reactions(msgs)
        assert out[0]["tapbacks"] == [{"type": "👍", "senders": [_ANON]}]

    def test_emoji_verb_sad(self):
        """😢 is new in Phase 29."""
        msgs = [_msg("so sad"), _msg('😢 "so sad"')]
        out = _apply_sms_reactions(msgs)
        assert out[0]["tapbacks"] == [{"type": "😢", "senders": [_ANON]}]

    def test_to_variant(self):
        """'Loved to "text"' form."""
        msgs = [_msg("hello"), _msg('Loved to "hello"')]
        out = _apply_sms_reactions(msgs)
        assert out[0]["tapbacks"] == [{"type": "❤️", "senders": [_ANON]}]

    def test_no_match_kept_as_plain(self):
        """If the quoted text doesn't appear in any prior message, keep as-is."""
        msgs = [_msg("unrelated"), _msg('Liked "missing text"')]
        out = _apply_sms_reactions(msgs)
        assert len(out) == 2
        assert "tapbacks" not in out[0]

    def test_count_accumulates(self):
        """Two reactions to the same target message accumulate senders."""
        msgs = [_msg("hi"), _msg('Liked "hi"'), _msg('Loved "hi"')]
        out = _apply_sms_reactions(msgs)
        assert len(out) == 1
        assert _tb_counts(out[0]["tapbacks"]) == {"👍": 1, "❤️": 1}

    def test_backward_window_50(self):
        """Target is exactly 50 messages back — should still match."""
        target = _msg("needle")
        fillers = [_msg(f"filler {k}") for k in range(49)]
        reaction = _msg('Liked "needle"')
        msgs = [target] + fillers + [reaction]
        assert len(msgs) == 51
        out = _apply_sms_reactions(msgs)
        assert len(out) == 50  # reaction suppressed, 49 fillers + 1 target
        assert out[0]["tapbacks"] == [{"type": "👍", "senders": [_ANON]}]

    def test_backward_window_too_far(self):
        """Target is 51 messages back — should NOT match (kept as plain text)."""
        target = _msg("needle")
        fillers = [_msg(f"filler {k}") for k in range(50)]
        reaction = _msg('Liked "needle"')
        msgs = [target] + fillers + [reaction]
        assert len(msgs) == 52
        out = _apply_sms_reactions(msgs)
        assert len(out) == 52  # reaction NOT suppressed
        assert "tapbacks" not in out[0]

    def test_sender_name_propagated(self):
        """If the reaction message has a sender_name, it appears in senders."""
        msgs = [_msg("hello"), _msg('Liked "hello"', sender_name="Alice")]
        out = _apply_sms_reactions(msgs)
        assert out[0]["tapbacks"] == [{"type": "👍", "senders": [{"name": "Alice", "time": ""}]}]

    def test_from_me_sender_is_you(self):
        """Reactions sent by the user (from_me=True) have name='You'."""
        msgs = [_msg("hello"), _msg('Liked "hello"', from_me=True)]
        out = _apply_sms_reactions(msgs)
        assert out[0]["tapbacks"] == [{"type": "👍", "senders": [{"name": "You", "time": ""}]}]


# ---------------------------------------------------------------------------
# Media reactions (verb + "an image / a video / ...")
# ---------------------------------------------------------------------------

class TestMediaReactions:
    def test_loved_an_image(self):
        msgs = [_img_msg(), _msg("Loved an image")]
        out = _apply_sms_reactions(msgs)
        assert len(out) == 1
        assert out[0]["tapbacks"] == [{"type": "❤️", "senders": [_ANON]}]

    def test_liked_a_video(self):
        msgs = [_video_msg(), _msg("Liked a video")]
        out = _apply_sms_reactions(msgs)
        assert len(out) == 1
        assert out[0]["tapbacks"] == [{"type": "👍", "senders": [_ANON]}]

    def test_laughed_at_an_image(self):
        msgs = [_img_msg(), _msg("Laughed at an image")]
        out = _apply_sms_reactions(msgs)
        assert out[0]["tapbacks"] == [{"type": "😂", "senders": [_ANON]}]

    def test_sad_to_a_photo(self):
        """😢 to a photo (emoji verb, 'to' variant, 'photo' synonym)."""
        msgs = [_img_msg(), _msg("😢 to a photo")]
        out = _apply_sms_reactions(msgs)
        assert out[0]["tapbacks"] == [{"type": "😢", "senders": [_ANON]}]

    def test_loved_a_picture(self):
        msgs = [_img_msg(), _msg("Loved a picture")]
        out = _apply_sms_reactions(msgs)
        assert out[0]["tapbacks"] == [{"type": "❤️", "senders": [_ANON]}]

    def test_liked_a_gif(self):
        msgs = [_img_msg(), _msg("Liked a GIF")]
        out = _apply_sms_reactions(msgs)
        assert len(out) == 1

    def test_liked_an_audio(self):
        msgs = [_audio_msg(), _msg("Liked an audio")]
        out = _apply_sms_reactions(msgs)
        assert out[0]["tapbacks"] == [{"type": "👍", "senders": [_ANON]}]

    def test_liked_an_attachment(self):
        """'attachment' matches any kind."""
        msgs = [_video_msg(), _msg("Liked an attachment")]
        out = _apply_sms_reactions(msgs)
        assert len(out) == 1

    def test_media_reaction_skips_text_only_messages(self):
        """Media reaction should skip over text-only messages to find attachment."""
        msgs = [
            _img_msg(),
            _msg("some text in between"),
            _msg("Loved an image"),
        ]
        out = _apply_sms_reactions(msgs)
        assert len(out) == 2  # reaction suppressed; text + image remain
        assert out[0]["tapbacks"] == [{"type": "❤️", "senders": [_ANON]}]
        assert out[1]["text"] == "some text in between"

    def test_media_reaction_kind_mismatch_kept(self):
        """Image reaction should NOT attach to a video-only message."""
        msgs = [_video_msg(), _msg("Loved an image")]
        # video message doesn't have kind=="image", so no match for image reaction
        # ... BUT wait: video's kind is "video", and we want "image". No match → kept.
        out = _apply_sms_reactions(msgs)
        # The reaction message should be kept (not suppressed) since no image found
        assert len(out) == 2
        assert "tapbacks" not in out[0]

    def test_media_no_attachments_kept(self):
        """No attachments at all → reaction kept as plain text."""
        msgs = [_msg("text only"), _msg("Loved an image")]
        out = _apply_sms_reactions(msgs)
        assert len(out) == 2

    def test_media_reaction_count_accumulates(self):
        """Two media reactions to the same image message accumulate senders."""
        msgs = [_img_msg(), _msg("Liked an image"), _msg("Loved an image")]
        out = _apply_sms_reactions(msgs)
        assert len(out) == 1
        assert _tb_counts(out[0]["tapbacks"]) == {"👍": 1, "❤️": 1}

    def test_text_and_media_reactions_coexist(self):
        """One text reaction and one media reaction in the same conversation."""
        text_msg = _msg("cool")
        img = _img_msg()
        text_rx = _msg('Liked "cool"')
        media_rx = _msg("Loved an image")
        out = _apply_sms_reactions([text_msg, img, text_rx, media_rx])
        assert len(out) == 2
        assert out[0]["tapbacks"] == [{"type": "👍", "senders": [_ANON]}]  # text_msg
        assert out[1]["tapbacks"] == [{"type": "❤️", "senders": [_ANON]}]  # img

    def test_case_insensitive_media_noun(self):
        """'an Image' / 'a VIDEO' should match too."""
        msgs = [_img_msg(), _msg("Loved an Image")]
        out = _apply_sms_reactions(msgs)
        assert len(out) == 1

        msgs2 = [_video_msg(), _msg("Liked a VIDEO")]
        out2 = _apply_sms_reactions(msgs2)
        assert len(out2) == 1
