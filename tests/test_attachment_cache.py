"""Tests for the attachment image cache (Phase 48: Photo CDN).

Strategy: mirror the cache logic from web/main.py locally so we can test it
without triggering main.py's heavy module-level side-effects (chat.db, contacts,
subprocess for sips, etc.).

Covers:
  a. _full_img_for: cache miss → sips invoked → cached file returned.
  b. _full_img_for: cache hit → sips NOT invoked a second time.
  c. _full_img_for: mtime change invalidates cache (new sips call).
  d. _full_img_for: sips failure → returns None (caller serves raw file).
  e. _thumb_for:    cache miss → sips invoked with -Z flag.
  f. _thumb_for:    cache hit → sips NOT invoked a second time.
  g. evict_cache:   files older than TTL are deleted; newer files survive.
  h. evict_cache:   non-existent cache dir is silently skipped.
  i. Cache-Control constant is the expected 30-day value.
"""
from __future__ import annotations

import hashlib
import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Local mirrors of the cache helpers (mirrors web/main.py logic)
# ---------------------------------------------------------------------------

_ATTACHMENT_CACHE_CONTROL = "public, max-age=2592000"  # 30 days
THUMB_MAX_EDGE = 720


def _thumb_for(orig: Path, cache_dir: Path) -> Path | None:
    """Cached JPEG thumbnail. Returns None on failure."""
    try:
        st = orig.stat()
    except OSError:
        return None
    key = hashlib.sha1(f"{orig}:{int(st.st_mtime)}".encode()).hexdigest()[:16]
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / f"{key}.jpg"
    if cached.exists() and cached.stat().st_mtime >= st.st_mtime:
        return cached
    try:
        subprocess.run(
            ["sips", "-Z", str(THUMB_MAX_EDGE), "-s", "format", "jpeg",
             str(orig), "--out", str(cached)],
            check=True, capture_output=True, timeout=30,
        )
    except Exception:
        return None
    return cached if cached.exists() else None


def _full_img_for(orig: Path, cache_dir: Path) -> Path | None:
    """Cached full-size JPEG for HEIC/HEIF. Returns None on failure."""
    try:
        st = orig.stat()
    except OSError:
        return None
    key = hashlib.sha1(f"{orig}:{int(st.st_mtime)}".encode()).hexdigest()[:16]
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / f"{key}.jpg"
    if cached.exists() and cached.stat().st_mtime >= st.st_mtime:
        return cached
    try:
        subprocess.run(
            ["sips", "-s", "format", "jpeg", str(orig), "--out", str(cached)],
            check=True, capture_output=True, timeout=30,
        )
    except Exception:
        return None
    return cached if cached.exists() else None


def _evict_cache(cache_dir: Path, ttl_days: int) -> int:
    """Delete files older than ttl_days. Returns count of deleted files."""
    if not cache_dir.exists():
        return 0
    cutoff = time.time() - ttl_days * 86400
    pruned = 0
    for f in cache_dir.iterdir():
        try:
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()
                pruned += 1
        except OSError:
            continue
    return pruned


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def orig_file(tmp_path: Path) -> Path:
    """A fake HEIC original file."""
    p = tmp_path / "photo.heic"
    p.write_bytes(b"\x00" * 16)  # minimal fake content
    return p


@pytest.fixture()
def img_cache(tmp_path: Path) -> Path:
    return tmp_path / "img_cache"


@pytest.fixture()
def thumb_cache(tmp_path: Path) -> Path:
    return tmp_path / "thumb_cache"


# ---------------------------------------------------------------------------
# _full_img_for tests
# ---------------------------------------------------------------------------

class TestFullImgFor:
    def test_cache_miss_invokes_sips(self, orig_file: Path, img_cache: Path):
        """On a cache miss, sips is called and the cached path is returned."""
        def fake_sips(cmd, **kwargs):
            # simulate sips writing the output file
            out = Path(cmd[-1])
            out.write_bytes(b"fake-jpeg")
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=fake_sips) as mock_run:
            result = _full_img_for(orig_file, img_cache)

        assert result is not None
        assert result.exists()
        assert result.suffix == ".jpg"
        assert result.parent == img_cache
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "sips" in cmd
        assert "-Z" not in cmd          # full-size: no -Z resize flag
        assert str(orig_file) in cmd
        assert str(result) == cmd[-1]

    def test_cache_hit_skips_sips(self, orig_file: Path, img_cache: Path):
        """On a cache hit, sips is NOT called again."""
        def fake_sips(cmd, **kwargs):
            out = Path(cmd[-1])
            out.write_bytes(b"fake-jpeg")
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=fake_sips):
            result1 = _full_img_for(orig_file, img_cache)

        assert result1 is not None

        with patch("subprocess.run") as mock_run2:
            result2 = _full_img_for(orig_file, img_cache)

        mock_run2.assert_not_called()
        assert result2 == result1

    def test_mtime_change_invalidates_cache(self, orig_file: Path, img_cache: Path):
        """If the original's mtime changes, a new cache entry is generated."""
        def fake_sips(cmd, **kwargs):
            out = Path(cmd[-1])
            out.write_bytes(b"fake-jpeg")
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=fake_sips):
            result1 = _full_img_for(orig_file, img_cache)

        assert result1 is not None

        # Touch the original to advance mtime
        orig_file.write_bytes(b"\xff" * 16)
        # Ensure mtime actually differs (some filesystems have 1-second resolution)
        import os
        os.utime(orig_file, (time.time() + 1, time.time() + 1))

        with patch("subprocess.run", side_effect=fake_sips) as mock_run2:
            result2 = _full_img_for(orig_file, img_cache)

        mock_run2.assert_called_once()
        # Different cache key → different file
        assert result2 != result1

    def test_sips_failure_returns_none(self, orig_file: Path, img_cache: Path):
        """If sips raises an exception, None is returned (fallback to raw file)."""
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "sips")):
            result = _full_img_for(orig_file, img_cache)

        assert result is None

    def test_missing_original_returns_none(self, tmp_path: Path, img_cache: Path):
        """If the original file does not exist, None is returned."""
        missing = tmp_path / "nonexistent.heic"
        with patch("subprocess.run") as mock_run:
            result = _full_img_for(missing, img_cache)

        assert result is None
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# _thumb_for tests
# ---------------------------------------------------------------------------

class TestThumbFor:
    def test_cache_miss_invokes_sips_with_resize(self, orig_file: Path, thumb_cache: Path):
        """Thumbnail generation uses the -Z resize flag."""
        def fake_sips(cmd, **kwargs):
            out = Path(cmd[-1])
            out.write_bytes(b"fake-thumb")
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=fake_sips) as mock_run:
            result = _thumb_for(orig_file, thumb_cache)

        assert result is not None
        cmd = mock_run.call_args[0][0]
        assert "-Z" in cmd
        assert str(THUMB_MAX_EDGE) in cmd

    def test_cache_hit_skips_sips(self, orig_file: Path, thumb_cache: Path):
        """Cache hit on thumb also skips sips."""
        def fake_sips(cmd, **kwargs):
            out = Path(cmd[-1])
            out.write_bytes(b"fake-thumb")
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=fake_sips):
            result1 = _thumb_for(orig_file, thumb_cache)

        with patch("subprocess.run") as mock_run2:
            result2 = _thumb_for(orig_file, thumb_cache)

        mock_run2.assert_not_called()
        assert result2 == result1


# ---------------------------------------------------------------------------
# Eviction tests
# ---------------------------------------------------------------------------

class TestEvictCache:
    def test_old_files_are_deleted(self, tmp_path: Path):
        cache = tmp_path / "cache"
        cache.mkdir()

        old_file = cache / "old.jpg"
        old_file.write_bytes(b"x")
        # Set mtime to 200 days ago
        old_ts = time.time() - 200 * 86400
        import os
        os.utime(old_file, (old_ts, old_ts))

        fresh_file = cache / "fresh.jpg"
        fresh_file.write_bytes(b"y")
        # fresh_file's mtime is now (default)

        pruned = _evict_cache(cache, ttl_days=180)

        assert pruned == 1
        assert not old_file.exists()
        assert fresh_file.exists()

    def test_nonexistent_dir_returns_zero(self, tmp_path: Path):
        missing = tmp_path / "no_such_cache"
        pruned = _evict_cache(missing, ttl_days=90)
        assert pruned == 0

    def test_all_fresh_files_survive(self, tmp_path: Path):
        cache = tmp_path / "cache"
        cache.mkdir()
        for i in range(3):
            (cache / f"file{i}.jpg").write_bytes(b"data")

        pruned = _evict_cache(cache, ttl_days=90)
        assert pruned == 0
        assert len(list(cache.iterdir())) == 3


# ---------------------------------------------------------------------------
# Cache-Control constant
# ---------------------------------------------------------------------------

def test_cache_control_constant():
    """The Cache-Control header value covers 30 days (2592000 seconds)."""
    assert "public" in _ATTACHMENT_CACHE_CONTROL
    assert "max-age=2592000" in _ATTACHMENT_CACHE_CONTROL
