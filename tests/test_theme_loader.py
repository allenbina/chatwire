"""Tests for web/theme_loader.py — JSON theme package loading and CSS generation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import web.theme_loader as loader_mod
from web.theme_loader import (
    css_for_package,
    load_packages,
    parse_package,
    sanitize_custom_css,
)


# ---------------------------------------------------------------------------
# sanitize_custom_css
# ---------------------------------------------------------------------------

class TestSanitizeCustomCss:
    def test_clean_css_unchanged(self):
        css = ".foo { color: red; background: blue; }"
        result, modified = sanitize_custom_css(css)
        assert result == css
        assert modified is False

    def test_strips_import_with_url(self):
        css = '@import url("https://evil.com/steal.css");'
        result, modified = sanitize_custom_css(css)
        assert "@import" not in result
        assert modified is True

    def test_strips_import_with_string(self):
        css = '@import "https://evil.com/steal.css";'
        result, modified = sanitize_custom_css(css)
        assert "@import" not in result
        assert modified is True

    def test_strips_import_case_insensitive(self):
        css = "@IMPORT url(bad.css);"
        result, modified = sanitize_custom_css(css)
        assert "@IMPORT" not in result.upper() or "@import" not in result.lower()
        assert modified is True

    def test_strips_https_url(self):
        css = ".bg { background: url(https://tracker.example.com/pixel.png); }"
        result, modified = sanitize_custom_css(css)
        assert "https://tracker.example.com" not in result
        assert "url(about:blank)" in result
        assert modified is True

    def test_strips_http_url(self):
        css = ".bg { background: url(http://cdn.example.com/img.png); }"
        result, modified = sanitize_custom_css(css)
        assert "http://cdn.example.com" not in result
        assert "url(about:blank)" in result
        assert modified is True

    def test_strips_quoted_https_url(self):
        css = '.bg { background: url("https://example.com/img.png"); }'
        result, modified = sanitize_custom_css(css)
        assert "https://example.com" not in result
        assert modified is True

    def test_preserves_data_uri(self):
        css = '.icon { background: url(data:image/png;base64,abc123); }'
        result, modified = sanitize_custom_css(css)
        assert "data:image/png;base64,abc123" in result
        assert modified is False

    def test_preserves_fragment_reference(self):
        css = ".icon { fill: url(#myGradient); }"
        result, modified = sanitize_custom_css(css)
        assert "url(#myGradient)" in result
        assert modified is False

    def test_preserves_relative_path(self):
        css = ".bg { background: url(./local-image.png); }"
        result, modified = sanitize_custom_css(css)
        assert "url(./local-image.png)" in result
        assert modified is False

    def test_parse_package_sanitizes_import(self):
        """parse_package must sanitize @import in custom_css and set flag."""
        raw = {
            "name": "evil",
            "custom_css": '@import url("https://bad.example.com/x.css"); .foo { color: red; }',
        }
        pkg = parse_package(raw)
        assert pkg is not None
        assert "@import" not in pkg["custom_css"]
        assert pkg["custom_css_sanitized"] is True

    def test_parse_package_clean_css_not_flagged(self):
        """parse_package must not flag packages with clean custom_css."""
        raw = {
            "name": "clean",
            "custom_css": ".foo { color: red; }",
        }
        pkg = parse_package(raw)
        assert pkg is not None
        assert pkg["custom_css_sanitized"] is False

    def test_parse_package_no_custom_css_not_flagged(self):
        """Packages without custom_css should have custom_css_sanitized=False."""
        pkg = parse_package({"name": "minimal"})
        assert pkg is not None
        assert pkg["custom_css_sanitized"] is False


# ---------------------------------------------------------------------------
# parse_package
# ---------------------------------------------------------------------------

class TestParsePackage:
    def test_minimal_valid_package(self):
        pkg = parse_package({"name": "my-theme"})
        assert pkg is not None
        assert pkg["name"] == "my-theme"
        assert pkg["colors"] == {}
        assert pkg["structure"] == {}
        assert pkg["decorations"] == {}
        assert pkg["custom_css"] == ""

    def test_full_package(self):
        raw = {
            "name": "my-theme",
            "author": "Alice",
            "version": "1.2.3",
            "colors": {"background": "#1a1a2e", "primary": "#7c3aed"},
            "structure": {"radius-bubble": "0.5rem"},
            "decorations": {"avatar-shape": "4px", "bubble-shadow": "0 1px 3px rgba(0,0,0,0.1)"},
            "custom_css": ".extra { color: red; }",
        }
        pkg = parse_package(raw)
        assert pkg is not None
        assert pkg["name"] == "my-theme"
        assert pkg["author"] == "Alice"
        assert pkg["version"] == "1.2.3"
        assert pkg["colors"]["background"] == "#1a1a2e"
        assert pkg["structure"]["radius-bubble"] == "0.5rem"
        assert pkg["decorations"]["avatar-shape"] == "4px"
        assert pkg["custom_css"] == ".extra { color: red; }"

    def test_missing_name_returns_none(self):
        assert parse_package({}) is None
        assert parse_package({"author": "Alice"}) is None

    def test_empty_name_returns_none(self):
        assert parse_package({"name": ""}) is None

    def test_name_with_uppercase_returns_none(self):
        assert parse_package({"name": "MyTheme"}) is None

    def test_name_with_spaces_returns_none(self):
        assert parse_package({"name": "my theme"}) is None

    def test_name_with_underscore_returns_none(self):
        assert parse_package({"name": "my_theme"}) is None

    def test_name_starting_with_dash_returns_none(self):
        assert parse_package({"name": "-theme"}) is None

    def test_unknown_color_keys_skipped(self):
        pkg = parse_package({"name": "t", "colors": {"nonexistent-var": "#fff"}})
        assert pkg is not None
        assert "nonexistent-var" not in pkg["colors"]

    def test_unknown_structure_keys_skipped(self):
        pkg = parse_package({"name": "t", "structure": {"fake-var": "1rem"}})
        assert pkg is not None
        assert "fake-var" not in pkg["structure"]

    def test_unknown_decoration_keys_skipped(self):
        pkg = parse_package({"name": "t", "decorations": {"fake-var": "1px"}})
        assert pkg is not None
        assert "fake-var" not in pkg["decorations"]

    def test_value_with_semicolon_rejected(self):
        pkg = parse_package({"name": "t", "colors": {"background": "#fff; color: red"}})
        assert pkg is not None
        assert "background" not in pkg["colors"]

    def test_value_with_braces_rejected(self):
        pkg = parse_package({"name": "t", "colors": {"background": "{evil}"}})
        assert pkg is not None
        assert "background" not in pkg["colors"]

    def test_value_with_angle_bracket_rejected(self):
        pkg = parse_package({"name": "t", "colors": {"background": "<script>"}})
        assert pkg is not None
        assert "background" not in pkg["colors"]

    def test_non_string_value_rejected(self):
        pkg = parse_package({"name": "t", "colors": {"background": 123}})
        assert pkg is not None
        assert "background" not in pkg["colors"]

    def test_custom_css_truncated_if_too_long(self):
        big_css = "a" * (loader_mod._MAX_CUSTOM_CSS + 1)
        pkg = parse_package({"name": "t", "custom_css": big_css})
        assert pkg is not None
        assert pkg["custom_css"] == ""

    def test_non_dict_colors_ignored(self):
        pkg = parse_package({"name": "t", "colors": "not-a-dict"})
        assert pkg is not None
        assert pkg["colors"] == {}


# ---------------------------------------------------------------------------
# css_for_package
# ---------------------------------------------------------------------------

class TestCssForPackage:
    def test_empty_package_produces_empty_css(self):
        pkg = parse_package({"name": "empty"})
        assert css_for_package(pkg) == ""

    def test_colors_generate_selector_block(self):
        pkg = parse_package({"name": "dark", "colors": {"background": "#000", "primary": "#fff"}})
        css = css_for_package(pkg)
        assert '[data-theme-pack="dark"]' in css
        assert "--background: #000;" in css
        assert "--primary: #fff;" in css

    def test_structure_vars_in_same_block(self):
        pkg = parse_package({"name": "t", "structure": {"radius-bubble": "0.5rem"}})
        css = css_for_package(pkg)
        assert "--radius-bubble: 0.5rem;" in css

    def test_decoration_vars_in_same_block(self):
        pkg = parse_package({"name": "t", "decorations": {"avatar-shape": "4px"}})
        css = css_for_package(pkg)
        assert "--avatar-shape: 4px;" in css

    def test_custom_css_appended(self):
        pkg = parse_package({"name": "t", "custom_css": ".foo { color: red; }"})
        css = css_for_package(pkg)
        assert ".foo { color: red; }" in css

    def test_selector_uses_package_name(self):
        pkg = parse_package({"name": "my-custom", "colors": {"background": "#fff"}})
        css = css_for_package(pkg)
        assert '[data-theme-pack="my-custom"]' in css


# ---------------------------------------------------------------------------
# load_packages — isolated (tmp_path patches THEME_PACKS_DIR)
# ---------------------------------------------------------------------------

class TestLoadPackages:
    def test_missing_dir_returns_empty(self, tmp_path):
        original = loader_mod.THEME_PACKS_DIR
        loader_mod.THEME_PACKS_DIR = tmp_path / "nonexistent"
        try:
            assert load_packages() == []
        finally:
            loader_mod.THEME_PACKS_DIR = original

    def test_loads_valid_package(self, tmp_path):
        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "my-theme.json").write_text(
            json.dumps({"name": "my-theme", "colors": {"background": "#000"}}),
            encoding="utf-8",
        )
        original = loader_mod.THEME_PACKS_DIR
        loader_mod.THEME_PACKS_DIR = themes_dir
        try:
            pkgs = load_packages()
            assert len(pkgs) == 1
            assert pkgs[0]["name"] == "my-theme"
            assert pkgs[0]["colors"]["background"] == "#000"
        finally:
            loader_mod.THEME_PACKS_DIR = original

    def test_skips_invalid_json(self, tmp_path):
        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "broken.json").write_text("not json", encoding="utf-8")
        original = loader_mod.THEME_PACKS_DIR
        loader_mod.THEME_PACKS_DIR = themes_dir
        try:
            assert load_packages() == []
        finally:
            loader_mod.THEME_PACKS_DIR = original

    def test_skips_invalid_name(self, tmp_path):
        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "bad.json").write_text(
            json.dumps({"name": "Bad Name!"}), encoding="utf-8"
        )
        original = loader_mod.THEME_PACKS_DIR
        loader_mod.THEME_PACKS_DIR = themes_dir
        try:
            assert load_packages() == []
        finally:
            loader_mod.THEME_PACKS_DIR = original

    def test_skips_non_dict_json(self, tmp_path):
        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "list.json").write_text("[1, 2, 3]", encoding="utf-8")
        original = loader_mod.THEME_PACKS_DIR
        loader_mod.THEME_PACKS_DIR = themes_dir
        try:
            assert load_packages() == []
        finally:
            loader_mod.THEME_PACKS_DIR = original

    def test_multiple_packages_sorted(self, tmp_path):
        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "zebra.json").write_text(json.dumps({"name": "zebra"}), encoding="utf-8")
        (themes_dir / "alpha.json").write_text(json.dumps({"name": "alpha"}), encoding="utf-8")
        original = loader_mod.THEME_PACKS_DIR
        loader_mod.THEME_PACKS_DIR = themes_dir
        try:
            pkgs = load_packages()
            names = [p["name"] for p in pkgs]
            assert names == ["alpha", "zebra"]
        finally:
            loader_mod.THEME_PACKS_DIR = original

    def test_only_json_files_loaded(self, tmp_path):
        themes_dir = tmp_path / "themes"
        themes_dir.mkdir()
        (themes_dir / "theme.json").write_text(json.dumps({"name": "theme"}), encoding="utf-8")
        (themes_dir / "theme.css").write_text(":root {}", encoding="utf-8")
        (themes_dir / "README.md").write_text("hello", encoding="utf-8")
        original = loader_mod.THEME_PACKS_DIR
        loader_mod.THEME_PACKS_DIR = themes_dir
        try:
            pkgs = load_packages()
            assert len(pkgs) == 1
            assert pkgs[0]["name"] == "theme"
        finally:
            loader_mod.THEME_PACKS_DIR = original


# ---------------------------------------------------------------------------
# scheme_dark / scheme_light — theme import preference cascade fields
# ---------------------------------------------------------------------------

class TestSchemeFields:
    def test_valid_scheme_dark_accepted(self):
        pkg = parse_package({"name": "t", "scheme_dark": "dracula"})
        assert pkg is not None
        assert pkg["scheme_dark"] == "dracula"
        assert pkg["scheme_light"] is None

    def test_valid_scheme_light_accepted(self):
        pkg = parse_package({"name": "t", "scheme_light": "default"})
        assert pkg is not None
        assert pkg["scheme_light"] == "default"
        assert pkg["scheme_dark"] is None

    def test_both_schemes_accepted(self):
        pkg = parse_package({"name": "t", "scheme_dark": "nord", "scheme_light": "github-light"})
        assert pkg is not None
        assert pkg["scheme_dark"] == "nord"
        assert pkg["scheme_light"] == "github-light"

    def test_unknown_scheme_dark_rejected(self):
        pkg = parse_package({"name": "t", "scheme_dark": "not-a-real-scheme"})
        assert pkg is not None
        assert pkg["scheme_dark"] is None

    def test_unknown_scheme_light_rejected(self):
        pkg = parse_package({"name": "t", "scheme_light": "also-fake"})
        assert pkg is not None
        assert pkg["scheme_light"] is None

    def test_non_string_scheme_rejected(self):
        pkg = parse_package({"name": "t", "scheme_dark": 42, "scheme_light": None})
        assert pkg is not None
        assert pkg["scheme_dark"] is None
        assert pkg["scheme_light"] is None

    def test_scheme_injection_attempt_rejected(self):
        # CSS-injection attempts in scheme values must be rejected (not in _KNOWN_SCHEMES)
        pkg = parse_package({"name": "t", "scheme_dark": "dracula; color: red"})
        assert pkg is not None
        assert pkg["scheme_dark"] is None

    def test_all_known_dark_schemes_accepted(self):
        dark_schemes = [
            "dracula", "catppuccin-frappe", "catppuccin-macchiato", "catppuccin-mocha",
            "github-dark", "gruvbox", "night-owl", "nord", "one-dark",
            "rose-pine", "rose-pine-moon", "solarized-dark", "tokyo-night",
        ]
        for slug in dark_schemes:
            pkg = parse_package({"name": "t", "scheme_dark": slug})
            assert pkg is not None
            assert pkg["scheme_dark"] == slug, f"expected scheme_dark={slug!r} to be accepted"

    def test_all_known_light_schemes_accepted(self):
        light_schemes = [
            "default", "catppuccin-latte", "github-light", "gruvbox-light",
            "one-light", "rose-pine-dawn", "solarized-light",
        ]
        for slug in light_schemes:
            pkg = parse_package({"name": "t", "scheme_light": slug})
            assert pkg is not None
            assert pkg["scheme_light"] == slug, f"expected scheme_light={slug!r} to be accepted"

    def test_missing_scheme_fields_default_to_none(self):
        pkg = parse_package({"name": "t"})
        assert pkg is not None
        assert pkg["scheme_dark"] is None
        assert pkg["scheme_light"] is None
