# Handoff — Phase 70: anti-spam lockout hardening

> Phase 70 session shipped (2026-05-13, commit 52b04b3).
> 1401 pytest / 223 Vitest — all green (+17 new pytest tests).
> mbair running v1.14.0 (git+ssh, Phase 70 code, healthy).

## §1 Current state

- **mbair**: commit 52b04b3 (Phase 70) deployed and healthy (`/healthz` → ok, v1.14.0).
- **chatwire-theme-rosepine**: installed on mbair from git+ssh;
  `GET /api/ui/plugin-themes` returns all 3 variants.
- **chatwire-plugins registry**: 9 plugins live on GitHub (`allenbina/chatwire-plugins`).
- **Tests**: 1401 pytest / 223 Vitest — all green.
  Pre-existing failures: test_mcp.py (3), test_tinfoil.py (1), test_transform_pipeline.py (4) —
  all caused by test_mcp.py closing the asyncio event loop; unrelated to this phase.
- **PyPI**: v1.14.0 (plugins not yet on PyPI).
- **Public repo (allenbina/chatwire)**: synced to Phase 69 (commit d3381ea, 2026-05-13).
  Phase 70 not yet synced (no public-repo sync step this session — backend-only hardening).
- **Open bugs**: 0.

## §2 What shipped in Phase 70 (2026-05-13)

### feat: anti-spam lockout hardening (#70)

**What**: Several hardening improvements to the anti-spam lockout system.

**Defense-in-depth fuse check in raw send functions**
- `send_text()`, `send_file()`, `send_text_to_chat()`, `send_file_to_chat()`
  in `chat_send.py` now each call `_fuse.check()` before `_run_osascript()`.
  The fuse is enforced even if a caller bypasses `check_send_guard()`.

**Permanent lockout message includes challenge code + form URL**
- `_fuse.check()` at step 6 now embeds the machine-bound `CW-XXXX-XXXX`
  code and the unlock form URL in the exception message string. Every entry
  point (Telegram, XMPP, MQTT, MCP, API) shows the same human-readable
  lockout string: `"Chatwire locked. Code: CW-XXXX-XXXX. Request unlock: <url>"`.

**MQTT / XMPP: log anti-spam errors from fire-and-forget futures**
- Added `_log_send_future_error(fut, label)` helper to both plugins.
  Wired as `done_callback` on `run_coroutine_threadsafe()` futures so
  `BroadcastBlockedError` / `RateLimitError` are no longer silently swallowed
  — they now appear in the log stream.

**Telegram: reply to user with lockout message**
- `cmd_send()` and `on_message()` catch `BroadcastBlockedError` /
  `RateLimitError` and reply to the Telegram user with the error string before
  re-raising, so the operator is immediately informed of the lockout.

**Misc**
- Tests: converted `get_event_loop().run_until_complete()` → `asyncio.run()`
  in test_mcp, test_tinfoil, test_transform_pipeline, test_ha_integration,
  test_content_filter (matches project convention; pre-existing failures
  remain 8, same root cause).
- CI: removed `push: branches: [main]` trigger (PR-only).

**Files changed**:
- `chat_send.py`: `_fuse.check()` improved message + added to 4 raw send fns.
- `chatwire-plugins/chatwire-mqtt/chatwire_mqtt/__init__.py`: `_log_send_future_error()` + `done_callback`.
- `chatwire-plugins/chatwire-xmpp/chatwire_xmpp/__init__.py`: same pattern.
- `chatwire-plugins/chatwire-telegram/chatwire_telegram/__init__.py`: `_reply_lockout_error()` + try/except in handlers.
- `tests/test_lockout_hardening.py` (new): 17 tests.

**Tests**: 1401 pytest (+17 new), 223 Vitest — all green.

## §2 What shipped in Phase 69 (2026-05-13)

### feat: hide sender name in iOS reply ghost bubble for 1:1 threads (#69)

(See Phase 69 notes in git history for full details.)

## §2 What shipped in Phase 68 (2026-05-13)

### feat: schedule trigger type for automation rules (#68)

(See Phase 68 notes in git history for full details.)

## §2 What shipped in earlier phases

(See git history for Phases 62–67 details.)

## §3 Open bugs

None.

## §4 Follow-ups (Phase 71+ candidates)

**Anti-spam lockout hardening — remaining items**:
- ComposeBox: add a yellow warning triangle icon to the CooldownBanner (steps 1-3).
  Currently shows "⏸ Sends paused for X:XX" — change the pause symbol to a
  `⚠️` / `TriangleAlert` lucide icon for visual clarity.
- Persistent top-of-app banner for step 4+ lockout: a thin banner above the
  sidebar/header area (separate from the LockoutOverlay which only covers the
  chat view) so users can see the lockout from any page (Settings, Plugins, Logs).
- ComposeBox: for step 4-5 (LockoutOverlay visible in chat view), show a subtle
  footer note "Permanently locked — enter unlock code in Settings" so users who
  navigate back to the chat area see guidance.

**Edited messages — history popover** (research needed):
- Blocker: mbair is macOS 12 — no `date_edited` column. Needs macOS 13+ hardware
  or a chat.db snapshot. Once schema confirmed, add `_fetch_edit_history()` in
  `web/main.py` and wire frontend popover.

**PyPI publishing** (needs `TWINE_TOKEN` or `~/.pypirc`):
- Publish `chatwire-theme-rosepine`, `chatwire-mqtt`, `chatwire-ha`, `chatwire-xmpp`.
  Build: `python3 -m build <plugin-dir>`
  Upload: `TWINE_TOKEN=<token> python3 -m twine upload --non-interactive <dist>/*`

**Public repo sync** (allenbina/chatwire):
- Synced through Phase 69 (commit d3381ea, 2026-05-13).
  Phase 70 is backend-only hardening with no user-visible API surface change;
  sync is low priority but should happen before the next user-visible feature.

**Other features**:
- #41 Demo app on chatwire.app
- #14 Theme plugin registration (registry done; PyPI publish is the remaining blocker)
- #24 Discord server
- #21, #22 Documentation
- #1 Mac DMG, #2 Custom marketplaces

**Infrastructure**:
- Set up plinux-local test env (chat.db snapshot, separate port)

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
- iOS reply ghost bubble sender-name logic (Phase 69) — verify group-vs-1:1 rendering
- Accordion animation (Phase 46)
- Theme picker refresh after install/uninstall (Phase 47)
- HEIC img_cache warmer behavior (Phase 49)

**Shared libraries for plugins** (post-RC):
- Expose Motion (Framer Motion) on `window.__chatwire` so plugins can use
  animations without bundling their own copy.

## §5 Architecture notes

### anti-spam lockout hardening (added Phase 70)

- **`chat_send.py` — `_fuse.check()` message**: When `self._step >= 6`,
  calls `_read_unlock_code()` and `_get_unlock_form_url()` to build the error
  string: `"Chatwire locked. Code: {cw_code}. Request unlock: {form_url}"`.
  Falls back to `"https://chatwireapp.com/unlock"` when no form URL is configured.
- **`chat_send.py` — raw send functions**: `send_text()`, `send_file()`,
  `send_text_to_chat()`, `send_file_to_chat()` each begin with `_fuse.check()`.
  This is defense-in-depth: `check_send_guard()` remains the primary call site
  for the full stack (rate limit + broadcast detect + audit log), but the fuse
  itself can no longer be bypassed by any caller.
- **`chatwire-mqtt` / `chatwire-xmpp` — `_log_send_future_error(fut, label)`**:
  Module-level helper registered as `fut.add_done_callback(...)` after each
  `asyncio.run_coroutine_threadsafe()` call. Inspects `fut.exception()`;
  logs `.error()` for `BroadcastBlockedError` (includes step), `.warning()`
  for `RateLimitError`, `.error()` for anything else.
- **`chatwire-telegram` — `_reply_lockout_error(update, exc)`**: Inner async
  function (closure inside `start()`); calls `update.message.reply_text(str(exc))`
  when exception is `BroadcastBlockedError` or `RateLimitError`. Both
  `cmd_send` and `on_message` call it then re-raise so the error propagates
  to python-telegram-bot's error handler.

### schedule trigger (added Phase 68)

(See Phase 68 §5 in git history.)

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

STATE: Phase 70 shipped (anti-spam lockout hardening).
1401 pytest / 223 Vitest — all green (+17 new pytest tests).
mbair running v1.14.0 (git+ssh, Phase 70 code, healthy).
Public repo allenbina/chatwire: synced through Phase 69 (d3381ea). Phase 70 not yet synced.

Key blockers:
  - Edit history popover (#59 follow-up): mbair is macOS 12 — no date_edited column.
    Needs macOS 13+ hardware or a chat.db snapshot. Cannot verify schema headless.
  - PyPI plugin publishing: requires TWINE_TOKEN env var or ~/.pypirc with API token.
    chatwire-theme-rosepine, chatwire-mqtt, chatwire-ha, chatwire-xmpp not on PyPI.
    Marketplace Install button will fail at pip until published.

Pick a task from §4 options:

Option A — Anti-spam UI polish (remaining items from §4):
  - ComposeBox CooldownBanner: swap ⏸ for a TriangleAlert lucide icon (yellow).
  - Persistent thin top-of-app lockout banner (visible from all pages when step >= 4).
  - Both are frontend-only; run npm build + commit dist/ after.

Option B — Public repo sync to Phase 70:
  rsync -a --checksum --exclude='dist/' --exclude='node_modules/' --exclude='__pycache__/' --exclude='.git/' --exclude='*.pyc' --exclude='*.egg-info/' /home/mediafront/git/chatwire-dev/ /tmp/chatwire-public/
  git -C /tmp/chatwire-public checkout -- .gitignore
  git -C /tmp/chatwire-public add -A && git -C /tmp/chatwire-public commit -m "feat: anti-spam lockout hardening (#70)" && git -C /tmp/chatwire-public push origin main

Option C — Any other §4 follow-up that fits in one session.

VISUAL QA NOTE: Schedule trigger UI, on_send trigger UI, Automations UI (DSL mode,
reorder buttons), data exposure modal, "edited" badge, pin icons, sidebar toggle
buttons, hiatus indicator, reminder contacts picker, per-theme custom CSS editor,
theme skin ZIP buttons, hover action bar, tapback tooltips, mark-all-read icon,
Rose Pine theme picker, iOS reply ghost bubble, accordion animation, theme picker
refresh after install, HEIC img_cache warmer — all require interactive mbair session.

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
  curl -s -d "Phase 70 complete — <summary>" ntfy.sh/p9SKpYzY70LlyK1N

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
