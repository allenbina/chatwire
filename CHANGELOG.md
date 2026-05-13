# Changelog

All notable changes to chatwire are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

## [1.14.0] - 2026-05-11

### Added
- **Read receipts** (#85 part 1): `is_read` and `date_read` from `chat.db`
  are now included in the message history API. The web UI shows "Read at
  H:MM AM/PM" below sent iMessage bubbles when a read receipt is available.
- **Tapbacks / reactions** (#85 part 2): Reaction emoji badges (❤️ 👍 👎 😂
  ‼️ ❓ 🎉) are queried from `chat.db` via `associated_message_guid` /
  `associated_message_type` and displayed as small pills anchored to the
  bottom-right of the relevant message bubble.
- **Inline replies** (#85 part 3): `reply_to_guid` is resolved to the parent
  message text + sender and included in the API response. A quoted-reply block
  is rendered above the bubble; clicking it scrolls to the original message.
- **Location share cards** (#84): Messages with `balloon_bundle_id =
  com.apple.messages.MapBalloonProvider` or Apple Maps URLs are rendered as a
  📍 card with a Google Maps link.
- **Sticker / Memoji display** (#85 part 4): Stickers and Memoji attachments
  already stored as image files now display correctly. The attachment `kind`
  field normalises sticker MIME types so they render as inline images.
- **chatwire-ntfy standalone plugin** (#78): ntfy notification support
  extracted from core into `chatwire-plugins/chatwire-ntfy/`. Install with
  `pipx inject chatwire chatwire-ntfy`. `TIER = "notify"`.
- **chatwire-telegram standalone plugin** (#81): Telegram relay extracted
  from core into `chatwire-plugins/chatwire-telegram/`. `TIER = "official"`.
- **chatwire-webhook standalone plugin** (#80): Webhook output extracted from
  core into `chatwire-plugins/chatwire-webhook/`. `TIER = "official"`.
- **Theme ecosystem foundation** (#76): `sanitize_custom_css()` strips
  `@import` rules and external `url()` references from user theme packages.
  `parse_package()` sets `custom_css_sanitized` flag. Settings UI shows a
  warning when the active theme pack includes custom CSS.
  `docs/wiki/theme-format.md` documents the full JSON schema. Three example
  themes added to `docs/examples/`.
- **macOS compatibility matrix** (#86): `docs/wiki/compatibility.md` with
  feature-by-feature breakdown across macOS 12–15, Python versions, and
  hardware configurations. Linked from README.

### Fixed
- **Logout icon missing** (audit MEDIUM): `LogOut` icon from lucide-react
  now appears on the sign-out link in SettingsPage.

## [1.13.0] - 2026-05-11

### Added
- **Structured log viewer** (#60): `web.log_stream` is now wired into the web
  process. Startup, inbound messages (sender name only), outbound sends, and
  plugin enable/disable events are written to `~/.chatwire/chatwire.jsonl`.
  The LogsPage `GET /api/ui/logs` and SSE `GET /api/ui/logs/stream` endpoints
  now have data to display.
- **Auto dark/light theme** (#62): New "Auto" option in the color scheme
  picker. When selected, two sub-dropdowns appear (dark scheme + light scheme,
  defaulting to Dracula / GitHub Light). `useTheme` listens to
  `matchMedia('(prefers-color-scheme: dark)')` and switches `data-theme`
  automatically on OS preference changes.
- **API key inline edit/rescope** (#63): Edit button per row in the API Keys
  settings section; click to rename a key and toggle its permission scopes
  inline with a Save/Cancel form. Backed by the existing
  `PATCH /api/ui/api-keys/{prefix}` endpoint.
- **Offline indicator** (#65): `useOnline` hook tracks `navigator.onLine`.
  When offline: sidebar shows a red dot + "Offline" pill; compose box shows
  "No connection — messages will send when back online".
- **Mark seen on scroll** (#64): `markSeen` now fires when the user scrolls
  to the bottom of the message list, or immediately when new messages arrive
  while already at the bottom. Removed the imprecise 3-second timer.

### Fixed
- **Group chats 403 on open** (#61): Removed the WHITELIST_HANDLES guard from
  `GET /api/ui/messages`. Whitelist controls who can SEND; if a conversation
  is in chat.db the user owns it and can read it.

## [1.12.0] - 2026-05-10

### Added
- **Scoped API keys** (#26): Multiple named API keys with per-key permission
  scopes (`trigger_actions`, `read_conversations`, `send_messages`,
  `manage_settings`). Keys use the `cwk_` prefix + 32 hex chars and are
  stored PBKDF2-SHA256-hashed in `~/.chatwire/api_keys.json` (chmod 600).
  Authenticate via `Authorization: Bearer cwk_<key>`.
  Settings UI: create / delete / copy keys with scope checkboxes.
- **Mark all read** (#19): "Mark all read" button in the sidebar clears all
  unread badges; also calls `navigator.clearAppBadge()` on supported
  browsers (PWA / Android). Keyboard shortcut `Shift+Escape` works from
  anywhere in the app.
- **Appearance quick-link** (#10): Sidebar footer now has an "Appearance"
  link that navigates to `/settings#appearance` and auto-opens the
  Appearance accordion section.
- **Hash-driven settings accordion** (#9): `SettingsPage` reads the URL
  hash on mount and on hash changes to open the matching section and
  scroll it into view — enables deep-linking to any settings section.

### Changed
- `web/main.py` auth gate: Bearer token path added before cookie path —
  `Authorization: Bearer cwk_…` header is validated against the API key
  store and the required scope is checked against the route map before
  falling through to cookie auth.

## [1.11.0] - 2026-05-10

### Changed
- MediaGallery lightbox migrated from raw `@radix-ui/react-dialog` to the
  shadcn `Dialog` wrapper (`Dialog`, `DialogPortal`, `DialogOverlay`,
  `DialogClose`, `DialogTitle` from `@/components/ui/dialog`).
  Visually-hidden `DialogTitle` added for screen-reader accessibility.

### Added
- Lightbox keyboard navigation: `ArrowLeft` / `ArrowRight` keys step through
  images; `Escape` closes (handled by Radix).
- 14 Vitest unit tests for `MediaGallery` covering gallery grid rendering
  (1 / 2 / 4 / 5+ images, overflow badge) and full lightbox interaction
  (open, close, prev/next buttons, arrow-key navigation, boundary clamping).
  Total Vitest count: 84 (was 70).

## [1.10.0] - 2026-05-09

### Added
- Sign out link in the SettingsPage footer — `<a href="/logout">Sign out</a>` (Option H).

### Removed
- `POST /api/auth/password` endpoint and `_render_password_card()` helper removed from
  `web/main.py` (htmx-era dead code, superseded by `POST /api/ui/settings/password` in v1.8.0).
- `web/templates/_login.html` and `web/templates/_password_card.html` deleted
  (replaced by React LoginPage and PasswordSection respectively).

## [1.9.0] - 2026-05-09

### Added
- React login page at `/app/login` — replaces the Jinja2 `_login.html`
  template. New JSON endpoint `POST /api/ui/auth/login` (public path, no
  cookie required) verifies the password, sets the session cookie, and
  returns `{"ok": true, "next": "<url>"}`. Same rate-limit bucket as the
  old `/login` form. The auth-gate middleware now redirects unauthenticated
  requests to `/app/login`; `/logout` redirects there too.

### Changed
- `web/auth.py`: `_PUBLIC_PREFIXES` now includes `/app/assets/` so the
  React SPA JavaScript and CSS load correctly for unauthenticated users
  (required for the login page to render). `/app/login` added to
  `_PUBLIC_PATHS`.

### Removed
- Jinja2 `GET /login` and `POST /login` route handlers removed from
  `web/main.py`. The `_login.html` template remains on disk but is no
  longer served.

## [1.8.0] - 2026-05-09

### Added
- React Settings — Password section: set, change, or remove the web UI
  password directly from the Settings page without touching config files.
  New JSON endpoints `GET /api/ui/settings/password` (auth status) and
  `POST /api/ui/settings/password` (set / change / clear). Same rate-limit
  and current-password verification as the existing login route. On
  password change the response issues a fresh session cookie so the user
  stays logged in.

### Changed
- Legacy Jinja2/htmx UI removed (Option D — Chunk 19). React SPA at
  `/app/` is now the only UI; `GET /` always redirects to `/app/`.
  `POST /whitelist/add`, `POST /whitelist/remove`, `POST /refresh_contacts`
  now return JSON (`{"ok": true}`) instead of HTML fragments.
  `POST /whitelist/remove` now accepts the `input` field that the React
  SettingsPage sends (previously a silent no-op due to field name mismatch).

## [1.7.0] - 2026-05-09

### Added
- Docker image published to GHCR (`ghcr.io/allenbina/chatwire`)
  - Multi-stage Dockerfile: Node 22 builds the React frontend; Python 3.13-slim serves the app
  - Multi-platform build (linux/amd64 + linux/arm64) via docker/build-push-action
  - GitHub Actions workflow (`.github/workflows/docker.yml`) triggers on the same `v*` tags as `publish.yml`
  - Serves the web dashboard, REST API, SSE stream, and /healthz inside Docker
  - macOS-specific features (iMessage read/send, menu-bar toolbar) unavailable in Docker (documented)
  - Layer cache backed by GitHub Actions cache for fast incremental rebuilds
- React Native + Expo mobile app (iOS + Android)
  - Shared TypeScript client package (`@chatwire/shared`) with full API coverage
  - Core screens: ServerConfig, ConversationList, MessageList, Settings
  - Real-time SSE updates with polling fallback and exponential back-off reconnect
  - Push notifications via Expo Notifications (Android channel, iOS permission prompt)
  - Background fetch registration (15-min interval, TaskManager)
  - Full-screen image viewer: pinch-to-zoom, pan, double-tap zoom, spring reset, Share
  - Video player: expo-video, thumbnail → expand, fullscreen, picture-in-picture
  - Haptics wired into compose send and message long-press
  - Dracula theme tokens (`src/theme/colors.ts`) used throughout
  - EAS build profiles: development / preview / production; autoIncrement build numbers
  - GitHub Actions stub for Android preview APK (`mobile-preview.yml`)
  - Distribution docs (`docs/MOBILE_DISTRIBUTE.md`)
- PWA overhaul
  - Offline support, service worker (`dist/sw.js` via VitePWA)
  - PWA install prompt with beforeinstallprompt capture
  - 17 Vitest unit tests; 4 Jest mobile test files
  - Playwright E2E tests with route intercepts (no live backend required)
  - axe-core accessibility scans via `@axe-core/playwright`
  - Code splitting: SettingsPage (27 KB), PopoutPage (1.4 KB), StatsWidget (2.1 KB)
  - Main bundle 315 KB / ~100 KB gzip
  - `/` → `/app/` redirect (302); legacy Jinja2/htmx UI preserved at `/?legacy=1`

## [1.6.0] - 2024-10-15

### Added
- Third-party integration entry-point group (`chatwire.integrations`)
- Frontend plugin slot system — integrations can inject UI widgets
- Stats integration end-to-end proof

## [1.5.0] - 2024-07-01

### Added
- Initial public release
- iMessage ↔ Telegram bridge (macOS only, requires macOS + Messages.app)
- FastAPI web UI with real-time server-sent events
- macOS menu bar app via rumps
- `chatwire install-agents` launchd plist installer
- `chatwire-toolbar` menu-bar entry point
