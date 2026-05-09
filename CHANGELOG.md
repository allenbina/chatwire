# Changelog

All notable changes to chatwire are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

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
