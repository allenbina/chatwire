# Changelog

All notable changes to chatwire are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

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
