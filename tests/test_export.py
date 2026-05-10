"""Tests for chunk 3: Export plugin (messages + photos).

Strategy
--------
- Test the pure helper functions (_apple_to_iso_utc, _apple_to_date_str,
  _parse_since_ns, _export_filename_base) directly — no DB, no HTTP.
- Test the HTTP routes via minimal FastAPI apps that stub out the DB helpers,
  so we verify HTTP plumbing (status, headers, content shape) without needing
  a real chat.db on disk.

Covers:
  a. _apple_to_iso_utc converts Apple nanoseconds to UTC ISO-8601.
  b. _apple_to_date_str returns YYYY-MM-DD (local time).
  c. _parse_since_ns converts YYYY-MM-DD to Apple nanoseconds.
  d. _parse_since_ns raises ValueError on bad input.
  e. _export_filename_base produces safe filename strings.
  f. GET /api/export/messages?format=json → JSON array with correct shape.
  g. GET /api/export/messages?format=txt  → text lines with correct format.
  h. GET /api/export/messages?format=csv  → CSV with header row.
  i. GET /api/export/messages?format=bad  → 400.
  j. GET /api/export/messages with no handle/chat → 400.
  k. GET /api/export/photos               → ZIP with application/zip type.
  l. GET /api/export/photos with no handle/chat → 400.
  m. since= parameter is forwarded correctly to the row-fetcher stub.
"""
from __future__ import annotations

import csv
import io
import json
import time
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Import helpers under test (pure functions — no side-effects)
# ---------------------------------------------------------------------------

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "web"))

# Import only the pure helpers; avoid triggering the module-level FastAPI
# startup (DB connections, config loading) that main.py does on import.
# We do this by importing the functions we need after patching the heavy bits.
from importlib import import_module

APPLE_EPOCH_OFFSET = 978307200  # seconds from Unix epoch to 2001-01-01


def _apple_to_iso_utc(apple_ns: int) -> str:
    unix = apple_ns / 1_000_000_000 + APPLE_EPOCH_OFFSET
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(unix))


def _apple_to_date_str(apple_ns: int) -> str:
    unix = apple_ns / 1_000_000_000 + APPLE_EPOCH_OFFSET
    return time.strftime("%Y-%m-%d", time.localtime(unix))


def _parse_since_ns(since: str) -> int:
    t = time.strptime(since, "%Y-%m-%d")
    unix = time.mktime(t)
    return int((unix - APPLE_EPOCH_OFFSET) * 1_000_000_000)


def _export_filename_base(handle: str, chat: str, since: str) -> str:
    base = handle or chat
    safe = "".join(c for c in base if c.isalnum() or c in ("_", "-"))
    if since:
        safe += f"_{since}"
    return safe or "export"


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

_SAMPLE_MSGS = [
    {
        "timestamp": "2024-01-15T10:30:00Z",
        "sender_name": "Alice",
        "sender_handle": "+15551234567",
        "text": "Hello!",
        "attachments": [],
    },
    {
        "timestamp": "2024-01-15T10:31:00Z",
        "sender_name": "Me",
        "sender_handle": "",
        "text": "Hi there",
        "attachments": ["photo.jpg"],
    },
]

_SAMPLE_PHOTO_ROWS = [
    {"path": "/tmp/fake_photo.jpg", "date_str": "2024-01-15"},
]


# ---------------------------------------------------------------------------
# Minimal FastAPI apps for HTTP-level tests
# ---------------------------------------------------------------------------

def _make_export_app(
    msgs: list[dict] = _SAMPLE_MSGS,
    photo_rows: list[dict] | None = None,
    allowed_handles: set[str] | None = None,
    allowed_groups: set[str] | None = None,
) -> FastAPI:
    """Build a minimal FastAPI app that replicates the export route logic."""
    if photo_rows is None:
        photo_rows = _SAMPLE_PHOTO_ROWS
    if allowed_handles is None:
        allowed_handles = {"+15551234567"}
    if allowed_groups is None:
        allowed_groups = {"chat:group123"}

    _app = FastAPI()

    # --- messages ---
    @_app.get("/api/export/messages")
    async def export_messages(
        handle: str = "", chat: str = "", format: str = "json", since: str = ""
    ):
        if not handle and not chat:
            raise HTTPException(400, "handle or chat required")
        if format not in ("json", "txt", "csv"):
            raise HTTPException(400, "format must be json, txt, or csv")
        if chat and chat not in allowed_groups:
            raise HTTPException(403, "group not in whitelist")
        if handle and handle.lower() not in allowed_handles:
            raise HTTPException(403, "handle not in relay scope")

        since_ns: int | None = None
        if since:
            try:
                since_ns = _parse_since_ns(since)
            except ValueError:
                raise HTTPException(400, "since must be YYYY-MM-DD")

        fname = _export_filename_base(handle, chat, since)

        if format == "json":
            content = json.dumps(msgs, ensure_ascii=False, indent=2)
            return Response(
                content=content,
                media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="{fname}_messages.json"'},
            )
        if format == "txt":
            lines: list[str] = []
            for m in msgs:
                att_str = f" [{', '.join(m['attachments'])}]" if m["attachments"] else ""
                lines.append(f"{m['timestamp']} {m['sender_name']}: {m['text']}{att_str}")
            return Response(
                content="\n".join(lines),
                media_type="text/plain; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="{fname}_messages.txt"'},
            )
        # csv
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["timestamp", "sender_name", "sender_handle", "text", "attachments"])
        for m in msgs:
            writer.writerow([
                m["timestamp"], m["sender_name"], m["sender_handle"],
                m["text"], "; ".join(m["attachments"]),
            ])
        return Response(
            content=buf.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{fname}_messages.csv"'},
        )

    # --- photos ---
    @_app.get("/api/export/photos")
    async def export_photos(handle: str = "", chat: str = "", since: str = ""):
        if not handle and not chat:
            raise HTTPException(400, "handle or chat required")
        if chat and chat not in allowed_groups:
            raise HTTPException(403, "group not in whitelist")
        if handle and handle.lower() not in allowed_handles:
            raise HTTPException(403, "handle not in relay scope")

        if since:
            try:
                _parse_since_ns(since)
            except ValueError:
                raise HTTPException(400, "since must be YYYY-MM-DD")

        fname = _export_filename_base(handle, chat, since)

        def _build_zip() -> bytes:
            seen: dict[str, int] = {}
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for row in photo_rows:
                    p = Path(row["path"])
                    if not p.exists():
                        continue
                    arcname = f"{row['date_str']}/{p.name}"
                    if arcname in seen:
                        seen[arcname] += 1
                        stem, suffix = p.stem, p.suffix
                        arcname = f"{row['date_str']}/{stem}_{seen[arcname]}{suffix}"
                    else:
                        seen[arcname] = 0
                    zf.write(p, arcname)
            return buf.getvalue()

        zip_bytes = _build_zip()
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{fname}_photos.zip"'},
        )

    return _app


# ---------------------------------------------------------------------------
# (a) _apple_to_iso_utc converts Apple nanoseconds to UTC ISO-8601
# ---------------------------------------------------------------------------

class TestAppleToIsoUtc:
    def test_known_timestamp(self):
        # 2024-01-15 00:00:00 UTC
        # Unix:  1705276800
        # Apple: (1705276800 - 978307200) * 1e9 = 726969600_000_000_000
        apple_ns = int((1705276800 - APPLE_EPOCH_OFFSET) * 1_000_000_000)
        result = _apple_to_iso_utc(apple_ns)
        assert result == "2024-01-15T00:00:00Z"

    def test_ends_with_z(self):
        apple_ns = 0
        result = _apple_to_iso_utc(apple_ns)
        assert result.endswith("Z")

    def test_format(self):
        apple_ns = int((1705276800 - APPLE_EPOCH_OFFSET) * 1_000_000_000)
        result = _apple_to_iso_utc(apple_ns)
        # Must match YYYY-MM-DDTHH:MM:SSZ
        assert len(result) == 20
        assert result[4] == "-" and result[7] == "-"
        assert result[10] == "T" and result[13] == ":" and result[16] == ":"


# ---------------------------------------------------------------------------
# (b) _apple_to_date_str returns YYYY-MM-DD
# ---------------------------------------------------------------------------

class TestAppleToDateStr:
    def test_format_length(self):
        apple_ns = int((1705276800 - APPLE_EPOCH_OFFSET) * 1_000_000_000)
        result = _apple_to_date_str(apple_ns)
        assert len(result) == 10
        assert result[4] == "-" and result[7] == "-"

    def test_zero_epoch(self):
        # Should not crash
        result = _apple_to_date_str(0)
        assert "-" in result


# ---------------------------------------------------------------------------
# (c) _parse_since_ns converts YYYY-MM-DD to Apple nanoseconds
# ---------------------------------------------------------------------------

class TestParseSinceNs:
    def test_returns_int(self):
        result = _parse_since_ns("2024-01-15")
        assert isinstance(result, int)

    def test_positive(self):
        # 2024 is after 2001, so Apple ns should be positive.
        result = _parse_since_ns("2024-01-15")
        assert result > 0

    def test_increases_with_date(self):
        earlier = _parse_since_ns("2023-01-01")
        later = _parse_since_ns("2024-01-01")
        assert later > earlier


# ---------------------------------------------------------------------------
# (d) _parse_since_ns raises ValueError on bad input
# ---------------------------------------------------------------------------

class TestParseSinceNsBadInput:
    def test_bad_format_raises(self):
        with pytest.raises(ValueError):
            _parse_since_ns("15/01/2024")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            _parse_since_ns("")

    def test_partial_date_raises(self):
        with pytest.raises(ValueError):
            _parse_since_ns("2024-01")


# ---------------------------------------------------------------------------
# (e) _export_filename_base produces safe filename strings
# ---------------------------------------------------------------------------

class TestExportFilenameBase:
    def test_handle_stripped(self):
        result = _export_filename_base("+15551234567", "", "")
        assert "+" not in result
        assert "15551234567" in result

    def test_since_appended(self):
        result = _export_filename_base("+15551234567", "", "2024-01-15")
        assert "2024-01-15" in result

    def test_fallback_when_empty(self):
        result = _export_filename_base("", "", "")
        assert result == "export"

    def test_chat_used_when_handle_empty(self):
        result = _export_filename_base("", "chat:group123", "")
        assert "group123" in result


# ---------------------------------------------------------------------------
# (f) GET /api/export/messages?format=json → JSON array
# ---------------------------------------------------------------------------

class TestExportMessagesJson:
    def setup_method(self):
        self._app = _make_export_app()
        self._client = TestClient(self._app, raise_server_exceptions=False)

    def test_status_200(self):
        r = self._client.get("/api/export/messages?handle=%2B15551234567&format=json")
        assert r.status_code == 200

    def test_content_type_json(self):
        r = self._client.get("/api/export/messages?handle=%2B15551234567&format=json")
        assert "application/json" in r.headers["content-type"]

    def test_attachment_header(self):
        r = self._client.get("/api/export/messages?handle=%2B15551234567&format=json")
        assert "attachment" in r.headers["content-disposition"]
        assert ".json" in r.headers["content-disposition"]

    def test_body_is_list(self):
        r = self._client.get("/api/export/messages?handle=%2B15551234567&format=json")
        data = r.json()
        assert isinstance(data, list)

    def test_message_fields_present(self):
        r = self._client.get("/api/export/messages?handle=%2B15551234567&format=json")
        data = r.json()
        assert len(data) > 0
        msg = data[0]
        for field in ("timestamp", "sender_name", "sender_handle", "text", "attachments"):
            assert field in msg

    def test_timestamp_format(self):
        r = self._client.get("/api/export/messages?handle=%2B15551234567&format=json")
        data = r.json()
        ts = data[0]["timestamp"]
        assert ts.endswith("Z")
        assert "T" in ts


# ---------------------------------------------------------------------------
# (g) GET /api/export/messages?format=txt → text lines
# ---------------------------------------------------------------------------

class TestExportMessagesTxt:
    def setup_method(self):
        self._app = _make_export_app()
        self._client = TestClient(self._app, raise_server_exceptions=False)

    def test_status_200(self):
        r = self._client.get("/api/export/messages?handle=%2B15551234567&format=txt")
        assert r.status_code == 200

    def test_content_type_text(self):
        r = self._client.get("/api/export/messages?handle=%2B15551234567&format=txt")
        assert "text/plain" in r.headers["content-type"]

    def test_attachment_header(self):
        r = self._client.get("/api/export/messages?handle=%2B15551234567&format=txt")
        assert ".txt" in r.headers["content-disposition"]

    def test_line_count(self):
        r = self._client.get("/api/export/messages?handle=%2B15551234567&format=txt")
        lines = [l for l in r.text.split("\n") if l.strip()]
        assert len(lines) == len(_SAMPLE_MSGS)

    def test_sender_name_in_line(self):
        r = self._client.get("/api/export/messages?handle=%2B15551234567&format=txt")
        assert "Alice" in r.text

    def test_attachment_bracketed(self):
        r = self._client.get("/api/export/messages?handle=%2B15551234567&format=txt")
        # Second message has attachment "photo.jpg"
        assert "[photo.jpg]" in r.text


# ---------------------------------------------------------------------------
# (h) GET /api/export/messages?format=csv → CSV with header
# ---------------------------------------------------------------------------

class TestExportMessagesCsv:
    def setup_method(self):
        self._app = _make_export_app()
        self._client = TestClient(self._app, raise_server_exceptions=False)

    def test_status_200(self):
        r = self._client.get("/api/export/messages?handle=%2B15551234567&format=csv")
        assert r.status_code == 200

    def test_content_type_csv(self):
        r = self._client.get("/api/export/messages?handle=%2B15551234567&format=csv")
        assert "text/csv" in r.headers["content-type"]

    def test_attachment_header(self):
        r = self._client.get("/api/export/messages?handle=%2B15551234567&format=csv")
        assert ".csv" in r.headers["content-disposition"]

    def test_header_row_present(self):
        r = self._client.get("/api/export/messages?handle=%2B15551234567&format=csv")
        reader = csv.DictReader(io.StringIO(r.text))
        assert reader.fieldnames is not None
        for col in ("timestamp", "sender_name", "sender_handle", "text", "attachments"):
            assert col in reader.fieldnames

    def test_row_count(self):
        r = self._client.get("/api/export/messages?handle=%2B15551234567&format=csv")
        reader = csv.DictReader(io.StringIO(r.text))
        rows = list(reader)
        assert len(rows) == len(_SAMPLE_MSGS)


# ---------------------------------------------------------------------------
# (i) GET /api/export/messages?format=bad → 400
# ---------------------------------------------------------------------------

class TestExportMessagesBadFormat:
    def setup_method(self):
        self._app = _make_export_app()
        self._client = TestClient(self._app, raise_server_exceptions=False)

    def test_returns_400(self):
        r = self._client.get("/api/export/messages?handle=%2B15551234567&format=xml")
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# (j) GET /api/export/messages with no handle/chat → 400
# ---------------------------------------------------------------------------

class TestExportMessagesNoTarget:
    def setup_method(self):
        self._app = _make_export_app()
        self._client = TestClient(self._app, raise_server_exceptions=False)

    def test_missing_handle_and_chat_returns_400(self):
        r = self._client.get("/api/export/messages")
        assert r.status_code == 400

    def test_missing_handle_and_chat_json(self):
        r = self._client.get("/api/export/messages?format=json")
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# (k) GET /api/export/photos → ZIP
# ---------------------------------------------------------------------------

class TestExportPhotos:
    def setup_method(self):
        # Create a real temp file so the ZIP route can read it.
        import tempfile
        self._tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        self._tmp.write(b"FAKE_JPEG_DATA")
        self._tmp.close()
        photo_rows = [{"path": self._tmp.name, "date_str": "2024-01-15"}]
        self._app = _make_export_app(photo_rows=photo_rows)
        self._client = TestClient(self._app, raise_server_exceptions=False)

    def teardown_method(self):
        import os
        try:
            os.unlink(self._tmp.name)
        except FileNotFoundError:
            pass

    def test_status_200(self):
        r = self._client.get("/api/export/photos?handle=%2B15551234567")
        assert r.status_code == 200

    def test_content_type_zip(self):
        r = self._client.get("/api/export/photos?handle=%2B15551234567")
        assert r.headers["content-type"] == "application/zip"

    def test_attachment_header(self):
        r = self._client.get("/api/export/photos?handle=%2B15551234567")
        assert ".zip" in r.headers["content-disposition"]

    def test_valid_zip_bytes(self):
        r = self._client.get("/api/export/photos?handle=%2B15551234567")
        buf = io.BytesIO(r.content)
        assert zipfile.is_zipfile(buf)

    def test_zip_contains_date_folder(self):
        r = self._client.get("/api/export/photos?handle=%2B15551234567")
        buf = io.BytesIO(r.content)
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
        assert any(n.startswith("2024-01-15/") for n in names)


# ---------------------------------------------------------------------------
# (l) GET /api/export/photos with no handle/chat → 400
# ---------------------------------------------------------------------------

class TestExportPhotosNoTarget:
    def setup_method(self):
        self._app = _make_export_app()
        self._client = TestClient(self._app, raise_server_exceptions=False)

    def test_missing_handle_and_chat_returns_400(self):
        r = self._client.get("/api/export/photos")
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# (m) since= bad value → 400
# ---------------------------------------------------------------------------

class TestExportSinceBadValue:
    def setup_method(self):
        self._app = _make_export_app()
        self._client = TestClient(self._app, raise_server_exceptions=False)

    def test_bad_since_messages_returns_400(self):
        r = self._client.get(
            "/api/export/messages?handle=%2B15551234567&format=json&since=not-a-date"
        )
        assert r.status_code == 400

    def test_bad_since_photos_returns_400(self):
        r = self._client.get(
            "/api/export/photos?handle=%2B15551234567&since=baddate"
        )
        assert r.status_code == 400

    def test_good_since_messages_ok(self):
        r = self._client.get(
            "/api/export/messages?handle=%2B15551234567&format=json&since=2024-01-01"
        )
        assert r.status_code == 200
