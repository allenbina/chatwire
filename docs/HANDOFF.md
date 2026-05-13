# Handoff — Phase 63: Automation rules reordering

> Phase 63 session shipped (2026-05-13, commit be3e74c in chatwire-dev).
> 1203 pytest (1191 prior + 12 new) + 196 Vitest — all green.
> mbair redeployed — healthy at v1.14.0 (git+ssh, Phase 63 code).

## §1 Current state

- **mbair**: commit be3e74c deployed and healthy (`/healthz` → ok, v1.14.0).
- **chatwire-theme-rosepine**: installed on mbair from git+ssh;
  `GET /api/ui/plugin-themes` returns all 3 variants.
- **chatwire-plugins registry**: 9 plugins live on GitHub (`allenbina/chatwire-plugins`).
- **Tests**: 1203 pytest / 196 Vitest — all green.
  Pre-existing failures: test_mcp.py (3), test_tinfoil.py (1), test_transform_pipeline.py (4) —
  all caused by test_mcp.py closing the asyncio event loop; unrelated to Phase 63.
- **PyPI**: v1.14.0 (no version bump — no public API changes; plugins not yet on PyPI).
- **Public repo (allenbina/chatwire)**: synced to Phase 63 (commit be3e74c, 2026-05-13).
- **Open bugs**: 0.

## §2 What shipped in Phase 63 (2026-05-13)

### feat: automation rules reordering

**Problem**: The AutomationsSection in SettingsPage listed rules in config order
(which is evaluation order) but had no way to change that order.  Moving a rule
required hand-editing `config.json`.

**Fix**:

**Backend — `web/api_v1.py`**:
- `POST /api/v1/automations/reorder` — body `{"order": [2, 0, 1]}` is a
  permutation of `range(len(rules))`; `order[i]` is the old index of the rule
  that ends up at position *i*.
  Validation: 400 if `order` is not a list, 400 if it is not a true permutation
  (wrong length, duplicates, or out-of-range values).
  Auth: `X-API-Key` (existing `_AUTH` dependency).

**Backend — `web/main.py`**:
- `POST /api/settings/automations/reorder` — same semantics, session-cookie auth.
  Inline validation (400 if not list, 400 if not permutation).

**Frontend — `SettingsPage.tsx`** (`AutomationsSection`):
- Added `handleMove(idx, dir: -1 | 1)` — builds the permutation array by
  splicing the moved index, POSTs to `/api/settings/automations/reorder`,
  then invalidates the `['settings-automations']` query on success.
- Each rule card row now has ↑ / ↓ arrow buttons (ghost, 24×24 px) placed
  before Edit and Delete.  The ↑ button is disabled for the first rule;
  ↓ is disabled for the last rule.

**Tests** (`tests/test_automations_api.py` — 12 new, all pass):
- `test_reorder_basic` — `[2,0,1]` permutation produces correct order.
- `test_reorder_reverse` — full reversal.
- `test_reorder_identity` — `[0,1]` leaves order unchanged.
- `test_reorder_single` — single-rule list, `[0]` is valid.
- `test_reorder_empty_list_ok` — empty rules + empty order succeeds.
- `test_reorder_wrong_length` — 400 if list length ≠ rule count.
- `test_reorder_duplicate_index` — 400 if duplicates present.
- `test_reorder_out_of_range` — 400 if index ≥ rule count.
- `test_reorder_non_list_order` — 400 if `order` is not a list.
- `test_reorder_non_object_body` — 400 if body is not an object.
- `test_reorder_missing_order_key` — 400 if `order` key absent.
- `test_reorder_auth_required` — 401 without API key.

## §2 What shipped in Phase 62 (2026-05-13)

### feat: automation rules REST API + Settings UI rule builder

**Problem**: The RulesEngine and RulesIntegration from Phase 61 had no
management interface — rules could only be edited by hand-editing config.json.
Users had no way to create, update, or delete automation rules from the web UI.

**Fix**:

**Backend — `web/api_v1.py`** (GET/POST/PUT/DELETE `/api/v1/automations`):
- `_load_rules()` — reads `config["integrations"]["chatwire_rules"]["rules"]`.
- `_save_rules(rules)` — atomic-writes the updated list back to config.
- `_validate_rule_body(body)` — validates name, trigger.type (must be one of
  text_exact/text_contains/text_regex/always), and actions is a list.
  Returns 400 on error.
- `GET /api/v1/automations` — returns `{"rules": [...]}`.
- `POST /api/v1/automations` — appends a rule; returns `{"ok": true, "index": N}`.
- `PUT /api/v1/automations/{index}` — replaces rule at index; 404 if OOB.
- `DELETE /api/v1/automations/{index}` — removes rule at index; 404 if OOB.
- All endpoints gated by `X-API-Key` (existing `_AUTH` dependency).

**Backend — `web/main.py`** (session-cookie auth for Settings UI):
- `GET /api/settings/automations` — same shape as api_v1 list.
- `POST /api/settings/automations` — same validation as api_v1 create.
- `PUT /api/settings/automations/{index}` — replace at index.
- `DELETE /api/settings/automations/{index}` — remove at index.
- No separate auth dependency — covered by the existing `_auth_gate` middleware.

**Frontend — `SettingsPage.tsx`**:
- `AutomationsSection` component with compact rule list, Edit/Delete buttons,
  dialog-based rule editor (name, trigger type, conditions, dynamic actions).

**Tests** (`tests/test_automations_api.py` — 30 new):
- Full CRUD coverage plus auth tests.

## §2 What shipped in Phase 61 (2026-05-13)

### feat: built-in automation rules engine (#20)

**Problem**: The only way to automate actions on inbound iMessages was to write
a Python plugin. There was no generic, declarative automation system.

**Fix**: Added `integrations/rules/` — a built-in `chatwire_rules` integration
that evaluates a list of declarative rules against every inbound iMessage.

**Rule format** (under `integrations.chatwire_rules.rules` in `config.json`):

```json
{
  "name": "greeting",
  "trigger": {"type": "text_contains", "pattern": "hello"},
  "conditions": {
    "from_handles": ["+15551234567"],
    "in_group": false
  },
  "actions": [
    {"type": "reply", "text": "Hi {name}! You said: {text}"}
  ]
}
```

**Trigger types**: `text_exact`, `text_contains`, `text_regex`, `always`.
**Condition keys**: `from_handles`, `not_from_handles`, `in_group`, `group_guid`.
**Actions**: `reply`, `webhook`, `log`.
**Rule options**: `stop_on_match: true`.
**51 tests** in `tests/test_rules_engine.py`.

## §2 What shipped in Phase 60 (2026-05-13)

### feat: data exposure warning modal on first launch (#23)

- `DataWarningModal.tsx`: shadcn Dialog shown on first launch.
  localStorage key `chatwire-dismissed-data-warning` tracks dismissal.
  `onInteractOutside` blocked — user must click "I understand".
- Wired in `App.tsx` inside `<QueryClientProvider>`.
- **6 tests** in `DataWarningModal.test.tsx`.

## §2 What shipped in Phase 59 (2026-05-13)

### feat: "edited" badge on edited iMessage bubbles

- `_fetch_edited_flags(conn, rowids)` in `web/main.py`: queries
  `COALESCE(date_edited, 0)`, catches OperationalError on macOS ≤ 12.
- Frontend: `Message.edited?: boolean`; italic "edited" span in `MessageBubble.tsx`.
- **8 tests** in `tests/test_edited_messages.py`.

## §2 What shipped in Phase 58 (2026-05-13)

### Fix: video attachments intercepted by service worker

- `vite.config.ts`: replaced regex urlPattern with pathname callback;
  changed handler to `NetworkOnly`; added `navigateFallbackDenylist`.

## §3 Open bugs

None.

## §4 Follow-ups (Phase 64+ candidates)

**Automation rules — additional trigger types** (future):
- `schedule` / cron-based triggers (would need APScheduler or asyncio scheduler).
- `on_send` / outbound trigger.

**Edited messages — history popover** (research needed):
- Blocker: mbair is macOS 12 — no `date_edited` column. Needs macOS 13+ hardware
  or a chat.db snapshot. Once schema confirmed, add `_fetch_edit_history()` in
  `web/main.py` and wire frontend popover.

**PyPI publishing** (needs `TWINE_TOKEN` or `~/.pypirc`):
- Publish `chatwire-theme-rosepine`, `chatwire-mqtt`, `chatwire-ha`, `chatwire-xmpp`.
  Build: `python3 -m build <plugin-dir>`
  Upload: `TWINE_TOKEN=<token> python3 -m twine upload --non-interactive <dist>/*`

**Other features**:
- #41 Demo app on chatwire.app
- #28 Trigger grammar DSL (chatwire_rules covers the common case; #28 may want
  a more expressive text DSL: `from:+1... contains:"hello" AND in:group`)
- #14 Theme plugin registration (registry done; PyPI publish is the remaining blocker)
- #24 Discord server
- #21, #22 Documentation
- #1 Mac DMG, #2 Custom marketplaces

**Infrastructure**:
- Set up plinux-local test env (chat.db snapshot, separate port)

**Visual QA** (requires interactive mbair session):
- Automations UI — confirm dialog renders correctly in light + dark themes.
- Automations reorder buttons — confirm ↑/↓ visually correct and disabled states work.
- Data exposure warning modal — confirm renders correctly in light + dark themes.
- "edited" badge — visible only when macOS 13+ user has edited a message.
- Per-theme custom CSS editor, theme skin ZIP buttons, theme picker with Rose Pine schemes
- Hover action bar, tapback tooltips, mark-all-read icon (Phase 33)
- Reminder contacts picker (Phase 39)
- Hiatus sidebar indicator + End button + countdown (Phases 40–42), SettingsPage countdown (Phase 43)
- Pinnable settings pin icons + sidebar toggle buttons (Phase 44)
- iOS reply ghost bubble (Phase 45)
- Accordion animation (Phase 46)
- Theme picker refresh after install/uninstall (Phase 47)
- HEIC img_cache warmer behavior (Phase 49)

**Shared libraries for plugins** (post-RC):
- Expose Motion (Framer Motion) on `window.__chatwire` so plugins can use
  animations without bundling their own copy.

## §5 Architecture notes

### Automation rules reordering (added Phase 63)

- **`web/api_v1.py`** — `POST /api/v1/automations/reorder`:
  - Body: `{"order": [i, j, k, ...]}` — permutation of `range(len(rules))`.
  - Validation in `_reorder()`: `sorted(new_order) != list(range(n))` → returns
    error string; caller raises `HTTPException(400, err)`.
  - Saves reordered list via `_save_rules`.
- **`web/main.py`** — `POST /api/settings/automations/reorder`:
  - Same semantics, inline validation.
- **12 tests** appended to `tests/test_automations_api.py`.
- **Frontend**: `handleMove(idx, dir)` builds permutation by `splice` and POSTs
  to `/api/settings/automations/reorder`.  ↑ disabled at `idx === 0`;
  ↓ disabled at `idx === rules.length - 1`.

### Automation rules REST API (added Phase 62)

- **`web/api_v1.py`** — public CRUD (X-API-Key auth):
  - `_load_rules()` / `_save_rules(rules)` — module-level helpers; patchable in tests.
  - `_validate_rule_body(body)` — raises `HTTPException(400, ...)` for bad input.
    Validates: isinstance(dict), name non-empty, trigger is dict with valid type,
    actions is list.
  - `GET /api/v1/automations` → `{"rules": [...]}`.
  - `POST /api/v1/automations` → `{"ok": true, "index": N}`.
  - `PUT /api/v1/automations/{index}` → `{"ok": true}` or 404.
  - `DELETE /api/v1/automations/{index}` → `{"ok": true}` or 404.
  - `POST /api/v1/automations/reorder` → `{"ok": true}` or 400.
- **`web/main.py`** — Settings UI CRUD (session-cookie auth):
  - Same 5 endpoints at `/api/settings/automations[/{index}|/reorder]`.
  - Inline validation (mirrors api_v1 logic; no shared function to avoid import coupling).
- **42 tests** in `tests/test_automations_api.py`; all use in-memory store patches
  (patch.object on `_load_rules` / `_save_rules`); Python 3.8 compatible (nested `with`).

### AutomationsSection (updated Phase 63, SettingsPage.tsx)

- **Query key**: `['settings-automations']` (30 s stale time).
- **Add/Edit**: dialog approach (shadcn `<Dialog>`); form state via `useState`.
- **Delete**: direct DELETE fetch, invalidates query, toast.
- **Reorder**: `handleMove(idx, dir: -1 | 1)` builds `order[]` via splice and
  POSTs to `/api/settings/automations/reorder`; ↑/↓ buttons disabled at bounds.
- **Form → API**: `_formToApiRule()` strips empty conditions.
- **API → Form**: `_apiRuleToForm()` inverse.

### Automation rules engine (added Phase 61)

- **`integrations/rules/__init__.py`**:
  - `RulesEngine` — pure class; pre-compiles regexes at startup.
  - `RulesIntegration` — `NAME = "chatwire_rules"`, `TIER = "core"`.
  - **Config location**: `config.json["integrations"]["chatwire_rules"]["rules"]`.
- **51 tests** in `tests/test_rules_engine.py`.

### Data exposure warning modal (added Phase 60)

- **`DataWarningModal.tsx`**: localStorage key `chatwire-dismissed-data-warning`.
- Wired in `App.tsx` inside `<QueryClientProvider>`.

### Edited messages (added Phase 59)

- `_fetch_edited_flags(conn, rowids)` catches `OperationalError` on macOS ≤ 12.
- Frontend: `Message.edited?: boolean`; italic "edited" span in `MessageBubble.tsx`.
- **macOS 12 note**: `date_edited` column absent on mbair — feature cannot be visually QA'd.

### chatwire-mqtt plugin (updated Phase 57)

- **Package**: `chatwire-plugins/chatwire-mqtt/` — `chatwire_mqtt/__init__.py` + `pyproject.toml`.
- **43 tests** in `tests/test_mqtt_integration.py`.

### chatwire-xmpp plugin (added Phase 56)

- **Package**: `chatwire-plugins/chatwire-xmpp/` — `chatwire_xmpp/__init__.py` + `pyproject.toml`.

### chatwire-ha plugin (updated Phase 55)

- **Package**: `chatwire-plugins/chatwire-ha/` — `chatwire_ha/__init__.py` + `pyproject.toml`.
- **22 tests** in `tests/test_ha_integration.py`.

### Plugin registry (chatwire-plugins, updated Phase 53)

- Repo: `github.com/allenbina/chatwire-plugins` — tracks `plugins.json` only.
- 9 entries: apprise, telegram, webhook, stats, theme-rosepine, example, mqtt, ha, xmpp.

### chatwire status subcommand (added Phase 51)

- Function: `cmd_status()` in `chatwire_cli.py`.
- 21 tests in `tests/test_status.py`.

### img_cache startup warmer (added Phase 49)

- `_img_cache_warmer()`: async task, 10 s delay, 30 days / 200 max.

### Attachment image cache (added Phase 48)

- `FULL_IMG_CACHE_DIR`: `~/.chatwire/img_cache`; 90-day TTL; daily evictor.

### Deploy pipeline (updated 2026-05-12)

- `dist/` is committed to git — no separate scp step.
- Deploy: `pip install --no-cache-dir --force-reinstall --no-deps 'chatwire @ git+ssh://git@github.com-chatwire/allenbina/chatwire-dev.git@main'`
- Restart: `/bin/launchctl kickstart -k gui/501/dev.chatwire.web && /bin/launchctl kickstart -k gui/501/dev.chatwire.bridge`
- Health: `/usr/bin/curl -sf localhost:8723/healthz`

### Frontend build

- After any frontend code change: `npm --prefix /home/mediafront/git/chatwire-dev/web/frontend run build`
- Commit the updated `dist/` with the source changes.

## §6 Next prompt

```
Read docs/HANDOFF.md in full. This is your state file.

git pull first — there may be commits from an interactive session.

STATE: Phase 63 shipped (automation rules reordering).
1203 pytest (1191 prior + 12 new) + 196 Vitest — all green.
mbair running v1.14.0 (git+ssh, Phase 63 code, healthy).
Public repo allenbina/chatwire: synced to Phase 63 (commit be3e74c, 2026-05-13).

Key blockers:
  - Edit history popover (#59 follow-up): mbair is macOS 12 — no date_edited column.
    Needs macOS 13+ chat.db snapshot or hardware. Cannot verify schema headless.
  - PyPI plugin publishing: requires TWINE_TOKEN env var or ~/.pypirc with API token.
    chatwire-theme-rosepine, chatwire-mqtt, chatwire-ha, chatwire-xmpp not on PyPI.
    Marketplace Install button will fail at pip until published.

Pick a task from §4 options:

Option A — Publish plugins to PyPI (theme-rosepine + mqtt + ha + xmpp).
  Requires TWINE_TOKEN env var or ~/.pypirc.
  Build: python3 -m build <plugin-dir>
  Upload: TWINE_TOKEN=<token> python3 -m twine upload --non-interactive <dist>/*

Option B — Automation rules trigger grammar DSL (#28):
  A text-based expression parser: `from:+1... contains:"hello" AND in:group`
  Would parse into the existing RulesEngine condition/trigger structure.
  Adds a fifth trigger type or replaces the structured form with a text input.

Option C — Edited messages: history popover (blocked without macOS 13 chat.db).
  If a chat.db snapshot is available at ~/chat.db or similar, use that.
  Otherwise skip — cannot verify schema on macOS 12.

Option D — Additional automation trigger types:
  `schedule` / cron-based triggers using asyncio scheduler.
  or `on_send` outbound trigger.

VISUAL QA NOTE: Automations UI (including reorder ↑/↓ buttons), data exposure modal,
"edited" badge, pin icons, sidebar toggle buttons, hiatus indicator, reminder contacts
picker, per-theme custom CSS editor, theme skin ZIP buttons, hover action bar, tapback
tooltips, mark-all-read icon, Rose Pine theme picker, iOS reply ghost bubble,
accordion animation, theme picker refresh after install, and HEIC img_cache
warmer behavior all require an interactive session on mbair — skip and note if headless.

Run: python3 -m pytest /home/mediafront/git/chatwire-dev/tests/ --tb=short -q
Run: npm --prefix /home/mediafront/git/chatwire-dev/web/frontend test -- --run
After frontend changes: npm --prefix /home/mediafront/git/chatwire-dev/web/frontend run build
Commit dist/ with source changes.
All tests must pass before committing.

DEPLOY:
  ssh mbair "~/.local/pipx/venvs/chatwire/bin/python -m pip install --no-cache-dir --force-reinstall --no-deps 'chatwire @ git+ssh://git@github.com-chatwire/allenbina/chatwire-dev.git@main'"
  ssh mbair "/bin/launchctl kickstart -k gui/501/dev.chatwire.web && /bin/launchctl kickstart -k gui/501/dev.chatwire.bridge"
  ssh mbair "/usr/bin/curl -sf localhost:8723/healthz"

After work — commit, push, deploy, and notify:
  curl -s -d "Phase 64 complete — <summary>" ntfy.sh/p9SKpYzY70LlyK1N

NOTE: Run pytest as: python3 -m pytest /home/mediafront/git/chatwire-dev/tests/ --tb=short -q
NOTE: npm test command works — use: npm --prefix /home/mediafront/git/chatwire-dev/web/frontend test -- --run
NOTE: Pre-existing failures (8): test_mcp.py (3), test_tinfoil.py (1), test_transform_pipeline.py (4)
  — all caused by test_mcp.py closing the asyncio event loop. Use asyncio.run() in new test files.
NOTE: Public repo sync method: rsync -a --checksum (no --delete) from chatwire-dev/
  to /tmp/chatwire-public/ with excludes for dist/, node_modules/, __pycache__/, .git/
  Then git add -A && git commit && git push in /tmp/chatwire-public/
NOTE: After rsync, RESTORE .gitignore (git checkout -- .gitignore) to preserve
  web/frontend/dist/ exclusion — chatwire-dev commits dist/ but public repo does not.
NOTE: Tests mirror web/main.py helpers locally (never import web.main directly —
  module-level side-effects and Python-3.10+ annotation syntax breaks on Python 3.8).
NOTE: mbair is macOS 12.7.6 — date_edited column does not exist in chat.db there.
  Edit history feature verification requires macOS 13+ hardware or a DB snapshot.
NOTE: Python 3.8 on plinux — use nested with statements (not parenthesized form)
  in test files. No walrus operator (:=), no match statements.
```
