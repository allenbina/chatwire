"""chatwire-toolbar — macOS menu bar icon for chatwire.

Runs as a lightweight rumps app that shows service status and provides
one-click access to the web UI, service restarts, and settings.

Usage:
    chatwire-toolbar          # start the menu bar app

Design notes:
- Uses rumps (Rumps is not a macOS-native app framework; it wraps AppKit via
  PyObjC). Only available on macOS — importing on other platforms raises
  RuntimeError so test code can still import the module's pure helpers.
- Checks service status via two mechanisms:
    1. launchctl list — determines whether the launchd agent is loaded
    2. GET /healthz — confirms the web service is actually responding
- Status is refreshed every 30 s via a rumps.Timer.
- The app does NOT manage services itself beyond kicking launchctl; it never
  modifies config or the database.
"""
from __future__ import annotations

import subprocess
import sys
import urllib.error
import urllib.request
from typing import NamedTuple

import _version

# ---------------------------------------------------------------------------
# Platform guard — pure helpers below this line are importable on any OS.
# ---------------------------------------------------------------------------

HEALTHZ_URL = "http://localhost:8723/healthz"
SETTINGS_URL = "http://localhost:8723/settings"
WEB_URL = "http://localhost:8723/"

LABEL_PREFIX = "dev.chatwire"
SERVICES = ("bridge", "web")
REFRESH_INTERVAL = 30  # seconds


class ServiceStatus(NamedTuple):
    name: str
    loaded: bool        # launchd agent is loaded
    responding: bool    # healthz returned 200 (web only; False for others)


# ---------------------------------------------------------------------------
# Pure status-checking helpers (no rumps dependency; testable on Linux).
# ---------------------------------------------------------------------------

def _launchctl_list() -> set[str]:
    """Return the set of launchd labels currently loaded for this user.

    Returns an empty set on non-macOS or if launchctl is not available.
    """
    if sys.platform != "darwin":
        return set()
    try:
        result = subprocess.run(
            ["launchctl", "list"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        labels: set[str] = set()
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 3:
                labels.add(parts[2])
        return labels
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return set()


def _healthz_ok() -> bool:
    """Return True if the web service responds 200 to /healthz."""
    try:
        with urllib.request.urlopen(HEALTHZ_URL, timeout=3) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


def get_service_statuses() -> list[ServiceStatus]:
    """Return the current status for each chatwire launchd service."""
    loaded_labels = _launchctl_list()
    web_responding = _healthz_ok()
    statuses = []
    for name in SERVICES:
        label = f"{LABEL_PREFIX}.{name}"
        loaded = label in loaded_labels
        responding = web_responding if name == "web" else False
        statuses.append(ServiceStatus(name=name, loaded=loaded, responding=responding))
    return statuses


def service_status_line(status: ServiceStatus) -> str:
    """Human-readable one-liner for a service status."""
    if status.name == "web":
        if status.loaded and status.responding:
            return f"{status.name}: running"
        elif status.loaded:
            return f"{status.name}: loaded (not responding)"
        else:
            return f"{status.name}: stopped"
    else:
        return f"{status.name}: {'running' if status.loaded else 'stopped'}"


def _restart_service(name: str) -> None:
    """Kick a launchd agent via launchctl kickstart -k."""
    if sys.platform != "darwin":
        return
    label = f"{LABEL_PREFIX}.{name}"
    try:
        subprocess.run(
            ["launchctl", "kickstart", "-k", f"gui/{_get_uid()}/{label}"],
            check=False,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass


def _get_uid() -> int:
    """Return the current user's UID."""
    import os
    return os.getuid()


def _list_installed_plugins() -> list[str]:
    """Return the names of installed chatwire plugin packages.

    Scans importlib.metadata for distributions that declare a
    ``chatwire.integrations`` entry point.  Falls back to an empty list on
    any error so the toolbar still starts if metadata is unavailable.
    """
    try:
        from importlib.metadata import entry_points
        eps = entry_points(group="chatwire.integrations")
        return [ep.name for ep in eps]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# rumps application — only available on macOS.
# ---------------------------------------------------------------------------

def _build_app() -> "rumps.App":  # noqa: F821 — runtime import
    """Construct and return the rumps App object (does not start the event loop)."""
    import rumps  # type: ignore[import]

    app = ChatwireToolbarApp()
    return app


class ChatwireToolbarApp:
    """Thin wrapper so we can instantiate/test the class without running the loop."""

    def __init__(self) -> None:
        import rumps  # type: ignore[import]

        self._rumps = rumps
        self._app = rumps.App(
            f"chatwire {_version.__version__}",
            title="⬡",   # placeholder title shown in menu bar
            quit_button=None,  # we add our own Quit at the bottom
        )
        self._build_menu()
        self._timer = rumps.Timer(self._refresh, REFRESH_INTERVAL)

    # ------------------------------------------------------------------
    # Menu construction
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        rumps = self._rumps
        app = self._app

        # --- status header (non-clickable) ---
        self._status_item = rumps.MenuItem("chatwire — checking…")
        self._status_item.set_callback(None)

        # --- Open web UI ---
        open_item = rumps.MenuItem("Open web UI", callback=self._open_web)

        # --- Services submenu ---
        self._service_items: dict[str, rumps.MenuItem] = {}
        self._restart_items: dict[str, rumps.MenuItem] = {}
        services_menu = rumps.MenuItem("Services")
        for name in SERVICES:
            svc_label = rumps.MenuItem(f"{name}: …")
            svc_label.set_callback(None)
            restart_btn = rumps.MenuItem(
                f"Restart {name}",
                callback=self._make_restart_cb(name),
            )
            self._service_items[name] = svc_label
            self._restart_items[name] = restart_btn
            services_menu.add(svc_label)
            services_menu.add(restart_btn)
            services_menu.add(rumps.separator)
        self._services_menu = services_menu

        # --- Plugins submenu ---
        self._plugins_menu = rumps.MenuItem("Plugins")
        self._refresh_plugins_menu()

        # --- Settings ---
        settings_item = rumps.MenuItem("Settings…", callback=self._open_settings)

        # --- Quit ---
        quit_item = rumps.MenuItem("Quit chatwire toolbar", callback=self._quit)

        app.menu = [
            self._status_item,
            rumps.separator,
            open_item,
            self._services_menu,
            self._plugins_menu,
            rumps.separator,
            settings_item,
            rumps.separator,
            quit_item,
        ]

    # ------------------------------------------------------------------
    # Refresh logic
    # ------------------------------------------------------------------

    def _refresh(self, _timer=None) -> None:
        """Update status items. Called by timer and on startup."""
        statuses = get_service_statuses()
        all_running = all(s.loaded for s in statuses)
        web_ok = any(s.name == "web" and s.responding for s in statuses)

        # Menu bar title
        if web_ok:
            self._app.title = "⬡ ✓"
        elif all_running:
            self._app.title = "⬡ ·"
        else:
            self._app.title = "⬡ ✗"

        # Status header
        if web_ok:
            self._status_item.title = f"chatwire {_version.__version__} — running"
        elif all_running:
            self._status_item.title = f"chatwire {_version.__version__} — loaded"
        else:
            self._status_item.title = f"chatwire {_version.__version__} — stopped"

        # Per-service items
        for status in statuses:
            if status.name in self._service_items:
                self._service_items[status.name].title = service_status_line(status)

        self._refresh_plugins_menu()

    def _refresh_plugins_menu(self) -> None:
        rumps = self._rumps
        plugins = _list_installed_plugins()
        menu = self._plugins_menu
        # Clear existing children
        for key in list(menu.keys()):
            del menu[key]
        if plugins:
            for p in plugins:
                item = rumps.MenuItem(p)
                item.set_callback(None)
                menu.add(item)
        else:
            no_plugins = rumps.MenuItem("No plugins installed")
            no_plugins.set_callback(None)
            menu.add(no_plugins)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _open_web(self, _) -> None:
        import webbrowser
        webbrowser.open(WEB_URL)

    def _open_settings(self, _) -> None:
        import webbrowser
        webbrowser.open(SETTINGS_URL)

    def _make_restart_cb(self, name: str):
        def _cb(_):
            _restart_service(name)
            # refresh after a short delay — the service needs a moment to load
            import threading
            threading.Timer(2.0, self._refresh).start()
        return _cb

    def _quit(self, _) -> None:
        self._rumps.quit_application()

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        self._timer.start()
        self._refresh()
        self._app.run()


# ---------------------------------------------------------------------------
# Console script entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if sys.platform != "darwin":
        sys.exit(
            "chatwire-toolbar requires macOS (rumps wraps AppKit via PyObjC)."
        )
    try:
        import rumps  # noqa: F401 — confirm import before building app
    except ImportError:
        sys.exit(
            "rumps is not installed. Run: pip install rumps\n"
            "(or reinstall chatwire: pipx install chatwire)"
        )
    app = ChatwireToolbarApp()
    app.run()


if __name__ == "__main__":
    main()
