"""Tests for chatwire doctor — run_doctor_checks() and the wizard's
preflight_warnings().

Strategy:
  - Patch sys.platform, sys.version_info, shutil.which, and the two
    probes so tests run on any host (Linux CI, macOS, etc.).
  - run_doctor_checks() returns a structured dict; assert on status and
    labels rather than printed output.
  - preflight_warnings() is a pure function of sys.platform + shutil.which;
    easy to drive deterministically.
"""
from __future__ import annotations

import collections
import sys
from unittest.mock import MagicMock, patch

# sys.version_info is a C struct that can't be instantiated directly;
# use a namedtuple that supports tuple comparison.
_VersionInfo = collections.namedtuple(
    "_VersionInfo", ["major", "minor", "micro", "releaselevel", "serial"]
)

import pytest

import chatwire_cli
from chatwire_cli import run_doctor_checks
from web.probes import preflight_warnings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check(result: dict, label: str) -> dict:
    """Return the single check entry matching *label*, or raise KeyError."""
    for c in result["checks"]:
        if c["label"] == label:
            return c
    raise KeyError(f"no check with label {label!r}; got {[c['label'] for c in result['checks']]}")


# ---------------------------------------------------------------------------
# run_doctor_checks — structured results
# ---------------------------------------------------------------------------

class TestRunDoctorChecks:
    """run_doctor_checks() returns consistent structure regardless of host."""

    def _run(self, *, platform="darwin", version_info=(3, 12, 0),
             fda_status="ok", fda_detail="100 messages readable",
             auto_status="ok", auto_detail="2 services",
             pipx=None, sips="/usr/bin/sips"):
        vi = _VersionInfo(version_info[0], version_info[1], version_info[2], "final", 0)
        fda_result = {"status": fda_status, "detail": fda_detail}
        auto_result = {"status": auto_status, "detail": auto_detail}
        which_map = {"pipx": pipx, "sips": sips}

        with patch.object(sys, "platform", platform):
            with patch.object(sys, "version_info", vi):
                with patch("chatwire_cli.shutil.which", side_effect=lambda x: which_map.get(x)):
                    with patch("web.probes.probe_fda", return_value=fda_result):
                        with patch("web.probes.probe_automation", return_value=auto_result):
                            return run_doctor_checks()

    def test_returns_dict_with_required_keys(self):
        r = self._run()
        assert "critical_failures" in r
        assert "checks" in r
        assert isinstance(r["checks"], list)

    def test_all_ok_zero_critical_failures(self):
        r = self._run(pipx="/usr/local/bin/pipx")
        assert r["critical_failures"] == 0

    def test_macos_ok_on_darwin(self):
        r = self._run(platform="darwin")
        c = _check(r, "macOS")
        assert c["status"] == "ok"
        assert "version" in c["detail"]

    def test_macos_warn_on_linux(self):
        r = self._run(platform="linux")
        c = _check(r, "macOS")
        assert c["status"] == "warn"
        assert "linux" in c["detail"]

    def test_python_ok_when_310_or_above(self):
        for ver in [(3, 10, 0), (3, 11, 0), (3, 12, 4), (3, 13, 0)]:
            r = self._run(version_info=ver)
            c = _check(r, "Python")
            assert c["status"] == "ok", f"expected ok for {ver}"

    def test_python_warn_when_below_310(self):
        for ver in [(3, 8, 0), (3, 9, 7)]:
            r = self._run(version_info=ver)
            c = _check(r, "Python")
            assert c["status"] == "warn", f"expected warn for {ver}"

    def test_fda_ok(self):
        r = self._run(fda_status="ok", fda_detail="42,000 messages readable")
        c = _check(r, "Full Disk Access")
        assert c["status"] == "ok"
        assert "42,000" in c["detail"]

    def test_fda_fail_increments_critical(self):
        r = self._run(fda_status="fail", fda_detail="chat.db open denied")
        assert r["critical_failures"] == 1
        c = _check(r, "Full Disk Access")
        assert c["status"] == "fail"

    def test_automation_fail_increments_critical(self):
        r = self._run(auto_status="fail", auto_detail="-1743 denied")
        assert r["critical_failures"] == 1
        c = _check(r, "Automation → Messages")
        assert c["status"] == "fail"

    def test_both_critical_fail_counts_two(self):
        r = self._run(fda_status="fail", auto_status="fail")
        assert r["critical_failures"] == 2

    def test_pipx_ok_when_found(self):
        r = self._run(pipx="/usr/local/bin/pipx")
        c = _check(r, "pipx")
        assert c["status"] == "ok"
        assert "/usr/local/bin/pipx" in c["detail"]

    def test_pipx_warn_when_missing(self):
        r = self._run(pipx=None)
        c = _check(r, "pipx")
        assert c["status"] == "warn"

    def test_sips_ok_when_found(self):
        r = self._run(sips="/usr/bin/sips")
        c = _check(r, "sips")
        assert c["status"] == "ok"

    def test_sips_warn_when_missing(self):
        r = self._run(sips=None)
        c = _check(r, "sips")
        assert c["status"] == "warn"

    def test_non_critical_warnings_do_not_increment_critical(self):
        # macOS warn, python warn, pipx missing, sips missing — still 0 critical
        r = self._run(
            platform="linux",
            version_info=(3, 9, 0),
            fda_status="ok",
            auto_status="ok",
            pipx=None,
            sips=None,
        )
        assert r["critical_failures"] == 0

    def test_six_checks_returned(self):
        """Exactly six checks: macOS, Python, FDA, Automation, pipx, sips."""
        r = self._run()
        assert len(r["checks"]) == 6


# ---------------------------------------------------------------------------
# preflight_warnings — wizard banner content
# ---------------------------------------------------------------------------

class TestPreflightWarnings:
    def _run(self, *, platform="darwin", mac_ver="14.0",
             version_info=(3, 12, 0), sips="/usr/bin/sips"):
        vi = _VersionInfo(version_info[0], version_info[1], version_info[2], "final", 0)
        mock_platform = MagicMock()
        mock_platform.mac_ver.return_value = (mac_ver, ("", "", ""), "")
        with patch.object(sys, "platform", platform):
            with patch("web.probes.platform", mock_platform):
                with patch.object(sys, "version_info", vi):
                    with patch("web.probes.shutil.which",
                               side_effect=lambda x: sips if x == "sips" else None):
                        return preflight_warnings()

    def test_no_warnings_on_clean_macos(self):
        w = self._run()
        assert w == []

    def test_warns_on_non_macos(self):
        w = self._run(platform="linux")
        assert any("macOS" in s for s in w)

    def test_warns_on_old_macos(self):
        w = self._run(mac_ver="10.14.6")
        assert any("11+" in s or "Big Sur" in s for s in w)

    def test_no_warning_macos_11_or_newer(self):
        for ver in ["11.0", "12.4", "13.0", "14.0", "15.1"]:
            w = self._run(mac_ver=ver)
            assert not any("Big Sur" in s for s in w), f"unexpected warning for {ver}"

    def test_warns_old_python(self):
        w = self._run(version_info=(3, 9, 0))
        assert any("3.10" in s for s in w)

    def test_no_python_warning_310_or_newer(self):
        for ver in [(3, 10, 0), (3, 12, 0)]:
            w = self._run(version_info=ver)
            assert not any("3.10" in s for s in w)

    def test_warns_missing_sips(self):
        w = self._run(sips=None)
        assert any("sips" in s.lower() for s in w)

    def test_no_sips_warning_when_present(self):
        w = self._run(sips="/usr/bin/sips")
        assert not any("sips" in s.lower() for s in w)
