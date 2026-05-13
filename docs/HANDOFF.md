# Handoff — Phase 67: public repo sync to Phase 66

> Phase 67 session shipped (2026-05-13, commit caf2a8c in allenbina/chatwire public repo).
> 1326 pytest / 218 Vitest — all green (unchanged).
> mbair running v1.14.0 (git+ssh, Phase 66 code, healthy).

## §1 Current state

- **mbair**: commit b1b4275 (Phase 66) deployed and healthy (`/healthz` → ok, v1.14.0).
- **chatwire-theme-rosepine**: installed on mbair from git+ssh;
  `GET /api/ui/plugin-themes` returns all 3 variants.
- **chatwire-plugins registry**: 9 plugins live on GitHub (`allenbina/chatwire-plugins`).
- **Tests**: 1326 pytest / 218 Vitest — all green.
  Pre-existing failures: test_mcp.py (3), test_tinfoil.py (1), test_transform_pipeline.py (4) —
  all caused by test_mcp.py closing the asyncio event loop; unrelated to Phase 66/67.
- **PyPI**: v1.14.0 (plugins not yet on PyPI).
- **Public repo (allenbina/chatwire)**: synced to Phase 66 (commit caf2a8c, 2026-05-13).
- **Open bugs**: 0.

## §2 What shipped in Phase 67 (2026-05-13)

### chore: sync public repo (allenbina/chatwire) to Phase 66

**What**: Rsynced chatwire-dev source (excluding dist/, node_modules/, __pycache__/, .git/)
to /tmp/chatwire-public and pushed to github.com/allenbina/chatwire.

**Files synced**: bridge.py, integrations/base.py, integrations/rules/__init__.py,
web/api_v1.py, web/main.py, web/frontend/src/pages/SettingsPage.tsx,
web/frontend/src/pages/AutomationsDslMode.test.tsx, web/frontend/src/components/MediaGallery.tsx,
tests/test_on_send_rules.py (new), tests/test_automations_api.py, docs/HANDOFF.md.

**Public repo commit**: caf2a8c — "feat: on_send automation trigger for outbound iMessages (#66)"

## §2 What shipped in Phase 66 (2026-05-13)

### feat: on_send automation trigger for outbound iMessages

**Problem**: The automation rules engine only evaluated inbound iMessages.
There was no way to trigger actions (webhook calls, log lines, auto-replies)
when the user or an integration sends an outbound iMessage.

**Fix**: Added a new `on_send` trigger type to the rules engine.

**New trigger type**: `"type": "on_send"` — fires for every outbound text
message sent via the bridge (integration-initiated or web UI).

**Direction isolation**:
- `evaluate()` (inbound) silently skips `on_send` rules.
- `evaluate_outbound()` (outbound) skips all non-`on_send` rules.
- DSL-mode rules remain inbound-only.

**Outbound-specific conditions** (in the `conditions` block):
```json
{
  "to_handles":     ["+15551234567"],
  "not_to_handles": ["+15550000001"],
  "in_group":       false,
  "group_guid":     "iMessage;+;chat..."
}
```
`to_handles` / `not_to_handles` filter by recipient (lowercased frozensets).
`in_group` / `group_guid` shared semantics with inbound rules.

**Actions**: `reply`, `webhook`, `log` — same as inbound rules.
`webhook` payload carries `handle` (recipient), `text`, `is_group`, `chat_guid`.

**Example rule**:
```json
{
  "name": "log-urgent-sends",
  "trigger": {"type": "on_send"},
  "conditions": {"to_handles": ["+15551234567"]},
  "actions": [{"type": "log", "message": "sent to {handle}: {text}"}]
}
```

**Files changed**:
- `integrations/base.py`: `OutboundEvent` dataclass (`handle`, `text`,
  `is_group`, `chat_guid`); exported in `__all__`.
- `integrations/rules/__init__.py`:
  - `_compile()`: handles `"on_send"`; compiles `to_handles` / `not_to_handles`.
  - `evaluate()`: skips `on_send` rules.
  - `evaluate_outbound()`: new method; evaluates only `on_send` rules;
    checks `to_handles`, `not_to_handles`, `in_group`, `group_guid`,
    `stop_on_match`.
  - `RulesIntegration.on_outbound(event)`: new async hook; dispatches
    matched rules through the existing action pipeline.
  - `SETTINGS_SCHEMA`: `on_send` in trigger type enum; `to_handles` /
    `not_to_handles` in conditions properties.
- `bridge.py`: `_fan_out_outbound(integrations, target, body)` helper;
  called after each successful `BridgeContextImpl.send_text()`.
  Per-integration error catching — a failing hook never blocks the send.
- `web/api_v1.py`: `on_send` added to `valid_triggers`; no `expr` required.
- `web/frontend/src/pages/SettingsPage.tsx`:
  - `TriggerType` union gains `'on_send'`.
  - `AutomationRuleForm` gains `toHandles` / `notToHandles` string fields.
  - Trigger dropdown: "On send (outbound)" option; pattern input hidden.
  - Conditions: "To handles" / "Not to handles" shown for `on_send`;
    "From handles" / "Not from handles" shown for all other trigger types.
  - `_formToApiRule` / `_apiRuleToForm` handle `on_send` bidirectionally.
  - `_TRIGGER_LABELS`: `on_send` → "On send".
- `web/frontend/src/pages/AutomationsDslMode.test.tsx`: `_BASE_FORM` gains
  `toHandles`/`notToHandles` for TypeScript compliance.
- `tests/test_on_send_rules.py` (new) — **35 tests**:
  - `_compile`: to_handles lowercased frozensets, no pattern/regex needed.
  - `evaluate()`: skips on_send rules (direction isolation).
  - `evaluate_outbound()`: fires on_send rules, conditions (to_handles,
    not_to_handles, in_group, group_guid), stop_on_match, None inputs.
  - `api_v1._validate_rule_body`: accepts `on_send`; no `expr` required.
  - `OutboundEvent` dataclass: field values, group vs 1:1.
  - `RulesIntegration.on_outbound`: log action dispatch, no-match silence,
    no-ctx noop, webhook dispatch, action error isolation.
- `tests/test_automations_api.py`: updated `test_invalid_trigger_type_returns_400`
  to use `"bad_type"` (not `"on_send"`, which is now valid).

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

(See Phase 62 notes in git history for full details.)

## §3 Open bugs

None.

## §4 Follow-ups (Phase 67+ candidates)

**Automation rules — additional trigger types** (future):
- `schedule` / cron-based triggers (would need APScheduler or asyncio scheduler).

**Edited messages — history popover** (research needed):
- Blocker: mbair is macOS 12 — no `date_edited` column. Needs macOS 13+ hardware
  or a chat.db snapshot. Once schema confirmed, add `_fetch_edit_history()` in
  `web/main.py` and wire frontend popover.

**PyPI publishing** (needs `TWINE_TOKEN` or `~/.pypirc`):
- Publish `chatwire-theme-rosepine`, `chatwire-mqtt`, `chatwire-ha`, `chatwire-xmpp`.
  Build: `python3 -m build <plugin-dir>`
  Upload: `TWINE_TOKEN=<token> python3 -m twine upload --non-interactive <dist>/*`

**Public repo sync** (allenbina/chatwire):
- DONE through Phase 66 (commit caf2a8c, 2026-05-13). Keep in sync after future phases.

**Other features**:
- #41 Demo app on chatwire.app
- #14 Theme plugin registration (registry done; PyPI publish is the remaining blocker)
- #24 Discord server
- #21, #22 Documentation
- #1 Mac DMG, #2 Custom marketplaces

**Bugs from interactive QA (2026-05-13 batch 2)**:
- Whitelist add doesn't update sidebar live — need to restart to see new contact.
  Invalidate conversations query after whitelist add/remove.
- Whitelist removal needs testing — verify contact disappears from sidebar.
- Video thumbnails on contact info page show "video" text instead of first frame
  with play icon overlay. Also clicking video opens new tab — should open in
  the lightbox (same as photos).
- CI build failure notifications: add ntfy curl on failure to the self-hosted
  runner CI workflow (post-job step).

**Testing (post-RC1)**:
- Full install walkthrough on a clean Mac (document steps)
- Uninstall test: confirm all files removed (themes, plugins, DB, config)
- Reinstall test: confirm clean slate (no leftover state from previous install)
- Python version matrix: 3.10/3.11/3.12/3.13
- Node version matrix: 20/22
- macOS version compat: handle missing columns gracefully (date_edited = Ventura+)

**Admin tooling**:
- Google Form + Spreadsheet for account unlock requests. Form logs request,
  looks up previous requests/unlocks for that hardware. Share form without
  exposing the spreadsheet.

**Infrastructure**:
- Set up plinux-local test env (chat.db snapshot, separate port)

**Logs page enhancement**:
- Add a services/plugins status tab showing: installed plugins, which are
  on/off, and their health status.

**UI polish**:
- Reply ghost bubble: hide sender name in 1:1 threads (redundant — only two
  people). Show sender name only in group chats.

**Visual QA** (requires interactive mbair session):
- Automations UI — confirm on_send trigger dropdown + To handles / Not to handles
  conditions render correctly in the rule editor dialog.
- Automations UI — confirm DSL mode toggle, reorder ↑/↓ buttons, data exposure
  modal all render correctly in light + dark themes.
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

### on_send trigger (added Phase 66)

- **`integrations/base.py`** — `OutboundEvent` dataclass: `handle`, `text`,
  `is_group`, `chat_guid`.  Added to `__all__`.
- **`integrations/rules/__init__.py`** changes:
  - `_compile()`: `"on_send"` joins the valid trigger set; compiles
    `to_handles` and `not_to_handles` frozensets from `conds["to_handles"]`
    / `conds["not_to_handles"]`.  No regex or DSL parse needed.
  - `evaluate()`: `if tt == "on_send": continue` — direction isolation.
  - `evaluate_outbound(text, to_handle, is_group, chat_guid)`:
    iterates only `on_send` rules; checks `to_handles`, `not_to_handles`,
    `in_group`, `group_guid`; respects `stop_on_match`.
  - `RulesIntegration.on_outbound(event)`: calls `evaluate_outbound()`;
    dispatches matched rules via `_dispatch()`.  No-ctx early return.
  - `SETTINGS_SCHEMA`: `"on_send"` in trigger type enum; `to_handles` /
    `not_to_handles` added to conditions properties.
- **`bridge.py`** — `_fan_out_outbound(integrations, target, body)`:
  constructs `OutboundEvent`; iterates integrations; calls `on_outbound`
  when present; swallows per-integration exceptions with a warning log.
  Called from `BridgeContextImpl.send_text()` after the actual send.
- **`web/api_v1.py`**: `"on_send"` in `valid_triggers`; no `expr` check.
- **35 tests** in `tests/test_on_send_rules.py`.

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

### AutomationsSection (updated Phase 66, SettingsPage.tsx)

- **`on_send` trigger**: dropdown option "On send (outbound)"; pattern input
  hidden; conditions section shows To/Not-to handles instead of From/Not-from.
- **`_formToApiRule`**: for `on_send`, emits `to_handles`/`not_to_handles` in
  conditions; no `trigger.pattern`.
- **`_apiRuleToForm`**: detects `trigger.type === 'on_send'` →
  populates `toHandles`/`notToHandles`; clears `fromHandles`/`notFromHandles`.

### AutomationsSection (updated Phase 65, SettingsPage.tsx)

- **DSL mode toggle**: "Switch to DSL mode" button in Trigger section header.
  When active: monospace Textarea for `dslExpr`; Conditions section hidden;
  `_formToApiRule` emits `{type:'dsl', expr}`; `handleSave` requires non-empty expr.
- **`_formToApiRule`** / **`_apiRuleToForm`**: both exported for testing.
  `_apiRuleToForm` detects `trigger.type === 'dsl'` → `{dslMode: true, dslExpr: …}`.
- **Rule card**: DSL badge + truncated expression instead of pattern pill.
- **22 tests** in `web/frontend/src/pages/AutomationsDslMode.test.tsx`.

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

STATE: Phase 67 shipped (public repo allenbina/chatwire synced to Phase 66).
1326 pytest / 218 Vitest — all green (no code changes this session).
mbair running v1.14.0 (git+ssh, Phase 66 code, healthy).
Public repo allenbina/chatwire: synced through Phase 66 (commit caf2a8c).

Key blockers:
  - Edit history popover (#59 follow-up): mbair is macOS 12 — no date_edited column.
    Needs macOS 13+ chat.db snapshot or hardware. Cannot verify schema headless.
  - PyPI plugin publishing: requires TWINE_TOKEN env var or ~/.pypirc with API token.
    chatwire-theme-rosepine, chatwire-mqtt, chatwire-ha, chatwire-xmpp not on PyPI.
    Marketplace Install button will fail at pip until published.

Pick a task from §4 options:

Option A — Schedule trigger type (cron-based automation):
  `schedule` trigger using asyncio scheduler.
  Fires rules at a configured cron schedule (no incoming message context).
  Would need APScheduler or similar, or a simple asyncio.sleep loop.
  New trigger type: {"type": "schedule", "cron": "0 9 * * *"} (cron expression).
  Fires evaluate_scheduled() in rules engine — no text/handle context.
  Bridge starts scheduler loop on startup; stops on shutdown.

Option B — Publish plugins to PyPI (theme-rosepine + mqtt + ha + xmpp).
  Requires TWINE_TOKEN env var or ~/.pypirc.
  Build: python3 -m build <plugin-dir>
  Upload: TWINE_TOKEN=<token> python3 -m twine upload --non-interactive <dist>/*

Option C — Reply ghost bubble: hide sender name in 1:1 threads.
  In iOS reply ghost bubble, sender name is redundant in 1-to-1 threads.
  Show sender name only in group chats.
  Likely a small frontend-only change in the message thread component.

VISUAL QA NOTE: on_send trigger UI (To handles / Not to handles conditions),
Automations UI (DSL mode toggle, reorder ↑/↓ buttons), data exposure modal,
"edited" badge, pin icons, sidebar toggle buttons, hiatus indicator,
reminder contacts picker, per-theme custom CSS editor, theme skin ZIP buttons,
hover action bar, tapback tooltips, mark-all-read icon, Rose Pine theme picker,
iOS reply ghost bubble, accordion animation, theme picker refresh after install,
and HEIC img_cache warmer behavior all require an interactive session on mbair.

Run: python3 -m pytest /home/mediafront/git/chatwire-dev/tests/ --tb=short -q
Run: npm --prefix /home/mediafront/git/chatwire-dev/web/frontend test -- --run
After frontend changes: npm --prefix /home/mediafront/git/chatwire-dev/web/frontend run build
Commit dist/ with source changes.
All tests must pass before committing.

DEPLOY:
  ssh mbair "~/.local/pipx/venvs/chatwire/bin/python -m pip install --no-cache-dir --force-reinstall --no-deps 'chatwire @ git+ssh://git@github.com-chatwire/allenbina/chatwire-dev.git@main'"
  ssh mbair "/bin/launchctl kickstart -k gui/501/dev.chatwire.web && /bin/launchctl kickstart -k gui/501/dev.chatwire.bridge"
  ssh mbair "/usr/bin/curl -sf localhost:8723/healthz"

After work — commit, push, deploy (if code changed), sync public repo, and notify:
  curl -s -d "Phase 68 complete — <summary>" ntfy.sh/p9SKpYzY70LlyK1N

Public repo sync (after future code phases):
  rsync -a --checksum --exclude='dist/' --exclude='node_modules/' --exclude='__pycache__/' --exclude='.git/' --exclude='*.pyc' --exclude='*.egg-info/' /home/mediafront/git/chatwire-dev/ /tmp/chatwire-public/
  git -C /tmp/chatwire-public checkout -- .gitignore
  git -C /tmp/chatwire-public add -A && git -C /tmp/chatwire-public commit -m "..." && git -C /tmp/chatwire-public push origin main

NOTE: Run pytest as: python3 -m pytest /home/mediafront/git/chatwire-dev/tests/ --tb=short -q
NOTE: npm test command works — use: npm --prefix /home/mediafront/git/chatwire-dev/web/frontend test -- --run
NOTE: Pre-existing failures (8): test_mcp.py (3), test_tinfoil.py (1), test_transform_pipeline.py (4)
  — all caused by test_mcp.py closing the asyncio event loop. Use asyncio.run() in new test files.
NOTE: Tests mirror web/main.py helpers locally (never import web.main directly —
  module-level side-effects and Python-3.10+ annotation syntax breaks on Python 3.8).
NOTE: mbair is macOS 12.7.6 — date_edited column does not exist in chat.db there.
  Edit history feature verification requires macOS 13+ hardware or a DB snapshot.
NOTE: Python 3.8 on plinux — use nested with statements (not parenthesized form)
  in test files. No walrus operator (:=), no match statements.
NOTE: Use asyncio.run() in new test files (not asyncio.get_event_loop().run_until_complete)
  to avoid test_mcp.py event loop closure affecting async tests.
```
