"""Theme discovery and selection for the web UI.

Themes are CSS files in `web/static/themes/` that set `--app-*` variables;
the bridge file `_bridge.css` propagates those onto Shoelace's `--sl-*`
tokens. A user picks one via `web.theme` in `config.json`; the value must
match a shipped theme slug (the basename of the CSS file, sans extension).

Files starting with "_" are bridge/internal and not user-selectable.
"""
from __future__ import annotations

from pathlib import Path

THEMES_DIR = Path(__file__).resolve().parent / "static" / "themes"
DEFAULT_THEME = "default"
SYSTEM_THEME = "system"

# Themes that always appear at the top of the picker, in this order.
# "system" first so users immediately see the OS-adaptive option.
_PINNED_THEMES = [SYSTEM_THEME, DEFAULT_THEME]

# Display labels for shipped slugs. The fallback in `theme_label()` handles
# any slug not listed here (so new theme files don't have to touch this
# table just to render in the picker), but the explicit entries get the
# proper-noun spellings (Catppuccin Frappé's é, GitHub's casing, etc.)
# right where slug-derived auto-titles wouldn't.
THEME_LABELS: dict[str, str] = {
    "system": "System",
    "default": "Default",
    "dracula": "Dracula",
    "nord": "Nord",
    "tokyo-night": "Tokyo Night",
    "one-dark": "One Dark",
    "one-light": "One Light",
    "night-owl": "Night Owl",
    "solarized-dark": "Solarized Dark",
    "solarized-light": "Solarized Light",
    "gruvbox": "Gruvbox",
    "gruvbox-light": "Gruvbox Light",
    "github-light": "GitHub Light",
    "github-dark": "GitHub Dark",
    "catppuccin-latte": "Catppuccin Latte",
    "catppuccin-frappe": "Catppuccin Frappé",
    "catppuccin-macchiato": "Catppuccin Macchiato",
    "catppuccin-mocha": "Catppuccin Mocha",
    "rose-pine": "Rosé Pine",
    "rose-pine-moon": "Rosé Pine Moon",
    "rose-pine-dawn": "Rosé Pine Dawn",
}


def theme_label(slug: str) -> str:
    """Display label for a slug. Looks up the explicit table first, falls
    back to a simple title-case so unknown slugs still render reasonably."""
    if slug in THEME_LABELS:
        return THEME_LABELS[slug]
    return slug.replace("-", " ").title()


def themes_for_picker() -> list[dict[str, str]]:
    """[{slug, label}] for every available theme, default first.

    The picker UI consumes this directly — server-side label resolution
    keeps the template simple and means a future plugin theme that drops
    a CSS file into themes/ shows up with a sensible name without
    touching the template.
    """
    return [{"slug": s, "label": theme_label(s)} for s in available_themes()]


def available_themes() -> list[str]:
    """Slugs of every selectable theme. Pinned themes (system, default) come
    first in that order; the rest are sorted alphabetically.

    Discovered at call time, not cached, so dropping a new theme file in
    place is picked up on the next request without a restart. The cost is
    one directory listing per call — negligible at our request rates.
    """
    if not THEMES_DIR.is_dir():
        return [DEFAULT_THEME]
    all_slugs = sorted(
        p.stem for p in THEMES_DIR.glob("*.css")
        if not p.name.startswith("_")
    )
    pinned = [s for s in _PINNED_THEMES if s in all_slugs]
    rest = [s for s in all_slugs if s not in set(_PINNED_THEMES)]
    return (pinned + rest) or [DEFAULT_THEME]


def selected_theme(cfg: dict) -> str:
    """The configured theme, validated against `available_themes()`.

    Falls back to `DEFAULT_THEME` for any unknown / missing value, so a
    theme that's been removed from disk doesn't 404 its stylesheet.
    """
    web = cfg.get("web") or {}
    requested = web.get("theme") or DEFAULT_THEME
    if requested in available_themes():
        return requested
    return DEFAULT_THEME
