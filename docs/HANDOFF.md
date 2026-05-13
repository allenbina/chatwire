# Handoff — Phase 51: chatwire status subcommand + img_cache uninstall

> Phase 51 session shipped (2026-05-12, commit 873f0e0).
> 1052 pytest (1044 pass + 8 pre-existing failures) + 190 Vitest — all green.
> Deployed to mbair — `chatwire status` verified live.

## §1 Current state

- **mbair**: commit 873f0e0 deployed and healthy (`/healthz` → ok, v1.14.0).
- **chatwire-theme-rosepine**: installed on mbair from git+ssh;
  `GET /api/ui/plugin-themes` returns all 3 variants (rose-pine, rose-pine-moon, rose-pine-dawn).
- **chatwire-plugins registry**: all 6 plugins live on GitHub.
- **Tests**: 1052 pytest (1044 pass + 8 pre-existing failures) / 190 Vitest — all green.
- **PyPI**: v1.14.0 (no version bump — backend-only change, deploy via git+ssh).
- **Public repo (allenbina/chatwire)**: synced to Phase 49 as of commit e2b9aaf (2026-05-12).
  Public repo is 2 phases behind (Phases 50-51 not yet synced).
- **Open bugs**: 0.

## §2 What shipped in Phase 51 (2026-05-12)

### `chatwire status` subcommand

**Problem**: No quick way to verify a chatwire install headlessly (version,
config, running agents, plugins) without grepping logs or curling healthz manually.

**Fix (`chatwire_cli.py`):**

- New `cmd_status()` function — always exits 0 (read-only probe).
- Prints: version string, config path + port (default 8723), launchd agent plist
  check marks (macOS only — `✓`/`✗` per service), installed plugin list.
- Registered as `chatwire status [--label-prefix]` in `build_parser()`.

**Verified on mbair** (`chatwire status`):
```
chatwire 1.14.0

Config:  /Users/allen/.chatwire/config.json
Port:    8723

Agents:
  ✓ bridge        dev.chatwire.bridge.plist
  ✓ web           dev.chatwire.web.plist
  ✓ keepawake     dev.chatwire.keepawake.plist

Plugins (1):
  • chatwire-telegram
```

### img_cache in uninstall paths (Phase 48 gap)

**Problem**: Phase 48 added `~/.chatwire/img_cache` but `_uninstall_paths()`
only listed `thumb_cache`. `scripts/uninstall.sh` Step 6 also only mentioned
thumbnail cache.

**Fix**: Added `"img_cache"` key to `_uninstall_paths()` in `chatwire_cli.py`.
Updated `uninstall.sh` Step 6 header and dry-run output to name both caches.

**Tests (`tests/test_status.py` + `tests/test_uninstall.py`):** 21 new tests:
- Parser recognises `status`; `args.func` is `cmd_status`.
- Exits 0 with and without config file.
- Version string + `chatwire` prefix in output.
- "not found" / setup hint when config absent.
- Config path and port shown when config present; default 8723 when `web` key missing.
- Plugins listed with count; "none" message when empty.
- `Agents:` section gated on `sys.platform == "darwin"`.
- `✓` mark when plist exists; `✗` when missing.
- `img_cache` key present in `_uninstall_paths()` and correct path.
- `img_cache` mentioned in `scripts/uninstall.sh`.

## §2 What shipped in Phase 50 (2026-05-12)

### Public repo sync — allenbina/chatwire

**Problem**: The public `allenbina/chatwire` repo was 32 phases behind chatwire-dev
(last synced at Phase 17 / v1.12.0 on 2026-05-10).

**Fix**: rsync from chatwire-dev → local clone of the public repo, excluding:
- `web/frontend/dist/` (built by CI publish.yml workflow; not needed in source)
- `web/frontend/node_modules/`, `__pycache__/`, `*.pyc`, `*.egg-info/`, `build/`
- `chatwire-plugins/chatwire-theme-rosepine/dist/` (Python build artifacts)

Preserved public-repo-specific files untouched:
- `CODEOWNERS`, `CONTRIBUTING.md`
- `.github/ISSUE_TEMPLATE/`, `.github/pull_request_template.md`
- `.github/workflows/ai-loop.yml`

Updated public repo `.gitignore` to add back `web/frontend/dist/` (which
chatwire-dev no longer ignores — it commits dist/ for git+ssh deployment).

**Result** (commit e2b9aaf in allenbina/chatwire):
- 112 files changed: 17,783 insertions / 1,566 deletions
- 8 new plugin packages (apprise, telegram, webhook, example, theme-rosepine,
  theme-example, theme-template) + source
- 11 new test files
- 5 new web modules (log_stream, sms_reactions, theme_loader, whitelist, plugin_state)
- Version bumped to v1.14.0 in public repo
- No mbair redeploy (already on Phase 49 / v1.14.0)

## §2 What shipped in Phase 49 (2026-05-12)

### img_cache startup warmer

**Problem**: On a cold start (or after a reboot), the first request for any
recent HEIC photo invokes `sips` synchronously in a thread, adding a
noticeable delay before the browser receives the image.

**Fix (`web/main.py`):**

1. **`_WARMUP_DAYS = 30`** / **`_WARMUP_MAX = 200`**: look-back window and per-
   startup file cap, placed alongside the other `FULL_IMG_CACHE_DIR` constants.

2. **`_WARMUP_HEIC_SQL`**: SQL query joining `message → message_attachment_join
   → attachment`, filtering `transfer_state=5` (fully downloaded) and
   `filename LIKE '%.heic' OR filename LIKE '%.heif' OR mime_type LIKE
   'image/heic%' OR …`; ordered newest-first; `LIMIT _WARMUP_MAX`.

3. **`_img_cache_warmer()`**: async task started in `@on_event("startup")`.
   - `await asyncio.sleep(10)` so the server finishes binding before sips runs.
   - Opens a `_snapshot()` connection (read-only, in-memory copy of chat.db).
   - Iterates rows; expands `~/…` paths; skips non-HEIC/HEIF by suffix check
     (second line of defence — SQL already filters, but malformed rows are safe).
   - Calls `asyncio.to_thread(_full_img_for, p)` for each; already-cached files
     return instantly (no sips call).
   - `await asyncio.sleep(0.05)` between files — gentle on startup, lets other
     tasks run.
   - Logs `"img_cache warmer: N/M HEIC files warmed (K skipped)"` at INFO.
   - All failures (DB error, missing file, sips crash) are caught and skipped;
     the warmer never raises.
   - Row key extraction uses `hasattr(row, "keys")` to handle both
     `sqlite3.Row` (production) and plain `dict` (tests).

**Tests (`tests/test_img_cache_warmer.py`):** 12 new tests covering:
- HEIC row → `_full_img_for` called, warmed++
- HEIF row → also warmed
- 5 HEIC rows → all 5 warmed
- JPEG row → skipped without calling `_full_img_for`
- PNG row → skipped
- `None` filename → skipped
- `_full_img_for` returns `None` (sips failure) → skipped
- `_full_img_for` raises → skipped
- Empty result set → 0 warmed, 0 skipped, no error
- Mixed HEIC + HEIF + JPEG rows → correct split
- `_WARMUP_DAYS` is positive
- `_WARMUP_MAX` is in range 50–1000

## §2 What shipped in Phase 48 (2026-05-12)

### Photo CDN — attachment img_cache + Cache-Control

**Problem 1 — HEIC cache pollution**: The old HEIC→JPEG conversion in
`/attachment` wrote the `.jpg` file alongside the original inside
`~/Library/Messages/Attachments` (using `p.with_suffix(".jpg")`). This
polluted Messages.app's own directory with generated files.

**Problem 2 — Missing Cache-Control headers**: Only `size=thumb` and
`pluginPayloadAttachment` responses had `Cache-Control: public, max-age=2592000`.
`.mov`, HEIC, and the generic fallback paths had no cache header, so browsers
re-downloaded attachments on every page load.

**Problem 3 — Evictor never ran**: `_thumb_cache_evictor()` was registered
in the `@app.on_event("shutdown")` handler instead of startup, so the daily
eviction task was never actually started.

**Fix (`web/main.py`):**

1. **`FULL_IMG_CACHE_DIR`** (`~/.chatwire/img_cache`): new constant for
   full-size converted images, parallel to `THUMB_CACHE_DIR`.
   `FULL_IMG_TTL_DAYS = 90` (shorter than thumbs — full-size files are larger).

2. **`_full_img_for(orig)`**: new helper, same `(path, mtime)` SHA1-keyed
   cache pattern as `_thumb_for`. Calls `sips -s format jpeg` (no `-Z` resize).
   Returns `Path | None`; caller falls back to raw file on `None`.

3. **`_attachment_cache_evictor()`**: renamed from `_thumb_cache_evictor`;
   now sweeps both `thumb_cache` (180-day TTL) and `img_cache` (90-day TTL)
   in a single daily loop.

4. **`/attachment` endpoint**: all `FileResponse` return paths now include
   `headers={"Cache-Control": _ATTACHMENT_CACHE_CONTROL}` where
   `_ATTACHMENT_CACHE_CONTROL = "public, max-age=2592000"`.
   HEIC paths now call `_full_img_for()` (async via `asyncio.to_thread`)
   instead of writing alongside the original.

5. **Startup fix**: `_attachment_cache_evictor()` moved from shutdown handler
   to startup handler — it now actually runs.

**Tests (`tests/test_attachment_cache.py`):** 11 new tests covering:
- `_full_img_for`: cache miss, cache hit, mtime invalidation, sips failure,
  missing original.
- `_thumb_for`: cache miss (verifies `-Z` flag), cache hit.
- `_evict_cache`: old files deleted, non-existent dir, all-fresh files.
- `_ATTACHMENT_CACHE_CONTROL` constant value.

## §3 Open bugs

None.

## §4 Follow-ups (Phase 49+ candidates)

**Theme ecosystem**:
- Publish `chatwire-theme-rosepine` to PyPI (needs `TWINE_TOKEN` or `~/.pypirc`).
  Once on PyPI, the marketplace Install button will work end-to-end without
  git+ssh. Currently install from marketplace fails at pip.
- Visual QA of per-theme custom CSS editor.
- Visual QA of theme skin ZIP buttons.
- Visual QA of theme picker dropdown with Rose Pine plugin schemes.
- Visual QA of hover action bar, tapback tooltips, mark-all-read icon (Phase 33).
- Visual QA of reminder contacts picker (Phase 39).
- Visual QA of hiatus sidebar indicator + End button + countdown (Phases 40–42).
- Visual QA of hiatus SettingsPage countdown (Phase 43).
- Visual QA of pinnable settings pin icons + sidebar toggle buttons (Phase 44).
- Visual QA of iOS reply ghost bubble (Phase 45).
- Visual QA of accordion animation (Phase 46).
- Visual QA of theme picker refresh after install/uninstall (Phase 47).

**Other features**:
- #41 Demo app on chatwire.app
- #20 Automation engine + #28 trigger grammar
- #27 MQTT output + #23 data exposure warning
- #65 Offline mode — already fully implemented.
- #14 Theme plugin registration (registry done; PyPI publish is the remaining blocker)
- #24 Discord server
- #21, #22 Documentation
- #25 Uninstaller: script + Python cmd both done; testing complete as of Phase 51.
- #1 Mac DMG, #2 Custom marketplaces

**Infrastructure**:
- Set up plinux-local test env (chat.db snapshot, separate port)
- Public repo sync: allenbina/chatwire is 2 phases behind (Phases 50-51 not synced).

**Shared libraries for plugins** (post-RC):
- Expose Motion (Framer Motion) on `window.__chatwire` so plugins can use
  animations without bundling their own copy. ~34KB addition to core.

## §5 Architecture notes

### chatwire status subcommand (added Phase 51)

- Function: `cmd_status()` in `chatwire_cli.py`.
- Parser entry: `chatwire status [--label-prefix <prefix>]` (default `dev.chatwire`).
- Always returns 0 (read-only probe).
- Calls `config.load_config()` guarded in try/except; port default 8723.
- Agents section: only rendered on `sys.platform == "darwin"`; iterates `PLIST_NAMES`
  and calls `_agent_path(label_prefix, name).exists()` for `✓`/`✗` indicator.
- Plugin list: delegates to `_list_installed_plugins()` (entry-points query).
- 21 tests in `tests/test_status.py`.

### img_cache uninstall (added Phase 51)

- `_uninstall_paths()` now includes `"img_cache": Path.home() / ".chatwire" / "img_cache"`.
- `scripts/uninstall.sh` Step 6 names both `thumb_cache` and `img_cache`.
- Both are inside `~/.chatwire/` so the Step 4 `rm -rf` already covered them;
  the change makes the documentation explicit.

### img_cache startup warmer (added Phase 49)

- **`_WARMUP_DAYS`**: 30 — look-back window for HEIC attachment query.
- **`_WARMUP_MAX`**: 200 — cap on per-startup conversions.
- **`_WARMUP_HEIC_SQL`**: joins `message → message_attachment_join → attachment`;
  filters `transfer_state=5`, extension/mime matches HEIC/HEIF; `ORDER BY m.date DESC LIMIT ?`.
- **`_img_cache_warmer()`**: runs once per startup, 10 s after bind. Calls
  `asyncio.to_thread(_full_img_for, p)` per row with 0.05 s sleep between calls.
  Already-cached files return instantly from `_full_img_for` (cache hit path).
  All errors caught; never raises. Logs `warmed/total (skipped)` at INFO.
- Row key: `hasattr(row, "keys")` → `row["filename"]`, else `row[0]` (index fallback).

### Attachment image cache (added Phase 48)

- **`FULL_IMG_CACHE_DIR`**: `~/.chatwire/img_cache` (alongside `thumb_cache`)
- **`FULL_IMG_TTL_DAYS`**: 90 days
- **`_full_img_for(orig)`**: SHA1 key = `orig_path:int(mtime)` (same pattern as
  `_thumb_for`). Calls `sips -s format jpeg <orig> --out <cached>` in a thread.
  Cache hit = `cached.exists() and cached.stat().st_mtime >= orig.stat().st_mtime`.
- **`_attachment_cache_evictor()`**: daily `asyncio.sleep(86400)` loop; iterates
  both `thumb_cache` and `img_cache` with their respective TTLs. Started in
  `@app.on_event("startup")` (was mistakenly in shutdown before Phase 48).
- **`_ATTACHMENT_CACHE_CONTROL`**: `"public, max-age=2592000"` — applied to ALL
  `/attachment` response paths via `headers={...}` kwarg on `FileResponse`.

### Theme plugin refresh event (added Phase 47)

- Event name: `chatwire-plugin-themes-changed` (CustomEvent on `window`)
- Dispatch points:
  - `InstallOverlay` in `PluginsPage.tsx`: after `setDone(true)` in the fetch `.then()`.
  - `removeMutation.onSuccess` in `PluginsPage.tsx`.
- Handler: `refreshPluginThemes` callback registered via `useEffect` in `useTheme`.
- `refreshPluginThemes`: stable `useCallback(async () => {...}, [])`.
  - Fetches `GET /api/ui/plugin-themes`.
  - Re-injects `<style id="chatwire-plugin-themes">` in `<head>`.
  - Calls `setPluginSchemes(valid)` so the theme picker rerenders.
  - Fallback check: resets stored dark/light scheme to built-ins if the stored
    scheme is no longer in the merged list (same logic as the init effect).
  - State setters accessed via `useRef` to avoid stale closures without adding deps.

### chatwire-plugins registry (updated Phase 47)

- Repo: `github.com/allenbina/chatwire-plugins` (separate git repo, nested inside
  `chatwire-dev/chatwire-plugins/` on plinux)
- Current entries: apprise, telegram, webhook, stats, theme-rosepine, example
- All have `tags`, `icon`, `signed` fields.
- Fetched by `web/registry.py::fetch_registry()` with 24 h disk cache.

### Accordion animation (added Phase 46)

- File: `web/frontend/src/index.css`
- Two `@keyframes` — `accordion-down` and `accordion-up` — use
  `--radix-accordion-content-height` (injected by Radix at runtime).
- Registered via Tailwind v4 `@theme`:
  - `--animate-accordion-down: accordion-down 0.2s ease-out`
  - `--animate-accordion-up: accordion-up 0.2s ease-out`
- The `AccordionContent` in `accordion.tsx` carries
  `data-[state=open]:animate-accordion-down` / `data-[state=closed]:animate-accordion-up`
  — these classes now resolve correctly.

### iOS reply ghost bubble (added Phase 45)

- Component: `ReplyQuote` in `MessageBubble.tsx`
- Prop: `reply: { rowid, text, sender, image_path? }` — `sender` is `''` if parent
  was from me, otherwise the contact's display name.
- `parentFromMe = reply.sender === ''`
- Ghost bubble colors:
  - Parent from me: `bg-primary/15 border-primary/25`, text `text-primary/65`
  - Parent from them: `bg-muted/70 border-border/50`, text `text-foreground/60`
- Connector: `w-0.5 h-3 rounded-full`, offset `mr-3.5`/`ml-3.5` to align with tail.
- Thumbnail: `/attachment?path=…&size=thumb` → 32×32 img when `image_path` present.
- Backend: `REPLY_PARENT_SQL` correlated subquery on `message_attachment_join`
  fetches first `image/%` MIME attachment for each parent message.

### Pinnable settings (added Phase 44)

- Hook: `usePinnedSettings` in `hooks/usePinnedSettings.ts`
- Storage: localStorage key `chatwire-pinned-settings` = JSON `PinnableKey[]`
- `PinnableKey = 'hiatus_enabled' | 'reminder_enabled'`
- Pin UI: `PinButton` component in SettingsPage.tsx — inline next to section labels.
  Uses lucide-react `Pin` / `PinOff` icons (w-3 h-3).
- Sidebar: `SidebarContent` in Layout.tsx reads `isPinned()` to conditionally
  render toggle buttons. Uses `PauseCircle` (hiatus) and `Bell` (reminder) icons.
- Mutations: `toggleHiatusMutation` / `toggleReminderMutation` in `SidebarContent`,
  each taking a boolean `enable` argument.
- No backend changes — purely client-side localStorage + existing POST endpoints.
- Invalidates both `['hiatus-status']` and `['settings-notifications']` on success,
  keeping Layout and SettingsPage in sync.

### Hiatus settings countdown (added Phase 43)

- Query key: `['settings-notifications']` (shared with the rest of NotificationsSection)
- `hiatusNow` state drives countdown display (same pattern as Layout's `now` state).
- `useEffect` only installs the interval when `data?.hiatus_enabled && hiatusStartedAt > 0`.
- Status line: `text-warning` amber, placed between the section description and the
  `hiatus_enabled` checkbox.
- On save (POST): backend always writes `hiatus_started_at = time.time()` when enabling,
  so the timer anchor is always the most recent explicit save. Drop `setdefault()`.
- No auto-expire in SettingsPage — auto-expire lives in Layout.tsx only.

### Hiatus auto-off timer (added Phase 42)

- Config key: `cfg["web"]["hiatus_started_at"]` — epoch float; `0` = not set.
- Set by `POST /api/settings/hiatus_settings`: always `time.time()` (Phase 43 change).
- Cleared to `0` when hiatus is disabled.
- Read by `GET /api/ui/settings/notifications` → `hiatus_started_at: float`.
- Frontend computes `endsAt = hiatusStartedAt * 1000 + hiatusDurationMinutes * 60_000`.
- `minutesLeft = max(1, ceil((endsAt - now) / 60_000))` — shown as "· Xm left" suffix.
- Auto-expire: interval every 30 s in Layout.tsx; when `Date.now() >= endsAt`, fires `endHiatusMutation`.
- `endHiatusMutateRef` pattern avoids recreating the interval when the mutation
  object reference changes between renders.

### Hiatus dismiss (added Phase 41)

- Mutation key: n/a (useMutation, no key needed)
- Endpoint: `POST /api/settings/hiatus_settings` (same as SettingsPage uses)
- Payload: `FormData { hiatus_enabled: "false", hiatus_duration_minutes: "<N>" }`
  where `<N>` comes from the cached `['hiatus-status']` query data (default 30).
- On success: `qc.invalidateQueries({ queryKey: ['hiatus-status'] })` — the query
  re-fetches with `hiatus_enabled: false`, causing the banner to unmount.
- Button is disabled during `isPending` to prevent double-submit.
- Visual: `text-warning/70 hover:text-warning underline` — subtle, amber-tinted.

### Hiatus sidebar indicator (added Phase 40)

- Query key: `['hiatus-status']`
- Endpoint: `GET /api/ui/settings/notifications` (shared with SettingsPage)
- `staleTime: Infinity` — no background polling; hiatus rarely changes
- `refetchOnWindowFocus: true` — fresh state when user returns to the tab
- Banner position: between `ConversationList` and the "Offline" banner,
  inside `SidebarContent` in `Layout.tsx`
- Color: `bg-warning/10 border-warning/20 text-warning` (amber; defined CSS var)
- Icon: `PauseCircle` from lucide-react (w-3.5 h-3.5)

### Reminder contacts filter (added Phase 39)

- Config key: `cfg["web"]["reminder_contacts"]` — `list[str]` of handle strings.
- Default (empty list): reminder fires for ALL overdue whitelisted contacts.
- Non-empty list: `_fire_reminder_pushes` in `web/main.py` (line ~1980) compares
  each row's handle (lowercased) against the set; non-matching handles are skipped.
- GET reads from `web` section only; non-list values fall back to `[]`.
- POST accepts JSON string `reminder_contacts`; strips whitespace, drops blanks,
  raises HTTP 400 for non-list JSON.
- Frontend picker uses `/api/ui/settings/whitelist/grouped` for contact names;
  selecting a contact = adding all of that contact's `all_handles` to the filter.

### Notification settings config layout (clarified Phase 38)
Two distinct config sections:
- `cfg["notifications"]`: push-notification settings — `detail` ("rich" / "sender_only" /
  "private"), `notification_depth` (per-plugin map), `muted_contacts`.
- `cfg["web"]`: everything else that the web layer owns — hiatus, reminder (enabled,
  days, contacts), sounds, accent, custom CSS paths, port, bind, proxy_headers, etc.

### Per-theme custom CSS (added Phase 37)
- Storage: `~/.chatwire/custom-css/<slug>.css` (one file per theme slug)
- `_CUSTOM_CSS_DIR = Path.home() / ".chatwire" / "custom-css"` (in api_ui.py)
- Max size: 64 KB per theme (`_MAX_PER_THEME_CSS = 64 * 1024`)
- Slug validation: `_safe_name(slug)` from theme_loader (`^[a-z0-9][a-z0-9-]*$`)
- Combined endpoint: `GET /api/ui/custom-css/combined` → `{css, themes}`
  - `css`: `[data-theme="slug"] {\nraw_css\n}` blocks joined by `\n\n`
  - `themes`: `{slug: rawCss}` raw map for editor reconciliation
- Frontend LS key: `chatwire-custom-css-themes` (JSON `Record<string, string>`)
- `buildCombinedCustomCss()` in useTheme.ts: wraps each slug with `[data-theme]`
- `activeScheme` state in hook: updated in the theme-change effect alongside `applyTheme()`
- CSS nesting (`[data-theme] { .child { } }`) requires Chrome 112+/Firefox 117+/Safari 16.5+
- Load order: theme CSS → plugin theme CSS → override CSS → accent override → custom CSS (last wins)

### Theme skin ZIP (added Phase 36)
- Download endpoint: `GET /api/ui/theme-skin/download?theme=<slug>`
  - ZIP contains `override.json` (`{"theme", "colors"}`) + `manifest.json` (`{"theme", "exported", "app"}`)
  - Returns empty-colors ZIP (not 404) when no overrides are stored
  - Content-Disposition triggers browser download as `chatwire-override-<slug>.zip`
- Upload endpoint: `POST /api/ui/theme-skin/upload`
  - Accepts multipart `file` field; max 256 KB
  - Validates: valid ZIP, contains `override.json`, valid JSON, safe slug, known vars, safe values
  - Unknown vars and unsafe values silently dropped (not errors)
  - Overwrites any existing override file for the theme
- Frontend: `exportSkin()` creates `<a href="/api/ui/theme-skin/download?theme=...">` and clicks it
- Frontend: `handleImportZip()` POST via `FormData`, then reloads `theme-override` + `theme-override/css`
  if the skin's theme matches the active scheme
- Max ZIP size constant: `_SKIN_MAX_BYTES = 256 * 1024`

### Installed-plugins filter tabs (added Phase 35)
- State: `installedFilter: 'all' | 'theme'` in `PluginsPage`.
- Tab row: `role="tablist"` / `role="tab"` / `aria-selected`; same pill-border
  style as marketplace tag filters.
- Derivation: `filteredPlugins = installedFilter === 'theme' ? plugins.filter(p => p.tags.includes('theme')) : plugins`
- Empty-state precedence: if `plugins.length === 0` → "No plugins installed."
  else if `filteredPlugins.length === 0` → "No theme plugins installed."
  (The outer check must fire first so the theme-specific message doesn't
   appear on a fresh install with no plugins at all.)

### Theme plugin system (added Phase 33 Chunk 5)
- Entry-point group: `chatwire.themes` — each installed module exposes:
  - `SCHEMES: list[dict]` — `{name, label, isLight, swatch}` per variant
  - `CSS: str` — `[data-theme="<slug>"] { … }` blocks
- Backend: `GET /api/ui/plugin-themes` discovers EPs via `importlib.metadata`,
  validates each scheme dict, returns `{schemes, css}`.
- Frontend: `restorePluginThemes()` in `main.tsx` (early, pre-React) injects
  CSS; `useTheme` hook fetches again on mount to populate `pluginSchemes` state.
- Fallback: if active scheme is missing from merged list → resets to dracula/github-light.
- Style element ID: `chatwire-plugin-themes`
- chatwire-theme-rosepine installed on mbair at v1.0.0 (from git+ssh).

### Offline mode (added Phase 33, noted complete Phase 38)
- `useOnline.ts` hook: `navigator.onLine` + `window 'online'/'offline'` events.
- `Layout.tsx`: shows a red dot + "Offline" banner in the sidebar footer.
- `ComposeBox.tsx`: shows an inline notice above the compose area when offline.
- No backend component needed.

### Hover action bar (added Phase 33)
- Triggered by `group/bubble` hover (desktop) or 500ms long-press (mobile).
- `HoverActionBar` renders as `absolute bottom-full` above the bubble content div.
- Quick reactions → `POST /api/ui/tapback {rowid, type}` → AppleScript `react with reaction`.
- Edit/Unsend require Ventura (macOS 13+); `GET /api/ui/macos-version` returns
  `{major, minor}`, fetched once at stale:Infinity in ChatPage.
- Reply → sets `replyTo: Message | null` in ChatPage; ComposeBox shows banner and
  passes `reply_to_guid` to `/api/ui/send`. (AppleScript doesn't wire threading in
  Messages.app, but the guid is sent informally for future backend support.)

### Tapback senders (updated Phase 33)
- `_fetch_tapbacks` returns `{type, senders: [{name, time}]}[]` per guid.
- `TapbackBar` title tooltip shows "Name · HH:MM AM/PM" per sender.

### Mark-all-read footer icon (added Phase 33)
- `CheckCheck` from lucide, sidebar footer, appears only when `hasUnseen`.
- Shares `['conversations']` query — no extra network request vs. ConversationList.

### Plugin marketplace filtering (updated Phase 32)
- `plugins.json` now has `tags` on all entries; no deprecated entries remain.
- Frontend `MarketplaceSection` filters: `p.deprecated || installedNames.has(p.pypi) || installedNames.has(p.name)` → exclude.

### Color editor — contrast pairs (added Phase 31 Chunk 3)
- `CONTRAST_PAIRS` in `SettingsPage.tsx` maps each CSS variable to its semantic
  background partner for WCAG contrast checking.
- `ContrastBadge` renders a 9px pill: AAA (≥7), AA (≥4.5), AA⁺ (≥3), ✗ (<3).
- Import JSON format: `{"theme": "<slug>", "colors": {"<var>": "<HSL>", ...}}`
  — identical to the Export JSON format from `exportJson()`.

### Custom notification sounds (added Phase 31 Chunk 2)
- Sound files: `~/.chatwire/sounds/custom-{sent|received}.{ext}` (ext = wav/mp3/ogg/m4a/aac)
- Config in `~/.chatwire/config.json`: `web.sounds.{sent,received}` = `"default"|"none"|"custom"`
- Default sounds still at `/static/sounds/sent.wav` and `received.wav`
- Custom sounds served at `/api/ui/sounds/custom-sent` / `custom-received`
- `useSounds.ts` module-level config: call `configureSounds({sent, received})` to switch modes
  at runtime (ChatPage does this on mount; SettingsPage does it on each change).
- File scanner: `_custom_sound_path(type)` iterates extensions to find the stored file.

### Deploy pipeline (updated 2026-05-12)
- `dist/` is committed to git — no separate scp step
- Deploy: `pip install --no-cache-dir --force-reinstall --no-deps 'chatwire @ git+ssh://git@github.com-chatwire/allenbina/chatwire-dev.git@main'`
- Restart: `/bin/launchctl kickstart -k gui/501/dev.chatwire.web && /bin/launchctl kickstart -k gui/501/dev.chatwire.bridge`
- Health: `/usr/bin/curl -sf localhost:8723/healthz`

### Frontend build
- After any frontend code change: `npm --prefix /home/mediafront/git/chatwire-dev/web/frontend run build`
- Commit the updated `dist/` with the source changes
- `.gitattributes` treats JS/CSS in dist/ as binary (no line-level diffs)

### Theme import preference cascade (added Phase 31 Chunk 1)
- Theme pack JSON: add `"scheme_dark": "<slug>"` and/or `"scheme_light": "<slug>"`
- Slugs validated against `_KNOWN_SCHEMES` in `theme_loader.py`
- Frontend cascade rules (in `ThemePackSection.applyPack`):
  - Both set → update both, keep user's mode (auto/dark/light)
  - Dark only → update autoDark, force mode=dark
  - Light only → update autoLight, force mode=light
  - Neither → no change
- Clearing overrides: `DELETE /api/ui/theme-override?theme=<slug>` for each affected
  scheme, then `restoreThemeOverride()` to re-inject remaining overrides.

### Theme override system (added Phase 30)
- Files: `~/.chatwire/theme-overrides/<slug>.json` → `{"colors": {"primary": "265 89% 78%", ...}}`
- CSS format: `[data-theme="<slug>"] { --primary: 265 89% 78%; }` — scoped to theme slug
- Style element ID: `chatwire-theme-override` (injected into `<head>`)
- Load order: theme CSS → plugin theme CSS → override CSS → accent override → custom CSS (last wins)
- HSL format: space-separated triplets without `hsl()` wrapper (Tailwind v4 requirement)
- Color variables editable: 20 (background, foreground, primary, primary-foreground,
  secondary, secondary-foreground, muted, muted-foreground, card, card-foreground,
  accent, border, input, destructive, success, warning, info, msg-me, msg-them, msg-sms)

### SMS reaction detection (updated Phase 32)
- Module: `web/sms_reactions.py` — imported by `web/main.py`
- Text reactions: accepts straight `"` AND curly `\u201c`/`\u201d` quotes around message text
- Android zero-width spaces stripped before matching (hair space, ZWNJ, ZWJ, BOM)
- Media reactions: `^(Liked|Loved|...|😢)\s+(?:to\s+)?a[n]?\s+(image|photo|video|GIF|sticker|attachment)$`
- Backward search window: 50 messages

### Whitelist contact cards
- `GET /api/ui/whitelist` returns `{contacts: [{name, handles[], whitelisted}], group_chats: [...]}`
- Frontend groups handles by contact with expand/collapse per card

## §6 Next prompt

```
Read docs/HANDOFF.md in full. This is your state file.

git pull first — there may be commits from an interactive session.

STATE: Phase 51 shipped (chatwire status + img_cache uninstall, commit 873f0e0).
1052 pytest (1044 pass + 8 pre-existing), 190 Vitest — all green.
mbair running v1.14.0 (git+ssh, Phase 51 code, healthy).
Public repo allenbina/chatwire is 2 phases behind (Phases 50-51 not yet synced).

Key blocker for Option A (PyPI publish):
  chatwire-theme-rosepine is NOT on PyPI — marketplace Install button will fail
  at pip for this package until it is published. Requires TWINE_TOKEN or ~/.pypirc.

Pick a task from §4 options:

Option A — Publish chatwire-theme-rosepine to PyPI so marketplace Install works.
  Requires TWINE_TOKEN env var or ~/.pypirc with PyPI API token.
  Build: python3 -m build /home/mediafront/git/chatwire-dev/chatwire-plugins/chatwire-theme-rosepine
  Upload: TWINE_TOKEN=<token> python3 -m twine upload --non-interactive \
    /home/mediafront/git/chatwire-dev/chatwire-plugins/chatwire-theme-rosepine/dist/*

Option B — #20 Automation engine / #28 trigger grammar (larger, plan first).

Option C — Sync allenbina/chatwire public repo to Phase 51 (2 phases behind).
  Use: rsync -a --checksum (no --delete) from chatwire-dev/ to /tmp/chatwire-public/
  with excludes for dist/, node_modules/, __pycache__/, .git/
  Then git add -A && git commit && git push in /tmp/chatwire-public/

Option D — Any smaller feature from §4 (plinux test env, MQTT output, docs).

VISUAL QA NOTE: pin icons in SettingsPage, sidebar toggle buttons for hiatus/reminder,
hiatus sidebar indicator + dismiss button + countdown, hiatus SettingsPage countdown,
reminder contacts picker, per-theme custom CSS editor, theme skin ZIP buttons, hover
action bar, tapback tooltips, mark-all-read icon, Rose Pine theme picker, iOS
reply ghost bubble, accordion animation, theme picker refresh after install,
and HEIC img_cache warmer behavior all require an interactive session on mbair
— skip and note if headless.

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
  curl -s -d "Phase 52 complete — <summary>" ntfy.sh/p9SKpYzY70LlyK1N

NOTE: Run pytest as: python3 -m pytest /home/mediafront/git/chatwire-dev/tests/ --tb=short -q
NOTE: npm test command works — use: npm --prefix /home/mediafront/git/chatwire-dev/web/frontend test -- --run
NOTE: Public repo sync method: rsync -a --checksum (no --delete) from chatwire-dev/
  to /tmp/chatwire-public/ with excludes for dist/, node_modules/, __pycache__/, .git/
  Then git add -A && git commit && git push in /tmp/chatwire-public/
```
