"""Tests for the theme skin ZIP download/upload helpers (api_ui.py).

Strategy: same as test_theme_override.py — the FastAPI route functions are
async and require pytest-asyncio (not installed), so we test the underlying
logic layer-by-layer using plain helper functions that mirror the route code.

  1. ZIP construction — builds a valid ZIP with override.json + manifest.json.
  2. ZIP parsing — extracts and validates the override.json payload.
  3. Roundtrip — build then parse produces the original colors.
  4. Error cases — bad ZIP, missing file, invalid JSON, bad slug, unsafe values.
  5. Filesystem write — the parsed colors are persisted correctly.
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from web.theme_loader import _COLOR_VARS, _safe_name, _safe_value


# ---------------------------------------------------------------------------
# Helpers that mirror the route handler logic
# ---------------------------------------------------------------------------

_SKIN_MAX_BYTES = 256 * 1024  # 256 KB


def _build_skin_zip(theme: str, colors: dict[str, str]) -> bytes:
    """Build a skin ZIP bytes from a theme slug and color overrides dict."""
    override_payload = json.dumps({"theme": theme, "colors": colors}, indent=2)
    manifest_payload = json.dumps(
        {"theme": theme, "exported": "2026-01-01T00:00:00Z", "app": "chatwire"},
        indent=2,
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("override.json", override_payload)
        zf.writestr("manifest.json", manifest_payload)
    return buf.getvalue()


def _parse_skin_zip(content: bytes) -> tuple[str, dict[str, str]]:
    """Parse a skin ZIP, returning (theme_slug, safe_colors).

    Mirrors the validation logic in the upload route handler.
    Raises ValueError with a descriptive message on any error.
    """
    if len(content) > _SKIN_MAX_BYTES:
        raise ValueError(f"ZIP too large (max {_SKIN_MAX_BYTES // 1024} KB)")

    try:
        buf = io.BytesIO(content)
        with zipfile.ZipFile(buf, "r") as zf:
            if "override.json" not in zf.namelist():
                raise ValueError("ZIP is missing override.json")
            raw_bytes = zf.read("override.json")
    except zipfile.BadZipFile:
        raise ValueError("not a valid ZIP file")

    try:
        data = json.loads(raw_bytes.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise ValueError("override.json is not valid JSON")

    theme = data.get("theme", "")
    if not isinstance(theme, str) or not _safe_name(theme):
        raise ValueError("override.json has an invalid or missing 'theme' slug")

    colors_raw = data.get("colors") or {}
    if not isinstance(colors_raw, dict):
        raise ValueError("override.json 'colors' must be an object")

    safe_colors: dict[str, str] = {}
    for k, v in colors_raw.items():
        if not isinstance(k, str) or k not in _COLOR_VARS:
            continue
        if isinstance(v, str):
            safe = _safe_value(v)
            if safe:
                safe_colors[k] = safe

    return theme, safe_colors


def _save_skin(overrides_dir: Path, theme: str, colors: dict[str, str]) -> None:
    """Persist skin colors to the overrides directory (mirrors upload route)."""
    overrides_dir.mkdir(parents=True, exist_ok=True)
    dest = overrides_dir / f"{theme}.json"
    dest.write_text(
        json.dumps({"theme": theme, "colors": colors}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Tests — ZIP construction
# ---------------------------------------------------------------------------

class TestBuildSkinZip:
    def test_produces_valid_zip(self):
        data = _build_skin_zip("dracula", {"primary": "265 89% 78%"})
        assert zipfile.is_zipfile(io.BytesIO(data))

    def test_contains_override_and_manifest(self):
        data = _build_skin_zip("dracula", {})
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            assert "override.json" in zf.namelist()
            assert "manifest.json" in zf.namelist()

    def test_override_json_content(self):
        colors = {"primary": "265 89% 78%", "background": "230 15% 15%"}
        data = _build_skin_zip("dracula", colors)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            payload = json.loads(zf.read("override.json"))
        assert payload["theme"] == "dracula"
        assert payload["colors"] == colors

    def test_manifest_json_content(self):
        data = _build_skin_zip("nord", {})
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            manifest = json.loads(zf.read("manifest.json"))
        assert manifest["theme"] == "nord"
        assert manifest["app"] == "chatwire"
        assert "exported" in manifest

    def test_empty_colors_allowed(self):
        data = _build_skin_zip("dracula", {})
        _, colors = _parse_skin_zip(data)
        assert colors == {}


# ---------------------------------------------------------------------------
# Tests — ZIP parsing / validation
# ---------------------------------------------------------------------------

class TestParseSkinZip:
    def test_roundtrip_preserves_colors(self):
        original = {"primary": "265 89% 78%", "background": "230 15% 15%"}
        data = _build_skin_zip("dracula", original)
        theme, colors = _parse_skin_zip(data)
        assert theme == "dracula"
        assert colors == original

    def test_unknown_color_keys_dropped(self):
        data = _build_skin_zip("dracula", {"nonexistent-var": "100 50% 50%"})
        _, colors = _parse_skin_zip(data)
        assert "nonexistent-var" not in colors

    def test_unsafe_color_values_dropped(self):
        data = _build_skin_zip("dracula", {"primary": "{ evil: code }"})
        _, colors = _parse_skin_zip(data)
        assert "primary" not in colors

    def test_valid_hsl_values_kept(self):
        data = _build_skin_zip("nord", {"primary": "213 32% 52%"})
        _, colors = _parse_skin_zip(data)
        assert colors.get("primary") == "213 32% 52%"

    def test_not_a_zip_raises(self):
        with pytest.raises(ValueError, match="not a valid ZIP"):
            _parse_skin_zip(b"this is not a zip file")

    def test_missing_override_json_raises(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("manifest.json", '{"theme": "dracula"}')
        with pytest.raises(ValueError, match="missing override.json"):
            _parse_skin_zip(buf.getvalue())

    def test_invalid_json_in_override_raises(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("override.json", "NOT JSON {{{{")
        with pytest.raises(ValueError, match="not valid JSON"):
            _parse_skin_zip(buf.getvalue())

    def test_missing_theme_slug_raises(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("override.json", json.dumps({"colors": {}}))
        with pytest.raises(ValueError, match="invalid or missing 'theme' slug"):
            _parse_skin_zip(buf.getvalue())

    def test_invalid_theme_slug_raises(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("override.json", json.dumps({"theme": "INVALID SLUG!", "colors": {}}))
        with pytest.raises(ValueError, match="invalid or missing 'theme' slug"):
            _parse_skin_zip(buf.getvalue())

    def test_colors_not_dict_raises(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("override.json", json.dumps({"theme": "dracula", "colors": ["bad"]}))
        with pytest.raises(ValueError, match="'colors' must be an object"):
            _parse_skin_zip(buf.getvalue())

    def test_oversized_zip_raises(self):
        # Build a ZIP larger than the 256 KB limit by padding the raw bytes
        data = _build_skin_zip("dracula", {}) + b"\x00" * (_SKIN_MAX_BYTES + 1)
        with pytest.raises(ValueError, match="too large"):
            _parse_skin_zip(data)


# ---------------------------------------------------------------------------
# Tests — filesystem persistence
# ---------------------------------------------------------------------------

class TestSaveSkin:
    def test_writes_override_file(self, tmp_path):
        colors = {"primary": "213 32% 52%"}
        _save_skin(tmp_path, "nord", colors)
        dest = tmp_path / "nord.json"
        assert dest.exists()
        data = json.loads(dest.read_text())
        assert data["theme"] == "nord"
        assert data["colors"] == colors

    def test_overwrites_existing_file(self, tmp_path):
        _save_skin(tmp_path, "dracula", {"primary": "265 89% 78%"})
        _save_skin(tmp_path, "dracula", {"primary": "0 0% 100%"})
        data = json.loads((tmp_path / "dracula.json").read_text())
        assert data["colors"]["primary"] == "0 0% 100%"

    def test_creates_dir_if_missing(self, tmp_path):
        nested = tmp_path / "overrides" / "sub"
        _save_skin(nested, "nord", {})
        assert (nested / "nord.json").exists()


# ---------------------------------------------------------------------------
# Tests — full roundtrip (build → parse → save → read back)
# ---------------------------------------------------------------------------

class TestFullRoundtrip:
    def test_build_parse_save_readback(self, tmp_path):
        original = {
            "primary": "265 89% 78%",
            "background": "230 15% 15%",
            "foreground": "0 0% 95%",
        }
        zip_bytes = _build_skin_zip("dracula", original)
        theme, colors = _parse_skin_zip(zip_bytes)
        _save_skin(tmp_path, theme, colors)

        saved = json.loads((tmp_path / "dracula.json").read_text())
        assert saved["theme"] == "dracula"
        assert saved["colors"] == original

    def test_unknown_keys_stripped_on_roundtrip(self, tmp_path):
        dirty = {"primary": "265 89% 78%", "UNKNOWN_KEY": "bad value"}
        zip_bytes = _build_skin_zip("dracula", dirty)
        theme, colors = _parse_skin_zip(zip_bytes)
        _save_skin(tmp_path, theme, colors)

        saved = json.loads((tmp_path / "dracula.json").read_text())
        assert "UNKNOWN_KEY" not in saved["colors"]
        assert "primary" in saved["colors"]
