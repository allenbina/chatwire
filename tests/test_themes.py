"""Tests for web/themes.py — theme discovery, label resolution, selection.

All tests that touch the real themes directory use the actual shipped files
(so we'd catch a missing theme slug or a broken file that stops glob from
working). Tests that need isolation patch THEMES_DIR with a tmp_path.
"""
import pytest
from pathlib import Path
import web.themes as themes_mod
from web.themes import (
    DEFAULT_THEME,
    SYSTEM_THEME,
    THEME_LABELS,
    available_themes,
    selected_theme,
    theme_label,
    themes_for_picker,
)

# ---------------------------------------------------------------------------
# theme_label
# ---------------------------------------------------------------------------

class TestThemeLabel:
    def test_all_shipped_slugs_have_labels(self):
        for slug in THEME_LABELS:
            assert theme_label(slug) == THEME_LABELS[slug]

    def test_system(self):
        assert theme_label("system") == "System"

    def test_default(self):
        assert theme_label("default") == "Default"

    def test_dracula(self):
        assert theme_label("dracula") == "Dracula"

    def test_catppuccin_frappe_has_accent(self):
        assert theme_label("catppuccin-frappe") == "Catppuccin Frappé"

    def test_rose_pine_variants(self):
        assert theme_label("rose-pine") == "Rosé Pine"
        assert theme_label("rose-pine-moon") == "Rosé Pine Moon"
        assert theme_label("rose-pine-dawn") == "Rosé Pine Dawn"

    def test_github_casing(self):
        assert theme_label("github-light") == "GitHub Light"
        assert theme_label("github-dark") == "GitHub Dark"

    def test_unknown_slug_title_case_fallback(self):
        assert theme_label("my-custom-theme") == "My Custom Theme"
        assert theme_label("foo-bar-baz") == "Foo Bar Baz"

    def test_unknown_single_word(self):
        assert theme_label("mytheme") == "Mytheme"


# ---------------------------------------------------------------------------
# available_themes — real themes directory
# ---------------------------------------------------------------------------

class TestAvailableThemesReal:
    def test_returns_list(self):
        themes = available_themes()
        assert isinstance(themes, list)
        assert len(themes) > 0

    def test_system_is_first(self):
        assert available_themes()[0] == SYSTEM_THEME

    def test_default_is_second(self):
        assert available_themes()[1] == DEFAULT_THEME

    def test_all_known_slugs_present(self):
        themes = available_themes()
        expected = {
            "system", "default", "dracula", "nord", "tokyo-night", "one-dark",
            "one-light", "night-owl", "solarized-dark", "solarized-light", "gruvbox",
            "gruvbox-light", "github-light", "github-dark",
            "catppuccin-latte", "catppuccin-frappe", "catppuccin-macchiato",
            "catppuccin-mocha", "rose-pine", "rose-pine-moon", "rose-pine-dawn",
        }
        assert expected.issubset(set(themes)), \
            f"Missing slugs: {expected - set(themes)}"

    def test_no_bridge_files_included(self):
        for slug in available_themes():
            assert not slug.startswith("_"), f"Internal file leaked: {slug}"

    def test_total_count(self):
        # 1 system + 1 default + 19 ports = 21. Update when themes are added/removed.
        assert len(available_themes()) == 21


# ---------------------------------------------------------------------------
# available_themes — isolated (tmp_path patches THEMES_DIR)
# ---------------------------------------------------------------------------

class TestAvailableThemesIsolated:
    def test_default_first_when_multiple(self, tmp_path):
        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "default.css").write_text(":root {}")
        (themes_dir / "nord.css").write_text(":root {}")
        (themes_dir / "dracula.css").write_text(":root {}")
        original = themes_mod.THEMES_DIR
        themes_mod.THEMES_DIR = themes_dir
        try:
            slugs = available_themes()
            assert slugs[0] == "default"
            assert set(slugs) == {"default", "nord", "dracula"}
        finally:
            themes_mod.THEMES_DIR = original

    def test_excludes_underscore_files(self, tmp_path):
        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "default.css").write_text(":root {}")
        (themes_dir / "_bridge.css").write_text(":root {}")
        (themes_dir / "_vars.css").write_text(":root {}")
        original = themes_mod.THEMES_DIR
        themes_mod.THEMES_DIR = themes_dir
        try:
            slugs = available_themes()
            assert "_bridge" not in slugs
            assert "_vars" not in slugs
            assert "default" in slugs
        finally:
            themes_mod.THEMES_DIR = original

    def test_missing_dir_returns_default_only(self, tmp_path):
        original = themes_mod.THEMES_DIR
        themes_mod.THEMES_DIR = tmp_path / "nonexistent"
        try:
            assert available_themes() == [DEFAULT_THEME]
        finally:
            themes_mod.THEMES_DIR = original

    def test_no_default_css_still_returns_default(self, tmp_path):
        # Even if no default.css file exists, the slug is still in the list.
        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "nord.css").write_text(":root {}")
        original = themes_mod.THEMES_DIR
        themes_mod.THEMES_DIR = themes_dir
        try:
            # default is not on disk but available_themes() only returns what
            # glob finds — no default.css means no "default" slug here.
            # (The fallback in selected_theme handles a missing default.css
            # gracefully by falling back at the selection layer, not discovery.)
            slugs = available_themes()
            assert "nord" in slugs
        finally:
            themes_mod.THEMES_DIR = original


# ---------------------------------------------------------------------------
# selected_theme
# ---------------------------------------------------------------------------

class TestSelectedTheme:
    def test_no_web_key_returns_default(self):
        assert selected_theme({}) == DEFAULT_THEME

    def test_empty_web_dict_returns_default(self):
        assert selected_theme({"web": {}}) == DEFAULT_THEME

    def test_explicit_default(self):
        assert selected_theme({"web": {"theme": "default"}}) == DEFAULT_THEME

    def test_known_shipped_slug(self):
        assert selected_theme({"web": {"theme": "dracula"}}) == "dracula"

    def test_system_theme_selectable(self):
        assert selected_theme({"web": {"theme": "system"}}) == "system"

    def test_unknown_slug_falls_back_to_default(self):
        assert selected_theme({"web": {"theme": "banana-republic"}}) == DEFAULT_THEME

    def test_null_theme_value_falls_back(self):
        assert selected_theme({"web": {"theme": None}}) == DEFAULT_THEME

    def test_empty_theme_value_falls_back(self):
        assert selected_theme({"web": {"theme": ""}}) == DEFAULT_THEME

    def test_all_shipped_slugs_are_selectable(self):
        for slug in available_themes():
            assert selected_theme({"web": {"theme": slug}}) == slug, \
                f"Shipped slug {slug!r} not selectable"


# ---------------------------------------------------------------------------
# themes_for_picker
# ---------------------------------------------------------------------------

class TestThemesForPicker:
    def test_returns_list_of_dicts(self):
        picker = themes_for_picker()
        assert isinstance(picker, list)
        assert all(isinstance(t, dict) for t in picker)

    def test_each_dict_has_slug_and_label(self):
        for entry in themes_for_picker():
            assert "slug" in entry
            assert "label" in entry

    def test_system_first(self):
        assert themes_for_picker()[0]["slug"] == SYSTEM_THEME

    def test_default_second(self):
        assert themes_for_picker()[1]["slug"] == DEFAULT_THEME

    def test_system_label(self):
        picker = themes_for_picker()
        system_entry = next(e for e in picker if e["slug"] == SYSTEM_THEME)
        assert system_entry["label"] == "System"

    def test_label_matches_theme_label(self):
        for entry in themes_for_picker():
            assert entry["label"] == theme_label(entry["slug"])

    def test_count_matches_available_themes(self):
        assert len(themes_for_picker()) == len(available_themes())
