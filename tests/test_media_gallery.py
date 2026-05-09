"""Tests for chunk 5: Media gallery grid + lightbox (wave 4).

Covers:
  a. Grouping: consecutive all-image messages from same sender within 3s
     are merged into a single gallery entry.
  b. Grouping: gap > 3s keeps messages separate.
  c. Grouping: message with text body is NOT bundled.
  d. Grouping: message with no attachments is NOT bundled.
  e. Grouping: message with non-image attachment (video) is NOT bundled.
  f. Grouping: non-ready (pending) image is NOT bundled.
  g. Grouping: different sender (from_me differs) breaks the bundle.
  h. Grouping: group-chat, different sender_handle breaks the bundle.
  i. Grouping: 3+ consecutive all-image messages merge into one entry.
  j. Grid class: 1 image → gallery-1, 2 → gallery-2, 3 → gallery-3,
     4 → gallery-4, 5+ → gallery-5p.
  k. Lightbox: #media-dialog and #media-thumb-strip are present in the
     _conversation.html template.
  l. Lightbox: Escape key handler present in the template JS.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import helpers — isolate _bundle_galleries from the full main.py import
# chain (which needs a real Messages.app DB).
# ---------------------------------------------------------------------------

def _import_bundle_galleries():
    """Import *only* _bundle_galleries from web/main.py without side-effects.

    We reload the module's source as text and exec only the one function so
    we don't trigger top-level DB / config reads that require a real Mac env.
    """
    src_path = Path(__file__).resolve().parent.parent / "web" / "main.py"
    src = src_path.read_text()

    # Extract from the _GALLERY_BUNDLE_WINDOW_NS constant down to (but not
    # including) history_for(); that block contains our target function.
    start_marker = "_GALLERY_BUNDLE_WINDOW_NS"
    end_marker = "def history_for("
    start = src.index(start_marker)
    end = src.index(end_marker)
    snippet = src[start:end]

    ns: dict = {}
    exec(snippet, ns)  # noqa: S102
    return ns["_bundle_galleries"], ns["_GALLERY_BUNDLE_WINDOW_NS"]


_bundle_galleries, _WINDOW = _import_bundle_galleries()

# Apple nanosecond epoch helpers
_1S = 1_000_000_000   # 1 second in ns
_BASE = 700_000_000_000_000_000  # arbitrary large date value


def _img(name: str = "photo.jpg", ready: bool = True) -> dict:
    return {"path": f"/tmp/{name}", "name": name, "mime": "image/jpeg",
            "kind": "image", "ready": ready, "is_plugin": False, "total_bytes": 0}


def _msg(date: int, from_me: bool = False, atts: list | None = None,
         text: str = "", link_preview=None, sender_handle: str = "") -> dict:
    m: dict = {
        "rowid": date,
        "date": date,
        "from_me": from_me,
        "ts": "12:00 PM",
        "text": text,
        "attachments": atts or [],
        "link_preview": link_preview,
    }
    if sender_handle:
        m["sender_handle"] = sender_handle
        m["sender_name"] = sender_handle
    return m


# ---------------------------------------------------------------------------
# a. Messages within 3s, same sender, all-image → bundled
# ---------------------------------------------------------------------------

class TestBundleBasic:
    def test_two_images_within_window_bundled(self):
        msgs = [
            _msg(_BASE,          atts=[_img("a.jpg")]),
            _msg(_BASE + _1S,    atts=[_img("b.jpg")]),
        ]
        result = _bundle_galleries(msgs)
        assert len(result) == 1
        assert result[0]["gallery"] is True
        assert len(result[0]["attachments"]) == 2

    def test_merged_attachments_in_order(self):
        msgs = [
            _msg(_BASE,       atts=[_img("first.jpg")]),
            _msg(_BASE + _1S, atts=[_img("second.jpg")]),
        ]
        result = _bundle_galleries(msgs)
        names = [a["name"] for a in result[0]["attachments"]]
        assert names == ["first.jpg", "second.jpg"]

    def test_three_consecutive_merged(self):
        msgs = [
            _msg(_BASE,           atts=[_img("a.jpg")]),
            _msg(_BASE + _1S,     atts=[_img("b.jpg")]),
            _msg(_BASE + 2 * _1S, atts=[_img("c.jpg")]),
        ]
        result = _bundle_galleries(msgs)
        assert len(result) == 1
        assert len(result[0]["attachments"]) == 3

    def test_gallery_flag_set(self):
        msgs = [
            _msg(_BASE,       atts=[_img()]),
            _msg(_BASE + _1S, atts=[_img("b.jpg")]),
        ]
        result = _bundle_galleries(msgs)
        assert result[0].get("gallery") is True

    def test_metadata_from_first_message(self):
        m0 = _msg(_BASE,       atts=[_img("a.jpg")], from_me=True)
        m1 = _msg(_BASE + _1S, atts=[_img("b.jpg")], from_me=True)
        result = _bundle_galleries([m0, m1])
        assert result[0]["rowid"] == m0["rowid"]
        assert result[0]["from_me"] is True


# ---------------------------------------------------------------------------
# b. Gap > 3s keeps messages separate
# ---------------------------------------------------------------------------

class TestGapKeepsSeparate:
    def test_gap_just_over_window(self):
        msgs = [
            _msg(_BASE,                       atts=[_img("a.jpg")]),
            _msg(_BASE + _WINDOW + 1,         atts=[_img("b.jpg")]),
        ]
        result = _bundle_galleries(msgs)
        assert len(result) == 2

    def test_gap_exactly_at_window_merged(self):
        msgs = [
            _msg(_BASE,                       atts=[_img("a.jpg")]),
            _msg(_BASE + _WINDOW,             atts=[_img("b.jpg")]),
        ]
        result = _bundle_galleries(msgs)
        assert len(result) == 1

    def test_large_gap_separate(self):
        msgs = [
            _msg(_BASE,           atts=[_img("a.jpg")]),
            _msg(_BASE + 60 * _1S, atts=[_img("b.jpg")]),
        ]
        result = _bundle_galleries(msgs)
        assert len(result) == 2
        assert "gallery" not in result[0]
        assert "gallery" not in result[1]


# ---------------------------------------------------------------------------
# c. Message with text body is NOT bundled
# ---------------------------------------------------------------------------

class TestTextNotBundled:
    def test_text_message_not_candidate(self):
        msgs = [
            _msg(_BASE,       atts=[_img()], text="check this out"),
            _msg(_BASE + _1S, atts=[_img("b.jpg")]),
        ]
        result = _bundle_galleries(msgs)
        assert len(result) == 2

    def test_pure_image_after_text_not_merged_with_preceding_text(self):
        msgs = [
            _msg(_BASE,       text="hello", atts=[]),
            _msg(_BASE + _1S, atts=[_img("b.jpg")]),
        ]
        result = _bundle_galleries(msgs)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# d. Message with no attachments is NOT bundled
# ---------------------------------------------------------------------------

class TestNoAttachmentsNotBundled:
    def test_empty_attachments_not_candidate(self):
        msgs = [
            _msg(_BASE,       atts=[]),
            _msg(_BASE + _1S, atts=[_img()]),
        ]
        result = _bundle_galleries(msgs)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# e. Non-image attachment prevents bundling
# ---------------------------------------------------------------------------

class TestNonImageNotBundled:
    def _video(self) -> dict:
        return {"path": "/tmp/v.mp4", "name": "v.mp4", "mime": "video/mp4",
                "kind": "video", "ready": True, "is_plugin": False, "total_bytes": 0}

    def test_video_attachment_not_bundled(self):
        msgs = [
            _msg(_BASE,       atts=[self._video()]),
            _msg(_BASE + _1S, atts=[_img()]),
        ]
        result = _bundle_galleries(msgs)
        assert len(result) == 2

    def test_mixed_image_video_not_bundled(self):
        msgs = [
            _msg(_BASE,       atts=[_img(), self._video()]),
            _msg(_BASE + _1S, atts=[_img("b.jpg")]),
        ]
        result = _bundle_galleries(msgs)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# f. Non-ready (pending) image is NOT bundled
# ---------------------------------------------------------------------------

class TestPendingImageNotBundled:
    def test_not_ready_not_candidate(self):
        msgs = [
            _msg(_BASE,       atts=[_img(ready=False)]),
            _msg(_BASE + _1S, atts=[_img("b.jpg")]),
        ]
        result = _bundle_galleries(msgs)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# g. Different sender (from_me) breaks the bundle
# ---------------------------------------------------------------------------

class TestDifferentSenderBreaks:
    def test_from_me_flip_breaks_bundle(self):
        msgs = [
            _msg(_BASE,       from_me=False, atts=[_img()]),
            _msg(_BASE + _1S, from_me=True,  atts=[_img("b.jpg")]),
        ]
        result = _bundle_galleries(msgs)
        assert len(result) == 2

    def test_same_from_me_false_bundles(self):
        msgs = [
            _msg(_BASE,       from_me=False, atts=[_img()]),
            _msg(_BASE + _1S, from_me=False, atts=[_img("b.jpg")]),
        ]
        result = _bundle_galleries(msgs)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# h. Group-chat: different sender_handle breaks the bundle
# ---------------------------------------------------------------------------

class TestGroupChatSenderHandle:
    def test_different_handle_breaks(self):
        msgs = [
            _msg(_BASE,       atts=[_img()],      sender_handle="+1111"),
            _msg(_BASE + _1S, atts=[_img("b.jpg")], sender_handle="+2222"),
        ]
        result = _bundle_galleries(msgs)
        assert len(result) == 2

    def test_same_handle_bundles(self):
        msgs = [
            _msg(_BASE,       atts=[_img()],      sender_handle="+1111"),
            _msg(_BASE + _1S, atts=[_img("b.jpg")], sender_handle="+1111"),
        ]
        result = _bundle_galleries(msgs)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# i. Multiple non-bundleable messages interspersed
# ---------------------------------------------------------------------------

class TestInterspersed:
    def test_bundle_then_text_then_bundle(self):
        msgs = [
            _msg(_BASE,             atts=[_img("a.jpg")]),
            _msg(_BASE + _1S,       atts=[_img("b.jpg")]),
            _msg(_BASE + 2 * _1S,   text="between", atts=[]),
            _msg(_BASE + 3 * _1S,   atts=[_img("c.jpg")]),
            _msg(_BASE + 4 * _1S,   atts=[_img("d.jpg")]),
        ]
        result = _bundle_galleries(msgs)
        assert len(result) == 3
        assert result[0].get("gallery") is True
        assert result[1].get("gallery") is None
        assert result[2].get("gallery") is True

    def test_empty_input(self):
        assert _bundle_galleries([]) == []

    def test_single_image_not_marked_gallery(self):
        msgs = [_msg(_BASE, atts=[_img()])]
        result = _bundle_galleries(msgs)
        assert len(result) == 1
        assert "gallery" not in result[0]


# ---------------------------------------------------------------------------
# j. Grid class correctness based on image count
# ---------------------------------------------------------------------------

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "web" / "templates"


def _render_messages(msgs: list[dict], is_group: bool = False) -> str:
    """Render _messages.html with the given message list."""
    from fastapi.templating import Jinja2Templates

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    tmpl = templates.get_template("_messages.html")
    return tmpl.render(msgs=msgs, is_group=is_group)


def _make_img_msg(n_images: int, from_me: bool = False) -> dict:
    atts = [_img(f"img{i}.jpg") for i in range(n_images)]
    return _msg(_BASE, from_me=from_me, atts=atts)


class TestGridClass:
    def test_one_image_gallery_1(self):
        html = _render_messages([_make_img_msg(1)])
        assert "gallery-1" in html

    def test_two_images_gallery_2(self):
        html = _render_messages([_make_img_msg(2)])
        assert "gallery-2" in html

    def test_three_images_gallery_3(self):
        html = _render_messages([_make_img_msg(3)])
        assert "gallery-3" in html

    def test_four_images_gallery_4(self):
        html = _render_messages([_make_img_msg(4)])
        assert "gallery-4" in html

    def test_five_images_gallery_5p(self):
        html = _render_messages([_make_img_msg(5)])
        assert "gallery-5p" in html

    def test_ten_images_gallery_5p(self):
        html = _render_messages([_make_img_msg(10)])
        assert "gallery-5p" in html

    def test_five_images_overflow_label(self):
        html = _render_messages([_make_img_msg(5)])
        assert "+1" in html   # 5 total, show 4, overflow = +1

    def test_seven_images_overflow_label(self):
        html = _render_messages([_make_img_msg(7)])
        assert "+3" in html   # 7 total, show 4, overflow = +3

    def test_four_images_no_overflow(self):
        html = _render_messages([_make_img_msg(4)])
        assert "gallery-overflow" not in html

    def test_images_use_media_anchor(self):
        html = _render_messages([_make_img_msg(2)])
        assert 'class="media"' in html


# ---------------------------------------------------------------------------
# k. Lightbox: #media-dialog and #media-thumb-strip present in template
# ---------------------------------------------------------------------------

class TestLightboxMarkup:
    def setup_method(self):
        self._tmpl_path = (
            Path(__file__).resolve().parent.parent
            / "web" / "templates" / "_conversation.html"
        )
        self._src = self._tmpl_path.read_text()

    def test_media_dialog_present(self):
        assert 'id="media-dialog"' in self._src

    def test_media_thumb_strip_present(self):
        assert 'id="media-thumb-strip"' in self._src

    def test_media_prev_button_present(self):
        assert 'media-prev' in self._src

    def test_media_next_button_present(self):
        assert 'media-next' in self._src

    def test_media_close_button_present(self):
        assert 'media-close' in self._src

    def test_escape_key_handler_present(self):
        assert "Escape" in self._src

    def test_thumb_strip_click_handler_present(self):
        assert "openAt(i)" in self._src

    def test_build_thumb_strip_function_present(self):
        assert "buildThumbStrip" in self._src
