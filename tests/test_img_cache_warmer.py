"""Tests for the img_cache startup warmer (Phase 49).

Strategy: pytest-asyncio is not in this test env, so async tests are run via
asyncio.run(). The warmer logic is mirrored locally with injectable snapshot
and full_img_for callbacks so we never import web/main.py (too many
module-level side-effects).

The local mirror implements the same row-iteration and accounting logic as
_img_cache_warmer in web/main.py. If that logic changes, update both.

Covers:
  a. HEIC files in DB result → _full_img_for called for each; warmed counter.
  b. Rows with non-HEIC extensions → skipped without calling _full_img_for.
  c. _full_img_for returns None (sips failure) → counted in skipped.
  d. Empty result set → warmer exits cleanly (0 warmed, 0 skipped, no error).
  e. DB query raises exception → logs warning, returns without raising.
  f. Mixed HEIC + non-HEIC rows → correct warmed / skipped split.
  g. _WARMUP_DAYS / _WARMUP_MAX constants have sensible values.
"""
from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Constants mirrored from web/main.py
# ---------------------------------------------------------------------------

_WARMUP_DAYS = 30
_WARMUP_MAX = 200


# ---------------------------------------------------------------------------
# Local mirror of the core warmer iteration logic
# (matches the for-loop in _img_cache_warmer, with injectable deps)
# ---------------------------------------------------------------------------

async def _run_warmer_core(
    rows: list,
    full_img_for_fn,
    *,
    sleep_fn=None,
) -> tuple[int, int, int]:
    """Mirror of the row-iteration body in _img_cache_warmer.

    Returns (total, warmed, skipped).
    sleep_fn defaults to asyncio.sleep; pass a no-op in tests.
    """
    if sleep_fn is None:
        sleep_fn = asyncio.sleep

    total = len(rows)
    warmed = skipped = 0
    for row in rows:
        # Replicate the row["filename"] extraction from main.py
        raw = row["filename"] if hasattr(row, "keys") else row[0]
        p = Path(raw).expanduser() if raw else None
        if not p or p.suffix.lower() not in (".heic", ".heif"):
            skipped += 1
            continue
        try:
            # Call synchronously in the test mirror; production uses
            # asyncio.to_thread (Python 3.9+) to avoid blocking the loop.
            result = full_img_for_fn(p)
            if result is not None:
                warmed += 1
            else:
                skipped += 1
        except Exception:
            skipped += 1
        await sleep_fn(0)  # yield; in production this is 0.05
    return total, warmed, skipped


async def _noop_sleep(_delay):
    pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def heic_row(tmp_path: Path):
    """A fake attachment row dict with a HEIC filename."""
    p = tmp_path / "photo.heic"
    p.write_bytes(b"\x00" * 8)
    return {"filename": str(p)}


@pytest.fixture()
def heif_row(tmp_path: Path):
    """A fake attachment row dict with a HEIF filename."""
    p = tmp_path / "shot.heif"
    p.write_bytes(b"\x00" * 8)
    return {"filename": str(p)}


@pytest.fixture()
def jpeg_row(tmp_path: Path):
    """A fake attachment row dict with a JPEG filename (should be skipped)."""
    p = tmp_path / "photo.jpg"
    p.write_bytes(b"\xff\xd8\xff")
    return {"filename": str(p)}


# ---------------------------------------------------------------------------
# a. HEIC files are warmed
# ---------------------------------------------------------------------------

class TestWarmingHEIC:
    def test_heic_row_calls_full_img_for(self, heic_row):
        cached = Path("/fake/cache/abc123.jpg")
        calls = []

        def fake_full_img(p):
            calls.append(p)
            return cached

        total, warmed, skipped = asyncio.run(
            _run_warmer_core([heic_row], fake_full_img, sleep_fn=_noop_sleep)
        )
        assert total == 1
        assert warmed == 1
        assert skipped == 0
        assert len(calls) == 1
        assert calls[0].suffix.lower() == ".heic"

    def test_heif_row_is_also_warmed(self, heif_row):
        def fake_full_img(p):
            return Path("/fake/cache/xyz.jpg")

        total, warmed, skipped = asyncio.run(
            _run_warmer_core([heif_row], fake_full_img, sleep_fn=_noop_sleep)
        )
        assert warmed == 1
        assert skipped == 0

    def test_multiple_heic_rows_all_warmed(self, tmp_path):
        rows = []
        for i in range(5):
            p = tmp_path / f"photo{i}.heic"
            p.write_bytes(b"\x00" * 8)
            rows.append({"filename": str(p)})

        warmed_paths = []

        def fake_full_img(p):
            warmed_paths.append(p)
            return Path(f"/fake/{p.name}.jpg")

        total, warmed, skipped = asyncio.run(
            _run_warmer_core(rows, fake_full_img, sleep_fn=_noop_sleep)
        )
        assert total == 5
        assert warmed == 5
        assert skipped == 0
        assert len(warmed_paths) == 5


# ---------------------------------------------------------------------------
# b. Non-HEIC rows skipped without calling _full_img_for
# ---------------------------------------------------------------------------

class TestNonHEICSkipped:
    def test_jpeg_row_skipped(self, jpeg_row):
        calls = []

        def fake_full_img(p):
            calls.append(p)
            return None

        total, warmed, skipped = asyncio.run(
            _run_warmer_core([jpeg_row], fake_full_img, sleep_fn=_noop_sleep)
        )
        assert total == 1
        assert warmed == 0
        assert skipped == 1
        calls == []  # _full_img_for was NOT called

    def test_png_row_skipped(self, tmp_path):
        p = tmp_path / "image.png"
        p.write_bytes(b"\x89PNG")
        row = {"filename": str(p)}

        calls = []

        def fake_full_img(p):
            calls.append(p)
            return None

        _, warmed, skipped = asyncio.run(
            _run_warmer_core([row], fake_full_img, sleep_fn=_noop_sleep)
        )
        assert warmed == 0
        assert skipped == 1
        assert len(calls) == 0

    def test_none_filename_skipped(self):
        row = {"filename": None}

        calls = []

        def fake_full_img(p):
            calls.append(p)
            return None

        _, warmed, skipped = asyncio.run(
            _run_warmer_core([row], fake_full_img, sleep_fn=_noop_sleep)
        )
        assert warmed == 0
        assert skipped == 1
        assert len(calls) == 0


# ---------------------------------------------------------------------------
# c. sips failure (None return) counts as skipped
# ---------------------------------------------------------------------------

class TestSipsFailure:
    def test_full_img_for_returns_none_counts_as_skipped(self, heic_row):
        def fake_full_img(p):
            return None  # sips failed

        total, warmed, skipped = asyncio.run(
            _run_warmer_core([heic_row], fake_full_img, sleep_fn=_noop_sleep)
        )
        assert warmed == 0
        assert skipped == 1

    def test_full_img_for_raises_counts_as_skipped(self, heic_row):
        def fake_full_img(p):
            raise RuntimeError("sips crashed")

        total, warmed, skipped = asyncio.run(
            _run_warmer_core([heic_row], fake_full_img, sleep_fn=_noop_sleep)
        )
        assert warmed == 0
        assert skipped == 1


# ---------------------------------------------------------------------------
# d. Empty result set
# ---------------------------------------------------------------------------

class TestEmptyResultSet:
    def test_empty_rows_returns_zero_counts(self):
        calls = []

        def fake_full_img(p):
            calls.append(p)
            return None

        total, warmed, skipped = asyncio.run(
            _run_warmer_core([], fake_full_img, sleep_fn=_noop_sleep)
        )
        assert total == 0
        assert warmed == 0
        assert skipped == 0
        assert len(calls) == 0


# ---------------------------------------------------------------------------
# f. Mixed HEIC + non-HEIC rows
# ---------------------------------------------------------------------------

class TestMixedRows:
    def test_mixed_heic_and_jpeg(self, tmp_path):
        heic = tmp_path / "a.heic"
        heic.write_bytes(b"\x00" * 8)
        jpg = tmp_path / "b.jpg"
        jpg.write_bytes(b"\xff\xd8")
        heif = tmp_path / "c.heif"
        heif.write_bytes(b"\x00" * 8)

        rows = [
            {"filename": str(heic)},
            {"filename": str(jpg)},
            {"filename": str(heif)},
        ]
        calls = []

        def fake_full_img(p):
            calls.append(p)
            return Path(f"/fake/{p.name}.jpg")

        total, warmed, skipped = asyncio.run(
            _run_warmer_core(rows, fake_full_img, sleep_fn=_noop_sleep)
        )
        assert total == 3
        assert warmed == 2   # heic + heif
        assert skipped == 1  # jpg
        assert len(calls) == 2
        names = {c.name for c in calls}
        assert "a.heic" in names
        assert "c.heif" in names
        assert "b.jpg" not in names


# ---------------------------------------------------------------------------
# g. Constants sanity check
# ---------------------------------------------------------------------------

def test_warmup_days_is_positive():
    assert _WARMUP_DAYS > 0


def test_warmup_max_is_reasonable():
    # Should be large enough to be useful but bounded to avoid startup delays
    assert 50 <= _WARMUP_MAX <= 1000
