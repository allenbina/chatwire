# Chatwire: Greenfield Architecture Analysis

> If you were building this from scratch today — what would you choose?
> Plus: should we move to React + Vite?

---

## Current Stack (for reference)

| Layer | Today | Notes |
|-------|-------|-------|
| Backend | Python 3.10+ / FastAPI (async) | ~19K lines, 69 .py files |
| Frontend | Jinja2 SSR + htmx + Tailwind CDN | Zero build step, 2 JS files total |
| Real-time | SSE (Server-Sent Events) via FastAPI | Tails a JSONL mirror file |
| Database | Raw SQLite3 (macOS Messages `chat.db`) | Read-only snapshot; writes via AppleScript |
| Plugins | `importlib.metadata` entry points | Protocol-based, JSON Schema settings |
| Packaging | PyPI via `pipx` | Console scripts, launchd plist templates |
| Themes | 23 plain CSS files | No preprocessor, no build |
| Tests | pytest, 781 passing | Mostly unit, some integration |
| PWA | Service worker + manifest | Minimal, hand-rolled |

---

## Part 1: React + Vite — Pros and Cons

### What you'd gain

1. **Component model.** React's component tree maps naturally to chat UI
   elements (message bubble, conversation list, compose box, media
   lightbox, settings panel). Today these are Jinja2 partials swapped
   via htmx — functional, but every new interactive behavior requires
   careful htmx wiring and server round-trips. React components
   encapsulate state + markup + behavior in one place.

2. **Rich interactivity without server round-trips.** Typing indicators,
   optimistic sends, drag-and-drop media uploads, inline link previews,
   emoji pickers, message reactions, read receipts — all of these are
   painful with htmx because they need client-side state. React makes
   this straightforward.

3. **Contributor familiarity.** React is the most widely known frontend
   framework. If you want outside contributors, React + Vite is the
   stack they expect. htmx is respected but niche — most frontend
   developers haven't used it.

4. **Ecosystem.** Off-the-shelf components for virtualized message lists
   (critical for perf with 10K+ messages), accessible modals/dialogs,
   date pickers, markdown rendering, syntax highlighting, image
   galleries with gestures, etc.

5. **TypeScript.** Vite has first-class TS support. You get type safety
   across your entire frontend, catch bugs at build time, and get
   better IDE support for contributors.

6. **Hot module replacement (HMR).** Vite's HMR is instant. During
   development you see changes in <100ms without losing component state.
   Today you do a full page reload.

7. **Code splitting.** Vite automatically splits your bundle so the
   initial load only includes what's needed. Settings panel, plugin UIs,
   admin views — loaded on demand.

8. **Testing.** Vitest + React Testing Library gives you component-level
   tests that are far more meaningful than testing raw HTML strings in
   pytest. You can test "when user clicks send, the message appears
   optimistically" rather than "this HTML fragment contains this class."

### What you'd lose

1. **Simplicity.** Today: zero build step, zero node_modules, zero
   bundler config. The entire frontend is ~2 JS files and some HTML
   templates. Moving to React + Vite means: node 18+, npm/pnpm, a
   build pipeline, source maps, a dev server proxy, and the full modern
   JS toolchain. This is the single biggest cost.

2. **The "it just works" install.** `pipx install chatwire` gives users
   a working app with no other dependencies. With React, you either:
   - Pre-build and ship the bundle inside the Python package (adds a
     build step to your CI but preserves the user experience), or
   - Require users to have Node.js (bad — kills the simplicity story).
   
   The first option is standard (FastAPI + SPA is well-trodden) but
   adds CI complexity.

3. **SEO / SSR irrelevance.** Chat apps don't need SEO. SSR is
   pointless here. But you lose progressive enhancement — if JS fails
   to load, the app is a blank page instead of a functional (if static)
   page. For a self-hosted app on localhost, this doesn't matter much.

4. **Bundle size.** React + ReactDOM is ~40KB gzipped. Today your total
   JS is probably <5KB. For a localhost app this is irrelevant, but
   it's a philosophical departure from the current zero-bloat approach.

5. **Two languages, two mental models.** Today everything is Python.
   Contributors need to know Python only. With React, they need Python
   + TypeScript + React patterns + Vite config. For a solo maintainer
   this is fine (you already know both worlds), but it raises the bar
   for casual contributors.

6. **Migration cost.** This is a full rewrite of the frontend. Every
   template, every htmx swap, every SSE handler, every theme CSS file
   needs to be rebuilt. Estimate: **2-3 days of continuous Sonnet work**
   for the core UI, plus another day for edge cases, plugin UIs, and
   testing. During migration, you're maintaining two frontends or
   doing a hard cutover.

### Verdict on React + Vite

**Do it if** you're committed to building a polished, interactive,
contributor-friendly app that competes with commercial alternatives.
The interactivity ceiling of htmx is real — you'll hit it on every
feature that needs client-side state (typing indicators, reactions,
drag-drop, offline support).

**Don't do it if** you value the zero-dependency, zero-build-step,
pure-Python simplicity that makes chatwire unique in this space. The
htmx approach is a legitimate architectural choice, not a compromise.

**My recommendation:** Do it. The features you'll want for a "Cadillac"
release (reactions, typing indicators, media galleries with gestures,
plugin settings UIs, offline PWA) all push you toward a real frontend
framework. Pre-build the bundle into the Python package so the install
experience stays identical.

---

## Part 2: Greenfield Architecture — If Starting From Scratch

### Backend: Keep Python + FastAPI

**Don't change this.** Here's why:

- The macOS integration layer (chat.db reads, AppleScript sends,
  launchd plists, TCC permissions) is inherently macOS-specific and
  Python handles it well.
- FastAPI is modern, async, well-documented, and has excellent
  WebSocket support.
- Your plugin system's `importlib.metadata` entry points are clean.
- `pipx install` distribution is a killer feature for end users.
- 19K lines of working, tested Python is not worth rewriting.

The backend is already well-architected. The greenfield changes are
all in the frontend, real-time layer, and plugin DX.

### Frontend: React + Vite + TypeScript

For the reasons above. Specific choices:

| Choice | Why |
|--------|-----|
| **React 19** | Stable, massive ecosystem, best hiring/contributor pool |
| **Vite 6** | Fast builds, great DX, native TS support |
| **TypeScript** (strict) | Catch bugs early, self-documenting APIs |
| **Tailwind CSS 4** | You already use Tailwind. Keep it. Move from CDN to build-time for tree-shaking and custom theme tokens |
| **Zustand** (not Redux) | Lightweight state management. Chat state (messages, conversations, typing, presence) in a single store. Redux is overkill here |
| **TanStack Query** | Server state management (conversation list, message history, search). Handles caching, pagination, background refetch |
| **Radix UI** | Unstyled, accessible primitives (dialogs, dropdowns, tooltips). You style them with Tailwind. Saves you from building accessible components from scratch |

### Real-Time: WebSockets (replace SSE)

SSE is one-directional (server → client). For a chat app you want
bidirectional:

- **Client → server:** typing indicators, read receipts, presence
- **Server → client:** new messages, status updates, delivery confirmations

FastAPI has native WebSocket support. Use a single persistent WebSocket
per client with JSON message framing:

```json
{"type": "message.new", "data": {...}}
{"type": "typing.start", "conversation": "chat123"}
{"type": "presence.update", "status": "online"}
```

Fall back to SSE for environments where WebSockets are blocked (rare
for localhost, but good practice).

### Database: Keep SQLite — but add an app database

Today you read macOS's `chat.db` directly. Keep that — it's the source
of truth for iMessage data. But add a **separate app database** for
chatwire-specific state:

- User preferences / settings
- Plugin configuration
- Read receipts / last-read markers
- Starred / pinned messages
- Search index (FTS5)
- Theme preferences per conversation
- Notification preferences

Use **SQLite + SQLAlchemy** (or raw `aiosqlite` if you prefer). No
Postgres — it would kill the zero-config install story. Ship migrations
with Alembic.

### Plugin System: Overhaul for DX

The current `importlib.metadata` entry point system works but has poor
developer experience. For a "Cadillac" plugin system:

1. **Plugin SDK package** (`chatwire-sdk`): Published separately on
   PyPI. Contains base classes, type stubs, and a `chatwire plugin
   init` scaffolding command. Developers `pip install chatwire-sdk`
   and get autocomplete + type checking without installing all of
   chatwire.

2. **Frontend plugin API**: This is where React pays off. Plugins can
   ship React components that render in designated slots:
   - Message toolbar (reactions, actions)
   - Sidebar panels
   - Settings pages
   - Compose box extensions (slash commands, media pickers)
   
   Use a simple registration API:
   ```typescript
   chatwire.registerSlot('message.toolbar', MyReactionPicker);
   chatwire.registerSlot('sidebar.panel', MySearchPanel);
   ```

3. **Plugin manifest** (`chatwire-plugin.toml`): Declarative metadata
   — name, version, permissions required, settings schema, slot
   registrations. Machine-readable, validatable.

4. **Hot reload in dev**: `chatwire plugin dev` watches the plugin
   directory and live-reloads both Python and frontend changes.

5. **Plugin marketplace / registry**: A simple JSON index hosted on
   GitHub Pages. `chatwire plugin search`, `chatwire plugin install`.
   Not needed for launch, but architect for it now.

### Packaging: Keep pipx, add Homebrew formula

- **Primary:** `pipx install chatwire` (unchanged)
- **Secondary:** `brew install chatwire` via your homebrew-tap
- **Build:** Pre-compile the React frontend in CI (GitHub Actions),
  include the dist/ bundle in the sdist/wheel. Users never need Node.
- **One-liner install:** Keep the `curl | bash` script. It should
  detect whether pipx or brew is available and use the right one.

### Themes: Design tokens, not CSS files

Today you have 23 separate CSS files for themes. In a React + Tailwind
build:

1. Define themes as **JSON design tokens**:
   ```json
   {
     "name": "Dracula",
     "colors": {
       "bg-primary": "#282a36",
       "bg-secondary": "#44475a",
       "text-primary": "#f8f8f2",
       "accent": "#bd93f9"
     }
   }
   ```

2. Inject tokens as CSS custom properties at runtime.
3. Tailwind classes reference the properties (`bg-[var(--bg-primary)]`
   or custom theme utilities).
4. Theme files become ~20 lines of JSON instead of full CSS files.
5. **Plugin themes**: Third-party themes are just JSON files. No CSS
   knowledge needed.

### Testing Strategy

| Layer | Tool | What to test |
|-------|------|-------------|
| Python unit | pytest | Bridge logic, DB queries, plugin lifecycle |
| Python integration | pytest + httpx | API endpoints, WebSocket handlers, auth |
| React component | Vitest + Testing Library | Component rendering, user interactions |
| React integration | Vitest | Store logic, WebSocket message handling |
| E2E | Playwright | Full flows: send message, switch convo, install plugin |
| Accessibility | axe-core + Playwright | Automated a11y scanning on every page |
| Visual regression | Playwright screenshots | Catch unintended theme/layout changes |

### PWA / Mobile

For a truly polished app:

1. **Service worker** (Workbox): Offline support, background sync for
   messages sent while offline, push notifications.
2. **App manifest**: Proper splash screens, icons, standalone display.
3. **Responsive design**: Mobile-first layout. Conversation list and
   chat as separate "pages" on mobile (slide transition), side-by-side
   on desktop.
4. **Touch gestures**: Swipe to reply, swipe to archive, long-press
   for reactions. Libraries like `use-gesture` make this easy in React.

### Security Hardening

For a public-facing open source project:

1. **CSP headers**: Strict Content-Security-Policy. No inline scripts.
2. **Auth upgrade**: Consider passkey/WebAuthn support alongside the
   current password auth. The `py_webauthn` library makes this
   straightforward.
3. **Rate limiting**: Per-IP rate limits on auth endpoints.
4. **Signed plugins**: You already have Ed25519 signature verification
   — surface it in the UI with a "verified" badge.
5. **Audit log**: Log all auth events, plugin installs, config changes.

---

## Part 3: Migration Strategy

If you decide to go ahead, here's the phased approach:

### Phase 1: Scaffold (Day 1, ~4 hours Sonnet)
- Initialize Vite + React + TypeScript in `web/frontend/`
- Configure Tailwind 4 with design tokens for one theme (Dracula)
- Set up FastAPI to serve the built SPA + API routes
- CI: GitHub Actions builds frontend, bundles into wheel
- Smoke test: blank React app served by FastAPI, `pipx install` works

### Phase 2: Core UI (Day 1-2, ~8 hours Sonnet)
- Conversation list component (with search)
- Message list component (with virtualized scrolling)
- Compose box (text + media upload)
- WebSocket connection manager
- Port SSE → WebSocket on backend
- Basic routing (conversation switching)

### Phase 3: Feature Parity (Day 2, ~6 hours Sonnet)
- All 23 themes as JSON tokens
- Media viewer (images, video, audio)
- Contact info panel
- Settings / preference pages
- Popout window
- Plugin settings UI framework

### Phase 4: Plugin SDK (Day 2-3, ~4 hours Sonnet)
- `chatwire-sdk` package scaffold
- Frontend slot registration API
- `chatwire plugin init` scaffolding command
- Port one built-in integration (Telegram) to new SDK as proof

### Phase 5: Polish (Day 3, ~4 hours Sonnet)
- PWA: offline support, push notifications, install prompt
- Accessibility audit (axe-core)
- Playwright E2E tests
- README / docs refresh
- Performance profiling (Lighthouse score)

**Total estimate: ~26 hours of Sonnet work = 2-3 calendar days of
autonomous loop time.**

---

## Part 4: What the Competition Looks Like

| App | Stack | Status | Weakness |
|-----|-------|--------|----------|
| **BlueBubbles** | .NET + Angular | Active | Heavy, Windows server required, complex setup |
| **AirMessage** | Java + vanilla JS | Stale | No updates since 2023, aging UI, no plugin system |
| **Beeper** | React + Go | Active (commercial) | Closed source, subscription model, privacy concerns |
| **Pypush** | Python | Experimental | Registration-only, no web UI, Apple TOS gray area |

**Your opportunity:** The only open-source, self-hosted iMessage bridge
with a modern React UI, plugin ecosystem, and single-command install.
BlueBubbles is the closest competitor and it requires a Windows/Mac
server running .NET with a complex setup process. If chatwire has a
polished React UI + plugin marketplace + `pipx install` simplicity,
it's categorically better.

---

## Part 5: Things That Would Make It "Cadillac"

Beyond the architecture, these features would put chatwire in a
different class:

1. **End-to-end encrypted web sessions.** The web UI talks to your Mac
   over HTTPS, but adding E2E encryption (Signal protocol or Noise
   framework) for the WebSocket channel means even a compromised
   network can't read messages in transit. Marketing gold for
   privacy-conscious users.

2. **Multi-bridge support.** Today it's iMessage. The plugin
   architecture already supports Telegram. Add first-class bridges for
   Signal (via signal-cli), WhatsApp (via whatsmeow), and Matrix. One
   web UI for all your messaging. This is what Beeper charges $10/mo
   for.

3. **AI integration.** You already have an MCP integration. Go further:
   - Smart reply suggestions
   - Message summarization for long threads
   - Scheduled messages ("remind me to text X tomorrow")
   - Translation (inline, per-message)
   
   Ship it as a built-in plugin with a toggle, not a core feature.

4. **Desktop app via Tauri.** A native macOS/Windows/Linux desktop app
   that wraps the React UI. Tauri is 10x lighter than Electron. System
   tray icon, native notifications, global keyboard shortcuts. The
   React UI you'd build for the browser works as-is inside Tauri.

5. **Conversation sync / backup.** Export conversations as searchable
   archives. Import from other platforms. iMessage → chatwire →
   searchable offline archive is a use case people pay for.

6. **Read-receipt privacy controls.** Choose per-conversation whether
   to send read receipts. Apple doesn't let you do this natively.

7. **Message scheduling.** "Send at 9am tomorrow." Queue in the app
   database, AppleScript fires at the scheduled time.

8. **Unified search.** Full-text search across all bridges (iMessage +
   Telegram + Signal) with filters by date, sender, media type.
   SQLite FTS5 makes this fast and zero-dependency.

---

## TL;DR Recommendation

**Do the React + Vite migration.** The htmx approach got you to 1.6.0
and proved the concept. For a polished, contributor-friendly,
press-release-worthy app, you need a real frontend framework. The
install experience stays identical (`pipx install chatwire`) because
you pre-build the bundle in CI.

**Don't rewrite the backend.** FastAPI + Python is the right choice for
a macOS-native bridge. The plugin entry-point system is solid. Invest
backend time in WebSocket support and the plugin SDK, not a rewrite.

**The "Cadillac" differentiator is the combination of:** single-command
install + modern React UI + plugin ecosystem + multi-bridge support.
No competitor offers all four.
