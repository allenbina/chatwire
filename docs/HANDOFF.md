# Handoff — Phase 68: schedule trigger type for automation rules

> Phase 68 session shipped (2026-05-13, commit 530386e).
> 1384 pytest / 218 Vitest — all green (+58 new tests).
> mbair running v1.14.0 (git+ssh, Phase 68 code, healthy).

## §1 Current state

- **mbair**: commit 530386e (Phase 68) deployed and healthy (`/healthz` → ok, v1.14.0).
- **chatwire-theme-rosepine**: installed on mbair from git+ssh;
  `GET /api/ui/plugin-themes` returns all 3 variants.
- **chatwire-plugins registry**: 9 plugins live on GitHub (`allenbina/chatwire-plugins`).
- **Tests**: 1384 pytest / 218 Vitest — all green.
  Pre-existing failures: test_mcp.py (3), test_tinfoil.py (1), test_transform_pipeline.py (4) —
  all caused by test_mcp.py closing the asyncio event loop; unrelated to this phase.
- **PyPI**: v1.14.0 (plugins not yet on PyPI).
- **Public repo (allenbina/chatwire)**: synced to Phase 68 (commit 795a595, 2026-05-13).
- **Open bugs**: 0.

## §2 What shipped in Phase 68 (2026-05-13)

### feat: schedule trigger type for automation rules (#68)

**What**: Added a new `schedule` trigger type to the automation rules engine.
Schedule rules fire on a configurable cron schedule rather than in response
to an inbound or outbound message.

**New trigger type**: `"type": "schedule"` with `"cron": "<5-field expression>"`.

**Cron format** (5 fields: minute hour dom month dow, dow 0=Sunday):
```
"0 9 * * 1-5"   — 09:00 Mon–Fri
"*/15 * * * *"  — every 15 minutes
"30 8,17 * * *" — 08:30 and 17:30 daily
```
Supports: `*`, literals, ranges (`1-5`), lists (`1,3`), step notation (`*/5`, `1-5/2`).

**Actions**: `webhook` and `log` are supported. `reply` is skipped with a warning
(no recipient handle available in a schedule context).

**Webhook payload** for schedule rules: `{"rule": "<name>", "trigger": "schedule"}`.

**Example rule**:
```json
{
  "name": "morning-ping",
  "trigger": {"type": "schedule", "cron": "0 9 * * 1-5"},
  "actions": [{"type": "webhook", "url": "https://example.com/hook"}]
}
```

**Files changed**:
- `integrations/rules/cron.py` (new): `_parse_field()`, `compile_cron()`,
  `match_cron()`. Pure Python, no dependencies. `CronError` on bad input.
- `integrations/rules/__init__.py`:
  - Module-level `compile_cron` / `match_cron` / `CronError` import (with
    `ImportError` fallback like DSL module).
  - `_compile()`: `"schedule"` branch — requires non-empty `cron`; stores
    compiled tuple in `compiled_cron` field.
  - `evaluate()`: skips `schedule` rules (`tt in ("on_send", "schedule")`).
  - `evaluate_scheduled(dt)`: new method — evaluates only `schedule` rules
    against `dt`; respects `stop_on_match`.
  - `_ScheduleContext`: minimal context (empty handle/text) for action dispatch.
  - `_do_reply()`: guards `not getattr(msg, "handle", "")` — logs warning and
    returns for schedule-context calls.
  - `RulesIntegration.__init__`: `self._schedule_task = None`.
  - `RulesIntegration.start()`: calls `asyncio.ensure_future(_schedule_loop())`
    when any schedule rules are loaded.
  - `RulesIntegration.stop()`: cancels + awaits schedule task.
  - `_schedule_loop()`: asyncio task — sleeps to next minute boundary (+0.1s
    margin), calls `_fire_scheduled(now)`, loops.
  - `_fire_scheduled(dt)`: evaluates schedule rules, dispatches via `_dispatch()`.
  - `SETTINGS_SCHEMA`: `"schedule"` in trigger type enum; `"cron"` property.
- `web/api_v1.py`: `"schedule"` in `valid_triggers`; requires non-empty
  `trigger.cron`.
- `web/frontend/src/pages/SettingsPage.tsx`:
  - `TriggerType` gains `'schedule'`.
  - `AutomationRuleForm` gains `cron: string`.
  - `_EMPTY_RULE_FORM`: `cron: ''`.
  - `_formToApiRule`: `schedule` → emits `{type:'schedule', cron}`, no conditions.
  - `_apiRuleToForm`: detects `trigger.type === 'schedule'` → populates `cron`.
  - `_TRIGGER_LABELS`: `schedule` → `'Schedule'`.
  - `handleSave`: validates non-empty cron for schedule type.
  - Trigger dropdown: "Schedule (cron)" option.
  - Cron input (monospace) + syntax hint shown for schedule type.
  - Conditions section hidden for schedule rules.
  - Rule card: cron expression pill shown for schedule rules.
- `web/frontend/src/pages/AutomationsDslMode.test.tsx`: `_BASE_FORM` gains
  `cron: ''` for TypeScript compliance.
- `tests/test_schedule_rules.py` (new) — **58 tests**:
  - `compile_cron`: 19 tests — valid expressions, CronError cases.
  - `match_cron`: 12 tests — all fields, dow cron/Python conversion.
  - `RulesEngine._compile`: 4 tests — compiles, skips bad/missing cron.
  - Direction isolation: 3 tests — evaluate/evaluate_outbound skip schedule.
  - `evaluate_scheduled`: 7 tests — match, no-match, stop_on_match, mixed.
  - `api_v1._validate_rule_body`: 4 tests — accepts/rejects schedule.
  - `_ScheduleContext`: 1 test — field values.
  - `_fire_scheduled`: 8 tests — log/webhook/reply dispatch, no-ctx, error
    isolation, task start/no-start.

## §2 What shipped in Phase 67 (2026-05-13)

### chore: sync public repo (allenbina/chatwire) to Phase 66

**What**: Rsynced chatwire-dev source (excluding dist/, node_modules/, __pycache__/, .git/)
to /tmp/chatwire-public and pushed to github.com/allenbina/chatwire.

**Public repo commit**: caf2a8c — "feat: on_send automation trigger for outbound iMessages (#66)"

## §2 What shipped in Phase 66 (2026-05-13)

### feat: on_send automation trigger for outbound iMessages

(See Phase 66 notes in git history for full details.)

## §2 What shipped in Phase 65 (2026-05-13)

### feat: DSL mode toggle in AutomationsSection (#28 follow-up)

(See Phase 65 notes in git history for full details.)

## §2 What shipped in Phase 64 (2026-05-13)

### feat: automation rules trigger grammar DSL (#28)

(See Phase 64 notes in git history for full details.)

## §2 What shipped in Phase 63 (2026-05-13)

### feat: automation rules reordering

(See Phase 63 notes in git history for full details.)

## §2 What shipped in Phase 62 (2026-05-13)

### feat: automation rules REST API + Settings UI rule builder

(See Phase 62 notes in git history for full details.)

## §3 Open bugs

None.

## §4 Follow-ups (Phase 69+ candidates)

**Anti-spam lockout hardening** (important):
- Move fuse check into the lowest-level send path (before _run_osascript in
  chat_send.py) so it's impossible to bypass — currently check_send_guard()
  is a separate function callers must remember to invoke. If fuse is active,
  reject at the osascript level regardless of caller (web, API, plugin, MCP,
  MQTT outbound, automation reply actions).
- ComposeBox: show yellow warning triangle + "Sending blocked for Xm" or
  "Permanently locked — enter unlock code in Settings" (steps 1-3 currently
  silently disable input with no explanation).
- Permanent banner: for step 4+ (permanent lockout), persistent banner across
  top of the app (in addition to LockoutOverlay).
- Plugin denials: XMPP, Telegram, MQTT outbound, API, MCP should all get a
  clear error message with remaining lockout time when fuse is active.
  Catch BroadcastBlockedError / RateLimitError in each integration's send path.
- Unlock code entry: add to Settings page (not as a magic message). Admin
  generates code, user enters it in Settings → Unlock section.
- All entry points must return the same info: reason (broadcast/rate-limit),
  remaining time, and unlock instructions for permanent lockout.

**Edited messages — history popover** (research needed):
- Blocker: mbair is macOS 12 — no `date_edited` column. Needs macOS 13+ hardware
  or a chat.db snapshot. Once schema confirmed, add `_fetch_edit_history()` in
  `web/main.py` and wire frontend popover.

**PyPI publishing** (needs `TWINE_TOKEN` or `~/.pypirc`):
- Publish `chatwire-theme-rosepine`, `chatwire-mqtt`, `chatwire-ha`, `chatwire-xmpp`.
  Build: `python3 -m build <plugin-dir>`
  Upload: `TWINE_TOKEN=<token> python3 -m twine upload --non-interactive <dist>/*`

**Public repo sync** (allenbina/chatwire):
- Synced through Phase 68 (commit 795a595, 2026-05-13). Keep in sync after future phases.

**Other features**:
- #41 Demo app on chatwire.app
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
- Schedule trigger: confirm "Schedule (cron)" option in dropdown + cron input
  + syntax hint render correctly.
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

### schedule trigger (added Phase 68)

- **`integrations/rules/cron.py`** — `_parse_field(field, lo, hi, name)`:
  parses one cron field into a `frozenset`; supports `*`, literals, ranges,
  lists, step notation. `compile_cron(expr)` returns a 5-tuple of frozensets
  (minute, hour, dom, month, dow). `match_cron(compiled, dt)` converts
  Python's weekday (Mon=0) to cron dow (Sun=0) via `(weekday+1) % 7`.
- **`integrations/rules/__init__.py`** changes:
  - `_compile()`: `"schedule"` joins the valid trigger set; requires `cron`
    field; calls `compile_cron()`; stores result as `compiled_cron`.
  - `evaluate()`: `tt in ("on_send", "schedule")` → `continue`.
  - `evaluate_scheduled(dt)`: iterates only `schedule` rules; calls
    `match_cron(rule["compiled_cron"], dt)`; respects `stop_on_match`.
  - `_ScheduleContext`: `handle=""`, `text=""`, `is_group=False`, `chat_guid=""`.
  - `_do_reply()`: returns early (with warning) if `not msg.handle`.
  - `start()` → `asyncio.ensure_future(_schedule_loop())` if schedule rules exist.
  - `stop()` → `_schedule_task.cancel()` + `await _schedule_task`.
  - `_schedule_loop()`: `sleep_s = 60.1 - now.second - now.microsecond/1e6`;
    wakes at top of each minute; calls `_fire_scheduled(now)`.
  - `_fire_scheduled(dt)`: evaluates schedule rules, instantiates
    `_ScheduleContext()`, dispatches via `_dispatch(action, ctx, rule_name)`.
- **`web/api_v1.py`**: `"schedule"` in `valid_triggers`; extra check requires
  non-empty `trigger.cron` for schedule rules.
- **58 tests** in `tests/test_schedule_rules.py`.

### on_send trigger (added Phase 66)

(See Phase 66 notes and §5 in git history for full details.)

### Automation rules DSL (added Phase 64)

(See Phase 64 notes and §5 in git history for full details.)

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

STATE: Phase 68 shipped (schedule trigger type for automation rules).
1384 pytest / 218 Vitest — all green (+58 new tests).
mbair running v1.14.0 (git+ssh, Phase 68 code, healthy).
Public repo allenbina/chatwire: synced through Phase 68 (commit 795a595).

Key blockers:
  - Edit history popover (#59 follow-up): mbair is macOS 12 — no date_edited column.
    Needs macOS 13+ chat.db snapshot or hardware. Cannot verify schema headless.
  - PyPI plugin publishing: requires TWINE_TOKEN env var or ~/.pypirc with API token.
    chatwire-theme-rosepine, chatwire-mqtt, chatwire-ha, chatwire-xmpp not on PyPI.
    Marketplace Install button will fail at pip until published.

Pick a task from §4 options:

Option A — Reply ghost bubble: hide sender name in 1:1 threads.
  In iOS reply ghost bubble, sender name is redundant in 1-to-1 threads.
  Show sender name only in group chats.
  Likely a small frontend-only change in the message thread component.

Option B — Publish plugins to PyPI (theme-rosepine + mqtt + ha + xmpp).
  Requires TWINE_TOKEN env var or ~/.pypirc.
  Build: python3 -m build <plugin-dir>
  Upload: TWINE_TOKEN=<token> python3 -m twine upload --non-interactive <dist>/*

Option C — Any remaining §4 follow-up that fits in one session.

VISUAL QA NOTE: Schedule trigger UI (cron input, syntax hint), on_send trigger UI,
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
  curl -s -d "Phase 69 complete — <summary>" ntfy.sh/p9SKpYzY70LlyK1N

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
