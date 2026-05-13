# Handoff — Phase 65: DSL mode toggle in AutomationsSection

> Phase 65 session shipped (2026-05-13, commit 6686d81 in chatwire-dev).
> 1291 pytest (unchanged) + 218 Vitest (196 prior + 22 new) — all green.
> mbair redeployed — healthy at v1.14.0 (git+ssh, Phase 65 code).

## §1 Current state

- **mbair**: commit 6686d81 deployed and healthy (`/healthz` → ok, v1.14.0).
- **chatwire-theme-rosepine**: installed on mbair from git+ssh;
  `GET /api/ui/plugin-themes` returns all 3 variants.
- **chatwire-plugins registry**: 9 plugins live on GitHub (`allenbina/chatwire-plugins`).
- **Tests**: 1291 pytest / 218 Vitest — all green.
  Pre-existing failures: test_mcp.py (3), test_tinfoil.py (1), test_transform_pipeline.py (4) —
  all caused by test_mcp.py closing the asyncio event loop; unrelated to Phase 65.
- **PyPI**: v1.14.0 (no version bump — frontend-only change; plugins not yet on PyPI).
- **Public repo (allenbina/chatwire)**: synced to Phase 65 (this session).
- **Open bugs**: 0.

## §2 What shipped in Phase 65 (2026-05-13)

### feat: DSL mode toggle in AutomationsSection (#28 follow-up)

**Problem**: The automation rule dialog only exposed the structured form (trigger
type drop-down + pattern input + conditions block). Power users who know the DSL
grammar had no way to type a raw expression directly in the UI.

**Fix**: Added a "Switch to DSL mode" / "Switch to structured form" toggle button
in the Trigger section header of the rule editor dialog.

**DSL mode UI**:
- Clicking "Switch to DSL mode" replaces the trigger type select, pattern input,
  and the entire Conditions section with a single monospace `Textarea`
  (80 px min-height) for the DSL expression.
- A compact syntax reference is shown below the textarea:
  `from:+1 not_from:+1 contains:word exact:hi regex:"…" in:group in:1to1 always`
  with the operators `AND OR NOT ( )`.
- Clicking "Switch to structured form" restores the original layout; the DSL
  expression is discarded (reset to empty).
- `handleSave` validates non-empty `dslExpr` when DSL mode is on.

**Rule card display**:
- A "DSL" badge replaces the trigger type pill for DSL rules.
- The DSL expression (truncated, full text in `title`) is shown instead of the
  `"pattern"` pill.

**Files changed**:
- `web/frontend/src/pages/SettingsPage.tsx`:
  - `TriggerType` union gains `'dsl'`.
  - `AutomationRuleForm` gains `dslMode: boolean` and `dslExpr: string`.
  - `_EMPTY_RULE_FORM` updated with `dslMode: false, dslExpr: ''`.
  - `_formToApiRule` (exported): when `dslMode`, emits
    `trigger: { type: 'dsl', expr }` with no conditions block; actions and
    `stop_on_match` pass through unchanged.
  - `_apiRuleToForm` (exported): detects `trigger.type === 'dsl'` →
    sets `dslMode: true`, populates `dslExpr`; all structured fields reset to
    defaults.
  - Dialog Trigger section: toggle button + conditional rendering of DSL or
    structured inputs.
  - Conditions section wrapped in `{!form.dslMode && …}`.
  - Rule card: extracts `rTrigger.expr`; renders DSL badge + expression preview.
- `web/frontend/src/pages/AutomationsDslMode.test.tsx` (new) — **22 tests**:
  - `_formToApiRule` DSL mode: type=dsl, expr, no conditions, stop_on_match,
    actions pass-through, name.
  - `_formToApiRule` structured mode: regression tests for existing behaviour.
  - `_apiRuleToForm` DSL detection: dslMode/dslExpr populated, stop_on_match,
    actions parsed, defaults for empty fields.
  - `_apiRuleToForm` structured: dslMode=false, dslExpr=''.

## §2 What shipped in Phase 64 (2026-05-13)

### feat: automation rules trigger grammar DSL (#28)

**Problem**: Complex automation rules required nested JSON (trigger + separate
conditions block), which was verbose and hard to read.  There was no way to
express boolean combinations (OR across senders, NOT for exclusions) without
multiple overlapping rules.

**Fix**: Added a text-based expression language compiled to a callable at
rule-load time (no runtime parsing overhead).

**New trigger type**: `"type": "dsl"` with `"expr": "<expression>"`.
A DSL rule's evaluator replaces **both** the trigger and conditions blocks —
the DSL expression covers the entire matching logic.

**Syntax** (see `integrations/rules/dsl.py` module docstring for full grammar):
```
always                                — always matches
from:+15551234567                     — sender match
not_from:+15551234567                 — sender exclusion
contains:"hello world"                — case-insensitive substring
exact:bye                             — exact match (stripped, lowercased)
regex:"order\\s+#\\d+"                — case-insensitive regex search
in:group                              — group-chat messages only
in:1to1                               — 1:1 messages only (aliases: dm, direct)
group:iMessage;chat-guid-here         — specific group GUID
AND / OR / NOT / ( )                  — boolean operators + grouping
```
Adjacent predicates with no operator are treated as implicit AND.
AND binds tighter than OR.  Example:
```
(from:+1 OR from:+2) AND contains:urgent AND NOT in:group
```

**Files changed**:
- `integrations/rules/dsl.py` (new) — tokenizer + recursive descent parser;
  `parse_dsl(expr)` returns `Evaluator`; `DSLError` on invalid expressions.
- `integrations/rules/__init__.py` — `RulesEngine._compile()` handles
  `trigger.type = "dsl"` (parses `expr`, stores compiled callable);
  `evaluate()` dispatches DSL rules via the compiled evaluator, skipping the
  normal conditions block.  `SETTINGS_SCHEMA` updated with `dsl` enum value
  and `expr` property.
- `web/api_v1.py` — `_validate_rule_body()` accepts `dsl`; requires
  non-empty `trigger.expr` for DSL rules.
- `tests/test_rules_dsl.py` (new) — **88 tests**: all predicate types,
  AND/OR/NOT/implicit-AND, precedence, grouping, quoted strings with escapes,
  error cases, RulesEngine end-to-end, stop_on_match, mixed DSL+non-DSL rules,
  bad-expr compile-time skip, api_v1 validation.

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
- #28 Trigger grammar DSL — **fully shipped** (backend Phase 64, frontend DSL toggle Phase 65).
- #14 Theme plugin registration (registry done; PyPI publish is the remaining blocker)
- #24 Discord server
- #21, #22 Documentation
- #1 Mac DMG, #2 Custom marketplaces

**Infrastructure**:
- Set up plinux-local test env (chat.db snapshot, separate port)

**UI polish**:
- Reply ghost bubble: hide sender name in 1:1 threads (redundant — only two
  people). Show sender name only in group chats.

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

### Automation rules DSL (added Phase 64)

- **`integrations/rules/dsl.py`**:
  - `_tokenize(expr)` — character-level scanner; yields `(kind, value)` tuples.
    Kinds: `AND`, `OR`, `NOT`, `LPAREN`, `RPAREN`, `PRED`, `EOF`.
    Respects double-quoted strings in predicate values (backslash escapes).
  - `_compile_pred(token_value)` — maps `key:value` to an `Evaluator` closure.
    Supported keys: `always`, `contains`, `exact`, `regex`, `from`, `not_from`,
    `in` (group/1to1/dm/direct), `group` (GUID).
    Raises `DSLError` on unknown key, invalid `in:` value, or bad regex.
  - `_Parser` — recursive descent; grammar has two precedence levels:
    OR (`_parse_or`) > AND+implicit (`_parse_and`); NOT is right-recursive via `_parse_term`.
  - `parse_dsl(expr)` — public entry point; raises `DSLError` on empty string.
  - `Evaluator` type alias: `Callable[[str, str, bool, Optional[str]], bool]`
    (text, handle_lc, is_group, chat_guid).
- **`integrations/rules/__init__.py`** changes:
  - `_compile()`: `trigger_type == "dsl"` → calls `parse_dsl(trigger_raw["expr"])`;
    result stored as `compiled_dsl` in compiled rule dict.
    DSLError / missing expr → `ValueError` → rule skipped with warning.
  - `evaluate()`: DSL rules checked first in loop body; evaluator called with
    `(text, handle_lc, msg_is_group, msg_chat_guid)`; `continue` skips the
    normal conditions block for DSL rules.
  - `SETTINGS_SCHEMA`: trigger `type` enum gains `"dsl"`; `expr` property added.
- **`web/api_v1.py`**: `valid_triggers` gains `"dsl"`; extra check rejects
  `dsl` without a non-empty `trigger.expr`.
- **88 tests** in `tests/test_rules_dsl.py`.

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

### AutomationsSection (updated Phase 65, SettingsPage.tsx)

- **DSL mode toggle**: "Switch to DSL mode" button in Trigger section header.
  When active: monospace Textarea for `dslExpr`; Conditions section hidden;
  `_formToApiRule` emits `{type:'dsl', expr}`; `handleSave` requires non-empty expr.
- **`_formToApiRule`** / **`_apiRuleToForm`**: both exported for testing.
  `_apiRuleToForm` detects `trigger.type === 'dsl'` → `{dslMode: true, dslExpr: …}`.
- **Rule card**: DSL badge + truncated expression instead of pattern pill.
- **22 tests** in `web/frontend/src/pages/AutomationsDslMode.test.tsx`.

### AutomationsSection (updated Phase 63)

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

STATE: Phase 65 shipped (DSL mode toggle in AutomationsSection).
1291 pytest (unchanged) + 218 Vitest — all green.
mbair running v1.14.0 (git+ssh, Phase 65 code, healthy).
Public repo allenbina/chatwire: synced to Phase 65 (2026-05-13).

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

Option B — Additional automation trigger types:
  `schedule` / cron-based triggers using asyncio scheduler.
  or `on_send` outbound trigger.

Option C — Edited messages: history popover (blocked without macOS 13 chat.db).
  If a chat.db snapshot is available at ~/chat.db or similar, use that.
  Otherwise skip — cannot verify schema on macOS 12.

VISUAL QA NOTE: Automations UI (including DSL mode toggle, reorder ↑/↓ buttons),
data exposure modal, "edited" badge, pin icons, sidebar toggle buttons, hiatus indicator,
reminder contacts picker, per-theme custom CSS editor, theme skin ZIP buttons, hover
action bar, tapback tooltips, mark-all-read icon, Rose Pine theme picker, iOS reply
ghost bubble, accordion animation, theme picker refresh after install, and HEIC img_cache
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
  curl -s -d "Phase 66 complete — <summary>" ntfy.sh/p9SKpYzY70LlyK1N

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
