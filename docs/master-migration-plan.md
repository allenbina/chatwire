# Chatwire React Migration — Master Plan

> 8-phase migration from Jinja2/htmx to React/Vite/TypeScript.
> Each phase broken into loop-sized chunks (~15-20 min Sonnet sessions).
> Detailed specs written 1-2 phases ahead; high-level specs for all.

---

## Phase Overview

| Phase | What | Chunks | Status |
|-------|------|--------|--------|
| 1 | Scaffold: Vite + React + TS + Tailwind + FastAPI wiring | 1 | Done |
| 2 | Core UI: conversations, messages, compose, SSE | 2 | Done |
| 3 | Feature parity: themes, media, settings, export, a11y | 4-5 | Next |
| 4 | Plugin SDK: chatwire-sdk, frontend slots, scaffolding | 2-3 | Planned |
| 5 | Polish: PWA, Playwright E2E, axe-core a11y, perf | 2-3 | Planned |
| 6 | Mobile: React Native + Expo (iOS + Android) | 5-6 | Planned |
| 7 | CI/CD: PyPI + DMG + Homebrew + GitHub Releases | 2 | Independent |
| 8 | Extras: Tauri desktop, Docker, npm wrapper | 3 | Independent |
| 9 | shadcn/ui: polish all UI components | 3 | After Phase 3+ |

---

## Phase 1: Scaffold (COMPLETE)

- Vite 6 + React 18 + TypeScript 5.6 in `web/frontend/`
- Tailwind CSS 4 with Dracula design tokens
- FastAPI dual-serving: Jinja2 at `/`, React SPA at `/app/*`
- CI updated: Node.js 22 + npm ci + npm run build before Python wheel
- Vitest + React Testing Library smoke tests
- @tanstack/react-query + zustand installed

## Phase 2: Core UI (COMPLETE)

- `/api/ui/*` JSON endpoints (conversations, messages, send, themes)
- ConversationList, MessageList, MessageBubble, ComposeBox components
- Zustand store (activeHandle, optimistic messages, sidebarOpen)
- SSE hook with auto-reconnect
- React Router (/app/, /app/chat/:handle, /app/settings)
- Layout with mobile drawer
- Group chats, photo upload, load-older pagination

---

## Phase 3: Feature Parity

Goal: the React UI at `/app` must do everything the Jinja2 UI at `/`
does. After this phase, the Jinja2 UI can be deprecated.

### Chunk 1: All 23 themes as JSON design tokens
- Convert each of the 23 CSS theme files to a JSON token format
- Theme structure: `{ name, label, colors: { bg-primary, bg-secondary, ... } }`
- Store themes in `web/frontend/src/themes/` as individual .ts files
- Theme switcher component in settings applies tokens as CSS variables
- System theme detection (prefers-color-scheme) for "System" option
- Persist theme choice in localStorage + sync to server setting

### Chunk 2: Media handling
- Image gallery grid (1-4 images, +N overflow) — match existing layout
- Image lightbox (click to view full-size) — use Radix Dialog
- Video player (inline HTML5 with controls)
- Audio player (inline HTML5 with controls)
- File attachment download link with filename + size
- Attachment sync status spinner (pending/syncing)
- Thumbnail loading with lazy loading (IntersectionObserver)

### Chunk 3: Settings panel (full)
- Port all 16+ settings from the Jinja2 accordion UI
- Theme selection (dropdown with preview)
- Whitelist management (add/remove contacts + groups)
- Self handles configuration
- API key generation/revocation
- Notification settings (mute, mode, detail level)
- Port & bind address, proxy headers
- ntfy topic, hiatus mode, reminder settings
- Spam whitelist, history limit, thumbnail size, time format
- Custom CSS injection

### Chunk 4: Export + special features
- JSON/TXT/CSV export of message history
- Bulk photo ZIP download
- Popout window route (/app/popout?handle=X)
- Update banner (GitHub Releases polling, dismiss per version)
- Version display
- Contact sync button

### Chunk 5: Accessibility (port wave 6)
- role="log" + aria-live="polite" on message container
- role="article" + aria-label on each message bubble
- Semantic landmarks (nav, main)
- Skip-nav link (sr-only, visible on focus)
- aria-label on compose box and send button
- aria-current="page" on active conversation
- Focus management on conversation switch
- Gallery role="group" with aria-label
- Meaningful image alt text
- No div/span onclick — all interactive elements use button/a
- .sr-only CSS utility class
- axe-core automated scan in Vitest

---

## Phase 4: Plugin SDK

Goal: make it easy for third parties to build chatwire plugins with
both backend and frontend components.

### Chunk 1: chatwire-sdk Python package
- New package at `packages/sdk/` (or `chatwire-sdk/`)
- Contains: base Integration class, type stubs, settings schema types
- `chatwire plugin init <name>` CLI scaffolding command
- Generates: pyproject.toml, integration class, test file, README
- Publish to PyPI as `chatwire-sdk`

### Chunk 2: Frontend plugin slot system
- Plugin registration API in React:
  ```typescript
  chatwire.registerSlot('message.toolbar', ComponentRef)
  chatwire.registerSlot('sidebar.panel', ComponentRef)
  chatwire.registerSlot('settings.page', ComponentRef)
  chatwire.registerSlot('compose.extension', ComponentRef)
  ```
- SlotRenderer component that renders registered components
- Plugin manifest format (chatwire-plugin.toml)
- Hot reload support for plugin development

### Chunk 3: Port built-in integrations to SDK
- Refactor one built-in integration (e.g., Stats) to use the SDK
- Stats dashboard as a frontend slot (sidebar.panel)
- Prove the SDK works end-to-end with a real integration
- Document the plugin development workflow

---

## Phase 5: Polish

Goal: production-ready quality. PWA, E2E tests, accessibility
audit, performance optimization.

### Chunk 1: PWA overhaul
- Service worker via Workbox (replace hand-rolled sw.js)
- Offline support: cache shell + API responses
- Background sync for messages sent while offline
- Push notifications via APNs/FCM (server-side trigger)
- Web manifest with proper splash screens and icons
- Install prompt / add-to-home-screen

### Chunk 2: E2E tests + accessibility
- Playwright test suite covering:
  - Login flow
  - Send message (text + image)
  - Switch conversations
  - Change theme
  - Export messages
  - Popout window
- axe-core integration in Playwright (scan every page)
- Visual regression tests (Playwright screenshots per theme)

### Chunk 3: Performance + cleanup
- Virtualized message list (react-window or @tanstack/virtual)
- Code splitting (settings, popout, plugin UIs = lazy loaded)
- Lighthouse audit — target 90+ on all categories
- Remove Jinja2 templates (old UI) — React is now the default at /
- Remove htmx dependency
- Update README with new architecture

---

## Phase 6: Mobile App

Goal: React Native + Expo mobile app (iOS + Android) that connects
to the chatwire server as a remote client.

### Chunk 1: Project scaffold + shared package
- Initialize Expo project at `packages/mobile/`
- Create `packages/shared/` with TypeScript types, API client
- Share types between web and mobile
- Configure Expo with app.json (name, icons, splash)

### Chunk 2: Core mobile UI
- ConversationList screen (FlatList with pull-to-refresh)
- MessageList screen (inverted FlatList, auto-scroll)
- ComposeBox (text input + camera/gallery picker)
- Tab navigation (Chats, Settings)
- Server URL configuration screen (first-launch)

### Chunk 3: Real-time + notifications
- WebSocket connection to chatwire server
- Push notifications via Expo Push + server-side trigger
- Background fetch for new messages
- Typing indicators

### Chunk 4: Media + polish
- Image viewer with pinch-to-zoom
- Video player
- Share sheet integration (share photos/files to chatwire)
- Touch gestures (swipe to reply, long-press for actions)
- Haptic feedback

### Chunk 5: Build + distribute
- EAS Build configuration (iOS + Android)
- iOS TestFlight distribution
- Android APK on GitHub Releases
- App icons and splash screens
- App Store metadata (screenshots, description)

---

## Phase 7: CI/CD Pipeline (independent — can run in parallel)

Goal: one git tag produces all distribution artifacts automatically.

### Chunk 1: Enhanced publish workflow
- Build React frontend (npm ci + npm run build)
- Build Python wheel with frontend bundle included
- Publish to PyPI (existing OIDC trusted publisher)
- Create GitHub Release with changelog
- Update Homebrew tap formula (auto-PR to homebrew-tap)

### Chunk 2: macOS DMG + code signing
- Briefcase configuration for macOS .app bundle
- Bundled Python runtime (python-build-standalone)
- Code signing with Apple Developer certificate (GitHub secret)
- Notarization via `xcrun notarytool`
- Upload .dmg to GitHub Releases
- (Requires Apple Developer account — $99/year)

---

## Phase 8: Extras (independent — can run in parallel)

### Chunk 1: Tauri desktop app
- Tauri configuration wrapping the React web UI
- System tray icon with status
- Native notifications
- Global keyboard shortcuts
- Builds for macOS, Windows, Linux

### Chunk 2: Docker image
- Dockerfile (Python + pre-built React bundle)
- Multi-arch build (amd64 + arm64)
- Push to ghcr.io/allenbina/chatwire
- Demo mode (no macOS dependencies — mock data for demos)

### Chunk 3: npm wrapper package
- npm package that manages a Python venv under the hood
- `npx chatwire` installs Python if needed + runs chatwire
- Publish to npmjs.com

---

## API Versioning

Starting Phase 3, all new API endpoints use `/api/v1/` prefix:

```
/api/v1/conversations
/api/v1/messages/{handle}
/api/v1/settings
/api/v1/plugins
/api/v1/export/{format}
/ws/v1                    ← WebSocket (Phase 5+)
```

Existing `/api/ui/*` endpoints from Phase 2 get aliased to `/api/v1/*`
and the old paths deprecated.

---

## Repo Structure (post-split)

### allenbina/chatwire (public)
```
chatwire/
  web/
    frontend/          ← React + Vite (web UI)
    main.py            ← FastAPI backend
    api_v1.py          ← API routes
    ...
  packages/
    sdk/               ← chatwire-sdk (Phase 4)
    shared/            ← shared TS types (Phase 6)
    mobile/            ← React Native + Expo (Phase 6)
  integrations/        ← built-in integrations
  .github/workflows/   ← CI/CD
  docs/                ← user-facing docs only
  ...
```

### allenbina/chatwire-dev (private)
```
chatwire-dev/
  docs/
    HANDOFF.md         ← loop state file
    greenfield-analysis.md
    greenfield-distribution-and-migration.md
    master-migration-plan.md
    repo-split-plan.md
  scripts/
    chatwire-loop.sh
    chain-waves.sh
    wait_pypi.py
```

---

## Phase 9: shadcn/ui Migration

Goal: replace hand-rolled UI primitives with shadcn/ui components for
a polished, consistent look across the entire app. shadcn/ui is built
on Radix (already installed) + Tailwind (already configured).

### Chunk 1: Initialize shadcn/ui + core components
1. Run `npx shadcn@latest init` in `web/frontend/`
   - Style: Default
   - Base color: Slate (overridden by theme tokens)
   - CSS variables: Yes (maps to our existing --color-* tokens)
2. Configure `components.json` to use our existing Tailwind + path aliases
3. Add core components:
   ```bash
   npx shadcn@latest add button input textarea dialog dropdown-menu
   npx shadcn@latest add accordion select tooltip toast scroll-area
   npx shadcn@latest add avatar badge separator sheet tabs
   ```
4. Wire the shadcn CSS variables to our theme token system so all 23
   themes apply automatically to shadcn components
5. Verify `npm run build` still passes

### Chunk 2: Swap UI primitives across the app
Replace hand-rolled elements with shadcn equivalents:
- All `<button>` elements → `<Button>` (variants: default, ghost, outline)
- Compose input → `<Textarea>` with auto-resize
- Settings accordions → `<Accordion>`
- Theme picker → `<Select>`
- Export format picker → `<DropdownMenu>`
- Image lightbox → `<Dialog>`
- Mobile sidebar → `<Sheet>` (slide-over drawer)
- Popout window → uses `<Dialog>` primitives
- Notification toasts → `<Toast>` (sonner)
- Tooltips on icon buttons → `<Tooltip>`
- Conversation avatars → `<Avatar>` with fallback initials
- Unread badges → `<Badge>`
- Settings sections → `<Tabs>` or `<Accordion>`
- Message list scroll → `<ScrollArea>` (custom scrollbar styling)

### Chunk 3: Polish + dark/light consistency
- Audit every component for theme consistency across all 23 themes
- Ensure light themes (GitHub Light, One Light, Solarized Light, etc.)
  look correct — shadcn defaults to dark, need to verify light mode
- Update custom CSS injection to play nicely with shadcn's CSS layers
- Add transition animations (shadcn components support this natively)
- Verify accessibility — shadcn inherits Radix's a11y, should be free

---

## Feature Parity Checklist

Full checklist lives in `docs/greenfield-distribution-and-migration.md`
§5. Each item must pass before the Jinja2 UI is removed in Phase 5.

---

## Decision Log

| Decision | Rationale |
|----------|-----------|
| React 19 + Vite 6 + TypeScript | Ecosystem, contributor familiarity, component model |
| Tailwind CSS 4 (build-time) | Already using Tailwind; move from CDN to build for tree-shaking |
| Zustand (not Redux) | Lightweight, sufficient for chat state |
| TanStack Query | Server state caching, pagination, background refetch |
| Radix UI → shadcn/ui | Radix primitives + shadcn polish; copy-paste components, theme-token compatible |
| WebSocket (Phase 5) | Bidirectional needed for typing/presence; SSE is interim |
| Expo (not bare RN) | Build pipeline, OTA updates, push notifications |
| Briefcase (not PyInstaller) | Proper .app bundle, code signing, cross-platform |
| Keep FastAPI + Python backend | macOS integration layer, plugin system, pipx install |
| Pre-build React into wheel | Users never need Node.js |
| Separate public/private repos | Clean public history, internal dev state stays private |
