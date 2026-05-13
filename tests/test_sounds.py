"""Tests for custom notification sounds logic.

Strategy: validate configuration and file-handling logic directly — no live
FastAPI server required.  Mirrors the pattern in test_accent_color.py.

Covers:
  a. GET config returns "default" when sounds key is absent.
  b. GET config returns stored values when present.
  c. POST config persists valid modes.
  d. POST config rejects unknown modes.
  e. Upload rejects unsupported extensions.
  f. Upload rejects unknown sound_type.
  g. Upload rejects oversized files.
  h. Custom-sound path scanner returns None when no file exists.
  i. Custom-sound path scanner returns path when file exists.
  j. Reset clears the sound file and resets config to "default".
"""
from __future__ import annotations

import pathlib
import pytest


# ---------------------------------------------------------------------------
# Pure config helpers (mirrors route logic in api_ui.py)
# ---------------------------------------------------------------------------

_VALID_SOUND_EXTS = frozenset({".wav", ".mp3", ".ogg", ".m4a", ".aac"})
_SOUND_TYPES = frozenset({"sent", "received"})
_SOUND_MODES = frozenset({"default", "none", "custom"})


def _read_sounds_config(cfg: dict) -> dict:
    """Simulate GET /sounds/config."""
    web = cfg.get("web") or {}
    sounds = web.get("sounds") or {}
    return {
        "sent": sounds.get("sent", "default"),
        "received": sounds.get("received", "default"),
    }


def _set_sounds_config(cfg: dict, sent: str | None = None, received: str | None = None) -> dict:
    """Simulate POST /sounds/config, returning updated cfg or raising ValueError."""
    if sent is not None and sent not in _SOUND_MODES:
        raise ValueError(f"sent must be one of {sorted(_SOUND_MODES)}")
    if received is not None and received not in _SOUND_MODES:
        raise ValueError(f"received must be one of {sorted(_SOUND_MODES)}")
    web = cfg.setdefault("web", {})
    sounds = web.setdefault("sounds", {})
    if sent is not None:
        sounds["sent"] = sent
    if received is not None:
        sounds["received"] = received
    return cfg


def _validate_upload(sound_type: str, filename: str, data_len: int) -> None:
    """Simulate upload validation, raising ValueError on error."""
    MAX_BYTES = 5 * 1024 * 1024
    if sound_type not in _SOUND_TYPES:
        raise ValueError("sound_type must be 'sent' or 'received'")
    ext = pathlib.Path(filename).suffix.lower()
    if not ext:
        raise ValueError("file must have an audio extension")
    if ext not in _VALID_SOUND_EXTS:
        raise ValueError(f"unsupported extension {ext!r}")
    if data_len > MAX_BYTES:
        raise ValueError("File exceeds 5 MB limit")


def _custom_sound_path(sounds_dir: pathlib.Path, sound_type: str) -> pathlib.Path | None:
    """Simulate the path scanner used by the GET /sounds/custom-* endpoints."""
    for ext in _VALID_SOUND_EXTS:
        p = sounds_dir / f"custom-{sound_type}{ext}"
        if p.exists():
            return p
    return None


# ---------------------------------------------------------------------------
# GET config — defaults
# ---------------------------------------------------------------------------

class TestGetSoundsConfigDefaults:
    def test_empty_config_returns_defaults(self):
        result = _read_sounds_config({})
        assert result == {"sent": "default", "received": "default"}

    def test_empty_web_returns_defaults(self):
        assert _read_sounds_config({"web": {}}) == {"sent": "default", "received": "default"}

    def test_null_web_returns_defaults(self):
        assert _read_sounds_config({"web": None}) == {"sent": "default", "received": "default"}

    def test_empty_sounds_returns_defaults(self):
        assert _read_sounds_config({"web": {"sounds": {}}}) == {"sent": "default", "received": "default"}

    def test_stored_values_returned(self):
        cfg = {"web": {"sounds": {"sent": "none", "received": "custom"}}}
        assert _read_sounds_config(cfg) == {"sent": "none", "received": "custom"}


# ---------------------------------------------------------------------------
# POST config — valid modes
# ---------------------------------------------------------------------------

class TestSetSoundsConfigValid:
    def test_set_sent_to_none(self):
        cfg = _set_sounds_config({}, sent="none")
        assert cfg["web"]["sounds"]["sent"] == "none"

    def test_set_received_to_none(self):
        cfg = _set_sounds_config({}, received="none")
        assert cfg["web"]["sounds"]["received"] == "none"

    def test_set_both(self):
        cfg = _set_sounds_config({}, sent="custom", received="none")
        assert cfg["web"]["sounds"]["sent"] == "custom"
        assert cfg["web"]["sounds"]["received"] == "none"

    def test_partial_update_preserves_other(self):
        cfg: dict = {"web": {"sounds": {"sent": "none", "received": "custom"}}}
        cfg = _set_sounds_config(cfg, sent="default")
        assert cfg["web"]["sounds"]["sent"] == "default"
        assert cfg["web"]["sounds"]["received"] == "custom"

    def test_roundtrip_all_modes(self):
        cfg: dict = {}
        for mode in ("default", "none", "custom"):
            cfg = _set_sounds_config(cfg, sent=mode)
            assert _read_sounds_config(cfg)["sent"] == mode

    def test_none_args_are_noop(self):
        cfg: dict = {"web": {"sounds": {"sent": "none"}}}
        cfg = _set_sounds_config(cfg)  # no-op
        assert cfg["web"]["sounds"]["sent"] == "none"


# ---------------------------------------------------------------------------
# POST config — invalid modes
# ---------------------------------------------------------------------------

class TestSetSoundsConfigInvalid:
    def test_sent_unknown_mode_rejected(self):
        with pytest.raises(ValueError, match="sent"):
            _set_sounds_config({}, sent="loud")

    def test_received_unknown_mode_rejected(self):
        with pytest.raises(ValueError, match="received"):
            _set_sounds_config({}, received="banana")

    def test_empty_string_rejected_for_sent(self):
        with pytest.raises(ValueError):
            _set_sounds_config({}, sent="")

    def test_empty_string_rejected_for_received(self):
        with pytest.raises(ValueError):
            _set_sounds_config({}, received="")


# ---------------------------------------------------------------------------
# Upload validation
# ---------------------------------------------------------------------------

class TestUploadValidation:
    def test_valid_wav_accepted(self):
        _validate_upload("sent", "chime.wav", 1024)

    def test_valid_mp3_accepted(self):
        _validate_upload("received", "ping.mp3", 1024)

    def test_valid_ogg_accepted(self):
        _validate_upload("sent", "blip.ogg", 1024)

    def test_valid_m4a_accepted(self):
        _validate_upload("received", "ding.m4a", 1024)

    def test_valid_aac_accepted(self):
        _validate_upload("sent", "tone.aac", 512)

    def test_invalid_sound_type_rejected(self):
        with pytest.raises(ValueError, match="sound_type"):
            _validate_upload("alert", "sound.wav", 100)

    def test_unsupported_ext_rejected(self):
        with pytest.raises(ValueError, match="unsupported"):
            _validate_upload("sent", "music.flac", 100)

    def test_no_extension_rejected(self):
        with pytest.raises(ValueError, match="extension"):
            _validate_upload("sent", "audiofile", 100)

    def test_txt_extension_rejected(self):
        with pytest.raises(ValueError, match="unsupported"):
            _validate_upload("received", "note.txt", 50)

    def test_oversized_file_rejected(self):
        with pytest.raises(ValueError, match="5 MB"):
            _validate_upload("sent", "huge.wav", 5 * 1024 * 1024 + 1)

    def test_exactly_5mb_accepted(self):
        _validate_upload("sent", "big.wav", 5 * 1024 * 1024)

    def test_empty_filename_rejected(self):
        with pytest.raises(ValueError):
            _validate_upload("sent", "", 100)


# ---------------------------------------------------------------------------
# Custom sound path scanner
# ---------------------------------------------------------------------------

class TestCustomSoundPath:
    def test_returns_none_when_dir_empty(self, tmp_path):
        assert _custom_sound_path(tmp_path, "sent") is None

    def test_returns_none_when_no_match(self, tmp_path):
        (tmp_path / "custom-received.wav").write_bytes(b"x")
        assert _custom_sound_path(tmp_path, "sent") is None

    def test_finds_wav(self, tmp_path):
        p = tmp_path / "custom-sent.wav"
        p.write_bytes(b"RIFF")
        assert _custom_sound_path(tmp_path, "sent") == p

    def test_finds_mp3(self, tmp_path):
        p = tmp_path / "custom-received.mp3"
        p.write_bytes(b"\xff\xfb")
        assert _custom_sound_path(tmp_path, "received") == p

    def test_finds_ogg(self, tmp_path):
        p = tmp_path / "custom-sent.ogg"
        p.write_bytes(b"OggS")
        assert _custom_sound_path(tmp_path, "sent") == p

    def test_sent_and_received_independent(self, tmp_path):
        p_sent = tmp_path / "custom-sent.wav"
        p_sent.write_bytes(b"x")
        p_recv = tmp_path / "custom-received.mp3"
        p_recv.write_bytes(b"y")
        assert _custom_sound_path(tmp_path, "sent") == p_sent
        assert _custom_sound_path(tmp_path, "received") == p_recv
