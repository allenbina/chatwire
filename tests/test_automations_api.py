"""Tests for automation rule CRUD endpoints in web/api_v1.py.

Uses the same minimal-FastAPI-app pattern as test_api_v1.py so that
web/main.py's side-effectful imports are never triggered.

All config I/O (_load_rules / _save_rules) is patched at the module level
so tests run in-process without touching the filesystem.
"""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import web.api_v1 as _mod
from web.api_v1 import router as api_router

# ---------------------------------------------------------------------------
# Test app & client
# ---------------------------------------------------------------------------

_test_app = FastAPI()
_test_app.include_router(api_router)
client = TestClient(_test_app, raise_server_exceptions=False)

_PLAIN_KEY = "test-automations-key-deadbeef0123456789"
_KEY_HASH = hashlib.sha256(_PLAIN_KEY.encode()).hexdigest()
_AUTH = {"X-API-Key": _PLAIN_KEY}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_RULE = {
    "name": "greeting",
    "trigger": {"type": "text_contains", "pattern": "hello"},
    "actions": [{"type": "reply", "text": "Hi {name}!"}],
}

SAMPLE_RULE_2 = {
    "name": "farewell",
    "trigger": {"type": "text_exact", "pattern": "bye"},
    "actions": [{"type": "log", "message": "farewell from {handle}"}],
}


@contextmanager
def _rule_store(initial=None):
    """Patch _load_rules / _save_rules with an in-memory list."""
    store = list(initial or [])

    def _load():
        return list(store)

    def _save(rules):
        store.clear()
        store.extend(rules)

    # Nested with statements for Python 3.8 compatibility (no parenthesized form).
    with patch.object(_mod, "_load_rules", _load):
        with patch.object(_mod, "_save_rules", _save):
            with patch.object(_mod, "_api_key_hash", return_value=_KEY_HASH):
                yield store


# ---------------------------------------------------------------------------
# GET /automations
# ---------------------------------------------------------------------------

class TestAutomationsList:
    def test_empty_list(self):
        with _rule_store([]):
            r = client.get("/automations", headers=_AUTH)
        assert r.status_code == 200
        assert r.json() == {"rules": []}

    def test_returns_existing_rules(self):
        with _rule_store([SAMPLE_RULE]):
            r = client.get("/automations", headers=_AUTH)
        assert r.status_code == 200
        assert r.json()["rules"] == [SAMPLE_RULE]

    def test_requires_api_key(self):
        with _rule_store([]):
            r = client.get("/automations")
        assert r.status_code == 401

    def test_returns_multiple_rules(self):
        with _rule_store([SAMPLE_RULE, SAMPLE_RULE_2]):
            r = client.get("/automations", headers=_AUTH)
        data = r.json()
        assert r.status_code == 200
        assert len(data["rules"]) == 2
        assert data["rules"][0]["name"] == "greeting"
        assert data["rules"][1]["name"] == "farewell"


# ---------------------------------------------------------------------------
# POST /automations
# ---------------------------------------------------------------------------

class TestAutomationsCreate:
    def test_creates_rule(self):
        with _rule_store() as store:
            r = client.post("/automations", json=SAMPLE_RULE, headers=_AUTH)
            assert r.status_code == 200
            body = r.json()
            assert body["ok"] is True
            assert body["index"] == 0
            assert len(store) == 1
            assert store[0]["name"] == "greeting"

    def test_appends_to_existing(self):
        with _rule_store([SAMPLE_RULE]) as store:
            r = client.post("/automations", json=SAMPLE_RULE_2, headers=_AUTH)
            assert r.status_code == 200
            assert r.json()["index"] == 1
            assert len(store) == 2

    def test_missing_name_returns_400(self):
        bad = {**SAMPLE_RULE, "name": ""}
        with _rule_store():
            r = client.post("/automations", json=bad, headers=_AUTH)
        assert r.status_code == 400

    def test_missing_trigger_returns_400(self):
        bad = {"name": "x", "actions": []}
        with _rule_store():
            r = client.post("/automations", json=bad, headers=_AUTH)
        assert r.status_code == 400

    def test_missing_trigger_type_returns_400(self):
        bad = {"name": "x", "trigger": {"pattern": "hi"}, "actions": []}
        with _rule_store():
            r = client.post("/automations", json=bad, headers=_AUTH)
        assert r.status_code == 400

    def test_invalid_trigger_type_returns_400(self):
        bad = {"name": "x", "trigger": {"type": "on_send"}, "actions": []}
        with _rule_store():
            r = client.post("/automations", json=bad, headers=_AUTH)
        assert r.status_code == 400

    def test_actions_not_list_returns_400(self):
        bad = {"name": "x", "trigger": {"type": "always"}, "actions": "reply"}
        with _rule_store():
            r = client.post("/automations", json=bad, headers=_AUTH)
        assert r.status_code == 400

    def test_non_object_body_returns_400(self):
        with _rule_store():
            r = client.post("/automations", json=[SAMPLE_RULE], headers=_AUTH)
        assert r.status_code == 400

    def test_requires_api_key(self):
        with _rule_store():
            r = client.post("/automations", json=SAMPLE_RULE)
        assert r.status_code == 401

    def test_all_trigger_types_accepted(self):
        for tt in ("text_exact", "text_contains", "text_regex", "always"):
            rule = {"name": f"r_{tt}", "trigger": {"type": tt, "pattern": "x"}, "actions": []}
            with _rule_store():
                r = client.post("/automations", json=rule, headers=_AUTH)
            assert r.status_code == 200, f"trigger type {tt!r} rejected: {r.json()}"


# ---------------------------------------------------------------------------
# PUT /automations/{rule_index}
# ---------------------------------------------------------------------------

class TestAutomationsUpdate:
    def test_updates_rule(self):
        updated = {**SAMPLE_RULE, "name": "greeting-v2"}
        with _rule_store([SAMPLE_RULE]) as store:
            r = client.put("/automations/0", json=updated, headers=_AUTH)
            assert r.status_code == 200
            assert r.json()["ok"] is True
            assert store[0]["name"] == "greeting-v2"

    def test_updates_second_rule(self):
        updated = {**SAMPLE_RULE_2, "name": "farewell-v2"}
        with _rule_store([SAMPLE_RULE, SAMPLE_RULE_2]) as store:
            r = client.put("/automations/1", json=updated, headers=_AUTH)
            assert r.status_code == 200
            assert store[1]["name"] == "farewell-v2"
            assert store[0]["name"] == "greeting"  # untouched

    def test_out_of_bounds_returns_404(self):
        with _rule_store([SAMPLE_RULE]):
            r = client.put("/automations/5", json=SAMPLE_RULE, headers=_AUTH)
        assert r.status_code == 404

    def test_negative_index_returns_404(self):
        with _rule_store([SAMPLE_RULE]):
            r = client.put("/automations/-1", json=SAMPLE_RULE, headers=_AUTH)
        assert r.status_code == 404

    def test_empty_store_returns_404(self):
        with _rule_store():
            r = client.put("/automations/0", json=SAMPLE_RULE, headers=_AUTH)
        assert r.status_code == 404

    def test_non_object_body_returns_400(self):
        with _rule_store([SAMPLE_RULE]):
            r = client.put("/automations/0", json="bad", headers=_AUTH)
        assert r.status_code == 400

    def test_requires_api_key(self):
        with _rule_store([SAMPLE_RULE]):
            r = client.put("/automations/0", json=SAMPLE_RULE)
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /automations/{rule_index}
# ---------------------------------------------------------------------------

class TestAutomationsDelete:
    def test_deletes_rule(self):
        with _rule_store([SAMPLE_RULE]) as store:
            r = client.delete("/automations/0", headers=_AUTH)
            assert r.status_code == 200
            assert r.json()["ok"] is True
            assert len(store) == 0

    def test_deletes_correct_rule(self):
        with _rule_store([SAMPLE_RULE, SAMPLE_RULE_2]) as store:
            r = client.delete("/automations/0", headers=_AUTH)
            assert r.status_code == 200
            assert len(store) == 1
            assert store[0]["name"] == "farewell"

    def test_deletes_last_rule(self):
        with _rule_store([SAMPLE_RULE, SAMPLE_RULE_2]) as store:
            r = client.delete("/automations/1", headers=_AUTH)
            assert r.status_code == 200
            assert len(store) == 1
            assert store[0]["name"] == "greeting"

    def test_out_of_bounds_returns_404(self):
        with _rule_store([SAMPLE_RULE]):
            r = client.delete("/automations/1", headers=_AUTH)
        assert r.status_code == 404

    def test_negative_index_returns_404(self):
        with _rule_store([SAMPLE_RULE]):
            r = client.delete("/automations/-1", headers=_AUTH)
        assert r.status_code == 404

    def test_empty_store_returns_404(self):
        with _rule_store():
            r = client.delete("/automations/0", headers=_AUTH)
        assert r.status_code == 404

    def test_requires_api_key(self):
        with _rule_store([SAMPLE_RULE]):
            r = client.delete("/automations/0")
        assert r.status_code == 401

    def test_sequential_deletes(self):
        with _rule_store([SAMPLE_RULE, SAMPLE_RULE_2]) as store:
            r1 = client.delete("/automations/0", headers=_AUTH)
            assert r1.status_code == 200
            assert len(store) == 1
            r2 = client.delete("/automations/0", headers=_AUTH)
            assert r2.status_code == 200
            assert len(store) == 0


# ---------------------------------------------------------------------------
# Full CRUD round-trip
# ---------------------------------------------------------------------------

class TestAutomationsCrudRoundTrip:
    def test_create_read_update_delete(self):
        with _rule_store() as store:
            # Create
            r = client.post("/automations", json=SAMPLE_RULE, headers=_AUTH)
            assert r.status_code == 200
            assert r.json()["index"] == 0

            # Read
            r = client.get("/automations", headers=_AUTH)
            assert r.json()["rules"][0]["name"] == "greeting"

            # Update
            updated = {**SAMPLE_RULE, "name": "greeting-updated"}
            r = client.put("/automations/0", json=updated, headers=_AUTH)
            assert r.status_code == 200

            # Read again
            r = client.get("/automations", headers=_AUTH)
            assert r.json()["rules"][0]["name"] == "greeting-updated"

            # Delete
            r = client.delete("/automations/0", headers=_AUTH)
            assert r.status_code == 200

            # Empty
            r = client.get("/automations", headers=_AUTH)
            assert r.json()["rules"] == []
            assert len(store) == 0
