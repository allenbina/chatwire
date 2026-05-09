"""System-readiness probes used by the setup wizard and `chatwire doctor`.

This module is intentionally free of FastAPI / Jinja2 imports so that it can
be imported by the CLI (chatwire_cli.py) and by tests without pulling in the
full web stack.
"""
from __future__ import annotations

import platform
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

CHAT_DB = Path.home() / "Library" / "Messages" / "chat.db"


def probe_fda() -> dict:
    """Try to read chat.db.  Success = Full Disk Access is granted.

    Note: this checks FDA for whatever python is running the *web* process,
    which is the same binary the bridge uses (both come from the same venv).
    A fresh install where the user hasn't granted FDA yet will land here
    too — chat.db open will EPERM.
    """
    if not CHAT_DB.exists():
        return {
            "status": "fail",
            "detail": (
                f"{CHAT_DB} not found — has Messages.app ever run on this account?"
            ),
        }
    try:
        with sqlite3.connect(f"file:{CHAT_DB}?mode=ro", uri=True) as c:
            n = c.execute("SELECT COUNT(*) FROM message").fetchone()[0]
        return {"status": "ok", "detail": f"{n:,} messages readable"}
    except sqlite3.OperationalError as e:
        return {
            "status": "fail",
            "detail": (
                f"chat.db open denied: {e}. "
                "Grant Full Disk Access to the python.org Python framework binary."
            ),
        }
    except Exception as e:
        return {"status": "fail", "detail": f"{type(e).__name__}: {e}"}


def probe_automation() -> dict:
    """Probe Automation → Messages by asking Messages.app a trivial question.

    ``count of services`` is harmless and triggers the Automation prompt the
    first time.  Once granted it returns silently.  -1743 means denied.
    """
    try:
        r = subprocess.run(
            ["osascript", "-e", 'tell application "Messages" to count of services'],
            capture_output=True, text=True, timeout=10,
        )
    except FileNotFoundError:
        return {"status": "fail", "detail": "osascript not found (not on macOS?)"}
    except subprocess.TimeoutExpired:
        return {
            "status": "fail",
            "detail": "osascript timed out — Messages.app may not be running",
        }
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    if r.returncode == 0 and out.isdigit():
        return {"status": "ok", "detail": f"Messages.app reachable ({out} services)"}
    if "1743" in err:
        return {
            "status": "fail",
            "detail": (
                "Automation denied — System Settings → Privacy & Security "
                "→ Automation, allow this terminal/Python to control Messages."
            ),
        }
    return {"status": "fail", "detail": err or out or "unknown osascript failure"}


def preflight_warnings() -> list:
    """Return a list of human-readable warning strings for non-critical system
    checks.  Called by the wizard's permissions step to surface a banner above
    the FDA/Automation probes when the environment looks misconfigured.

    Checks performed here are the fast, import-only ones (platform, Python
    version, tool availability).  FDA and Automation are probed separately by
    probe_fda() / probe_automation() which are already shown inline.
    """
    warnings = []

    if sys.platform != "darwin":
        warnings.append(
            f"Not running on macOS (platform={sys.platform}). "
            "The bridge requires macOS — permissions below will fail."
        )
    else:
        ver = platform.mac_ver()[0]
        # Minimum macOS version is 10.15 (Catalina) for modern chat.db schema.
        # Warn but don't block — older installs may still work.
        parts = ver.split(".")
        try:
            major = int(parts[0])
            if major < 11:
                warnings.append(
                    f"macOS {ver} detected. chatwire works best on macOS 11+ "
                    "(Big Sur or later)."
                )
        except (ValueError, IndexError):
            pass

    vi = sys.version_info
    if vi < (3, 10):
        warnings.append(
            f"Python {vi.major}.{vi.minor}.{vi.micro} detected. "
            "chatwire requires Python 3.10 or later."
        )

    if not shutil.which("sips"):
        warnings.append(
            "sips not found — image thumbnail generation will be skipped. "
            "(sips is a macOS built-in; it should be at /usr/bin/sips.)"
        )

    return warnings
