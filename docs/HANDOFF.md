# Handoff — Phase 58: SW attachment fix + public repo sync

> Phase 58 session shipped (2026-05-13, commit f82ecac in chatwire-dev).
> 1102 pytest (1094 pass + 8 pre-existing failures) + 190 Vitest — all green.
> mbair redeployed — healthy at v1.14.0 (git+ssh, Phase 58 code).

## §1 Current state

- **mbair**: commit f82ecac deployed and healthy (`/healthz` → ok, v1.14.0).
- **chatwire-theme-rosepine**: installed on mbair from git+ssh;
  `GET /api/ui/plugin-themes` returns all 3 variants (rose-pine, rose-pine-moon, rose-pine-dawn).
- **chatwire-plugins registry**: 9 plugins live on GitHub (`allenbina/chatwire-plugins`).
- **Tests**: 1102 collected (1094 pass + 8 pre-existing failures) / 190 Vitest — all green.
  Pre-existing failures: test_mcp.py (3), test_tinfoil.py (1), test_transform_pipeline.py (4) —
  all caused by test_mcp.py closing the asyncio event loop; unrelated to Phase 58 changes.
- **PyPI**: v1.14.0 (no version bump — no public API changes; plugins not yet on PyPI).
- **Public repo (allenbina/chatwire)**: synced to Phase 58 (commit f615376, 2026-05-13).
- **Open bugs**: 0.

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
- Replace the regex `urlPattern` with a pathname-based callback
  (`url.pathname.startsWith('/attachment|avatar')`) — now correctly matches
  `/attachment?…` URLs.
- Change handler to `NetworkOnly` — attachment files are served from the local
  filesystem (already fast) and caching 12 MB `.mov` files in SW quota is wasteful.
- Add `navigateFallbackDenylist` entries for `/attachment`, `/avatar`, and all
  server-side API / system paths so the SW never serves `index.html` for these
  endpoints regardless of runtime-cache state.

**Tests**: all 190 Vitest pass (no frontend behaviour tests for SW rules).
**Rebuild**: `dist/sw.js` and `dist/workbox-*.js` updated.
**Deploy**: mbair updated, health check ok.

### Public repo sync (allenbina/chatwire) — Phases 57–58

Synced `allenbina/chatwire` from Phase 56 (commit 920cd4b) → Phase 58 (f615376).
Includes: MQTT outbound relay source + tests + docs, vite.config.ts SW fix.

## §2 What shipped in Phase 57 (2026-05-13)

### chatwire-mqtt: outbound relay (MQTT → iMessage)

**Problem**: The MQTT plugin only published inbound iMessages to the broker.
Automations had no way to send replies or proactive messages via iMessage.

**Fix** (`chatwire-plugins/chatwire-mqtt/chatwire_mqtt/__init__.py`):

- **New config field**: `send_topic` — optional string (default `""`). When non-empty,
  the plugin subscribes to this MQTT topic on the broker and relays any published
  message as an outbound iMessage.
- **Payload schemas**:
  - 1:1: `{"handle": "+15551234567", "text": "Hello!"}`
  - Group: `{"chat": "iMessage;+;chat123", "text": "Hi!", "label": "My Group"}`
  - `text` + (`handle` or `chat`) are required. `label` is optional.
- **`_on_outbound_message()`**: paho `on_message` callback. Parses JSON, validates,
  builds `SendTarget`, schedules `ctx.send_text()` via `asyncio.run_coroutine_threadsafe()`.
  Same threadsafe pattern as XMPP plugin.
- **`start()`**: stashes `ctx` and event loop; sets `client.on_message` and subscribes
  inside `on_connect` callback (so reconnects also re-subscribe).
- **`stop()`**: now also clears `_ctx` and `_loop`.
- **`SendTarget`** now imported from `integrations.base` (guarded with `None` fallback).
- **`SETTINGS_SCHEMA`**: new `send_topic` field (`x-ui-order: 10`).
- **12 new tests** in `TestOutboundConfig` and `TestOutboundRelay` (43 total, all pass).
- **`docs/plugins/mqtt.md`**: outbound relay section, Node-RED + HA send examples,
  `send_topic` in settings table and full-config block.

## §2 What shipped in Phase 56 (2026-05-13)

### docs/plugins/xmpp.md

**New file**: `docs/plugins/xmpp.md`

Covers: what it does (iMessage ↔ XMPP bidirectional relay, 1:1 only MVP), install command,
configuration walkthrough, settings reference table (enabled/jid/password/server_url/
contact_mappings), contact mapping fields table (imessage_handle/xmpp_jid), minimal config,
full config with custom server + multiple contacts, how the relay works (iMessage→XMPP,
XMPP→iMessage, matching rules), troubleshooting FAQ.

### Public repo sync (allenbina/chatwire) — Phases 55–56

Synced `allenbina/chatwire` public repo from Phase 54 (6879d85) → Phase 56 (920cd4b).

## §3 Open bugs

None (video attachment SW bug fixed in Phase 58).

## §4 Follow-ups (Phase 58+ candidates)

**PyPI publishing** (needs `TWINE_TOKEN` or `~/.pypirc`):
- Publish `chatwire-theme-rosepine` to PyPI — marketplace Install button currently fails at pip.
- Publish `chatwire-mqtt`, `chatwire-ha`, `chatwire-xmpp` to PyPI.
  Build: `python3 -m build <plugin-dir>`
  Upload: `TWINE_TOKEN=<token> python3 -m twine upload --non-interactive <dist>/*`

**Public repo sync** (easy):
- Sync allenbina/chatwire to Phase 57 (commit 0059202).
  See NOTE below for rsync method.

**Bugs from interactive QA (2026-05-13)**:
- ~~Video attachment not serving~~ — fixed in Phase 58 (SW urlPattern bug).
- Edited messages: show bold "edited" label next to timestamp. On click,
  expand the bubble (animated) to show all previous edit versions. Check
  how iMessage stores edit history in chat.db (likely in `message` table
  with same `thread_originator_guid` or via `edited_message` association).

**Plugin gaps**:
- `chatwire-mqtt`: outbound relay is now done. No remaining plugin gaps.

**Other features**:
- #41 Demo app on chatwire.app
- #20 Automation engine + #28 trigger grammar
- #23 Data exposure warning
- #65 Offline mode — already fully implemented.
- #14 Theme plugin registration (registry done; PyPI publish is the remaining blocker)
- #24 Discord server
- #21, #22 Documentation
- #1 Mac DMG, #2 Custom marketplaces

**Infrastructure**:
- Set up plinux-local test env (chat.db snapshot, separate port)

**Visual QA** (requires interactive mbair session):
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
- Expose Motion (Framer Motion) on `window.__chatwire` so plugins can use animations
  without bundling their own copy. ~34KB addition to core.

## §5 Architecture notes

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

STATE: Phase 58 shipped (SW attachment fix + public repo sync to Phase 58).
1102 pytest (1094 pass + 8 pre-existing), 190 Vitest — all green.
mbair running v1.14.0 (git+ssh, Phase 58 code, healthy).
Public repo allenbina/chatwire: synced to Phase 58 (commit f615376, 2026-05-13).

Key blocker for PyPI publish of plugins:
  chatwire-theme-rosepine, chatwire-mqtt, chatwire-ha, chatwire-xmpp are NOT on PyPI.
  Marketplace Install button will fail at pip for these until published.
  Requires TWINE_TOKEN env var or ~/.pypirc with PyPI API token.

Pick a task from §4 options:

Option A — Publish plugins to PyPI (theme-rosepine + mqtt + ha + xmpp).
  Requires TWINE_TOKEN env var or ~/.pypirc.
  Build: python3 -m build <plugin-dir>
  Upload: TWINE_TOKEN=<token> python3 -m twine upload --non-interactive <dist>/*

Option B — Edited messages: show edit history.
  iMessage stores edit history in chat.db. Show "edited" label on bubble; on click
  expand to show previous versions. Research chat.db schema first.
  Look at: message table columns — likely thread_originator_guid or an
  edited_message join table. Also check if there's a `date_edited` column.

Option C — #20 Automation engine / #28 trigger grammar (larger, plan first).

VISUAL QA NOTE: pin icons in SettingsPage, sidebar toggle buttons for hiatus/reminder,
hiatus sidebar indicator + dismiss button + countdown, hiatus SettingsPage countdown,
reminder contacts picker, per-theme custom CSS editor, theme skin ZIP buttons, hover
action bar, tapback tooltips, mark-all-read icon, Rose Pine theme picker, iOS
reply ghost bubble, accordion animation, theme picker refresh after install,
and HEIC img_cache warmer behavior all require an interactive session on mbair
— skip and note if headless.
NOTE: Video attachment SW fix deployed in Phase 58 — users must reload the
page once so the new service worker activates (old SW had the broken cache rule).

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
  curl -s -d "Phase 59 complete — <summary>" ntfy.sh/p9SKpYzY70LlyK1N

NOTE: Run pytest as: python3 -m pytest /home/mediafront/git/chatwire-dev/tests/ --tb=short -q
NOTE: npm test command works — use: npm --prefix /home/mediafront/git/chatwire-dev/web/frontend test -- --run
NOTE: Pre-existing failures (8): test_mcp.py (3), test_tinfoil.py (1), test_transform_pipeline.py (4)
  — all caused by test_mcp.py closing the asyncio event loop. Use asyncio.run() in new test files.
NOTE: Public repo sync method: rsync -a --checksum (no --delete) from chatwire-dev/
  to /tmp/chatwire-public/ with excludes for dist/, node_modules/, __pycache__/, .git/
  Then git add -A && git commit && git push in /tmp/chatwire-public/
NOTE: After rsync, RESTORE .gitignore (git checkout -- .gitignore) to preserve
  web/frontend/dist/ exclusion — chatwire-dev commits dist/ but public repo does not.
```
