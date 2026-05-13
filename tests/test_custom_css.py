"""Tests for per-theme user custom CSS (#15).

Strategy: test the underlying logic layer-by-layer without a live FastAPI
server (same pattern as test_accent_color.py, test_theme_override.py).

Covers:
  _safe_name validation (slug guard)
  Per-theme file write / read / delete
  Combined CSS generation (wrapping + ordering)
  Size limits (>64 KB rejected)
  Invalid / empty inputs handled gracefully
  POST with theme vs. legacy (no theme)
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from web.theme_loader import _safe_name


# ---------------------------------------------------------------------------
# Helpers — mirrors the route logic in web/api_ui.py and web/main.py
# ---------------------------------------------------------------------------

_MAX_PER_THEME_CSS = 64 * 1024  # 64 KB


def _write_custom_css(base_dir: Path, slug: str, css: str) -> None:
    """Write per-theme custom CSS to <base_dir>/<slug>.css."""
    assert _safe_name(slug), f"bad slug: {slug!r}"
    base_dir.mkdir(parents=True, exist_ok=True)
    path = base_dir / f"{slug}.css"
    if css.strip():
        path.write_text(css, encoding="utf-8")
    else:
        path.unlink(missing_ok=True)


def _read_custom_css(base_dir: Path, slug: str) -> str:
    """Read raw custom CSS for a slug, or empty string if absent."""
    path = base_dir / f"{slug}.css"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _build_combined_css(base_dir: Path) -> tuple[str, dict[str, str]]:
    """Build combined scoped CSS and raw themes map from a directory."""
    if not base_dir.is_dir():
        return "", {}

    themes: dict[str, str] = {}
    blocks: list[str] = []
    for path in sorted(base_dir.glob("*.css")):
        slug = path.stem
        if not _safe_name(slug):
            continue
        try:
            raw = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not raw:
            continue
        themes[slug] = raw
        blocks.append(f'[data-theme="{slug}"] {{\n{raw}\n}}')

    return "\n\n".join(blocks), themes


def _validate_css_request(theme: str | None, css: str) -> None:
    """Raise ValueError for invalid POST payloads (mirrors route guards)."""
    if not isinstance(css, str):
        raise TypeError("custom_css must be a string")
    if len(css) > _MAX_PER_THEME_CSS:
        raise ValueError("custom_css too large (max 64 KB)")
    if theme is not None:
        if not isinstance(theme, str) or not _safe_name(theme):
            raise ValueError(f"invalid theme name: {theme!r}")


# ---------------------------------------------------------------------------
# _safe_name — slug validation (reused from theme_loader)
# ---------------------------------------------------------------------------

class TestSlugValidation:
    def test_simple_slug_valid(self):
        assert _safe_name("dracula") is True

    def test_hyphenated_slug_valid(self):
        assert _safe_name("catppuccin-mocha") is True

    def test_alphanumeric_slug_valid(self):
        assert _safe_name("github-dark") is True

    def test_slug_with_numbers_valid(self):
        assert _safe_name("theme1") is True

    def test_empty_string_invalid(self):
        assert _safe_name("") is False

    def test_uppercase_invalid(self):
        assert _safe_name("Dracula") is False

    def test_dot_invalid(self):
        assert _safe_name("my.theme") is False

    def test_slash_invalid(self):
        assert _safe_name("../../etc") is False

    def test_space_invalid(self):
        assert _safe_name("my theme") is False

    def test_underscore_invalid(self):
        assert _safe_name("my_theme") is False


# ---------------------------------------------------------------------------
# Write / read / delete
# ---------------------------------------------------------------------------

class TestWriteReadDelete:
    def test_write_creates_file(self, tmp_path):
        _write_custom_css(tmp_path, "dracula", ".foo { color: red; }")
        path = tmp_path / "dracula.css"
        assert path.exists()

    def test_write_content_preserved(self, tmp_path):
        css = ".bar { background: hsl(var(--primary)); }"
        _write_custom_css(tmp_path, "dracula", css)
        assert _read_custom_css(tmp_path, "dracula") == css

    def test_write_empty_deletes_file(self, tmp_path):
        _write_custom_css(tmp_path, "dracula", ".foo { color: red; }")
        _write_custom_css(tmp_path, "dracula", "")
        assert not (tmp_path / "dracula.css").exists()

    def test_write_whitespace_only_deletes_file(self, tmp_path):
        _write_custom_css(tmp_path, "dracula", ".foo { color: red; }")
        _write_custom_css(tmp_path, "dracula", "   \n  ")
        assert not (tmp_path / "dracula.css").exists()

    def test_read_missing_returns_empty(self, tmp_path):
        assert _read_custom_css(tmp_path, "dracula") == ""

    def test_overwrite_replaces_content(self, tmp_path):
        _write_custom_css(tmp_path, "dracula", ".foo { color: red; }")
        _write_custom_css(tmp_path, "dracula", ".bar { color: blue; }")
        assert _read_custom_css(tmp_path, "dracula") == ".bar { color: blue; }"

    def test_multiple_slugs_independent(self, tmp_path):
        _write_custom_css(tmp_path, "dracula", ".foo { color: red; }")
        _write_custom_css(tmp_path, "github-light", ".bar { color: blue; }")
        assert _read_custom_css(tmp_path, "dracula") == ".foo { color: red; }"
        assert _read_custom_css(tmp_path, "github-light") == ".bar { color: blue; }"

    def test_creates_parent_dir(self, tmp_path):
        nested = tmp_path / "subdir"
        _write_custom_css(nested, "nord", ".x { margin: 0; }")
        assert (nested / "nord.css").exists()

    def test_missing_dir_read_returns_empty(self, tmp_path):
        missing = tmp_path / "no-such-dir"
        assert _read_custom_css(missing, "dracula") == ""


# ---------------------------------------------------------------------------
# Combined CSS generation
# ---------------------------------------------------------------------------

class TestCombinedCss:
    def test_empty_dir_returns_empty(self, tmp_path):
        css, themes = _build_combined_css(tmp_path)
        assert css == ""
        assert themes == {}

    def test_missing_dir_returns_empty(self, tmp_path):
        css, themes = _build_combined_css(tmp_path / "no-such-dir")
        assert css == ""
        assert themes == {}

    def test_single_theme_wrapped(self, tmp_path):
        _write_custom_css(tmp_path, "dracula", ".foo { color: red; }")
        css, themes = _build_combined_css(tmp_path)
        assert '[data-theme="dracula"]' in css
        assert ".foo { color: red; }" in css
        assert themes == {"dracula": ".foo { color: red; }"}

    def test_multiple_themes_all_wrapped(self, tmp_path):
        _write_custom_css(tmp_path, "dracula", ".a { color: red; }")
        _write_custom_css(tmp_path, "nord", ".b { color: blue; }")
        css, themes = _build_combined_css(tmp_path)
        assert '[data-theme="dracula"]' in css
        assert '[data-theme="nord"]' in css
        assert ".a { color: red; }" in css
        assert ".b { color: blue; }" in css
        assert set(themes.keys()) == {"dracula", "nord"}

    def test_themes_sorted_alphabetically(self, tmp_path):
        _write_custom_css(tmp_path, "nord", ".b {}")
        _write_custom_css(tmp_path, "dracula", ".a {}")
        css, _ = _build_combined_css(tmp_path)
        dracula_pos = css.index("dracula")
        nord_pos = css.index("nord")
        assert dracula_pos < nord_pos

    def test_empty_css_file_skipped(self, tmp_path):
        # Write a file then manually zero it out (bypassing our write helper)
        path = tmp_path / "dracula.css"
        path.write_text("", encoding="utf-8")
        css, themes = _build_combined_css(tmp_path)
        assert css == ""
        assert themes == {}

    def test_invalid_slug_file_skipped(self, tmp_path):
        # File with unsafe name should be ignored
        bad = tmp_path / "UPPERCASE.css"
        bad.write_text(".x { color: red; }", encoding="utf-8")
        css, themes = _build_combined_css(tmp_path)
        assert "UPPERCASE" not in css
        assert themes == {}

    def test_path_traversal_slug_skipped(self, tmp_path):
        # A file whose stem contains path chars (hard to create on most filesystems,
        # but we test that _safe_name correctly guards)
        assert not _safe_name("../../etc")

    def test_themes_map_contains_raw_css(self, tmp_path):
        raw = ".widget { border: 1px solid red; }"
        _write_custom_css(tmp_path, "dracula", raw)
        _, themes = _build_combined_css(tmp_path)
        assert themes["dracula"] == raw

    def test_combined_css_structure(self, tmp_path):
        """Each block must start with [data-theme="slug"] { and end with }."""
        _write_custom_css(tmp_path, "dracula", ".x { color: red; }")
        css, _ = _build_combined_css(tmp_path)
        assert css.startswith('[data-theme="dracula"] {')
        assert css.rstrip().endswith("}")


# ---------------------------------------------------------------------------
# POST payload validation
# ---------------------------------------------------------------------------

class TestPayloadValidation:
    def test_valid_with_theme(self):
        _validate_css_request("dracula", ".foo { color: red; }")

    def test_valid_without_theme(self):
        _validate_css_request(None, ".foo { color: red; }")

    def test_valid_empty_css(self):
        _validate_css_request("dracula", "")

    def test_invalid_theme_uppercase_raises(self):
        with pytest.raises(ValueError, match="invalid theme"):
            _validate_css_request("Dracula", ".foo {}")

    def test_invalid_theme_slash_raises(self):
        with pytest.raises(ValueError, match="invalid theme"):
            _validate_css_request("../../etc", ".foo {}")

    def test_invalid_theme_empty_string_raises(self):
        with pytest.raises(ValueError, match="invalid theme"):
            _validate_css_request("", ".foo {}")

    def test_oversized_css_raises(self):
        big_css = "a" * (_MAX_PER_THEME_CSS + 1)
        with pytest.raises(ValueError, match="too large"):
            _validate_css_request("dracula", big_css)

    def test_exactly_max_size_is_valid(self):
        at_limit = "a" * _MAX_PER_THEME_CSS
        _validate_css_request("dracula", at_limit)  # no exception

    def test_non_string_css_raises(self):
        with pytest.raises(TypeError):
            _validate_css_request("dracula", 123)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Roundtrip: write → build combined → themes map
# ---------------------------------------------------------------------------

class TestRoundtrip:
    def test_write_then_combined_roundtrip(self, tmp_path):
        css_d = ".dracula-rule { color: #bd93f9; }"
        css_n = ".nord-rule { color: #88c0d0; }"
        _write_custom_css(tmp_path, "dracula", css_d)
        _write_custom_css(tmp_path, "nord", css_n)
        combined, themes = _build_combined_css(tmp_path)
        assert themes["dracula"] == css_d
        assert themes["nord"] == css_n
        assert f'[data-theme="dracula"] {{\n{css_d}\n}}' in combined
        assert f'[data-theme="nord"] {{\n{css_n}\n}}' in combined

    def test_delete_then_combined_excludes(self, tmp_path):
        _write_custom_css(tmp_path, "dracula", ".foo {}")
        _write_custom_css(tmp_path, "nord", ".bar {}")
        _write_custom_css(tmp_path, "dracula", "")  # delete dracula
        _, themes = _build_combined_css(tmp_path)
        assert "dracula" not in themes
        assert "nord" in themes
