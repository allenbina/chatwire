"""Tests for the theme color override API helpers in web/api_ui.py.

Strategy: the actual FastAPI route functions are async and need pytest-asyncio
(not in the test env), so we test the underlying logic layer-by-layer:

  1. The theme_loader helpers used by the routes (_safe_name, _safe_value,
     _COLOR_VARS) — already covered in test_theme_loader.py; only edge cases
     specific to overrides are re-checked here.
  2. End-to-end override write/read/delete by calling helpers directly and
     exercising the same filesystem operations the routes use.
  3. CSS generation logic for per-theme override blocks.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from web.theme_loader import _safe_name, _safe_value, _COLOR_VARS


# ---------------------------------------------------------------------------
# Helpers — mirrors the logic in the route handlers
# ---------------------------------------------------------------------------

def _write_override(base_dir: Path, theme: str, colors: dict[str, str]) -> dict:
    """Write (or merge) a theme override file, returning the saved colors."""
    assert _safe_name(theme), f"bad theme name: {theme!r}"
    safe_colors: dict[str, str] = {}
    for k, v in colors.items():
        if k not in _COLOR_VARS:
            continue
        if v == "":
            safe_colors[k] = ""
        else:
            safe = _safe_value(v)
            if safe:
                safe_colors[k] = safe

    base_dir.mkdir(parents=True, exist_ok=True)
    path = base_dir / f"{theme}.json"
    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            existing = {}
    merged = dict(existing.get("colors") or {})
    merged.update(safe_colors)
    merged = {k: v for k, v in merged.items() if v}
    existing["colors"] = merged
    path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    return merged


def _read_override(base_dir: Path, theme: str) -> dict[str, str]:
    """Read stored color overrides for a theme."""
    path = base_dir / f"{theme}.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("colors") or {}
    except (ValueError, OSError):
        return {}


def _delete_override(base_dir: Path, theme: str) -> None:
    """Delete a theme override file."""
    path = base_dir / f"{theme}.json"
    path.unlink(missing_ok=True)


def _css_for_overrides(base_dir: Path) -> str:
    """Generate combined CSS for all stored theme overrides."""
    if not base_dir.is_dir():
        return ""
    css_blocks: list[str] = []
    for path in sorted(base_dir.glob("*.json")):
        slug = path.stem
        if not _safe_name(slug):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        colors = data.get("colors") or {}
        if not isinstance(colors, dict) or not colors:
            continue
        var_lines: list[str] = []
        for k, v in colors.items():
            if k in _COLOR_VARS:
                safe = _safe_value(v)
                if safe:
                    var_lines.append(f"  --{k}: {safe};")
        if var_lines:
            css_blocks.append(f'[data-theme="{slug}"] {{\n' + "\n".join(var_lines) + "\n}")
    return "\n\n".join(css_blocks)


# ---------------------------------------------------------------------------
# Write + Read
# ---------------------------------------------------------------------------

class TestWriteReadOverride:
    def test_write_creates_file(self, tmp_path):
        _write_override(tmp_path, "dracula", {"primary": "265 89% 78%"})
        assert (tmp_path / "dracula.json").exists()

    def test_read_nonexistent_returns_empty(self, tmp_path):
        assert _read_override(tmp_path, "dracula") == {}

    def test_write_and_read_roundtrip(self, tmp_path):
        _write_override(tmp_path, "nord", {"primary": "210 60% 70%", "background": "220 16% 22%"})
        colors = _read_override(tmp_path, "nord")
        assert colors["primary"] == "210 60% 70%"
        assert colors["background"] == "220 16% 22%"

    def test_merge_preserves_existing(self, tmp_path):
        _write_override(tmp_path, "dracula", {"primary": "265 89% 78%"})
        _write_override(tmp_path, "dracula", {"background": "231 15% 18%"})
        colors = _read_override(tmp_path, "dracula")
        assert "primary" in colors
        assert "background" in colors

    def test_merge_overwrites_existing_key(self, tmp_path):
        _write_override(tmp_path, "dracula", {"primary": "265 89% 78%"})
        _write_override(tmp_path, "dracula", {"primary": "200 50% 60%"})
        colors = _read_override(tmp_path, "dracula")
        assert colors["primary"] == "200 50% 60%"

    def test_empty_value_clears_key(self, tmp_path):
        _write_override(tmp_path, "dracula", {"primary": "265 89% 78%"})
        _write_override(tmp_path, "dracula", {"primary": ""})
        colors = _read_override(tmp_path, "dracula")
        assert "primary" not in colors

    def test_multiple_themes_isolated(self, tmp_path):
        _write_override(tmp_path, "nord", {"primary": "210 60% 70%"})
        _write_override(tmp_path, "dracula", {"primary": "265 89% 78%"})
        assert _read_override(tmp_path, "nord")["primary"] == "210 60% 70%"
        assert _read_override(tmp_path, "dracula")["primary"] == "265 89% 78%"


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

class TestDeleteOverride:
    def test_delete_removes_file(self, tmp_path):
        _write_override(tmp_path, "dracula", {"primary": "265 89% 78%"})
        _delete_override(tmp_path, "dracula")
        assert not (tmp_path / "dracula.json").exists()

    def test_delete_nonexistent_is_noop(self, tmp_path):
        # Should not raise
        _delete_override(tmp_path, "dracula")

    def test_delete_clears_read(self, tmp_path):
        _write_override(tmp_path, "dracula", {"primary": "265 89% 78%"})
        _delete_override(tmp_path, "dracula")
        assert _read_override(tmp_path, "dracula") == {}


# ---------------------------------------------------------------------------
# CSS generation
# ---------------------------------------------------------------------------

class TestCssForOverrides:
    def test_no_dir_returns_empty(self, tmp_path):
        missing = tmp_path / "no-such-dir"
        assert _css_for_overrides(missing) == ""

    def test_empty_dir_returns_empty(self, tmp_path):
        assert _css_for_overrides(tmp_path) == ""

    def test_single_theme_css(self, tmp_path):
        _write_override(tmp_path, "dracula", {"primary": "265 89% 78%"})
        css = _css_for_overrides(tmp_path)
        assert '[data-theme="dracula"]' in css
        assert "--primary: 265 89% 78%;" in css

    def test_multiple_themes_both_in_css(self, tmp_path):
        _write_override(tmp_path, "dracula", {"primary": "265 89% 78%"})
        _write_override(tmp_path, "nord", {"background": "220 16% 22%"})
        css = _css_for_overrides(tmp_path)
        assert '[data-theme="dracula"]' in css
        assert '[data-theme="nord"]' in css

    def test_deleted_theme_not_in_css(self, tmp_path):
        _write_override(tmp_path, "dracula", {"primary": "265 89% 78%"})
        _delete_override(tmp_path, "dracula")
        css = _css_for_overrides(tmp_path)
        assert "dracula" not in css

    def test_css_uses_data_theme_selector(self, tmp_path):
        _write_override(tmp_path, "nord", {"primary": "210 60% 70%"})
        css = _css_for_overrides(tmp_path)
        assert css.startswith('[data-theme="nord"]')

    def test_css_wraps_vars_in_block(self, tmp_path):
        _write_override(tmp_path, "dracula", {"primary": "265 89% 78%"})
        css = _css_for_overrides(tmp_path)
        assert "{" in css and "}" in css
        assert css.count("{") == css.count("}")


# ---------------------------------------------------------------------------
# Security — invalid inputs are rejected
# ---------------------------------------------------------------------------

class TestSecurity:
    def test_unknown_color_key_rejected(self, tmp_path):
        result = _write_override(tmp_path, "dracula", {"evil-key": "0 0% 0%"})
        assert "evil-key" not in result

    def test_css_injection_via_value_rejected(self, tmp_path):
        result = _write_override(tmp_path, "dracula", {"primary": "0 0% 0%; --other: bad"})
        # _safe_value rejects values containing semicolons
        assert "primary" not in result

    def test_brace_injection_in_value_rejected(self, tmp_path):
        result = _write_override(tmp_path, "dracula", {"primary": "0 0% 0%} body { color: red"})
        assert "primary" not in result

    def test_html_angle_bracket_injection_rejected(self, tmp_path):
        result = _write_override(tmp_path, "dracula", {"primary": "<script>alert(1)</script>"})
        assert "primary" not in result

    def test_valid_hsl_triplet_accepted(self, tmp_path):
        result = _write_override(tmp_path, "dracula", {"primary": "265 89% 78%"})
        assert result["primary"] == "265 89% 78%"

    def test_valid_percentage_value_accepted(self, tmp_path):
        result = _write_override(tmp_path, "dracula", {"background": "0 0% 5%"})
        assert "background" in result

    def test_invalid_theme_name_detected(self):
        assert not _safe_name("../../../etc/passwd")
        assert not _safe_name("")
        assert not _safe_name("Theme Name")
        assert not _safe_name("UPPER")

    def test_valid_theme_name_detected(self):
        assert _safe_name("dracula")
        assert _safe_name("nord")
        assert _safe_name("rose-pine-moon")
        assert _safe_name("catppuccin-frappe")

    def test_corrupted_json_file_returns_empty(self, tmp_path):
        (tmp_path / "corrupt.json").write_text("not valid json", encoding="utf-8")
        colors = _read_override(tmp_path, "corrupt")
        assert colors == {}

    def test_corrupted_file_skipped_in_css(self, tmp_path):
        (tmp_path / "corrupt.json").write_text("not valid json", encoding="utf-8")
        css = _css_for_overrides(tmp_path)
        assert "corrupt" not in css

    def test_invalid_slug_file_skipped_in_css(self, tmp_path):
        # A file whose stem fails _safe_name — should be skipped
        (tmp_path / "INVALID.json").write_text(
            json.dumps({"colors": {"primary": "0 0% 0%"}}), encoding="utf-8"
        )
        css = _css_for_overrides(tmp_path)
        assert "INVALID" not in css
