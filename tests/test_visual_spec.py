"""Visual spec tests for the chatwire web UI.

These tests verify that CSS classes, font sizes, colors, and spacing match
the Flowbite reference design. They don't require a running server or
browser — they parse the Jinja templates directly and assert on the
Tailwind classes present.

Run: python3 -m pytest tests/test_visual_spec.py -v

For actual screenshot regression (pixel-perfect comparison), you'd use
Playwright. These structural tests are the lightweight version that
catches class-level regressions without a browser.

To add a new check:
  1. Identify the element (template file + CSS class or id)
  2. Assert the exact Tailwind classes that should be present
  3. If a theme variable is involved, assert the var(--app-color-*) name

The DESIGN_SPEC dict below is the single source of truth for "what should
the UI look like." When you want to change a design detail, update the spec
first, watch the test fail, then fix the template.
"""
from pathlib import Path
import re

TEMPLATES = Path(__file__).resolve().parent.parent / "web" / "templates"
STATIC = Path(__file__).resolve().parent.parent / "web" / "static"


def _read(relpath: str) -> str:
    return (TEMPLATES / relpath).read_text()


def _read_static(relpath: str) -> str:
    return (STATIC / relpath).read_text()


# ── Design Spec ──────────────────────────────────────────────────────
# Each entry: (template_file, description, css_classes_that_must_appear)
# If any of these classes are missing from the template, the test fails.

DESIGN_SPEC = {
    # --- Fonts ---
    "inter_font_index": {
        "file": "index.html",
        "desc": "Inter font loaded via Google Fonts",
        "contains": ["fonts.googleapis.com", "family=Inter"],
    },
    "inter_font_login": {
        "file": "_login.html",
        "desc": "Inter font loaded on login page",
        "contains": ["fonts.googleapis.com", "family=Inter"],
    },
    "inter_font_wizard": {
        "file": "wizard/index.html",
        "desc": "Inter font loaded on wizard page",
        "contains": ["fonts.googleapis.com", "family=Inter"],
    },

    # --- Sidebar conversation list ---
    "sidebar_name_font": {
        "file": "_conversations.html",
        "desc": "Contact name: 16px semibold, theme text color (matches Flowbite)",
        "contains": ["text-base", "font-semibold", "text-app-text"],
    },
    "sidebar_preview_font": {
        "file": "_conversations.html",
        "desc": "Preview text: 14px regular, muted theme color",
        "contains": ["text-sm", "text-app-text-muted"],
    },
    "sidebar_timestamp_font": {
        "file": "_conversations.html",
        "desc": "Timestamp: 12px, faint theme color",
        "contains": ["text-xs", "text-app-text-faint"],
    },
    "sidebar_bg_themed": {
        "file": "index.html",
        "desc": "Sidebar uses theme surface color, not hardcoded white",
        "contains": ["bg-app-surface"],
    },
    "sidebar_border_themed": {
        "file": "index.html",
        "desc": "Sidebar border uses theme color",
        "contains": ["border-app-border"],
    },
    "sidebar_hover_themed": {
        "file": "_conversations.html",
        "desc": "Conversation hover uses theme color",
        "contains": ["hover:bg-app-surface-hover"],
    },

    # --- Unread badge ---
    "badge_uses_primary_color": {
        "file": "_conversations.html",
        "desc": "Unread badge uses theme primary color",
        "contains": ["bg-app-primary", "text-app-on-primary"],
    },
    "badge_no_fixed_width": {
        "file": "_conversations.html",
        "desc": "Badge uses padding sizing (no fixed w-5 that overflows)",
        "contains": ["px-2"],
        "must_not_contain": ["min-w-5 h-5 px-1.5"],
    },

    # --- Media indicator ---
    "media_icon_svg": {
        "file": "_conversations.html",
        "desc": "Media indicator is an SVG icon (not emoji)",
        "contains": ["media_icon"],
        "must_not_contain": ["📎", "📷"],
    },

    # --- Message bubbles ---
    "bubble_me_themed": {
        "file": "_messages.html",
        "desc": "My message bubble uses theme primary color",
        "contains": ["bg-app-primary", "text-app-on-primary"],
    },
    "bubble_them_themed": {
        "file": "_messages.html",
        "desc": "Their message bubble uses theme bubble color",
        "contains": ["bg-app-bubble-them", "text-app-text"],
    },

    # --- Conversation header ---
    "header_bg_themed": {
        "file": "_conversation.html",
        "desc": "Header uses theme surface color",
        "contains": ["bg-app-surface"],
    },
    "header_border_themed": {
        "file": "_conversation.html",
        "desc": "Header border uses theme color",
        "contains": ["border-app-border"],
    },

    # --- Composer ---
    "composer_input_themed": {
        "file": "_conversation.html",
        "desc": "Composer input uses theme colors",
        "contains": ["text-app-text", "bg-app-surface-alt", "border-app-border"],
    },

    # --- Settings ---
    "settings_accordion": {
        "file": "_settings.html",
        "desc": "Settings uses accordion with toggle and arrow rotation",
        "contains": ["acc-toggle", "acc-arrow", "data-target"],
    },
    "settings_bg_themed": {
        "file": "_settings.html",
        "desc": "Settings surfaces use theme colors",
        "contains": ["bg-app-surface", "border-app-border"],
    },

    # --- Login ---
    "login_bg_themed": {
        "file": "_login.html",
        "desc": "Login page uses theme colors",
        "contains": ["bg-app-bg", "bg-app-surface", "text-app-text"],
    },

    # --- No hardcoded whites in themed elements ---
    "no_hardcoded_bg_white_sidebar": {
        "file": "_conversations.html",
        "desc": "Sidebar list has no hardcoded bg-white",
        "must_not_contain": ["bg-white"],
    },
    "no_hardcoded_bg_white_header": {
        "file": "_conversation.html",
        "desc": "Conversation header has no hardcoded bg-white (use bg-app-surface)",
        "must_not_contain": ["bg-white"],
    },
    "no_hardcoded_bg_white_settings": {
        "file": "_settings.html",
        "desc": "Settings has no hardcoded bg-white",
        "must_not_contain": ["bg-white"],
    },

    # --- Flowbite re-init after HTMX ---
    "flowbite_reinit": {
        "file": "index.html",
        "desc": "Flowbite re-inits after HTMX swaps (for accordion, etc.)",
        "contains": ["initFlowbite"],
    },

    # --- CSS uses variables, not hardcoded colors ---
    "style_css_uses_vars": {
        "file": None,  # checked separately
        "desc": "style.css uses CSS variables for colors",
        "static_file": "style.css",
        "contains": ["var(--app-color-"],
        "must_not_contain": ["#ffffff"],
    },

    # --- Scrolling ---
    "conversation_wrapper_flex": {
        "file": "_conversation.html",
        "desc": "Conversation wrapper is flex column so messages scroll",
        "contains": ["flex flex-col h-full overflow-hidden"],
    },

    # --- File input hidden ---
    "file_input_hidden": {
        "file": "_conversation.html",
        "desc": "File input is visually hidden (no browse button showing)",
        "contains": ['type="file"', "hidden"],
    },

    # --- Send button themed ---
    "send_button_themed": {
        "file": "_conversation.html",
        "desc": "Send button uses theme primary, not hardcoded blue",
        "contains": ["bg-app-primary", "text-app-on-primary"],
    },

    # --- No emoji in templates ---
    "no_emoji_in_messages": {
        "file": "_messages.html",
        "desc": "No emoji characters for attachment indicators",
        "must_not_contain": ["📎", "📷"],
    },
    "no_emoji_in_ghost": {
        "file": "_conversation.html",
        "desc": "Ghost message uses SVG icon, not emoji for attachments",
        "must_not_contain": ["📎"],
    },

    # --- Flowbite text color match ---
    "bridge_text_color_matches_flowbite": {
        "file": None,
        "desc": "Default text color matches Flowbite heading token (#111827 = gray-900)",
        "static_file": "themes/_bridge.css",
        "contains": ["--app-color-text: #111827"],
    },
}


class TestVisualSpec:
    """Each DESIGN_SPEC entry becomes a test case."""

    def _check(self, spec_name: str):
        spec = DESIGN_SPEC[spec_name]

        if spec.get("static_file"):
            content = _read_static(spec["static_file"])
        else:
            content = _read(spec["file"])

        for needle in spec.get("contains", []):
            assert needle in content, (
                f"[{spec_name}] {spec['desc']}\n"
                f"Expected '{needle}' in {spec.get('file') or spec.get('static_file')}"
            )

        for needle in spec.get("must_not_contain", []):
            assert needle not in content, (
                f"[{spec_name}] {spec['desc']}\n"
                f"'{needle}' should NOT appear in {spec.get('file') or spec.get('static_file')}"
            )

    def test_inter_font_index(self):
        self._check("inter_font_index")

    def test_inter_font_login(self):
        self._check("inter_font_login")

    def test_inter_font_wizard(self):
        self._check("inter_font_wizard")

    def test_sidebar_name_font(self):
        self._check("sidebar_name_font")

    def test_sidebar_preview_font(self):
        self._check("sidebar_preview_font")

    def test_sidebar_timestamp_font(self):
        self._check("sidebar_timestamp_font")

    def test_sidebar_bg_themed(self):
        self._check("sidebar_bg_themed")

    def test_sidebar_border_themed(self):
        self._check("sidebar_border_themed")

    def test_sidebar_hover_themed(self):
        self._check("sidebar_hover_themed")

    def test_badge_uses_primary_color(self):
        self._check("badge_uses_primary_color")

    def test_badge_no_fixed_width(self):
        self._check("badge_no_fixed_width")

    def test_media_icon_svg(self):
        self._check("media_icon_svg")

    def test_bubble_me_themed(self):
        self._check("bubble_me_themed")

    def test_bubble_them_themed(self):
        self._check("bubble_them_themed")

    def test_header_bg_themed(self):
        self._check("header_bg_themed")

    def test_header_border_themed(self):
        self._check("header_border_themed")

    def test_composer_input_themed(self):
        self._check("composer_input_themed")

    def test_settings_accordion(self):
        self._check("settings_accordion")

    def test_settings_bg_themed(self):
        self._check("settings_bg_themed")

    def test_login_bg_themed(self):
        self._check("login_bg_themed")

    def test_no_hardcoded_bg_white_sidebar(self):
        self._check("no_hardcoded_bg_white_sidebar")

    def test_no_hardcoded_bg_white_header(self):
        self._check("no_hardcoded_bg_white_header")

    def test_no_hardcoded_bg_white_settings(self):
        self._check("no_hardcoded_bg_white_settings")

    def test_flowbite_reinit(self):
        self._check("flowbite_reinit")

    def test_style_css_uses_vars(self):
        self._check("style_css_uses_vars")

    def test_conversation_wrapper_flex(self):
        self._check("conversation_wrapper_flex")

    def test_file_input_hidden(self):
        self._check("file_input_hidden")

    def test_send_button_themed(self):
        self._check("send_button_themed")

    def test_no_emoji_in_messages(self):
        self._check("no_emoji_in_messages")

    def test_no_emoji_in_ghost(self):
        self._check("no_emoji_in_ghost")

    def test_bridge_text_color_matches_flowbite(self):
        self._check("bridge_text_color_matches_flowbite")


class TestThemeVariables:
    """Every theme CSS file must define the core --app-color-* variables."""

    REQUIRED_VARS = [
        "--app-color-bg",
        "--app-color-surface",
        "--app-color-text",
        "--app-color-primary",
        "--app-color-on-primary",
        "--app-color-border",
        "--app-color-bubble-them-bg",
    ]

    def _theme_files(self):
        themes_dir = STATIC / "themes"
        return [
            f for f in sorted(themes_dir.glob("*.css"))
            if not f.name.startswith("_")
        ]

    def test_all_themes_define_core_vars(self):
        for theme_file in self._theme_files():
            content = theme_file.read_text()
            for var in self.REQUIRED_VARS:
                assert var in content, (
                    f"Theme '{theme_file.name}' missing required variable: {var}"
                )

    def test_bridge_defines_all_defaults(self):
        bridge = (STATIC / "themes" / "_bridge.css").read_text()
        for var in self.REQUIRED_VARS:
            assert var in bridge, f"_bridge.css missing default for {var}"
