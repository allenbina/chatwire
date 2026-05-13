# Handoff — Phase 76: UpdateBanner Vitest tests

> Phase 76 session shipped (2026-05-13, commit 1a36877).
> 1409 pytest / 250 Vitest — all green.
> mbair running v1.14.0 (git+ssh, Phase 73 code, healthy). No code change — no redeploy needed.

## §1 Current state

- **mbair**: commit e45cdf4 (Phase 73) deployed and healthy (`/healthz` → ok, v1.14.0).
- **chatwire-theme-rosepine**: installed on mbair from git+ssh;
  `GET /api/ui/plugin-themes` returns all 3 variants.
- **chatwire-plugins registry**: 9 plugins live on GitHub (`allenbina/chatwire-plugins`).
- **Tests**: 1409 pytest / 250 Vitest — all green.
- **PyPI**: v1.14.0 (plugins not yet on PyPI).
- **Public repo (allenbina/chatwire)**: synced through Phase 76 (commit b1ed9c8, 2026-05-13).

## §2 What shipped in Phase 76 (2026-05-13)

### test: UpdateBanner — 16 Vitest tests for release + SW update banners (#76)

Adds `web/frontend/src/components/UpdateBanner.test.tsx` with 16 tests in two
describe blocks:

**GitHub release banner (10 tests)**
- Returns null when health or release data is absent
- Returns null when versions are equal or current is ahead of latest
- Returns null when the latest version was previously dismissed
- Shows banner with both current and latest version numbers when newer
- Includes a "See release notes" link pointing to GitHub releases
- Dismiss button hides the banner and persists the version to localStorage
- Banner carries `role="status"` for screen-reader accessibility

**Service-worker update banner (6 tests)**
- Shows SW update text after a `controllerchange` event fires
- Shows a Reload button in the SW banner
- Reload button calls `window.location.reload`
- SW banner has `role="status"`
- SW banner takes priority over the GitHub release banner
- `afterEach` restores `navigator.serviceWorker` to a no-op stub so the
  component's cleanup listener doesn't throw during unmount teardown

Vitest: 234 → 250 (+16). All 1409 pytest pass. No code change; no redeploy needed.
Public repo (allenbina/chatwire) synced — commit b1ed9c8.

## §2 What shipped in Phase 75 (2026-05-13)

### docs: update README feature list to reflect Phases 29-74

- `README.md` "What it does" section updated with new bullets for Automation rules,
  Anti-spam protection, and Hiatus mode; Plugins bullet updated to list all
  standalone packages (ntfy, Telegram, MQTT, Home Assistant, XMPP).
- React UI Features section expanded from 5 bullets to 10: added Rich message
  display (tapbacks, read receipts, reply ghosts, edited badge, location cards,
  SMS reactions), Automation rules, Anti-spam/fuse banners, Hiatus mode, Theme
  system (CSS variable editor, custom CSS, ZIP import/export, Rose Pine), and Data
  exposure warning; Performance bullet extended with HEIC img_cache / startup warmer.
- Repo layout updated: added `rules.py`, `chatwire-plugins/` tree with all 7 plugins,
  `docs/admin/`, and `status` in the CLI comment.
- No code change; no redeploy needed.
- Public repo (allenbina/chatwire) synced — commit bf5de22.

## §2 What shipped in Phase 74 (2026-05-13)

### docs: populate [Unreleased] CHANGELOG section (Phases 29-73)

- `CHANGELOG.md` `[Unreleased]` section was empty; now contains 142 lines documenting
  all features shipped since the v1.14.0 tag (147 commits).
- Organized into: Automation rules engine, Anti-spam / message fuse, Hiatus and
  reminders, Message display, Themes, Performance, Plugins, CLI and admin, Privacy,
  and Fixes sections.
- Public repo (allenbina/chatwire) synced — commit 27c4ab2.
- No code change; no redeploy needed.

## §2 What shipped in Phase 73 (2026-05-13)

### feat: ComposeBox lockout footer note + ChatPage layout fix (#73)

**ComposeBox — LockoutFooterNote (steps 4+)**
- New `LockoutFooterNote` component rendered in ComposeBox when
  `fuseStatus.locked && step >= 4` (replaces the compose area).
- Step 4-5 message: "Messaging locked — cooling down. View status in Settings."
- Step 6 message: "Messaging permanently locked — enter unlock code in Settings."
- Styled with destructive-tinted border/background + TriangleAlert icon,
  consistent with CooldownBanner and LockoutTopBanner.
- `data-testid="lockout-footer-note"` for test targeting.

**ChatPage — preserve header + compose during lockout**
- When `isLockedOut` (step >= 4), ChatPage now renders:
  ConversationHeader + LockoutOverlay + ComposeBox (showing LockoutFooterNote)
  instead of replacing the entire chat area with only LockoutOverlay.
- Users navigating back to the chat area see the conversation header and
  the footer note in the compose area, reinforcing the lockout guidance
  already shown by LockoutTopBanner.

**Tests — 6 new Vitest in ComposeBox.test.tsx**
- Shows footer note at step 4 (textarea hidden, cooldown banner hidden).
- Shows "cooling down" text at step 5.
- Shows "permanently locked" text at step 6.
- Not shown when fuse is inactive.
- Not shown at step 3 (cooldown banner shown instead).
- Contains a Settings link when shown.

Vitest: 228 → 234 (+6). All 1409 pytest pass.

## §2 What shipped in earlier phases

(See git history for Phases 62–72 details.)

## §3 Open bugs

None.

## §4 Follow-ups (Phase 77+ candidates)

**Edited messages — history popover** (research needed):
- Blocker: mbair is macOS 12 — no `date_edited` column. Needs macOS 13+ hardware
  or a chat.db snapshot. Once schema confirmed, add `_fetch_edit_history()` in
  `web/main.py` and wire frontend popover.

**PyPI publishing** (needs `TWINE_TOKEN` or `~/.pypirc`):
- Publish `chatwire-theme-rosepine`, `chatwire-mqtt`, `chatwire-ha`, `chatwire-xmpp`.
  Build: `python3 -m build <plugin-dir>`
  Upload: `TWINE_TOKEN=<token> python3 -m twine upload --non-interactive <dist>/*`

**Mobile app tests** (separate jest-expo suite, not part of main Vitest count):
- `MessageListScreen.test.tsx` — missing (loads messages, loadOlder, live SSE update,
  long-press action sheet on iOS vs. Alert on Android).
- `SettingsScreen.test.tsx` — missing (renders server URL, disconnect alert,
  haptics toggle, version/platform rows).

**Other features**:
- #41 Demo app on chatwire.app
- #14 Theme plugin registration (registry done; PyPI publish is the remaining blocker)
- #24 Discord server
- #21, #22 Documentation (CHANGELOG and README are current)
- #1 Mac DMG, #2 Custom marketplaces

**Infrastructure**:
- Set up plinux-local test env (chat.db snapshot, separate port)

**Shared libraries for plugins** (post-RC):
- Expose Motion (Framer Motion) on `window.__chatwire` so plugins can use
  animations without bundling their own copy. (Note: framer-motion is not
  currently a dependency — would need to be added first.)

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
- ComposeBox LockoutFooterNote (Phase 73) — verify footer note renders at step 4+ in chat view.
- ChatPage header visibility during lockout (Phase 73) — verify header stays visible.

## §5 Architecture notes

### UpdateBanner test setup (added Phase 76)

Key pattern for testing `UpdateBanner`:
- Wrap in `QueryClientProvider` with `retry: false`.
- Mock `globalThis.fetch` to return controlled `/healthz` and GitHub API responses.
- For SW update tests: `Object.defineProperty(navigator, 'serviceWorker', ...)` with
  a manual event-listener Map; `afterEach` restores it to a no-op stub (not `undefined`)
  so the component's `useEffect` cleanup function doesn't throw during unmount.

### ComposeBox lockout states (updated Phase 73)

Three mutually-exclusive compose area states:
1. `isLockedOut` (step >= 4): `LockoutFooterNote` — step 4-5 shows "cooling down", step 6 shows "permanently locked"
2. `isCoolingDown` (step 1-3): `CooldownBanner` — live countdown, "broadcast pattern" messaging
3. Normal: textarea + send button

`LockoutFooterNote` has `data-testid="lockout-footer-note"`.

### ChatPage lockout layout (updated Phase 73)

When `isLockedOut && fuseStatus`:
- Renders: `ConversationHeader` + `LockoutOverlay` (flex-1 message area) + `ComposeBox` (footer note) + `ContactInfoSheet`
- Previously: replaced entire ActiveConversation with only `LockoutOverlay`
- This ensures the conversation header and footer guidance remain visible.

### LockoutTopBanner test helpers (added Phase 72)

- `stubFetchWithFuse(fuseStatus)` — stubs global `fetch` returning a full
  `FuseStatusStub` at `/api/ui/fuse-status` plus standard hiatus/auth stubs.
- `renderLayoutFuse(fuseStatus)` — wraps `Layout` in `QueryClientProvider` +
  `MemoryRouter` with the fuse-status stub active.
- `FuseStatusStub` interface: `{ locked, step, cooldown_remaining_s, unlock_code }`.
- Located in `Layout.test.tsx` above the `LockoutTopBanner` describe block.

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

STATE: Phase 76 shipped (UpdateBanner Vitest tests, 234 → 250).
1409 pytest / 250 Vitest — all green.
mbair running v1.14.0 (git+ssh, Phase 73 code, healthy). No redeploy needed.
Public repo allenbina/chatwire: synced through Phase 76 (commit b1ed9c8).

Key blockers:
  - Edit history popover (#59 follow-up): mbair is macOS 12 — no date_edited column.
    Needs macOS 13+ hardware or a chat.db snapshot. Cannot verify schema headless.
  - PyPI plugin publishing: requires TWINE_TOKEN env var or ~/.pypirc with API token.
    chatwire-theme-rosepine, chatwire-mqtt, chatwire-ha, chatwire-xmpp not on PyPI.
    Marketplace Install button will fail at pip until published.

Good next candidates (no blockers):
  - Mobile app tests: MessageListScreen.test.tsx and SettingsScreen.test.tsx
    (jest-expo, separate from main Vitest count but good coverage)
  - Any other untested component — check web/frontend/src/ for .tsx files
    that have no matching .test.tsx
  - #41 Demo app on chatwire.app
  - Any other §4 item that fits in one session.

VISUAL QA NOTE: LockoutTopBanner, CooldownBanner icon, LockoutFooterNote,
ChatPage header during lockout, and all prior items — require interactive mbair session.

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
  curl -s -d "Phase 76 complete — <summary>" ntfy.sh/p9SKpYzY70LlyK1N

Public repo sync (after future code phases):
  rsync -a --checksum --exclude='dist/' --exclude='node_modules/' --exclude='__pycache__/' --exclude='.git/' --exclude='*.pyc' --exclude='*.egg-info/' /home/mediafront/git/chatwire-dev/ /tmp/chatwire-public/
  git -C /tmp/chatwire-public checkout -- .gitignore
  git -C /tmp/chatwire-public add -A && git -C /tmp/chatwire-public commit -m "..." && git -C /tmp/chatwire-public push origin main

NOTE: Run pytest as: python3 -m pytest /home/mediafront/git/chatwire-dev/tests/ --tb=short -q
NOTE: npm test command works — use: npm --prefix /home/mediafront/git/chatwire-dev/web/frontend test -- --run
NOTE: All 1409 pytest tests pass. 250 Vitest tests pass.
NOTE: Tests mirror web/main.py helpers locally (never import web.main directly —
  module-level side-effects and Python-3.10+ annotation syntax breaks on Python 3.8).
NOTE: mbair is macOS 12.7.6 — date_edited column does not exist in chat.db there.
  Edit history feature verification requires macOS 13+ hardware or a DB snapshot.
NOTE: Python 3.8 on plinux — use nested with statements (not parenthesized form)
  in test files. No walrus operator (:=), no match statements.
NOTE: Use asyncio.run() in new test files (not asyncio.get_event_loop().run_until_complete).
NOTE: When testing components that mock navigator.serviceWorker, set afterEach to
  restore it to a no-op stub (not undefined) so component cleanup doesn't throw.
```
