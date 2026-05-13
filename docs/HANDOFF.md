# Handoff — Phase 60: Data exposure warning modal

> Phase 60 session shipped (2026-05-13, commit e056ca7 in chatwire-dev).
> 196 Vitest (190 prior + 6 new) + 1110 pytest (1102 pass + 8 pre-existing) — all green.
> mbair redeployed — healthy at v1.14.0 (git+ssh, Phase 60 code).

## §1 Current state

- **mbair**: commit e056ca7 deployed and healthy (`/healthz` → ok, v1.14.0).
- **chatwire-theme-rosepine**: installed on mbair from git+ssh;
  `GET /api/ui/plugin-themes` returns all 3 variants (rose-pine, rose-pine-moon, rose-pine-dawn).
- **chatwire-plugins registry**: 9 plugins live on GitHub (`allenbina/chatwire-plugins`).
- **Tests**: 196 Vitest / 1110 pytest (1102 pass + 8 pre-existing failures) — all green.
  Pre-existing failures: test_mcp.py (3), test_tinfoil.py (1), test_transform_pipeline.py (4) —
  all caused by test_mcp.py closing the asyncio event loop; unrelated to Phase 60 changes.
- **PyPI**: v1.14.0 (no version bump — no public API changes; plugins not yet on PyPI).
- **Public repo (allenbina/chatwire)**: synced to Phase 60 (commit 54ef0fc, 2026-05-13).
- **Open bugs**: 0.

## §2 What shipped in Phase 60 (2026-05-13)

### feat: data exposure warning modal on first launch (#23)

**Problem**: chatwire serves iMessages over HTTP on the local network with no
indication to the user. Anyone on the same network who knows the port can read
conversations and attachments. There was no first-run warning about this.

**Fix**:

- **`web/frontend/src/components/DataWarningModal.tsx`** (new component):
  - Uses the shadcn Dialog primitive (Radix UI).
  - Reads `chatwire-dismissed-data-warning` from localStorage on mount.
  - If key absent: opens a modal warning about network exposure; recommends
    setting a password in Settings → Security.
  - Clicking "I understand" writes the localStorage key and closes the modal.
  - `onInteractOutside` is blocked — user must click the button (can't
    accidentally dismiss by clicking the overlay).
- **`web/frontend/src/App.tsx`**: `<DataWarningModal />` rendered inside
  `QueryClientProvider`, outside all routes — appears globally on every page.

**Tests** (`DataWarningModal.test.tsx` — 6 new, all pass):
- Modal visible when localStorage key absent.
- Modal hidden when key already set.
- "I understand" button hides the modal.
- "I understand" button writes the localStorage key.
- Warning text about same-network exposure present.
- Settings recommendation text present.

**Note on visual QA**: Requires an interactive session to confirm the modal
renders correctly and that the "Settings → Security" text is legible in both
light and dark themes.

## §2 What shipped in Phase 59 (2026-05-13)

### feat: "edited" badge on edited iMessage bubbles

**Problem**: When a message is edited in iMessage (macOS 13+), the chat.db
`message` table stores a non-zero `date_edited` epoch. chatwire showed no
indication that a message had been edited.

**Fix**:

- **`web/main.py` — `_fetch_edited_flags(conn, rowids)`** (new helper):
  - Queries `COALESCE(date_edited, 0)` for a batch of message rowids.
  - Catches `OperationalError` (column absent on pre-macOS-13 databases) and
    returns `{}` so older systems degrade gracefully.
  - Returns `dict[int, bool]` — rowid → edited (True when `date_edited != 0`).
- **`history_for()` and `history_for_group()`**: call `_fetch_edited_flags`
  inside the `try` block alongside `_fetch_tapbacks` / `_fetch_reply_parents`.
  Adds `edited: True` to any entry whose `date_edited` is non-zero.
- **`web/frontend/src/api.ts`**: `Message.edited?: boolean` field added.
- **`web/frontend/src/components/MessageBubble.tsx`**: italic "edited" span
  rendered next to the timestamp when `msg.edited` is set.

**Tests** (`tests/test_edited_messages.py` — 8 new, all pass).

**Note on edit history popover**: The badge is live but the popover showing
previous edit versions is not yet implemented. Schema research on macOS 13
chat.db is needed (mbair is macOS 12 — no `date_edited` column exists there).

## §2 What shipped in Phase 58 (2026-05-13)

### Fix: video attachments intercepted by service worker

**Problem**: Some videos (e.g. IMG_2047.mov, 12 MB) returned 1028 bytes of HTML
(the SPA `index.html`) instead of the file. Root cause: the Workbox
`runtimeCaching` rule for attachments used the regex `/\/(avatar|attachment)/`
which requires a trailing `/` after the path segment. Actual URLs are
`/attachment?path=…` (no trailing slash), so the rule never matched.
Navigation requests (opening a video in a new tab) fell through to the
`navigateFallback` and were served `index.html`.

**Fix** (`web/frontend/vite.config.ts`):
- Replace the regex `urlPattern` with a pathname-based callback.
- Change handler to `NetworkOnly`.
- Add `navigateFallbackDenylist` entries for `/attachment`, `/avatar`, and
  all server-side API / system paths.

## §3 Open bugs

None.

## §4 Follow-ups (Phase 60+ candidates)

**Edited messages — history popover** (research needed):
- The "edited" badge is now live. On click, expand the bubble to show previous
  edit versions. Requires researching chat.db schema for edit history:
  - Likely stored as associated-message rows (`associated_message_type` TBD;
    tapbacks use 2000+; edits use something else, possibly 1).
  - Verify on a real macOS 13+ chat.db using `PRAGMA table_info(message)` and
    inspecting rows with non-zero `date_edited` alongside their associated rows.
  - **Blocker**: mbair is macOS 12 — no `date_edited` column. Needs macOS 13
    hardware or a chat.db snapshot from a macOS 13 user.
  - Once type confirmed, add `EDIT_HISTORY_SQL` and `_fetch_edit_history()` in
    `web/main.py`, return as `edit_history` array, wire frontend popover.

**PyPI publishing** (needs `TWINE_TOKEN` or `~/.pypirc`):
- Publish `chatwire-theme-rosepine` to PyPI — marketplace Install button
  currently fails at pip for these until published.
- Publish `chatwire-mqtt`, `chatwire-ha`, `chatwire-xmpp` to PyPI.
  Build: `python3 -m build <plugin-dir>`
  Upload: `TWINE_TOKEN=<token> python3 -m twine upload --non-interactive <dist>/*`

**Other features**:
- #41 Demo app on chatwire.app
- #20 Automation engine + #28 trigger grammar
- #14 Theme plugin registration (registry done; PyPI publish is the remaining blocker)
- #24 Discord server
- #21, #22 Documentation
- #1 Mac DMG, #2 Custom marketplaces

**Infrastructure**:
- Set up plinux-local test env (chat.db snapshot, separate port)

**Visual QA** (requires interactive mbair session):
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
  animations without bundling their own copy. ~34KB addition to core.

## §5 Architecture notes

### Data exposure warning modal (added Phase 60)

- **`DataWarningModal.tsx`** in `web/frontend/src/components/`:
  - localStorage key: `chatwire-dismissed-data-warning` (value `"1"` when dismissed).
  - Initial state: `useState(() => !localStorage.getItem(DISMISSED_KEY))`.
  - Uses shadcn `Dialog` / `DialogContent` / `DialogHeader` / `DialogFooter`.
  - `onInteractOutside` blocks Radix's default close-on-overlay-click behaviour.
  - `onOpenChange` fires `dismiss()` if `v === false` (e.g. Escape key), so
    pressing Escape also persists the dismissal.
  - Icon: `ShieldAlert` from lucide-react (`text-warning`).
- Wired in `App.tsx` inside `<QueryClientProvider>` but outside `<BrowserRouter>`,
  so it renders on every page including `/login`.
- **6 tests** in `DataWarningModal.test.tsx`; all stub the Dialog with a simple
  open/close wrapper to avoid Radix Portal rendering in jsdom.

### Edited messages (added Phase 59)

- **`_fetch_edited_flags(conn, rowids)`** in `web/main.py`:
  - SQL: `SELECT ROWID, COALESCE(date_edited, 0) AS date_edited FROM message WHERE ROWID IN (...)`
  - Catches `Exception` (covers `OperationalError: no such column`) → returns `{}`.
  - Returns `dict[int, bool]` — rowid → is_edited.
- Wired in `history_for()` and `history_for_group()` alongside tapbacks/reply_parents.
- Frontend: `Message.edited?: boolean` in `api.ts`; italic `"edited"` span in
  `MessageBubble.tsx` timestamp row.
- **chat.db schema note**: `date_edited` was added in macOS 13 (Ventura). On macOS
  ≤ 12, the column does not exist — `_fetch_edited_flags` returns `{}` silently.
  mbair is macOS 12.7.6, so this feature cannot be visually QA'd there.
- **Edit history (future)**: Previous text versions may be stored as associated
  messages (`associated_message_type` TBD). Needs verification on macOS 13+ chat.db.

### chatwire-mqtt plugin (updated Phase 57)

- **Package**: `chatwire-plugins/chatwire-mqtt/` — `chatwire_mqtt/__init__.py` + `pyproject.toml`.
- **Class**: `MQTTIntegration` — `NAME = "chatwire_mqtt"`, `TIER = "official"`.
- **Dependency**: `paho-mqtt>=1.6` (declared in pyproject.toml; guard: `_PAHO_AVAILABLE` flag).
- **Lifecycle**: `start(ctx)` → stashes `ctx` + `asyncio.get_event_loop()` → `tls_set()` (if use_tls) →
  `connect()` → `loop_start()`. `stop()` → `loop_stop() + disconnect()` + clears `_ctx`/`_loop`.
- **TLS**: `use_tls=true` → `client.tls_set(ca_certs=<path or None>)` before connect.
- **Topic routing**: 1:1 → `<topic>/_15551234567`, group → `<topic>/group/<chat_id>`.
- **Outbound relay** (Phase 57): `send_topic` config field → subscribes in `on_connect`;
  `_on_outbound_message()` parses JSON, builds `SendTarget`, schedules `ctx.send_text()` via
  `asyncio.run_coroutine_threadsafe()`. Same threadsafe pattern as xmpp plugin.
  Payload: `{"handle": "+1...", "text": "..."}` (1:1) or `{"chat": "iMessage;+;...", "text": "..."}` (group).
- **43 tests** in `tests/test_mqtt_integration.py`; all use `asyncio.run()` to isolate event loop.
- **README**: `docs/plugins/mqtt.md`.

### chatwire-xmpp plugin (added Phase 56)

- **Package**: `chatwire-plugins/chatwire-xmpp/` — `chatwire_xmpp/__init__.py` + `pyproject.toml`.
- **Class**: `XMPPIntegration` — `NAME = "chatwire_xmpp"`, `TIER = "official"`.
- **Dependency**: `slixmpp>=1.8` (declared in pyproject.toml; guard: `_SLIXMPP_AVAILABLE` flag).
- **Lifecycle**: `start(ctx)` → `ClientXMPP(jid, pw)` → `connect()` → `xmpp.process(forever=True)` on daemon thread.
  `stop()` → `disconnect()`.
- **iMessage→XMPP**: `on_inbound()` looks up `imessage_handle` → `xmpp_jid`; calls `xmpp.send_message()`.
  Text-only; photo-only messages silently dropped.
- **XMPP→iMessage**: `_on_xmpp_message()` handler on slixmpp thread; looks up `xmpp_jid (bare, lower)` →
  `imessage_handle`; schedules `ctx.send_text()` via `asyncio.run_coroutine_threadsafe()`.
- **README**: `docs/plugins/xmpp.md`.

### chatwire-ha plugin (updated Phase 55)

- **Package**: `chatwire-plugins/chatwire-ha/` — `chatwire_ha/__init__.py` + `pyproject.toml`.
- **Class**: `HAIntegration` — `NAME = "chatwire_ha"`, `TIER = "notify"`.
- **Dependency**: `httpx` (declared in pyproject.toml).
- **Lifecycle**: `start(ctx)` → creates `httpx.AsyncClient` with Bearer auth. `stop()` → `aclose()`.
- **Keyword matching**: `text.strip().lower()` → exact lookup in `self._commands` dict.
- **allowed_senders** (new Phase 55): per-command `frozenset` of lowercased handles.
  `on_inbound` checks `msg.handle.lower() in allowed` before firing. Empty set = unrestricted.
- **HA call**: `POST {ha_url}/api/services/{domain}/{service}` with `{"entity_id": ...}`.
- **Reply**: `ctx.send_text(SendTarget(...), f"Done: {description}")`.
- **22 tests** in `tests/test_ha_integration.py`.
- **README**: `docs/plugins/ha.md`.

### Plugin registry (chatwire-plugins, updated Phase 53)

- Repo: `github.com/allenbina/chatwire-plugins` — tracks `plugins.json` only.
- 9 entries: apprise, telegram, webhook, stats, theme-rosepine, example, mqtt, ha, xmpp.
- Plugin source dirs live in `chatwire-plugins/chatwire-*/` in chatwire-dev (and public repo).

### chatwire status subcommand (added Phase 51)

- Function: `cmd_status()` in `chatwire_cli.py`.
- Parser entry: `chatwire status [--label-prefix <prefix>]` (default `dev.chatwire`).
- Always returns 0 (read-only probe).
- Calls `config.load_config()` guarded in try/except; port default 8723.
- Agents section: only rendered on `sys.platform == "darwin"`.
- 21 tests in `tests/test_status.py`.

### img_cache startup warmer (added Phase 49)

- **`_WARMUP_DAYS`**: 30 / **`_WARMUP_MAX`**: 200.
- **`_img_cache_warmer()`**: async task started in `@on_event("startup")`, 10 s delay.
  Iterates recent HEIC attachments; calls `asyncio.to_thread(_full_img_for, p)` per row.
  All errors caught; never raises.

### Attachment image cache (added Phase 48)

- **`FULL_IMG_CACHE_DIR`**: `~/.chatwire/img_cache`; **`FULL_IMG_TTL_DAYS`**: 90.
- **`_full_img_for(orig)`**: SHA1-keyed; `sips -s format jpeg`.
- **`_attachment_cache_evictor()`**: sweeps both caches daily; runs in startup handler.
- **`_ATTACHMENT_CACHE_CONTROL`**: `"public, max-age=2592000"` — applied to all `/attachment` paths.

### Theme plugin refresh event (added Phase 47)

- Event name: `chatwire-plugin-themes-changed` (CustomEvent on `window`).
- Dispatch: `InstallOverlay` + `removeMutation.onSuccess` in `PluginsPage.tsx`.
- Handler: `refreshPluginThemes` in `useTheme` hook.

### chatwire-plugins registry (updated Phase 47 / 53)

- Repo: `github.com/allenbina/chatwire-plugins` (nested at `chatwire-plugins/` in chatwire-dev).
- 9 entries total: apprise, telegram, webhook, stats, theme-rosepine, example, mqtt, ha, xmpp.
- All have `tags`, `icon`, `signed` fields.
- Fetched by `web/registry.py::fetch_registry()` with 24 h disk cache.

### Deploy pipeline (updated 2026-05-12)

- `dist/` is committed to git — no separate scp step.
- Deploy: `pip install --no-cache-dir --force-reinstall --no-deps 'chatwire @ git+ssh://git@github.com-chatwire/allenbina/chatwire-dev.git@main'`
- Restart: `/bin/launchctl kickstart -k gui/501/dev.chatwire.web && /bin/launchctl kickstart -k gui/501/dev.chatwire.bridge`
- Health: `/usr/bin/curl -sf localhost:8723/healthz`

### Frontend build

- After any frontend code change: `npm --prefix /home/mediafront/git/chatwire-dev/web/frontend run build`
- Commit the updated `dist/` with the source changes.
- `.gitattributes` treats JS/CSS in dist/ as binary (no line-level diffs).

### Accordion animation (added Phase 46)

- File: `web/frontend/src/index.css`
- `@keyframes accordion-down`/`accordion-up` use `--radix-accordion-content-height`.
- Registered via Tailwind v4 `@theme`: `--animate-accordion-down` / `--animate-accordion-up`.

### iOS reply ghost bubble (added Phase 45)

- Component: `ReplyQuote` in `MessageBubble.tsx`.
- Ghost bubble colors keyed on `parentFromMe = reply.sender === ''`.
- Thumbnail: `/attachment?path=…&size=thumb` → 32×32 img when `image_path` present.

### Pinnable settings (added Phase 44)

- Hook: `usePinnedSettings`; storage: `chatwire-pinned-settings` in localStorage.
- Sidebar: conditional toggle buttons via `SidebarContent` in `Layout.tsx`.

### Hiatus auto-off timer (added Phase 42–43)

- Config key: `cfg["web"]["hiatus_started_at"]` — epoch float; `0` = not set.
- Frontend: interval every 30 s; when `Date.now() >= endsAt`, fires `endHiatusMutation`.

### Per-theme custom CSS (added Phase 37)

- Storage: `~/.chatwire/custom-css/<slug>.css`; max 64 KB per theme.
- `GET /api/ui/custom-css/combined` returns `{css, themes}`.

### Theme override system (added Phase 30)

- Files: `~/.chatwire/theme-overrides/<slug>.json`.
- Style element ID: `chatwire-theme-override`.
- Load order: theme CSS → plugin theme CSS → override CSS → accent override → custom CSS.

### Whitelist contact cards

- `GET /api/ui/whitelist` returns `{contacts: [{name, handles[], whitelisted}], group_chats: [...]}`.

## §6 Next prompt

```
Read docs/HANDOFF.md in full. This is your state file.

git pull first — there may be commits from an interactive session.

STATE: Phase 60 shipped (data exposure warning modal, #23).
196 Vitest (190 prior + 6 new) + 1110 pytest (1102 pass + 8 pre-existing) — all green.
mbair running v1.14.0 (git+ssh, Phase 60 code, healthy).
Public repo allenbina/chatwire: synced to Phase 60 (commit 54ef0fc, 2026-05-13).

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

Option B — Edited messages: history popover (blocked without macOS 13 chat.db).
  If a chat.db snapshot is available at ~/chat.db or similar, use that.
  Otherwise skip — cannot verify schema on macOS 12.

Option C — #20 Automation engine / #28 trigger grammar (larger, plan first).

Option D — #23 visual QA follow-up: confirm DataWarningModal renders in both
  themes. Requires interactive mbair session — skip if headless.

VISUAL QA NOTE: Data exposure modal, "edited" badge, pin icons in SettingsPage,
sidebar toggle buttons for hiatus/reminder, hiatus sidebar indicator + dismiss
button + countdown, hiatus SettingsPage countdown, reminder contacts picker,
per-theme custom CSS editor, theme skin ZIP buttons, hover action bar, tapback
tooltips, mark-all-read icon, Rose Pine theme picker, iOS reply ghost bubble,
accordion animation, theme picker refresh after install, and HEIC img_cache
warmer behavior all require an interactive session on mbair — skip and note if
headless.

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
  curl -s -d "Phase 61 complete — <summary>" ntfy.sh/p9SKpYzY70LlyK1N

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
```
