"""Load handle -> display-name lookup from macOS AddressBook (Contacts.app).

Reads the per-source `AddressBook-v22.abcddb` files directly. Faster and more
reliable than scripting Contacts.app over Apple Events. Falls back to the
raw handle when no name is found.
"""
from __future__ import annotations

import glob
import logging
import re
import sqlite3
from pathlib import Path

from web import log_stream as _ls

log = logging.getLogger("contacts")

ADDRESSBOOK_GLOB = str(
    Path.home() / "Library" / "Application Support" / "AddressBook" / "Sources" / "*" / "AddressBook-v22.abcddb"
)


def _norm_phone(s: str | None) -> str | None:
    if not s:
        return None
    digits = re.sub(r"[^\d]", "", s)
    if not digits:
        return None
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    if len(digits) == 10:
        return "+1" + digits
    return "+" + digits


def _label(first: str | None, last: str | None, org: str | None) -> str:
    parts = [p for p in [first, last] if p]
    nm = " ".join(parts).strip()
    if not nm and org:
        nm = org
    return nm


def load_lookup() -> dict[str, str]:
    """Return {handle_lowercased: display_name}. Empty dict on failure."""
    _ls.info("contacts", "contact sync starting")
    out: dict[str, str] = {}
    try:
        dbs = glob.glob(ADDRESSBOOK_GLOB)
    except Exception:
        log.exception("AddressBook glob failed")
        return out

    for db in dbs:
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        except sqlite3.Error:
            log.warning("can't open AddressBook source %s", db)
            continue
        try:
            labels: dict[int, str] = {}
            for pk, first, last, org in conn.execute(
                "SELECT Z_PK, ZFIRSTNAME, ZLASTNAME, ZORGANIZATION FROM ZABCDRECORD"
            ):
                nm = _label(first, last, org)
                if nm:
                    labels[pk] = nm
            for owner, num in conn.execute(
                "SELECT ZOWNER, ZFULLNUMBER FROM ZABCDPHONENUMBER"
            ):
                nm = labels.get(owner)
                n = _norm_phone(num)
                if nm and n:
                    out.setdefault(n, nm)
            for owner, addr in conn.execute(
                "SELECT ZOWNER, ZADDRESS FROM ZABCDEMAILADDRESS"
            ):
                nm = labels.get(owner)
                if nm and addr:
                    out.setdefault(addr.lower(), nm)
        finally:
            conn.close()

    log.info("contacts lookup loaded: %d handles", len(out))
    _ls.info("contacts", f"contact sync complete — {len(out)} handles loaded")
    return out


def load_image_index() -> dict[str, tuple[str, int]]:
    """Return {handle_lowercased: (db_path, record_pk)} for contacts that have
    an image blob (ZIMAGEDATA or ZTHUMBNAILIMAGEDATA) in the AddressBook."""
    out: dict[str, tuple[str, int]] = {}
    try:
        dbs = glob.glob(ADDRESSBOOK_GLOB)
    except Exception:
        return out
    for db in dbs:
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        except sqlite3.Error:
            continue
        try:
            with_image: set[int] = set()
            for (pk,) in conn.execute(
                "SELECT Z_PK FROM ZABCDRECORD "
                "WHERE ZIMAGEDATA IS NOT NULL OR ZTHUMBNAILIMAGEDATA IS NOT NULL"
            ):
                with_image.add(pk)
            if not with_image:
                continue
            for owner, num in conn.execute(
                "SELECT ZOWNER, ZFULLNUMBER FROM ZABCDPHONENUMBER"
            ):
                if owner in with_image:
                    n = _norm_phone(num)
                    if n:
                        out.setdefault(n, (db, owner))
            for owner, addr in conn.execute(
                "SELECT ZOWNER, ZADDRESS FROM ZABCDEMAILADDRESS"
            ):
                if owner in with_image and addr:
                    out.setdefault(addr.lower(), (db, owner))
        finally:
            conn.close()
    log.info("contacts image index: %d handles with images", len(out))
    return out


def fetch_image(db_path: str, pk: int, prefer_thumb: bool = True) -> bytes | None:
    """Return raw JPEG bytes (with the 1-byte AddressBook prefix stripped) or None."""
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        cols = ("ZTHUMBNAILIMAGEDATA", "ZIMAGEDATA") if prefer_thumb else ("ZIMAGEDATA", "ZTHUMBNAILIMAGEDATA")
        for col in cols:
            row = conn.execute(f"SELECT {col} FROM ZABCDRECORD WHERE Z_PK = ?", (pk,)).fetchone()
            if row and row[0]:
                blob = bytes(row[0])
                # AddressBook prepends a single tag byte before the JPEG. Strip
                # leading 0x01 if the next bytes look like JPEG magic.
                if len(blob) > 4 and blob[0] == 0x01 and blob[1:4] == b"\xff\xd8\xff":
                    blob = blob[1:]
                return blob
    finally:
        conn.close()
    return None
