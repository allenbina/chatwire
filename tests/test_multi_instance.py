"""Tests for the bridge single-instance PID lock.

Strategy:
  - Exercise acquire_pid_lock / release_pid_lock directly against a tmp dir
    so the real ~/.chatwire/bridge.pid is never touched.
  - Cover: first start (no lock), stale lock (dead PID), live lock (alive PID),
    and clean release.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from bridge import acquire_pid_lock, release_pid_lock


# ---------- helpers ----------

def _lock(tmp_path: Path) -> Path:
    return tmp_path / "bridge.pid"


# ---------- tests ----------

class TestAcquirePidLock:
    def test_no_lock_file_writes_pid(self, tmp_path):
        lp = _lock(tmp_path)
        acquire_pid_lock(lp)
        assert lp.read_text().strip() == str(os.getpid())

    def test_stale_lock_is_overwritten(self, tmp_path):
        lp = _lock(tmp_path)
        # Write a PID that definitely doesn't exist (use a very large fake PID).
        # We mock os.kill to raise ProcessLookupError (process is dead).
        fake_pid = 9_999_999
        lp.write_text(str(fake_pid))

        with patch("bridge.os.kill", side_effect=ProcessLookupError):
            acquire_pid_lock(lp)

        assert lp.read_text().strip() == str(os.getpid())

    def test_live_lock_raises_system_exit(self, tmp_path):
        lp = _lock(tmp_path)
        # Pretend a different PID owns the lock and is alive (os.kill returns None).
        other_pid = os.getpid() + 1
        lp.write_text(str(other_pid))

        with patch("bridge.os.kill", return_value=None):
            with pytest.raises(SystemExit) as exc_info:
                acquire_pid_lock(lp)

        assert str(other_pid) in str(exc_info.value)

    def test_permission_error_treated_as_alive(self, tmp_path):
        lp = _lock(tmp_path)
        other_pid = os.getpid() + 1
        lp.write_text(str(other_pid))

        with patch("bridge.os.kill", side_effect=PermissionError):
            with pytest.raises(SystemExit):
                acquire_pid_lock(lp)

    def test_corrupt_lock_file_is_overwritten(self, tmp_path):
        lp = _lock(tmp_path)
        lp.write_text("not-a-pid\n")

        # No os.kill should be called; should just overwrite.
        acquire_pid_lock(lp)
        assert lp.read_text().strip() == str(os.getpid())

    def test_own_pid_in_lock_does_not_raise(self, tmp_path):
        """Re-entrant: if the lock already holds our own PID, don't error."""
        lp = _lock(tmp_path)
        lp.write_text(str(os.getpid()))

        # Should not raise (our pid == old_pid, so alive check is skipped).
        acquire_pid_lock(lp)
        assert lp.read_text().strip() == str(os.getpid())


class TestReleasePidLock:
    def test_removes_file_when_pid_matches(self, tmp_path):
        lp = _lock(tmp_path)
        lp.write_text(str(os.getpid()))
        release_pid_lock(lp)
        assert not lp.exists()

    def test_does_not_remove_file_when_pid_differs(self, tmp_path):
        lp = _lock(tmp_path)
        lp.write_text(str(os.getpid() + 1))
        release_pid_lock(lp)
        assert lp.exists()

    def test_no_error_when_file_missing(self, tmp_path):
        lp = _lock(tmp_path)
        # Should be a no-op, not raise.
        release_pid_lock(lp)
