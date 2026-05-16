# Handoff — Phase 93: Onboarding & Installation

> Phase 93 session shipped (2026-05-16).
> 1161 pytest / 459 Vitest / 29 mobile jest — all green (1 pre-existing App.test.tsx jsdom failure: HTMLMediaElement.play).
> mbair running v1778952714 (git+ssh), healthy.

## §0 What shipped

### Phase 93: Onboarding & Installation (2026-05-16)

**MCP version gating:**
- `mcp` is now an optional extra: `pip install chatwire[mcp]`
- API endpoint returns `mcp_available` + `python_version` fields
- Frontend: amber warning banner when MCP package unavailable, all controls disabled
- CLI: `chatwire mcp` prints helpful install message and exits 1 if package missing
- `chatwire doctor` reports MCP package status (info level, not critical)

**Keepawake service removed:**
- Deleted `templates/launchd/keepawake.plist.template`
- `PLIST_NAMES = ("bridge", "web")` — removed keepawake
- `chatwire_toolbar.py` SERVICES updated to match
- Amphetamine recommendation printed during `chatwire install-agents`

**First-run wizard (`chatwire init`):**
- Detects first run (no config.json) — prompts for self_handles
- Auto-generates VAPID EC P-256 keypair via cryptography library
- Writes config.json with 0o600 permissions
- On macOS: offers to install launchd agents
- Prints Amphetamine note, doctor hint, web UI URL
- `chatwire setup` aliases to `chatwire init`
- `main()` suggests `chatwire init` when no subcommand + no config

**Plugin publishing:**
- 4 plugins published to PyPI: chatwire-mqtt, chatwire-ha, chatwire-xmpp, chatwire-ntfy
- Created minimal READMEs for plugins missing them (required for PyPI build)

**Install testing doc:**
- `docs/INSTALL_TESTING.md` — prerequisites per machine, test scripts per install method,
  verification checklist, macOS compatibility matrix

**Tests:**
- `tests/test_cli_init.py` — 12 tests covering VAPID generation, handle parsing,
  config structure, file permissions, existing config detection
- Updated test_doctor.py (7 checks), test_toolbar.py (2 services)

**Commits:** 92f6c18, a3465ed, 9571434, b5d8498

### Phase 92: MCP v2 — full rewrite (2026-05-16)

**Backend — scope model + 10 tools + safety:**
- Scope system: `mcp:read` (ON), `mcp:send` (OFF by default), `mcp:contacts` (ON), `mcp:meta` (ON)
- Contact filter: whitelist (default) / all / explicit — configurable per-tool
- Confirmation flow: always / contacts_only / never — pending queue with 5min TTL, `confirm_send` tool
- Send safety: pause_sends kill switch, send_allowed_contacts list, `--read-only` CLI flag
- `search_messages` now respects contact filter (was leaking all handles)
- 6 new tools: `send_message_to_group`, `resolve_contact`, `get_unread_summary`, `get_status`, `draft_message`, `confirm_send`
- `wait_for_delivery` option on `send_message` — false = fire-and-forget in <2s

**Frontend — Settings UI v2:**
- Master defaults section: scope grants, contact access dropdown, confirmation mode, pause sends kill switch
- Per-tool accordion rows: enable/disable toggle + expand for per-tool overrides (contact access, confirmation)
- "Inherit" = use master default; only override keys stored in config
- Expanded client setup snippets: Claude Code, Claude Desktop / ChatGPT Desktop, Cursor / Windsurf / VS Code Copilot, LM Studio / Local LLMs

**Performance:**
- Snapshot pooling: 2s cache window for back-to-back MCP tool calls (eliminates redundant 50ms .backup() calls)
- FTS5 sidecar index: persistent at ~/.chatwire/search_fts.db, incremental sync, MATCH queries <10ms
- LIKE fallback if FTS5 fails

**Transport:**
- Streamable HTTP (2025 MCP spec) — single endpoint at /mcp/, stateless, auto-selected
- Legacy SSE fallback — /mcp/sse + /mcp/messages, auto-selected if Streamable HTTP unavailable
- Auth middleware on both: Bearer cwk_ with mcp scope required
- Protocol layer fully delegated to `mcp` Python package — spec evolution = import swap

**Config schema (v2):**
```json
{
  "integrations": {
    "mcp": {
      "enabled": true,
      "http_enabled": true,
      "contact_filter": "whitelist",
      "confirmation_mode": "never",
      "send_allowed_contacts": [],
      "pause_sends": false,
      "scopes": ["mcp:read", "mcp:contacts", "mcp:meta"],
      "tools": {
        "send_message": { "enabled": true, "confirmation": "always" },
        "search_messages": { "enabled": true, "contact_filter": "all" }
      }
    }
  }
}
```

### Phase 91: Command palette + MCP Settings + LQIP (2026-05-16)

**Command palette (Cmd+K / Ctrl+K):**
- Installed shadcn Command component (wraps cmdk library)
- Fuzzy-search across all pages (Chat, Settings, Plugins, Logs, Debug) and all 8 Settings sections
- Opens via Cmd+K (macOS) or Ctrl+K (Windows/Linux) from any page
- Select navigates to the page/section, opens the accordion, scrolls into view
- Wired into App.tsx (inside BrowserRouter, accessible globally)
- Fixed shadcn-generated imports (src/ → @/ alias) in command.tsx and dialog.tsx

**MCP Server Settings section:**
- New accordion section in Settings (between Content Filter and Advanced)
- Enable/disable toggle with per-tool checkboxes (send_message, read_messages, list_conversations, search_messages)
- Stdio transport info with the `chatwire mcp` command
- Collapsible client setup snippets: Claude Code, Claude Desktop, Cursor
- Backend: GET/POST /api/ui/integrations/mcp/config — reads/writes integrations.mcp config in config.json
- Saves enabled, enabled_tools, http_enabled (transport toggle prepped for future HTTP/SSE)

**LQIP blur placeholders (Image perf Phase 2):**
- Backend: `size=lqip` on /attachment returns a base64 data URI (~200-400 bytes) for a 20px JPEG
- `_ensure_lqip()` generates and caches 20px thumbnails alongside small thumbnails in small_cache/
- `_lqip_for()` returns the base64 data URI, cached on disk
- Frontend: `BlurImage` component with blur(10px) overlay that fades out when real image loads
- Module-level LQIP cache (Map) in BlurImage — shared across instances, survives re-renders
- Applied to MediaGallery grid images and link preview images in MessageBubble
- Reply quote thumbnails (32x32) left as plain <img> — too small for blur to help

**Settings accordion now 8 sections:** Self handles, Whitelist, Appearance, Notifications,
Content Filter, MCP Server, Advanced, Password.

### Phase 90: Settings consolidation + content filter + MCP (2026-05-15)

**Settings accordion consolidation:**
- Merged API keys into Advanced section
- Merged Plugins + Image Cache into Advanced section
- Then removed Plugins from Settings entirely (dedicated /plugins page exists)
- Final accordion: Self handles, Whitelist, Appearance, Notifications, Content Filter, Advanced, Password

**Content filter → dedicated Settings section:**
- Moved from Plugins page to its own Settings accordion with shield icon
- 12 category checkboxes with descriptions and word counts
- Custom words textarea, emoji pool, matching mode, scope selector
- Expanded word lists from ~150 to ~1,834 total words (merged words/cuss MIT list + hand-curated topic supplements)
- Added nested object rendering to SchemaForm (PluginsPage) for category toggles
- Content filter stays core tier — hidden from Plugins page

**MCP → core tier:**
- Moved from official to core (needs raw chat.db access, too privileged for plugin tier)
- Hidden from Plugins page alongside content_filter
- Full MCP Settings section (transport, auth, tool gating) designed but not yet built — see memory/project_chatwire_mcp_flesh_out.md

**Bug fixes:**
- Missing inline SVG icons in SettingsPage causing white screen (ReferenceError on lazy-loaded chunk)
- Reaction panel hidden on macOS <13 — now shows Copy/Reply, hides emoji row + Edit/Unsend
- Installed plugin cards overflowing on narrow viewports
- Core plugins hidden from Plugins page (only installable/uninstallable plugins shown)

**RC1 gate established:** Security audit (first) + tech debt/consistency audit (second) — see memory/project_chatwire_rc1_gate.md

### Phase 89: Image optimization + SW caching (2026-05-15)

**White page on hard refresh fix** (`afdcbcc`):
- `index.html` served with `Cache-Control: no-cache, must-revalidate`
- `sw.js` and `registerSW.js` served with `no-cache, must-revalidate`
- Root cause: stale SW precache held old index.html referencing deleted asset hashes

**240px small thumbnail tier** (`74fd3a2`):
- New `size=small` (240px) on `/attachment` endpoint for chat-bubble images
- Separate cache dir `~/.local/share/chatwire/small_cache/`
- Chat bubbles, link previews, reply quotes all request `size=small` (~15-25KB vs ~80-150KB)
- ContactInfoSheet media grid upgraded from full-size to `size=thumb` (720px)
- Lightbox still serves full-size originals

**SW thumbnail/avatar caching**:
- Thumbnails (`size=small`, `size=thumb`): CacheFirst, 30-day TTL, max 2000 entries
- Avatars: CacheFirst, 7-day TTL, max 500 entries
- Full-size attachments: still NetworkOnly (too large to cache)

**Cache management UI** (Settings → Image cache):
- Shows total SW cache size (thumb-cache + avatar-cache)
- Clear Cache button
- Retention picker: 7d / 30d / 90d / Forever
- Startup sweep in main.tsx prunes entries older than chosen retention (checks response Date header)

### Phase 88: Mobile nav + automations removal + many fixes (2026-05-15)

### Debug page: reaction panel refresh

Updated the Reaction Panel section in `DebugPage.tsx` to match the real
`ReactionPanel.tsx` component:

- 8-column grid layout (was flex)
- `1.75rem` emoji size with `aspect-square` (was `var(--font-size-message)` + `2.2em`)
- `☺` for "more reactions" button (was `+`)
- `var(--icon-size-md)` / `var(--icon-stroke)` on all action SVGs (was hardcoded)
- Font size on action rows uses `var(--font-size-message)` (was `text-sm`)
- Added existing reactions summary section (Loved, Laughed with sample senders)
- Added edit mode panel (input + Save/Cancel)

### Mobile navigation spec

Wrote `docs/MOBILE_NAV_SPEC.md` — full design spec for replacing the hamburger +
Sheet drawer mobile navigation with a stack-based full-screen model:

- Conversations list = home screen (full-screen, no header)
- Every sub-page (chat, settings, logs, plugins, debug) gets a `←` back button
  in its header on mobile (`md:hidden`), navigating to `/`
- Swipe-from-left-edge gesture as alternative back action
- Remove hamburger, "Chatwire" branding bar, Sheet drawer, and inconsistent
  `← Back` text links
- Desktop layout unchanged
- Route-based navigation (not state-based) — browser back button works for free

### CF routing investigation (not resolved)

Investigated why `messages.allenbina.uk` shows "Failed to load conversations"
while Tailscale direct works fine. Findings:

- mbair port 8723 (dev.chatwire.web) serves React SPA correctly
- mbair port 8725 (rogue dev server since May 7) serves old htmx v0.5.1
- Cloudflared config points to 8723 (correct)
- CF Access policy is correct (allenbina@gmail.com, allenfrijole@gmail.com)
- Server returns correct JSON for `/healthz` and `/api/ui/conversations`
- Most likely cause: CF edge caching stale `/sw.js` (service worker served
  without Cache-Control headers). Needs cache purge (CF API token lacks
  purge permission) + adding `Cache-Control: no-cache` to SW response.
- The rogue 8725 server should be killed: `ssh mbair "kill 28802"`

## §1 Current state

- **mbair**: commit e09d756 (Phase 92) deployed and healthy (`/healthz` → ok, v1778952714). Phase 93 committed but not yet deployed.
- **Tests**: 1161 pytest / 459 Vitest / 29 mobile jest — all green (1 pre-existing App.test.tsx jsdom failure). test_rules_dsl.py excluded.
- **MCP v2**: 10 tools, 4 scopes (send OFF by default), contact filter, confirmation flow, FTS5 search, snapshot pooling, Streamable HTTP + legacy SSE transports.
- **MCP version gating**: optional extra `chatwire[mcp]`, grey-out UI when unavailable, doctor check.
- **Onboarding**: `chatwire init` wizard (self_handles + VAPID auto-gen), keepawake removed, Amphetamine recommended.
- **Settings accordion (8 sections)**: Self handles, Whitelist, Appearance, Notifications, Content Filter, MCP Server (v2 — master defaults + per-tool accordion), Advanced, Password.
- **Command palette**: Cmd+K / Ctrl+K from any page.
- **LQIP**: Blur placeholders for chat images. 20px JPEGs cached in small_cache/.
- **PyPI**: v1.14.0 + 4 plugins published. **Public repo**: synced through Phase 77. Phases 78–93 not yet synced.

## §1.1 Next up: Install methods & packaging (Chunk C)

**RC1 install methods:**
- pip/pipx (works today)
- `uv tool install chatwire` (needs end-to-end verification on mbair)
- Homebrew formula + tap (allenbina/homebrew-tap)
- Tauri DMG (post-RC1, scaffold in packages/tauri/)

**In progress (loop):**
- Install-method detection (pipx/uv/brew/standalone/dev)
- Duplicate-install warning (multiple chatwire on PATH)
- `chatwire uninstall --purge` command
- Uninstall logic per method
- Homebrew formula
- Tauri scaffold

**Needs macOS testing (deferred):**
- `uv tool install chatwire` end-to-end
- `brew install chatwire` from tap
- Tauri build (needs Rust on mbair)
- launchd agent install/uninstall per method

## §2 What shipped in Phase 86 (2026-05-13)

### test: SettingsPage — 45 Vitest tests for automation rules + AccentColorPicker + PasswordSection (#86)

Adds `web/frontend/src/pages/SettingsPage.test.tsx`. No production code changed.

**Tests cover:**
- `_formToApiRule` (17 tests): all action types (reply/webhook/log), all trigger types
  (text_contains/always/schedule/on_send/dsl), conditions (fromHandles, notFromHandles,
  toHandles, notToHandles, inGroup, groupGuid), stopOnMatch, webhook method/headers
  optional-field omission, invalid JSON headers silenced
- `_apiRuleToForm` (10 tests): all trigger types, on_send vs non-on_send handle fields,
  in_group → inGroup mapping, stopOnMatch, webhook headers round-trip, and a full
  `_formToApiRule → _apiRuleToForm` round-trip
- `AccentColorPicker` (9 tests): hex text input renders/updates, onChange called on
  valid hex only, blur reverts invalid draft, native picker proxies onChange,
  swatch aria-label, parent prop-reset syncs draft via useEffect
- `PasswordSection` (9 tests): auth-disabled vs auth-enabled UI, mismatch-password
  toast.error, successful set/change toast.success + field clear, API error detail in
  toast, Remove password button conditional render, confirm=false guards fetch,
  confirm=true POSTs with clear:true

Vitest: 466 → 511 (+45). All 1409 pytest + 29 mobile jest still green.

**Key mock pattern (SettingsPage module-level mocks):**
```typescript
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }))
vi.mock('../components/Layout', ...)
vi.mock('../hooks/usePinnedSettings', ...)
vi.mock('../hooks/useTheme', ...)
vi.mock('../hooks/useSounds', ...)
vi.mock('../plugins/SlotRenderer', ...)
vi.mock('react-router-dom', ...)
```
The pure exported functions (`_formToApiRule`, `_apiRuleToForm`) need no mocking —
the module-level mocks just allow the module to be imported cleanly.

## §2 What shipped in Phase 85 (2026-05-13)

### test: PopoutPage — 19 Vitest tests for popout chat view (#85)

Adds `web/frontend/src/pages/PopoutPage.test.tsx`. No production code changed.
Vitest: 447 → 466 (+19). All tests green.

## §2 What shipped in Phase 84 (2026-05-13)

### test: StatsWidget — 21 Vitest tests for stats sidebar panel (#84)

Adds `web/frontend/src/plugins/StatsWidget.test.tsx`. No production code changed.
Vitest: 426 → 447 (+21). All tests green.

## §2 What shipped in Phase 83 (2026-05-13)

### test: SlotRenderer + PluginFrame — 35 Vitest tests for plugin slot rendering (#83)

Adds `web/frontend/src/plugins/SlotRenderer.test.tsx` and
`web/frontend/src/plugins/PluginFrame.test.tsx`. No production code changed.
Vitest: 391 → 426 (+35). All tests green.

## §2 What shipped in earlier phases

(See git history for Phases 62–82 details.)

## §3 Open bugs

- Ghost bubble reply quote rendering regression — 0.75em border-radius fix deployed
  but user reported it "went back to the original issue." Needs screenshot + re-examination.

## §4 Follow-ups (Phase 91+ candidates)

**MCP HTTP/SSE transport** (Settings UI prepped, backend not yet implemented):
- Add HTTP/SSE transport (~150 lines using mcp package sse_server)
- Mount on existing port 8723 at /mcp/sse
- API key auth middleware for HTTP MCP requests (reuse existing API key system)
- http_enabled toggle already wired in Settings UI + config.json

**Image performance Phase 3** (remaining from Phase 2 design):
- MEDIA_BASE_URL env var for configurable media origin (~35 lines)
- WebP output from sips

**CF routing fix for messages.allenbina.uk**:
- SW no-cache headers now set (Phase 89). May self-resolve after CF cache TTL expires.
- Purge CF cache manually if still broken (dashboard or API token with purge permission).
- Kill rogue dev server: `ssh mbair "kill 28802"` (port 8725, old htmx v0.5.1).

**Edited messages — history popover** (research needed):
- Blocker: mbair is macOS 12 — no `date_edited` column. Needs macOS 13+ hardware
  or a chat.db snapshot. Once schema confirmed, add `_fetch_edit_history()` in
  `web/main.py` and wire frontend popover.

**PyPI publishing** (needs `TWINE_TOKEN` or `~/.pypirc`):
- Publish `chatwire-theme-rosepine`, `chatwire-mqtt`, `chatwire-ha`, `chatwire-xmpp`.
  Build: `python3 -m build <plugin-dir>`
  Upload: `TWINE_TOKEN=<token> python3 -m twine upload --non-interactive <dist>/*`

**Untested web frontend components**:
- `ChatPage.tsx` — complex; skip or mock heavily
- `AutomationsDslMode.test.tsx` already exists — check coverage gaps
- `SettingsPage.tsx` remaining sections: ThemeSection, ColorEditorSection,
  NotificationsSection, AutomationsSection UI (the complex dialog/form), etc.

**Public repo sync** (deferred from Phases 78–86 — test-only changes):
- When next code change ships, sync allenbina/chatwire including Phase 78–86 commits.

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

### SettingsPage test patterns (added Phase 86)

**Module-level mocks** — SettingsPage.tsx imports many things (Layout, usePinnedSettings,
useTheme, useSounds, SlotRenderer, react-router-dom, sonner). All must be mocked at the
top of the test file so the module loads cleanly.

**Pure function tests** (`_formToApiRule`, `_apiRuleToForm`):
- No React rendering needed — import and call directly.
- `_formToApiRule`: trigger omits `pattern` for `always` and `on_send`; omits `conditions`
  when all condition fields are empty; `stop_on_match` key is absent when false.
- Webhook action: `method` key omitted when `'POST'` (default); `headers` key omitted
  when empty or invalid JSON.
- Log action: `level` key omitted when `'info'` (default).
- `_apiRuleToForm`: `dsl` and `schedule` trigger types have early-return paths;
  `on_send` maps `to_handles`/`not_to_handles`, not `from_handles`/`not_from_handles`.

**AccentColorPicker**:
- No custom hooks; uses only React state + DOM refs. No wrapping needed.
- `getByLabelText('Accent color hex value')` for the text input.
- `document.querySelector('input[type="color"]')` for the native picker.
- `fireEvent.change(input, { target: { value } })` → onChange called only for valid hex.
- Blur reverts if `isDraftInvalid` (non-empty, non-hex); does not revert valid drafts.

**PasswordSection**:
- Wrap in `QueryClientProvider` with `retry: false`.
- `vi.stubGlobal('fetch', vi.fn())` first call = GET (query), subsequent = POST (mutation).
- CRITICAL: Use exact label strings `'New password'` and `'Confirm new password'` —
  regex `/new password/i` matches both and throws "Found multiple elements".
- `handleClear` uses `window.confirm()` — spy with `vi.spyOn(window, 'confirm')`.
- `toast.success` / `toast.error` spied via `vi.spyOn(toast, 'error').mockImplementation(...)`.

### PopoutPage test patterns (added Phase 85)

- Mock `../components/MessageList` and `../components/ComposeBox` with divs exposing
  `data-handle` and `data-is-group` attributes for assertion.
- Mock `../hooks/useTheme` to spy on `applyTheme`; assert called with `localStorage` value
  or `'dracula'` fallback.
- Mock `../hooks/useSSE` with `vi.fn()`. Capture the `onEvent` callback from
  `mockedUseSSE.mock.calls[calls.length-1][0].onEvent`. Call it inside `act()`.
- Mock `../store` (`useChatStore`) as a `vi.fn()` that calls the selector with a
  `{ clearOptimistic: mockClearOptimistic }` stub state.
- Wrap with `MemoryRouter` (`initialEntries`) + `QueryClientProvider`. Use percent-encoding
  (`%3B` → `;`, `%40` → `@`) in `initialEntries` to pass special chars in URL params.
- Spy on `qc.invalidateQueries` after `makeQC()` to assert cache invalidation.

### StatsWidget test patterns (added Phase 84)

- Wrap in `QueryClientProvider` with `retry: false` — same pattern as `UpdateBanner`.
- `vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok, json: async () => data }))` for all
  fetch-based tests. Restore via `vi.restoreAllMocks()` in `afterEach`.
- **Loading state**: pass a never-resolving `new Promise(() => {})` as the fetch mock return.
  The component returns null immediately (before any await), so `container.firstChild` is null.
- **Null checks** (`enabled: false`, error): use `await new Promise((r) => setTimeout(r, 50))`
  to let react-query settle, then assert `container.firstChild` is null.
- **Rendered assertions**: use `waitFor` since react-query state updates are async.
- **Progress bar**: assert `screen.getByLabelText(/% sent/)` for presence; check
  `(bar as HTMLElement).style.width` for the computed percentage.
- **Date range labels**: iterate `cases` array with a `for...of` loop, not `it.each`,
  to avoid template literal issues in Vitest test names.

### PluginFrame test patterns (added Phase 83)

- jsdom 25 gives `iframe.contentWindow` a real Window object — `vi.spyOn(cw, 'postMessage')`
  works directly. If `contentWindow` is null, fall back to `Object.defineProperty` with a
  `{ postMessage: vi.fn() }` fake window (the helper `getIframeWithSpy()` handles both).
- Message source check: `event.source !== iframeRef.current.contentWindow`. Dispatch with
  `new MessageEvent('message', { source: iframe.contentWindow as MessageEventSource, data })`.
  Wrapping dispatch in `act()` flushes any React state updates.
- `register-css` creates a `<style data-plugin-key="..." data-plugin-css-key="...">` in
  `document.head`. Use `document.querySelector('style[data-plugin-key="..."]')` to assert.
- `beforeEach` removes leftover style elements from previous tests (safety net, since
  cleanup/unmount also handles this).
- `fireEvent.load(iframe)` triggers the React `onLoad` handler to fire `handleLoad`.

### SlotRenderer test patterns (added Phase 83)

- Mock `./PluginFrame` with a div that exposes props as data attributes:
  `data-plugin-key`, `data-src`, `data-slot`, `data-slot-props` (JSON-stringified).
- Mock trusted components with `makeComp(testId)` that renders `data-props` as JSON.
- Error boundary: `vi.spyOn(console, 'error').mockImplementation(() => {})` suppresses
  React's caught-error logging. The boundary renders `role="alert"` with `textContent`
  containing the plugin key.

### useSounds test patterns (added Phase 82)

- `MockAudio` class captures all constructed instances in a static array; cleared
  in `beforeEach`. Constructor sets `this.src = new URL(url, location.href).href`
  to match browser absolute-URL behaviour used in `ensureLoaded` comparisons.
- `globalThis.Audio = MockAudio as unknown as typeof Audio` in `beforeEach`.
- **Critical**: `ensureLoaded()` eagerly initialises **both** `sentAudio` and
  `receivedAudio` in a single call. After any first `play*()` call, `instances`
  has 2 elements: `instances[0]=sentAudio`, `instances[1]=receivedAudio`.
- `document.hidden` overridden via `Object.defineProperty` with `configurable:true`.
- `configureSounds({ sent: 'default', received: 'default' })` in `beforeEach`
  resets module-level config and nulls both cached audio references.

### useSSE test patterns (added Phase 81)

- `MockEventSource` class captures all constructed instances in a static array; cleared
  in `beforeEach`. Exposes `simulateMessage(data)` and `simulateError()` helpers.
- `vi.useFakeTimers()` / `vi.useRealTimers()` for reconnect timer control.
- Set `globalThis.EventSource = MockEventSource` in `beforeEach`.
- `enabled` transitions tested by passing prop to `renderHook` and calling `rerender`.
- `onEvent` ref tests: use `renderHook` with `initialProps` + `rerender` to swap callback.

### useOnline test patterns (added Phase 81)

- `navigator.onLine` is read-only in jsdom; override via
  `Object.defineProperty(navigator, 'onLine', { get: () => value, configurable: true })`.
- Fire events via `window.dispatchEvent(new Event('offline'))` / `new Event('online')`.
- Wrap dispatches in `act()` to flush React state updates.

### usePinnedSettings test patterns (added Phase 81)

- `localStorage.clear()` in `beforeEach` ensures isolation between tests.
- Pre-populate localStorage with `localStorage.setItem(LS_KEY, JSON.stringify([...]))`.
- Test invalid/non-array/null JSON to exercise the `load()` catch branch.
- `PINNABLE_LABELS` is a named export — import and assert values directly.

### api.test.ts patterns (added Phase 80)

- No component rendering needed — import functions directly from `./api`.
- `window.location` mock: `Object.defineProperty(window, 'location', ...)` in `beforeEach`
  to intercept `window.location.href` assignments (jsdom blocks direct assignment).
- `vi.stubGlobal('fetch', vi.fn().mockResolvedValue({...}))` for all fetch-based tests.
  Restore via `vi.restoreAllMocks()` in `afterEach`.
- For `sendFile`: pass a real `File` object; assert `FormData.get('handle')` /
  `FormData.get('guid')` / `FormData.get('file')`.
- For URL param assertions: capture `fetchMock.mock.calls[0][0]` as a string and use
  `.toContain('param=value')` — avoids URL encoding surprises.
- For POST body assertions: `JSON.parse(fetchMock.mock.calls[0][1].body)`.

### LogsPage test patterns (added Phase 79)

- **Virtualizer mock**: `vi.mock('@tanstack/react-virtual', ...)` returns all `count` items
  as virtual items with estimated size. jsdom has no layout engine (clientHeight=0) so the
  real virtualizer would render nothing; this mock ensures entries appear in the DOM.
- **Layout mock**: `vi.mock('../components/Layout', ...)` renders children directly. Avoids
  Layout's sidebar fetches and `act()` warnings from uncontrolled state updates.
- **EventSource mock**: `globalThis.EventSource = MockEventSource` captures the latest
  instance in `lastEs`. Tests call `lastEs?.onopen?.()`, `lastEs?.onerror?.(ev)`, etc.
  Wrap in `act()` to flush React state updates synchronously.

### ExportDropdown test patterns (added Phase 78)

- No mocks needed — component only uses React state + DOM events.
- Outside-click test: `fireEvent.mouseDown(document.body)`.
- Link `href` assertions: use `.toContain()` (jsdom resolves relative hrefs to absolute).

### Mobile jest-expo setup (added Phase 77)

**Running mobile tests:**
```
npm --prefix packages/mobile test
```

**Key patterns:**
- `useAppState` mocked with `var mockClient` (not `const`) to avoid TDZ issues.
- `useServerEvents` stubbed as a no-op.
- `ActionSheetIOS.showActionSheetWithOptions` needs `.mockImplementation(jest.fn())`.
- `Platform.OS` set via `Object.defineProperty`.
- testIDs on `MessageListScreen`: `loading-indicator`, `loading-older`, `message-list`.

### UpdateBanner test setup (added Phase 76)

- Wrap in `QueryClientProvider` with `retry: false`.
- Mock `globalThis.fetch` for `/healthz` and GitHub API.
- `navigator.serviceWorker` mock: `afterEach` restores to no-op stub (not `undefined`).

### ComposeBox lockout states (updated Phase 73)

Three mutually-exclusive compose area states:
1. `isLockedOut` (step >= 4): `LockoutFooterNote`
2. `isCoolingDown` (step 1-3): `CooldownBanner`
3. Normal: textarea + send button

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

STATE: Phase 90 shipped (settings consolidation + content filter + MCP tier change).
1409 pytest / 459 Vitest / 29 mobile jest — all green (1 pre-existing jsdom failure).
mbair running v1778912535 (git+ssh), healthy.
Public repo allenbina/chatwire: synced through Phase 77 (commit 21e947a).
Phases 78–90 not yet synced.

Settings accordion (7 sections): Self handles, Whitelist, Appearance, Notifications,
Content Filter, Advanced (port/bind/proxy + API keys + image cache), Password.
Core integrations hidden from Plugins page: content_filter (Settings built),
mcp (Settings NOT yet built — see §4 and memory/project_chatwire_mcp_flesh_out.md).

COMPLETED IN PHASE 91:
  1. Command palette (Cmd+K) — DONE
  2. MCP Settings section (stdio transport + tool toggles + client snippets) — DONE
  3. LQIP blur placeholders — DONE

REMAINING ITEMS:
  1. MCP HTTP/SSE transport (~150 lines backend, Settings UI toggle prepped)
  2. Image perf Phase 3: MEDIA_BASE_URL env var, WebP output from sips
  3. RC1 gate: security audit + tech debt audit (memory/project_chatwire_rc1_gate.md)

Key blockers:
  - Edit history popover (#59): mbair is macOS 12 — no date_edited column.
  - PyPI plugin publishing: requires TWINE_TOKEN.
  - Ghost bubble reply quote: regression needs re-examination with screenshot.

VISUAL QA NOTE: LockoutTopBanner, CooldownBanner icon, LockoutFooterNote,
ChatPage header during lockout — require interactive mbair session.

Run: python3 -m pytest /home/mediafront/git/chatwire-dev/tests/ --tb=short -q
Run: npm --prefix /home/mediafront/git/chatwire-dev/web/frontend test -- --run
Run: npm --prefix /home/mediafront/git/chatwire-dev/packages/mobile test
After frontend changes: npm --prefix /home/mediafront/git/chatwire-dev/web/frontend run build
Commit dist/ with source changes.
All tests must pass before committing.

DEPLOY (only needed if code changed):
  ssh mbair "~/.local/pipx/venvs/chatwire/bin/python -m pip install --no-cache-dir --force-reinstall --no-deps 'chatwire @ git+ssh://git@github.com-chatwire/allenbina/chatwire-dev.git@main'"
  ssh mbair "/bin/launchctl kickstart -k gui/501/dev.chatwire.web && /bin/launchctl kickstart -k gui/501/dev.chatwire.bridge"
  ssh mbair "/usr/bin/curl -sf localhost:8723/healthz"

After work — commit, push, deploy (if code changed), sync public repo, and notify:
  curl -s -d "Phase NN complete — <summary>" ntfy.sh/p9SKpYzY70LlyK1N

Public repo sync (when next code change ships):
  rsync -a --checksum --exclude='dist/' --exclude='node_modules/' --exclude='__pycache__/' --exclude='.git/' --exclude='*.pyc' --exclude='*.egg-info/' /home/mediafront/git/chatwire-dev/ /tmp/chatwire-public/
  git -C /tmp/chatwire-public checkout -- .gitignore
  git -C /tmp/chatwire-public add -A && git -C /tmp/chatwire-public commit -m "..." && git -C /tmp/chatwire-public push origin main

NOTE: Run pytest as: python3 -m pytest /home/mediafront/git/chatwire-dev/tests/ --tb=short -q
NOTE: npm test command works — use: npm --prefix /home/mediafront/git/chatwire-dev/web/frontend test -- --run
NOTE: Mobile jest: npm --prefix /home/mediafront/git/chatwire-dev/packages/mobile test
NOTE: 1135 pytest / 459 Vitest / 29 mobile jest pass. 1 jsdom failure (App.test.tsx HTMLMediaElement.play — pre-existing, not a regression).
NOTE: test_rules_dsl.py excluded from pytest (pre-existing ImportError from stashed automations module).
NOTE: Tests mirror web/main.py helpers locally (never import web.main directly —
  module-level side-effects and Python-3.10+ annotation syntax breaks on Python 3.8).
NOTE: mbair is macOS 12.7.6 — date_edited column does not exist in chat.db there.
NOTE: Python 3.8 on plinux — use nested with statements (not parenthesized form)
  in test files. No walrus operator (:=), no match statements.
NOTE: Use asyncio.run() in new test files (not asyncio.get_event_loop().run_until_complete).
NOTE: When testing components that mock navigator.serviceWorker, set afterEach to
  restore it to a no-op stub (not undefined) so component cleanup doesn't throw.
NOTE: Mobile jest uses react@19 + react-test-renderer@19 (react-native 0.79 requires ^19).
  Mobile jest mocks: use var (not const) for objects referenced in jest.mock factories
  to avoid temporal-dead-zone issues with hoisting.
NOTE: ExportDropdown test pattern — outside-click: fireEvent.mouseDown(document.body).
  Link href assertions: use .toContain() not .toBe() since jsdom resolves relative hrefs.
NOTE: LogsPage test patterns — virtualizer mock: vi.mock('@tanstack/react-virtual') returns
  all items. Layout mock: vi.mock('../components/Layout') renders children directly.
  EventSource mock: globalThis.EventSource = MockEventSource, captures lastEs instance.
  Wrap SSE callbacks in act(). Export: spy document.createElement('a') + mock URL methods.
NOTE: api.test.ts patterns — no component rendering. window.location mocked via
  Object.defineProperty in beforeEach. vi.stubGlobal('fetch', vi.fn().mockResolvedValue(...))
  for fetch mocks. URL param assertions: fetchMock.mock.calls[0][0].toContain('param=val').
  POST body assertions: JSON.parse(fetchMock.mock.calls[0][1].body). FormData assertions:
  fd.get('handle') / fd.get('guid') / fd.get('file').
NOTE: useSSE test patterns — MockEventSource class with static instances array + helpers
  simulateMessage(data) and simulateError(). vi.useFakeTimers() for reconnect timer control.
  Set globalThis.EventSource = MockEventSource in beforeEach. enabled transitions tested
  via renderHook initialProps + rerender.
NOTE: useOnline test patterns — navigator.onLine override via Object.defineProperty with
  configurable:true. Fire events via window.dispatchEvent(new Event('offline'|'online')).
  Wrap dispatches in act().
NOTE: usePinnedSettings test patterns — localStorage.clear() in beforeEach for isolation.
  PINNABLE_LABELS is a named export; LS_KEY = 'chatwire-pinned-settings'. Test invalid/
  non-array/null JSON to exercise load() catch branch.
NOTE: useSounds test patterns — MockAudio class with static instances array; constructor
  sets this.src = new URL(url, location.href).href to match browser absolute-URL behaviour.
  globalThis.Audio = MockAudio in beforeEach. CRITICAL: ensureLoaded() creates BOTH
  sentAudio and receivedAudio — instances[0]=sentAudio, instances[1]=receivedAudio after
  any first play* call. configureSounds() in beforeEach resets config and nulls cache.
  document.hidden via Object.defineProperty. play() rejection: set rejecting mock on
  instance.play, call play function again, await Promise.resolve() to drain microtask.
NOTE: PluginFrame test patterns — jsdom 25 gives iframe.contentWindow a real Window;
  vi.spyOn(cw, 'postMessage') works directly. Dispatch messages with
  new MessageEvent('message', { source: iframe.contentWindow, data }) wrapped in act().
  register-css: assert document.querySelector('style[data-plugin-key="..."]').
  beforeEach removes leftover style elements. fireEvent.load(iframe) triggers onLoad.
NOTE: SlotRenderer test patterns — mock ./PluginFrame with a div exposing data-plugin-key,
  data-src, data-slot, data-slot-props (JSON). makeComp(testId) renders data-props as JSON.
  Error boundary: suppress console.error, check role="alert" textContent for plugin key.
NOTE: StatsWidget test patterns — QueryClientProvider with retry:false. Loading state:
  never-resolving Promise fetch mock, container.firstChild is null immediately.
  Null checks (error/disabled): setTimeout(r, 50) to let react-query settle.
  Rendered assertions: use waitFor. Progress bar: getByLabelText(/% sent/), check style.width.
  Date ranges: for...of loop over cases array (not it.each) to avoid template literal issues.
NOTE: PopoutPage test patterns — mock MessageList/ComposeBox with data-handle/data-is-group
  divs. Mock useTheme.applyTheme, useSSE (vi.fn()), useChatStore (vi.fn() with selector).
  Wrap MemoryRouter initialEntries + QueryClientProvider. Capture onEvent from
  mockedUseSSE.mock.calls[last][0].onEvent; call inside act(). Spy qc.invalidateQueries
  before renderPage() to assert cache invalidation.
NOTE: SettingsPage test patterns — mock sonner/Layout/usePinnedSettings/useTheme/useSounds/
  SlotRenderer/react-router-dom at module level. Pure functions (_formToApiRule,
  _apiRuleToForm) need no React wrapping. AccentColorPicker: use getByLabelText exact
  strings — 'Accent color hex value', 'Open color picker'. PasswordSection: use exact label
  strings 'New password' and 'Confirm new password' (regex /new password/i matches both).
  vi.spyOn(window, 'confirm') for handleClear guard. PasswordSection fetch: first call=GET
  (query), second call=POST (mutation).
```
