# Handoff — Phase 72: LockoutTopBanner test coverage

> Phase 72 session shipped (2026-05-13, commit 669928e).
> 1409 pytest / 228 Vitest — all green.
> mbair still running v1.14.0 (git+ssh, Phase 71 code, healthy — no code changes this phase).

## §1 Current state

- **mbair**: commit b55ce4a (Phase 71) deployed and healthy (`/healthz` → ok, v1.14.0).
  Phase 72 was test-only; no new code deployed.
- **chatwire-theme-rosepine**: installed on mbair from git+ssh;
  `GET /api/ui/plugin-themes` returns all 3 variants.
- **chatwire-plugins registry**: 9 plugins live on GitHub (`allenbina/chatwire-plugins`).
- **Tests**: 1409 pytest / 228 Vitest — all green.
- **PyPI**: v1.14.0 (plugins not yet on PyPI).
- **Public repo (allenbina/chatwire)**: synced through Phase 71 (commit a512f34, 2026-05-13).
  Phase 72 is test-only; public sync not required.

## §2 What shipped in Phase 72 (2026-05-13)

### test: LockoutTopBanner — 5 Vitest tests (#72)

Added a new `describe('Layout — LockoutTopBanner')` block to
`web/frontend/src/components/Layout.test.tsx`:

- Shows banner with "cooling down" message when `locked=true, step=4`.
- Shows "permanently locked" message when `step=6`.
- Hidden when `locked=false`.
- Hidden when `step < 4` (even if `locked=true`).
- Contains a `"Settings"` link when shown.

Also added two helpers (`stubFetchWithFuse`, `renderLayoutFuse`) that stub
global `fetch` to return a configurable `FuseStatusStub` payload at
`/api/ui/fuse-status`.

Vitest count: 223 → 228 (+5). All pass.

## §2 What shipped in Phase 71 (2026-05-13)

### feat: anti-spam UI polish (#71)

**ComposeBox CooldownBanner (steps 1-3)**
- Replaced the `⏸` pause symbol with a `TriangleAlert` lucide icon (amber,
  `w-4 h-4 flex-shrink-0`) for visual clarity.
- The icon renders inline with the "Sends paused for X:XX" text via
  `flex items-center gap-1.5`.

**Layout — persistent LockoutTopBanner (steps 4+)**
- New `LockoutTopBanner` component at the top of every `Layout` page
  (above sidebar + main content area).
- Polls `fuse-status` every 30 s; shows a thin destructive-tinted bar
  with `TriangleAlert` icon and a "Settings" link when step ≥ 4.
- Step 4-5 message: "Outbound messaging locked — cooling down. Check Settings for details."
- Step 6 message: "Outbound messaging permanently locked — enter unlock code in Settings to restore."
- Layout outer div changed `flex` → `flex flex-col`; sidebar + main
  wrapped in `flex flex-1 min-h-0 overflow-hidden` — no visual change
  for the non-lockout case.
- `data-testid="lockout-top-banner"` for future test targeting.

**fix: update unlock fallback URL**
- `chatwireapp.com/unlock` → `chatwire.app/unlock` in `chat_send.py`,
  `LockoutOverlay.tsx`, and `test_lockout_hardening.py`.

## §2 What shipped in earlier phases

(See git history for Phases 62–70 details.)

## §3 Open bugs

None.

## §4 Follow-ups (Phase 73+ candidates)

**Anti-spam lockout — remaining UI items**:
- ComposeBox: for step 4-5 (LockoutOverlay visible in chat view), show a subtle
  footer note "Permanently locked — enter unlock code in Settings" so users who
  navigate back to the chat area see guidance.
  (Note: LockoutTopBanner partially addresses this now via persistent banner.)

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
- #14 Theme plugin registration (registry done; PyPI publish is the remaining blocker)
- #24 Discord server
- #21, #22 Documentation
- #1 Mac DMG, #2 Custom marketplaces

**Infrastructure**:
- Set up plinux-local test env (chat.db snapshot, separate port)
- Public repo sync for Phase 72 (test-only — low priority; sync when next code phase ships)

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
- LockoutTopBanner (Phase 71) — verify it renders correctly on Settings/Plugins/Logs pages.
- CooldownBanner TriangleAlert icon (Phase 71) — verify icon renders in compose area.

**Shared libraries for plugins** (post-RC):
- Expose Motion (Framer Motion) on `window.__chatwire` so plugins can use
  animations without bundling their own copy.

## §5 Architecture notes

### LockoutTopBanner test helpers (added Phase 72)

- `stubFetchWithFuse(fuseStatus)` — stubs global `fetch` returning a full
  `FuseStatusStub` at `/api/ui/fuse-status` plus standard hiatus/auth stubs.
- `renderLayoutFuse(fuseStatus)` — wraps `Layout` in `QueryClientProvider` +
  `MemoryRouter` with the fuse-status stub active.
- `FuseStatusStub` interface: `{ locked, step, cooldown_remaining_s, unlock_code }`.
- Located in `Layout.test.tsx` above the `LockoutTopBanner` describe block.

### anti-spam UI polish (added Phase 71)

- **`ComposeBox.tsx` — `CooldownBanner`**: `TriangleAlert` icon from lucide-react
  replaces the `⏸` emoji. Renders as `<TriangleAlert className="w-4 h-4 flex-shrink-0">`.
- **`Layout.tsx` — `LockoutTopBanner`**: standalone component querying
  `['fuse-status']` (shared cache). `refetchInterval: 30_000` ensures the
  banner disappears within ~30 s after lockout clears (user stays on Settings etc.).
  Layout outer div: `flex flex-col h-screen w-screen overflow-hidden`.
  Inner app shell div: `flex flex-1 min-h-0 overflow-hidden`.

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

STATE: Phase 72 shipped (LockoutTopBanner test coverage — 5 new Vitest tests).
1409 pytest / 228 Vitest — all green.
mbair running v1.14.0 (git+ssh, Phase 71 code, healthy — Phase 72 was test-only).
Public repo allenbina/chatwire: synced through Phase 71 (commit a512f34).
  Phase 72 test-only — sync whenever next code phase ships.

Key blockers:
  - Edit history popover (#59 follow-up): mbair is macOS 12 — no date_edited column.
    Needs macOS 13+ hardware or a chat.db snapshot. Cannot verify schema headless.
  - PyPI plugin publishing: requires TWINE_TOKEN env var or ~/.pypirc with API token.
    chatwire-theme-rosepine, chatwire-mqtt, chatwire-ha, chatwire-xmpp not on PyPI.
    Marketplace Install button will fail at pip until published.

Pick a task from §4 options:

Option A — ComposeBox lockout footer note (step 4-5 guidance):
  - When fuse step 4-5 and LockoutOverlay is shown, add a subtle footer
    in the compose area: "Messaging locked — enter unlock code in Settings".
  - Requires checking how LockoutOverlay and ComposeBox interact in ChatPage.
  - Add Vitest tests in ComposeBox.test.tsx covering the new footer note.

Option B — Public repo sync + any other §4 follow-up that fits in one session.

VISUAL QA NOTE: LockoutTopBanner, CooldownBanner icon, all prior items — all
require interactive mbair session.

Run: python3 -m pytest /home/mediafront/git/chatwire-dev/tests/ --tb=short -q
Run: npm --prefix /home/mediafront/git/chatwire-dev/web/frontend test -- --run
After frontend changes: npm --prefix /home/mediafront/git/chatwire-dev/web/frontend run build
Commit dist/ with source changes.
All tests must pass before committing.

DEPLOY (only needed if code changed):
  ssh mbair "~/.local/pipx/venvs/chatwire/bin/python -m pip install --no-cache-dir --force-reinstall --no-deps 'chatwire @ git+ssh://git@github.com-chatwire/allenbina/chatwire-dev.git@main'"
  ssh mbair "/bin/launchctl kickstart -k gui/501/dev.chatwire.web && /bin/launchctl kickstart -k gui/501/dev.chatwire.bridge"
  ssh mbair "/usr/bin/curl -sf localhost:8723/healthz"

After work — commit, push, deploy (if code changed), sync public repo, and notify:
  curl -s -d "Phase 72 complete — <summary>" ntfy.sh/p9SKpYzY70LlyK1N

Public repo sync (after future code phases):
  rsync -a --checksum --exclude='dist/' --exclude='node_modules/' --exclude='__pycache__/' --exclude='.git/' --exclude='*.pyc' --exclude='*.egg-info/' /home/mediafront/git/chatwire-dev/ /tmp/chatwire-public/
  git -C /tmp/chatwire-public checkout -- .gitignore
  git -C /tmp/chatwire-public add -A && git -C /tmp/chatwire-public commit -m "..." && git -C /tmp/chatwire-public push origin main

NOTE: Run pytest as: python3 -m pytest /home/mediafront/git/chatwire-dev/tests/ --tb=short -q
NOTE: npm test command works — use: npm --prefix /home/mediafront/git/chatwire-dev/web/frontend test -- --run
NOTE: All 1409 pytest tests pass. 228 Vitest tests pass.
NOTE: Tests mirror web/main.py helpers locally (never import web.main directly —
  module-level side-effects and Python-3.10+ annotation syntax breaks on Python 3.8).
NOTE: mbair is macOS 12.7.6 — date_edited column does not exist in chat.db there.
  Edit history feature verification requires macOS 13+ hardware or a DB snapshot.
NOTE: Python 3.8 on plinux — use nested with statements (not parenthesized form)
  in test files. No walrus operator (:=), no match statements.
NOTE: Use asyncio.run() in new test files (not asyncio.get_event_loop().run_until_complete).
```
