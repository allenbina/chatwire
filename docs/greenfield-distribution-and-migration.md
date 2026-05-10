# Distribution, Mobile, and Migration Strategy

> Follow-up to greenfield-analysis.md — answers to your questions about
> packaging, mobile apps, bundling Python, CI/CD, and feature parity.

---

## 1. Distribution: All the Ways People Can Install It

Yes, you can publish everywhere from a single CI/CD pipeline. Here's
every channel that makes sense, ranked by effort:

| Channel | Format | User Experience | CI Effort | Priority |
|---------|--------|-----------------|-----------|----------|
| **PyPI** | wheel (sdist) | `pipx install chatwire` | Low — you already have this | Must-have |
| **Homebrew** | formula in your tap | `brew install allenbina/tap/chatwire` | Low — you have the tap | Must-have |
| **macOS DMG** | .app bundle | Double-click, drag to /Applications | Medium | Should-have |
| **GitHub Releases** | .dmg + .whl + .tar.gz | Download from releases page | Low (follows from DMG) | Should-have |
| **npm** | wrapper package | `npx chatwire` (installs Python under the hood) | Medium | Nice-to-have |
| **Docker** | image on GHCR | `docker run chatwire` (non-Mac demo mode) | Low | Nice-to-have |
| **iOS TestFlight** | .ipa via Xcode Cloud | TestFlight install | High | Future |
| **Android APK** | .apk on GitHub Releases | Sideload or F-Droid | Medium | Future |
| **Windows MSI** | installer | Traditional Windows install | Medium | Future |

### Can we keep pipx?

**Yes, absolutely.** pipx remains the primary install method. The React
frontend gets pre-built in CI and included in the wheel — users never
need Node.js. The wheel contains:

```
chatwire/
  web/
    frontend/
      dist/        ← pre-built React bundle (index.html, assets/)
    templates/     ← legacy Jinja2 (kept for email templates, etc.)
    static/        ← existing static files
```

FastAPI serves `dist/index.html` for all frontend routes and proxies
`/api/*` to the backend. Same `pipx install chatwire` command, same
experience.

### The DMG: How It Works

A macOS .app bundle packages everything:
- Python runtime (embedded, see §2 below)
- All pip dependencies
- Pre-built React frontend
- launchd plist templates
- The `chatwire` CLI as the app's main executable

Tools to build it:
- **py2app** (Python-native, macOS only) — simplest, well-tested
- **Briefcase** (BeeWare project) — cross-platform, generates .app/.dmg/.msi
- **PyInstaller** — single binary, but less Mac-native

**Recommendation: Briefcase.** It generates a proper .app with Info.plist,
code signing support, and notarization. One `briefcase package macOS`
command in CI produces a signed .dmg. It also handles Windows .msi and
Linux .AppImage from the same config, so you get desktop apps for all
three platforms from one pipeline.

### npm wrapper — how it would work

An npm package that:
1. Checks if Python 3.10+ exists
2. If not, downloads a standalone Python build (see §2)
3. Runs `pip install chatwire` in an isolated venv
4. Proxies `npx chatwire` → the installed CLI

This is how tools like `aws-cdk` and `pyright` distribute Python tools
via npm. It's a convenience wrapper, not a rewrite. Low priority but
trivially maintainable once the CI pipeline exists.

---

## 2. Bundling Python: Licensing and Strategy

### Can you bundle Python in the app?

**Yes.** CPython is BSD-licensed (PSF License). You can freely bundle it
in commercial or open-source apps. No licensing issues whatsoever.

### How to bundle it

Two approaches:

**Option A: Standalone Python builds (recommended)**

The [python-build-standalone](https://github.com/indygreg/python-build-standalone)
project publishes pre-built, relocatable Python interpreters for every
platform. These are self-contained — no dependency on the OS Python.
Briefcase uses these under the hood.

- macOS: ~30MB compressed
- Works on any macOS 11+ (Big Sur and later)
- No conflict with system Python or Homebrew Python
- User doesn't need Python installed at all

**Option B: PyInstaller single-binary**

Bundles Python + all deps into one executable. Simpler but:
- Slower startup (unpacks to temp dir)
- Antivirus false positives on Windows
- Harder to debug

**Recommendation:** Option A via Briefcase for .app/.dmg, and let pipx
users bring their own Python (they already have it if they have pipx).

### Fallback strategy

The install script (`curl | bash`) can do:

```bash
if command -v python3 &>/dev/null && python3 -c "import sys; assert sys.version_info >= (3,10)"; then
    pipx install chatwire
else
    # Download standalone Python, create venv, install chatwire
    curl -LO https://github.com/.../cpython-3.12-macos.tar.gz
    # ...
fi
```

Users with Python get the lightweight pipx path. Users without Python
get a self-contained install. Both end up with the same `chatwire` CLI.

---

## 3. CI/CD Pipeline: One Push, All Artifacts

A single GitHub Actions workflow triggered on version tags (`v*`):

```
v2.0.0 tag pushed
  │
  ├── Job 1: Build React frontend
  │   └── npm ci && npm run build → upload dist/ as artifact
  │
  ├── Job 2: Python wheel (needs Job 1)
  │   ├── Copy dist/ into wheel
  │   ├── Build sdist + wheel
  │   └── Publish to PyPI
  │
  ├── Job 3: macOS DMG (needs Job 1)
  │   ├── Briefcase package macOS
  │   ├── Code sign + notarize
  │   └── Upload .dmg to GitHub Releases
  │
  ├── Job 4: Windows MSI (needs Job 1) [future]
  │   ├── Briefcase package windows
  │   └── Upload .msi to GitHub Releases
  │
  ├── Job 5: Docker image (needs Job 1) [future]
  │   ├── Build multi-arch image
  │   └── Push to ghcr.io/allenbina/chatwire
  │
  ├── Job 6: Homebrew formula update (needs Job 2)
  │   ├── Update homebrew-tap formula with new version + SHA
  │   └── Push to allenbina/homebrew-tap
  │
  └── Job 7: GitHub Release (needs all)
      └── Create release with .dmg, .whl, .tar.gz, changelog

Total CI time: ~8-10 minutes (parallelized)
```

**Yes, this is mandatory.** You're not going to manually build a DMG,
wheel, and Docker image for every release. The pipeline pays for itself
on the first release.

---

## 4. Mobile Apps: How Much Work?

### The approach: React Native (not a webview wrapper)

Since you're moving to React for the web frontend, a **React Native**
mobile app shares ~60-70% of the business logic (API client, state
management, WebSocket handling, message parsing). The UI components
are rewritten in React Native primitives (`<View>`, `<Text>`,
`<FlatList>` instead of `<div>`, `<span>`, `<ul>`).

Alternatively: **Expo** (React Native framework) handles the build
pipeline, OTA updates, push notifications, and app store submission.

### What a mobile app does differently

The mobile app is a **client only** — it connects to the chatwire
server running on the user's Mac over the network (LAN, Tailscale, or
a tunnel). It does NOT run the bridge or access chat.db. It's a remote
UI for the FastAPI backend.

This means:
- The backend API must be complete (all features accessible via API,
  not just HTML templates)
- WebSocket support is essential (SSE is awkward on mobile)
- Push notifications go through APNs/FCM, triggered by the server

### Effort estimate

| Component | Effort | Notes |
|-----------|--------|-------|
| Shared API client + types | ~4 hours | TypeScript, shared with web |
| Core mobile UI (conversations + messages) | ~8 hours | React Native + Expo |
| Media handling (camera, gallery, share sheet) | ~4 hours | Expo modules |
| Push notifications | ~4 hours | Expo Push + server-side APNs/FCM |
| Settings + plugin UI | ~4 hours | Mirrors web settings |
| iOS build + TestFlight | ~2 hours | Expo EAS Build |
| Android build + APK | ~2 hours | Expo EAS Build |
| **Total** | **~28 hours** | Roughly 3 days of Sonnet work |

### Should you do it during the overhaul?

**Yes, but as Phase 6 — after the web React migration is stable.**

The web migration (Phases 1-5) produces the API layer and WebSocket
infrastructure that the mobile app consumes. Building them in parallel
would mean designing the API twice. The sequencing:

1. Phases 1-5: React web + WebSocket API + plugin SDK (~26 hours)
2. Phase 6: Mobile app using the same API (~28 hours)
3. Total: ~54 hours = roughly 5-6 days of autonomous Sonnet work

### Does it make logical sense?

**Yes, strongly.** The whole point of chatwire is accessing iMessage
from non-Apple devices. A mobile app for Android is arguably the
killer feature — it's literally "iMessage on Android" (via your Mac
as a bridge). iOS users don't need it (they have Messages.app), but
Android users would install chatwire specifically for this.

---

## 5. Feature Parity: Nothing Gets Lost

### Do we need a feature checklist?

**Yes, and here it is.** Every feature below must work in the React
frontend before the old Jinja2 templates are removed. This is the
migration acceptance test.

### Complete Feature Inventory (current state: v1.6.0)

#### Core Messaging
- [ ] Conversation list with search/filter
- [ ] Message bubbles (text, sent/received styling)
- [ ] Image galleries (1-4 grid, +N overflow)
- [ ] Video player (inline)
- [ ] Audio player (inline)
- [ ] File attachment download
- [ ] Link previews (domain, title, OG image)
- [ ] Compose box (text + emoji picker + attachment upload)
- [ ] Optimistic send (ghost message before server ACK)
- [ ] Auto-scroll on new messages
- [ ] Load-older pagination (intersection observer)
- [ ] Delivery status indicators
- [ ] Attachment sync status (spinner)

#### Real-Time
- [ ] Live message streaming (currently SSE → will be WebSocket)
- [ ] Conversation list auto-refresh
- [ ] Keepawake status indicator (coffee/moon icon)

#### Accessibility (Wave 6 — must migrate)
- [ ] `role="log"` + `aria-live="polite"` on message container
- [ ] `role="article"` + `aria-label` on each message
- [ ] Semantic landmarks (`<nav>`, `<main>`)
- [ ] Skip-nav link (sr-only, visible on focus)
- [ ] `aria-label` on compose box and send button
- [ ] `aria-current="page"` on active conversation
- [ ] Focus management on conversation switch
- [ ] Gallery `role="group"` with `aria-label`
- [ ] Meaningful image alt text
- [ ] No div/span onclick (all interactive = button/a)
- [ ] `.sr-only` CSS utility class

#### Themes
- [ ] 23 themes (System + 22 named themes)
- [ ] Dynamic theme switching (no reload)
- [ ] CSS variable bridge (--app-color-*)
- [ ] Custom CSS injection (user-provided styles)

#### Authentication & Security
- [ ] Login page (password + CSRF)
- [ ] Session management (30-day TTL, sliding refresh)
- [ ] Rate limiting (10 attempts / 15 min)
- [ ] API key auth (for programmatic access)

#### Settings (16+ config options)
- [ ] Theme selection
- [ ] Whitelist management (contacts + groups)
- [ ] Self handles configuration
- [ ] API key generation/revocation
- [ ] Notification settings (mute, mode, detail level)
- [ ] Port & bind address
- [ ] Proxy headers toggle
- [ ] ntfy topic configuration
- [ ] Hiatus mode (suppress during time ranges)
- [ ] Reminder settings (auto-check intervals)
- [ ] Spam whitelist
- [ ] History limit (pagination size)
- [ ] Thumbnail max size
- [ ] Time format selection
- [ ] Custom CSS injection

#### Export
- [ ] JSON export
- [ ] TXT export
- [ ] CSV export
- [ ] Bulk photo ZIP download

#### Plugin System
- [ ] Plugin browser (official signed + community unsigned)
- [ ] Plugin install/uninstall
- [ ] Plugin settings UI (JSON Schema driven)
- [ ] Signed plugin verification badge

#### Integrations (must continue working — backend unchanged)
- [ ] Telegram bridge
- [ ] Webhook relay
- [ ] Tinfoil (E2E encryption)
- [ ] Content filter
- [ ] Stats dashboard
- [ ] MCP (Claude Code tools)

#### PWA
- [ ] Service worker (push notifications)
- [ ] Web manifest (standalone, icons)
- [ ] Install prompt / add-to-home-screen

#### Special
- [ ] Popout window (standalone conversation)
- [ ] Update banner (GitHub Releases polling)
- [ ] Version display
- [ ] Health check endpoint

#### CLI (unchanged — not part of frontend migration)
- [ ] `chatwire setup`
- [ ] `chatwire install-agents` / `uninstall-agents`
- [ ] `chatwire logs`
- [ ] `chatwire doctor`
- [ ] `chatwire migrate`
- [ ] `chatwire uninstall`

#### Menu Bar Toolbar (unchanged — Python/rumps)
- [ ] Service status
- [ ] Quick-launch buttons
- [ ] Auto-refresh

### How migration works

The migration is **not** a line-by-line port. It's a functional rewrite
where each React component replaces a Jinja2 template:

| Jinja2 Template | React Component | Notes |
|-----------------|-----------------|-------|
| `_conversations.html` | `ConversationList.tsx` | + search, + virtualized |
| `_conversation.html` | `ConversationView.tsx` | + WebSocket, + compose |
| `_messages.html` | `MessageList.tsx` | + virtualized scroll |
| `_message.html` (partial) | `MessageBubble.tsx` | + reactions slot |
| `_popout.html` | `PopoutWindow.tsx` | Separate route |
| `_settings.html` | `SettingsPanel.tsx` | + plugin settings |
| `index.html` | `App.tsx` (shell) | SPA shell |
| `login.html` | `LoginPage.tsx` | |

The backend API endpoints stay the same — React calls them via
`fetch`/TanStack Query instead of htmx issuing HTML-fragment requests.
Some endpoints will need JSON variants (currently return HTML), but
most of the settings endpoints already return JSON.

### Tests

The existing 781 pytest tests cover **backend logic** (auth, API,
integrations, themes, etc.) — those don't change at all. What changes:

- **Removed:** Tests that assert HTML fragment content (htmx responses)
- **Added:** Vitest + React Testing Library tests for components
- **Added:** Playwright E2E tests for full flows
- **Added:** axe-core accessibility tests (replaces `test_accessibility.py`)
- **Kept:** All backend unit/integration tests

The accessibility tests from wave 6 get rewritten as axe-core scans +
specific ARIA assertions in React Testing Library. Same coverage,
better tooling.

---

## 6. Revised Phase Plan (Full Cadillac)

| Phase | What | Est. Hours | Autonomous? |
|-------|------|-----------|-------------|
| 1 | Scaffold: Vite + React + TS + Tailwind + FastAPI serving | 4 | Yes |
| 2 | Core UI: conversations, messages, compose, WebSocket | 8 | Yes |
| 3 | Feature parity: all 23 themes, media, settings, export | 6 | Yes |
| 4 | Plugin SDK: `chatwire-sdk`, frontend slots, scaffolding | 4 | Yes |
| 5 | Polish: PWA, a11y (axe-core), Playwright E2E, perf | 4 | Yes |
| 6 | Mobile: React Native + Expo (iOS + Android) | 28 | Yes |
| 7 | CI/CD: PyPI + DMG + Homebrew + GitHub Releases | 4 | Yes |
| 8 | Extras: Tauri desktop, Docker image, npm wrapper | 6 | Mostly |
| | **Total** | **~64 hours** | |

At ~8 hours/day of Sonnet loop time, that's roughly **8 days**.

Phases 1-5 are the web migration (must be sequential).
Phase 6 (mobile) can overlap with Phase 7 (CI/CD).
Phase 8 is independent nice-to-haves.

---

## 7. Anything Else? Yes — Three Things

### 7a. Monorepo structure

With React web + React Native mobile + Python backend + plugin SDK,
you want a monorepo with workspaces:

```
chatwire/
  packages/
    backend/          ← Python (FastAPI, bridge, integrations)
    web/              ← React + Vite (web frontend)
    mobile/           ← React Native + Expo (iOS + Android)
    sdk/              ← chatwire-sdk (plugin development kit)
    shared/           ← TypeScript types, API client, shared utils
  tools/
    briefcase/        ← .app/.dmg build config
    ci/               ← GitHub Actions workflows
  docs/
```

`packages/shared/` is the key — the API client, WebSocket message
types, and theme token types are shared between web and mobile. Write
once, import in both.

### 7b. API versioning

Once you have a mobile app, the API is a public contract. Version it
from day one:

```
/api/v1/conversations
/api/v1/messages/{handle}
/api/v1/settings
/api/v1/plugins
/ws/v1                  ← WebSocket endpoint
```

This lets you ship breaking API changes in v2 without breaking old
mobile app versions that haven't updated yet.

### 7c. Analytics / crash reporting (opt-in)

For an open-source project with mobile apps, consider opt-in anonymous
crash reporting via Sentry (free tier for open source). Helps you fix
bugs that users would otherwise silently suffer through. Must be:
- Off by default
- Single toggle in settings
- No message content, ever
- Only crash stacks + device info

This is a "Cadillac" touch — most open-source chat bridges don't have
any telemetry, which means bugs rot forever.
