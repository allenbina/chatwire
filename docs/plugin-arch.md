# chatwire plugin architecture

> Design sketch for extracting `integrations/telegram/` into an external
> pip-installable package, and for future third-party integrations.
> No code changes — this is a planning document only.

---

## 1. Current state

`integrations/telegram/` is a **built-in** integration: the bridge discovers
it by walking `integrations/` on startup (see `bridge._discover_integration_classes`).
The `chatwire.integrations` entry-point group already exists in `pyproject.toml`
with an empty body — it is ready to receive third-party plugins but currently
has no registrations.

The built-in Telegram module imports from three categories of the main package:

| Import | Module | Notes |
|---|---|---|
| `from prefix import …` | top-level `prefix.py` | relay prefix / reply routing |
| `from whitelist import …` | top-level `whitelist.py` | handle/group allow-list |
| `from integrations.base import …` | `integrations/base.py` | Protocol types |
| `from integrations.telegram._helpers import …` | helpers sub-module | pure helpers, no TG dep |

`python-telegram-bot` is currently in chatwire's **main** `dependencies` list.
Extracting Telegram means removing it from core and making it a dep of the
plugin package instead.

---

## 2. External plugin contract (already in place)

A third-party plugin declares one entry point in its own `pyproject.toml`:

```toml
[project.entry-points."chatwire.integrations"]
telegram = "chatwire_telegram:TelegramIntegration"
```

At startup, `bridge._discover_integration_classes` calls:

```python
importlib.metadata.entry_points(group="chatwire.integrations")
```

and loads every registered class.  The loaded class must satisfy the
`integrations.base.Integration` Protocol:

| Attribute / method | Type | Required |
|---|---|---|
| `NAME` | `str` | yes — stable key, matches config block name |
| `SETTINGS_SCHEMA` | `dict` | yes — JSON Schema; may be `{}` |
| `__init__(config: dict)` | constructor | yes |
| `async start(ctx: BridgeContext)` | coroutine | yes |
| `async stop()` | coroutine | yes |
| `async on_inbound(msg: InboundMessage)` | coroutine | yes |

The bridge validates `config[name]` against `SETTINGS_SCHEMA` at startup and
raises `SystemExit` with a human-readable message on schema mismatch — no
baffling runtime failures from misconfiguration.

Config opt-in: the class is only instantiated if `integrations.<name>.enabled: true`
is set in `config.json`.  A plugin installed but not configured is silently skipped.

---

## 3. The import problem

The Telegram integration imports `prefix` and `whitelist`, which are **flat
top-level modules** in the chatwire install (listed under `py-modules` in
`pyproject.toml`).  An external package can still import them after
`pip install chatwire` because `pip install chatwire` puts those modules on
`sys.path`.  They are part of the published wheel.

So imports like `from prefix import format_inbound` **work from an external
plugin** without any changes to chatwire core — as long as `chatwire` is an
install-time dependency of the plugin package.

The same is true for `integrations.base`: it ships inside the `integrations/`
package included in the chatwire wheel.

No API surface changes are needed in core to support the extraction.

---

## 4. Package layout options

### Option A: separate repo (recommended starting point)

```
github.com/allenbina/chatwire-telegram/
  pyproject.toml
  chatwire_telegram/
    __init__.py          # exposes TelegramIntegration
    _helpers.py          # copied from integrations/telegram/_helpers.py
  tests/
    test_telegram_helpers.py
    test_telegram_integration.py
```

**Pro:** clean separation, own release cadence, own test suite.  
**Pro:** third-party authors can use this as a reference implementation.  
**Con:** two repos to maintain; changes that touch both core and Telegram
need coordinated releases.

### Option B: packages/ subdir in this repo (monorepo)

```
chatwire/
  integrations/telegram/   ← kept as built-in OR removed after plugin ships
  packages/
    chatwire-telegram/
      pyproject.toml
      chatwire_telegram/
        __init__.py
        _helpers.py
```

**Pro:** one repo, atomic commits across core + plugin.  
**Con:** setuptools doesn't handle subdirectory packages out of the box;
needs `pip install packages/chatwire-telegram` or a workspace tool (uv
workspaces, flit path deps).  Slightly messier CI.

**Recommendation:** start with Option A.  The Protocol surface is small and
stable (5 methods, 2 attributes).  A separate repo keeps the plugin dependency
graph clean and lets `chatwire` core remove `python-telegram-bot` from its
mandatory deps — a meaningful win for users who only want the web UI.

---

## 5. Core changes needed for extraction

| Change | Scope | Notes |
|---|---|---|
| Remove `python-telegram-bot` from `[project.dependencies]` | `pyproject.toml` | Move to `chatwire-telegram`'s deps |
| Remove `integrations/telegram/` from the repo | source tree | After plugin package is published and tested on mbair |
| No change to `integrations/base.py` | — | Protocol is already the right shape |
| No change to `bridge._discover_integration_classes` | — | Entry-point path already works |
| Update `SELF_HANDLES` / contacts access via `BridgeContext` | `integrations/base.py` | Telegram currently accesses `ctx.contacts` and `ctx.chatdb` as attributes; these should be exposed as typed Protocol methods so external plugins can rely on them without attribute hacks |

The last point is the only real API design work: `BridgeContext.contacts` and
`BridgeContext.chatdb` are accessed as bare attributes in the Telegram
implementation today.  Before extraction, either:

- Add `contacts` and `chatdb` as explicit Protocol members, or
- Add a `ctx.list_contacts() -> dict[str, str]` method + `ctx.list_groups()` method so the plugin doesn't reach into internals.

The method approach is cleaner (keeps `chatdb` as an internal detail).

---

## 6. BridgeContext extension (proposed)

Current `BridgeContext` Protocol (in `integrations/base.py`):

```python
async def send_text(target, body) -> SendOutcome
async def send_file(target, path) -> SendOutcome
def name_for(handle) -> str | None
def mirror(event, **fields) -> None
```

Additions needed for Telegram extraction:

```python
@property
def contacts(self) -> dict[str, str]:
    """handle (lowercased) → display name. Read-only snapshot."""
    ...

def reload_contacts(self) -> int:
    """Reload Contacts.app lookup; returns new handle count."""
    ...

def relay_scope(self) -> dict[str, set[str]]:
    """{'self': set, 'handles': set, 'groups': set} — live view."""
    ...

def list_groups(self) -> list[dict]:
    """chat.db group metadata: [{'guid', 'name', 'participants', ...}]."""
    ...

def services_for(self, handles: list[str]) -> dict[str, list[str]]:
    """iMessage/SMS capability per handle. Keys are lowercased."""
    ...

def outcomes_for(self, handles: list[str]) -> dict[str, object]:
    """Most-recent send outcome per handle from chat.db."""
    ...
```

`contacts`, `reload_contacts`, and `relay_scope` are already present on the
concrete `_BridgeCtx` in `bridge.py`; they just aren't declared in the Protocol.
`list_groups`, `services_for`, `outcomes_for` delegate to `self._chatdb`.

---

## 7. Concrete next steps (ordered)

1. **Add `contacts`, `reload_contacts`, `relay_scope`, `list_groups`,
   `services_for`, `outcomes_for` to `BridgeContext` Protocol** in
   `integrations/base.py`.  Verify `_BridgeCtx` in `bridge.py` already
   satisfies all of them (it should — just undeclared).

2. **Create `chatwire-telegram` repo** (Option A).  Copy
   `integrations/telegram/__init__.py` and `_helpers.py` into
   `chatwire_telegram/`.  Update imports:
   `from integrations.base import …` stays the same (chatwire is a dep).

3. **Update `pyproject.toml`** in `chatwire-telegram`:
   - `dependencies = ["chatwire>=0.7.0", "python-telegram-bot>=21.0,<22"]`
   - entry point: `telegram = "chatwire_telegram:TelegramIntegration"`

4. **Remove `python-telegram-bot`** from chatwire core `pyproject.toml`.
   Bump chatwire to `0.7.0` (minor bump — breaking for direct Telegram dep).

5. **Delete `integrations/telegram/`** from chatwire repo once the plugin
   package is tested on mbair.

6. **Update `tests/test_telegram_helpers.py`** — move it to the plugin repo.
   The tests import only `_helpers` which has no TG dependency, so they stay
   green anywhere; moving them removes the only reason chatwire's test suite
   needs the TG test surface.

7. **Publish `chatwire-telegram` to PyPI** and update mbair install:
   `pipx inject chatwire chatwire-telegram` (or install both separately if
   mbair uses a venv rather than pipx).

---

## 8. Decision checklist before starting

- [ ] Confirm `pipx inject` vs venv install path on mbair (affects step 7)
- [ ] Decide on version pinning strategy: `chatwire>=0.7.0` vs `~=0.7`
- [ ] Decide whether to publish `chatwire-telegram` to PyPI immediately or
      keep it as a local editable install during development
- [ ] Confirm `integrations/base.py` is stable enough to commit to as a
      public API surface (it is: Protocol hasn't changed since it shipped)
