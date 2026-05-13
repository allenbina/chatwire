"""Theme package loader for user-installable JSON theme packages.

Theme packages live in ~/.chatwire/themes/*.json. Each is a JSON file
with optional sections: colors, structure, decorations, custom_css.
Any section can be absent — a colors-only pack is fine.

Package schema (all fields optional except ``name``):
{
  "name": "my-theme",        # required, kebab-case slug used in CSS selectors
  "author": "someone",       # optional display metadata
  "version": "1.0.0",        # optional version string
  "colors": {                # maps to CSS variables in schemes.css
    "background": "#1a1a2e",
    ...
  },
  "structure": {             # maps to CSS variables in themes.css
    "radius-bubble": "0.5rem",
    ...
  },
  "decorations": {           # maps to decoration slot variables
    "avatar-shape": "4px",
    "bubble-shadow": "0 1px 3px rgba(0,0,0,0.15)",
    ...
  },
  "custom_css": "..."        # injected verbatim into a <style> block
}

The ``css_for_package`` function generates a CSS snippet that the
frontend injects into the document head.  Colors and structure/decoration
variables are combined into a single ``[data-theme-pack="<name>"]`` block;
custom_css is appended as-is.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# User themes directory
THEME_PACKS_DIR = Path.home() / ".chatwire" / "themes"

# Valid CSS variable names for each section (prevents injection via crafted keys)
_COLOR_VARS = {
    "background", "foreground", "card", "card-foreground", "popover",
    "popover-foreground", "primary", "primary-foreground", "secondary",
    "secondary-foreground", "muted", "muted-foreground", "accent",
    "accent-foreground", "destructive", "destructive-foreground", "border",
    "input", "ring", "sidebar-bg",
    # extended semantic tokens
    "info", "warning", "success",
    "msg-me", "msg-me-text", "msg-them", "msg-them-text",
    "msg-sms", "msg-sms-text",
}

_STRUCTURE_VARS = {
    "radius", "radius-bubble", "radius-input", "spacing-message",
    "spacing-sidebar", "font-size-message", "font-size-sidebar",
    "shadow-card", "sidebar-width",
}

_DECORATION_VARS = {
    "avatar-shape", "avatar-size", "avatar-border",
    "bubble-shadow", "bubble-tail",
    "header-shadow", "header-border",
    "sidebar-divider", "border-width", "transition-speed",
}

# Built-in color scheme slugs (matches allSchemes in useTheme.ts).
# scheme_dark / scheme_light fields in a theme pack must be one of these.
_KNOWN_SCHEMES = {
    "dracula", "default",
    "catppuccin-frappe", "catppuccin-latte", "catppuccin-macchiato", "catppuccin-mocha",
    "github-dark", "github-light",
    "gruvbox", "gruvbox-light",
    "night-owl", "nord",
    "one-dark", "one-light",
    "rose-pine", "rose-pine-dawn", "rose-pine-moon",
    "solarized-dark", "solarized-light",
    "tokyo-night",
}

# Maximum sizes to prevent absurdly large packages
_MAX_FILE_SIZE = 64 * 1024  # 64 KB
_MAX_CUSTOM_CSS = 32 * 1024  # 32 KB


def _safe_name(name: str) -> bool:
    """Return True if name is a valid CSS identifier-safe string."""
    import re
    return bool(re.match(r'^[a-z0-9][a-z0-9\-]*$', name))


def _safe_value(value: Any) -> str | None:
    """Return the string value if it looks safe for a CSS variable, else None.

    Rejects values containing braces, semicolons, or angle brackets to prevent
    CSS injection through crafted theme files.
    """
    if not isinstance(value, str):
        return None
    if len(value) > 256:
        return None
    forbidden = set('{};:<>')
    if any(c in forbidden for c in value):
        return None
    return value


def sanitize_custom_css(css: str) -> tuple[str, bool]:
    """Strip dangerous constructs from user-provided custom CSS.

    Removes:
    - ``@import`` rules (any form — prevents loading external stylesheets)
    - ``url()`` references that point to http/https URLs (prevents external
      network requests and privacy leakage)

    Everything else is preserved verbatim so theme authors have full
    expressive power.  Returns ``(sanitized_css, was_modified)`` where
    ``was_modified`` is True if anything was removed/replaced.
    """
    # Strip @import statements (matches @import "url"; and @import url(...);)
    result = re.sub(r'@import\b[^;]*;?', '', css, flags=re.IGNORECASE)

    # Replace external url() references (http/https) with url(about:blank)
    def _url_filter(m: re.Match) -> str:
        inner = m.group(1).strip().strip('"\'')
        if re.match(r'https?://', inner, re.IGNORECASE):
            return 'url(about:blank)'
        return m.group(0)

    result = re.sub(r'url\(\s*([^)]*?)\s*\)', _url_filter, result, flags=re.IGNORECASE)

    return result, result != css


def parse_package(data: dict) -> dict | None:
    """Validate and normalize a raw theme package dict.

    Returns a cleaned dict with only safe/known keys, or None if the
    package is invalid (missing name, unsafe name, etc.).
    """
    name = data.get("name")
    if not isinstance(name, str) or not name or not _safe_name(name):
        return None

    pkg: dict[str, Any] = {
        "name": name,
        "author": str(data.get("author") or ""),
        "version": str(data.get("version") or ""),
        "colors": {},
        "structure": {},
        "decorations": {},
        "custom_css": "",
        "custom_css_sanitized": False,
        "scheme_dark": None,
        "scheme_light": None,
    }

    # Scheme preferences — validated against known built-in scheme slugs
    for field in ("scheme_dark", "scheme_light"):
        raw = data.get(field)
        if isinstance(raw, str) and raw in _KNOWN_SCHEMES:
            pkg[field] = raw

    # Colors
    raw_colors = data.get("colors") or {}
    if isinstance(raw_colors, dict):
        for k, v in raw_colors.items():
            if k in _COLOR_VARS:
                safe = _safe_value(v)
                if safe is not None:
                    pkg["colors"][k] = safe

    # Structure
    raw_struct = data.get("structure") or {}
    if isinstance(raw_struct, dict):
        for k, v in raw_struct.items():
            if k in _STRUCTURE_VARS:
                safe = _safe_value(v)
                if safe is not None:
                    pkg["structure"][k] = safe

    # Decorations
    raw_deco = data.get("decorations") or {}
    if isinstance(raw_deco, dict):
        for k, v in raw_deco.items():
            if k in _DECORATION_VARS:
                safe = _safe_value(v)
                if safe is not None:
                    pkg["decorations"][k] = safe

    # Custom CSS — sanitize before storing
    custom = data.get("custom_css")
    if isinstance(custom, str) and len(custom) <= _MAX_CUSTOM_CSS:
        sanitized, was_modified = sanitize_custom_css(custom)
        pkg["custom_css"] = sanitized
        pkg["custom_css_sanitized"] = was_modified

    return pkg


def load_packages() -> list[dict]:
    """Scan ~/.chatwire/themes/ and return all valid theme packages.

    Invalid or unreadable files are logged and skipped; they don't crash
    the package list.  Results are sorted alphabetically by name.
    """
    if not THEME_PACKS_DIR.is_dir():
        return []

    packages: list[dict] = []
    for path in sorted(THEME_PACKS_DIR.glob("*.json")):
        if path.stat().st_size > _MAX_FILE_SIZE:
            log.warning("theme_loader: skipping %s (too large)", path.name)
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("theme_loader: skipping %s (%s)", path.name, exc)
            continue
        if not isinstance(data, dict):
            continue
        pkg = parse_package(data)
        if pkg is None:
            log.warning("theme_loader: skipping %s (invalid name)", path.name)
            continue
        packages.append(pkg)

    return packages


def css_for_package(pkg: dict) -> str:
    """Generate a CSS snippet for a theme package.

    Colors, structure variables, and decoration variables are all merged
    into a single ``[data-theme-pack="<name>"]`` selector block so a
    single data attribute on <html> activates the whole package.

    Custom CSS is appended verbatim after the variable block.
    """
    name = pkg["name"]
    selector = f'[data-theme-pack="{name}"]'
    lines: list[str] = []

    # Collect all variable declarations
    vars_: list[str] = []
    for k, v in pkg.get("colors", {}).items():
        vars_.append(f"  --{k}: {v};")
    for k, v in pkg.get("structure", {}).items():
        vars_.append(f"  --{k}: {v};")
    for k, v in pkg.get("decorations", {}).items():
        vars_.append(f"  --{k}: {v};")

    if vars_:
        lines.append(f"{selector} {{")
        lines.extend(vars_)
        lines.append("}")

    custom = pkg.get("custom_css", "").strip()
    if custom:
        lines.append("")
        lines.append(f"/* custom_css from theme pack {name!r} */")
        lines.append(custom)

    return "\n".join(lines)
