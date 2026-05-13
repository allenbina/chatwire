# chatwire

Access your iMessages from anywhere — your phone, your laptop, your browser,
wherever you are. A lightweight bridge that runs on your Mac and gives you
a web UI, a Telegram relay, push notifications, and a plugin system for
extending it however you want.

This is the product Apple should have come out with years ago. iMessage is
the best messaging platform out there, but Apple locks it to their devices
and offers no remote access, no API, no way to check your messages when
you're away from your Mac. chatwire fixes that.

> **Status:** beta — actively looking for testers. The author runs this daily
> and it's stable, but you'll be among the first to install it on a fresh
> machine. If you hit a wall, [open an issue](https://github.com/allenbina/chatwire/issues).
> See [`docs/OPEN_SOURCE_PLAN.md`](docs/OPEN_SOURCE_PLAN.md) for the roadmap.

## What it does

- **Inbound.** A lightweight Python service watches `~/Library/Messages/chat.db`,
  resolves senders against Contacts.app, and forwards messages (text, photos,
  videos, attachments) to your configured integrations.
- **Outbound.** Reply from anywhere — your phone, a browser tab, a Telegram
  chat. The service drives Messages.app via AppleScript to send back as you.
- **Group chats.** First-class support. Replies route by chat GUID so group
  conversations stay intact across surfaces.
- **Plugins.** Extend chatwire with notification services (ntfy, Pushover),
  messaging stats, favorites, and more. Plugins get auto-generated settings
  sections in the web UI. [Build your own](docs/OPEN_SOURCE_PLAN.md) or
  install community plugins with `pipx inject`.

## Requirements

iMessage is Mac-only, so the bridge needs a Mac with your Apple ID logged
into Messages.app. macOS requires two permission grants — Full Disk Access
(to read `chat.db`) and Automation→Messages (to send). The setup wizard
walks you through both, but you will click through a couple of system
prompts on first run.

Tested on macOS 12 Monterey. macOS 13-15 should work. Run `chatwire doctor`
to verify your system is ready.

## Install

Recommended path: **pipx**, against python.org's Python.

```bash
# Install python.org Python first if you don't have it:
#   https://www.python.org/downloads/macos/
# (Homebrew Python works but TCC treats it as a different identity —
# you'd have to grant Full Disk Access + Automation to that binary
# specifically. python.org is the well-trodden path.)

# Install pipx if you don't have it (once per machine):
python3 -m pip install --user pipx
python3 -m pipx ensurepath

# Install chatwire from PyPI:
pipx install --python /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
    chatwire

# Wire it up:
chatwire install-agents
chatwire setup
```

The setup wizard walks you through the macOS permission grants (Full Disk
Access + Automation→Messages), identity, contact whitelist, and optional
web UI password. It writes `~/.chatwire/config.json`.

### Alternate install methods

**Homebrew tap.** Convenient if you already use brew.

```bash
brew install allenbina/tap/chatwire
chatwire install-agents
chatwire setup
```

Tap source: <https://github.com/allenbina/homebrew-tap>.

**curl-pipe-bash.** No PyPI access, no Homebrew, just a shell.

```bash
curl -fsSL https://raw.githubusercontent.com/allenbina/chatwire/main/scripts/install.sh | bash
```

Pin to a specific version with `CHATWIRE_REF=v1.1.0`. The script refuses
Xcode CLT's Python stub and warns on Homebrew Python (TCC identity
protection). Same post-install steps (`chatwire install-agents` etc.).

**Developer / git-clone path.** For hacking on the bridge itself:

```bash
git clone https://github.com/allenbina/chatwire.git ~/projects/chatwire
cd ~/projects/chatwire
python3 -m venv .venv
.venv/bin/pip install -e .

# Render and load the launchd agents:
.venv/bin/chatwire install-agents

# Sanity check:
.venv/bin/chatwire doctor
```

The setup wizard writes `~/.chatwire/config.json` (chmod 600) for you.
For manual edits or headless installs, see
[`docs/REFERENCE_INSTALL.md`](docs/REFERENCE_INSTALL.md).

## macOS permissions

Both the FDA grant and the Automation→Messages grant need to be given to the
**python.org Python binary** (not Homebrew's), because the python.org
installer ships two Mach-O binaries with different code-signing identities
that TCC tracks separately. See
[`docs/REFERENCE_INSTALL.md`](docs/REFERENCE_INSTALL.md) section 5 for the
full walkthrough — that section was the reason the bridge worked at all on
the first install, and it's the same on every Mac.

`scripts/check-permissions.sh` (or `chatwire doctor`) will tell you
which prompts you still need to click.

## React UI

chatwire ships a full-featured React SPA at `/app/` alongside the legacy
server-rendered UI. The React UI is the default — navigating to `/` redirects
to `/app/` automatically.

### Features

- **Real-time chat** — SSE stream + react-query polling, optimistic sends,
  group chat with sender names.
- **Full settings** — all settings sections ported from the Jinja2 UI: themes,
  notifications, whitelist, plugins, export, and more.
- **PWA** — installable on desktop and mobile. Workbox service worker handles
  offline access (cached conversations and messages), background sync (unsent
  messages are queued and retried on reconnect), and auto-update notifications.
- **Plugin slot system** — third-party plugins can register React components
  into named slots (`sidebar.panel`, `message.toolbar`, `compose.extension`,
  `settings.page`). The built-in StatsWidget uses the `sidebar.panel` slot.
- **Performance** — message list is virtualised with `@tanstack/react-virtual`
  (renders ≤ 30 DOM nodes regardless of conversation length). Settings and
  Popout pages are lazy-loaded (separate chunks, not in the main bundle).

### PWA install

Visit `/app/` in Chrome or Edge and click the install icon in the address bar
(or use the browser's "Add to Home Screen" on mobile). Once installed,
chatwire appears as a standalone window with no browser chrome.

### Legacy UI

The original htmx/Jinja2 UI is still available at `/?legacy=1` for one more
release cycle, then will be removed. If you relied on the legacy UI for any
integrations or automations, migrate to `/app/` before the next major version.

### Plugin slot system

Build a frontend plugin by registering a React component via the `window.chatwire` API:

```html
<!-- load your plugin script after the chatwire app boots -->
<script>
window.addEventListener('chatwire:ready', () => {
  window.chatwire.registerSlot('sidebar.panel', MyWidget, { key: 'my-widget' })
})
</script>
```

See [`docs/PLUGIN_DEVELOPMENT.md`](docs/PLUGIN_DEVELOPMENT.md) for the full
slot reference, `BaseIntegration` hook table, and an end-to-end example.

## Mobile App

chatwire has a native iOS + Android app built with React Native and Expo.
It connects to your existing chatwire server over the local network or
Tailscale — no cloud relay, no account required.

### Download

- **Android APK** — grab the latest `.apk` from
  [GitHub Releases](https://github.com/allenbina/chatwire/releases)
  and side-load it (enable "Install from unknown sources").
- **iOS** — TestFlight link coming soon (requires Apple Developer account).
  Build from source in the meantime (see below).

### Connect the app to your server

1. Open the app. On first launch you'll see the Server Setup screen.
2. Enter your chatwire server URL: `http://192.168.1.x:8723`
   (or your Tailscale hostname). Use `http://` — `https://` requires
   a reverse-proxy with a valid cert.
3. Enter your web UI password if you've set one in Settings.
4. Tap **Connect**. The app runs `/healthz` and saves the URL on success.

The server URL is stored in the app's `AsyncStorage`. To change it:
Settings tab → Disconnect → re-enter on next launch.

### Features

- **Conversation list** — FlatList with pull-to-refresh, unread badge,
  live updates via SSE.
- **Message list** — inverted scroll (newest at bottom), load-older
  pagination, sender names in group chats.
- **Compose** — multiline text input, haptic feedback on send,
  camera/gallery picker (stub — full upload in a future release).
- **Image viewer** — full-screen pinch-to-zoom via `expo-image` +
  react-native-gesture-handler.
- **Video player** — inline thumbnail → tap to play via `expo-video`.
- **Push notifications** — register your Expo push token with the server;
  the server fires a push when a new message arrives (requires a server
  upgrade to 1.7.0+ which is not yet released).
- **Dark / light theme** — Dracula palette by default; theme follows
  the server's active theme setting.

### Build from source

```bash
git clone https://github.com/allenbina/chatwire.git
cd chatwire/packages/mobile

# Install dependencies (Node 22 required)
npm install

# Start Expo dev server
npx expo start

# iOS simulator (macOS only)
npx expo start --ios

# Android emulator / device
npx expo start --android
```

For production builds, see [`docs/MOBILE_DISTRIBUTE.md`](docs/MOBILE_DISTRIBUTE.md).

### Repo layout (mobile)

```
packages/
  shared/          @chatwire/shared — types + ChaiwireClient (used by web + mobile)
  mobile/          React Native + Expo app
    App.tsx        Root: NavigationContainer + AppStateProvider
    app.json       Expo config (name, icons, bundle IDs)
    eas.json       EAS Build profiles (development / preview / production)
    src/
      navigation/  RootNavigator, MainTabNavigator (bottom tabs)
      screens/     ConversationListScreen, MessageListScreen,
                   ServerConfigScreen, SettingsScreen
      components/  ComposeBox, MessageBubble, ImageViewer, VideoPlayer
      hooks/       useServerEvents (SSE), usePushNotifications, useBackgroundFetch
      state/       AppStateContext (ChaiwireClient instance, serverUrl)
      theme/       colors.ts (Dracula tokens)
    src/__tests__/ Jest smoke tests for each screen + hook
```

## Web UI access

By default the web UI has no auth — anyone who can reach the URL can read
and send messages. The intended posture is to gate access at the network
layer (Tailscale, LAN-only, Cloudflare Access, etc.).

For setups where the URL leaks past that boundary, the wizard's **Security**
step (or Settings → Web UI password) sets an optional shared password.
It's a single password (not multi-user) stored as a PBKDF2-SHA256 hash in
`~/.chatwire/config.json`; sessions are signed cookies that expire after
30 days. Forgot it? Stop the web agent, edit `config.json` (already
`chmod 600`), drop the `web.auth` block, restart.

## Privacy

**Zero telemetry. Period.** chatwire collects no analytics, sends no usage
data, phones home to nobody, and includes no third-party SDKs that report
back. You run this on your own hardware and your data stays on your hardware.
Your messages, contacts, and `chat.db` never leave your Mac — outbound
traffic only goes to integrations you explicitly configure (your Telegram
bot, your ntfy server, etc.).

Two narrow third-party requests the web UI makes, neither carrying any of
your data:

- An update-check fetches `api.github.com/repos/<repo>/releases/latest`
  once a day to surface new-version notices. Disable by setting
  `UPDATE_CHECK_REPO=""` in the launchd agent's environment.
- Static assets (htmx, emoji-picker-element) load from `unpkg.com` and
  `cdn.jsdelivr.net`.

## Repo layout

```
bridge.py             message relay loop + integration dispatcher
chat_db.py            reads chat.db, HEIC -> JPEG via sips
chat_send.py          osascript wrappers (send_text, send_file)
config.py             config.json loader
chatwire_cli.py       CLI: setup / install-agents / doctor / logs / migrate
contacts.py           Contacts.app -> handle/name lookup
echo_log.py           cross-process echo dedup
whitelist.py          runtime-mutable contact allowlist
_version.py           semver source of truth
integrations/         built-in plugins (web, webhook, stats, favorites)
packages/sdk/         chatwire-sdk Python package (BaseIntegration, plugin CLI)
packages/shared/      @chatwire/shared TypeScript types + ChaiwireClient (web + mobile)
packages/mobile/      React Native + Expo mobile app (iOS + Android)
web/                  FastAPI server: REST API, SSE stream, SPA host
web/frontend/         React SPA (TypeScript, Vite, TanStack Query, Zustand)
  src/components/     UI components (MessageList, ComposeBox, Layout, …)
  src/pages/          Route-level pages (ChatPage, SettingsPage, PopoutPage)
  src/plugins/        Plugin slot system (registry, SlotRenderer, StatsWidget)
  e2e/                Playwright E2E + axe accessibility tests
migrations/           config-schema migration runner
templates/launchd/    plist templates rendered by install-agents
scripts/              install.sh, chatwire-loop.sh (dev automation)
docs/                 OPEN_SOURCE_PLAN.md, REFERENCE_INSTALL.md, HANDOFF.md,
                      PLUGIN_DEVELOPMENT.md, master-migration-plan.md
docs/wiki/            Developer reference: architecture, disk layout, permissions,
                      plugin development, install/uninstall
```

## Trademarks

iMessage, Messages, macOS, and AppleScript are trademarks of Apple Inc.,
referenced here in their descriptive sense — this project relays to and
from Apple's iMessage service. **chatwire is not affiliated with,
endorsed by, or sponsored by Apple Inc.**

## License

MIT — see [`LICENSE`](LICENSE). Copy it, fork it, put your thang down, flip
it, and reverse it. Just follow the MIT requirements and give credit to the
original project.

## Contributing

Pull requests are welcome. Whether it's a bug fix, a new feature, or a whole
plugin — get involved. Check the [plugin system docs](docs/OPEN_SOURCE_PLAN.md)
if you want to build an integration, or browse the
[open issues](https://github.com/allenbina/chatwire/issues) to find something
to pick up.

The [developer wiki](docs/wiki/) covers architecture, disk layout, macOS
permissions, plugin development, and install/uninstall in detail.
See the [macOS compatibility matrix](docs/wiki/compatibility.md) for a
feature-by-feature breakdown across macOS 12–15 and hardware configurations.

**Looking for beta testers.** If you have a Mac with iMessage and want to
try chatwire, [open an issue](https://github.com/allenbina/chatwire/issues)
with your setup details and we'll get you running.

## Sponsors

If chatwire is useful to you, consider
[sponsoring the project](https://github.com/sponsors/allenbina).
