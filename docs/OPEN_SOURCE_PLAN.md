# Open-source plan

Make `imessage-tg-bridge` installable by anyone with a Mac, configured entirely
from a web UI, extensible to integrations beyond Telegram.

This is a planning document. None of it is implemented yet. Order is
deliberately top-down: scope and contracts first, then plumbing, then UX
polish.

---

## Constraints that shape every decision

The bridge has to live on a Mac. iMessage's `chat.db` and the Messages
AppleScript dictionary are not available off-Mac, and Apple's TCC framework
gates both behind per-binary Full Disk Access and Automation grants that have
to be approved by the user clicking in System Settings — not from CLI, not from
an installer, not from any signed bundle. That is the load-bearing constraint:
**we cannot hide the permissions step. We can only make it short and obvious.**

Everything else is downstream of that.

---

## macOS version support

| macOS | Supported? | Notes |
|---|---|---|
| 11 Big Sur | best effort | chat.db schema works; AppleScript Messages works. Untested. |
| 12 Monterey | **yes — reference install runs here** | Intel + Apple Silicon. |
| 13 Ventura | yes | Same APIs. |
| 14 Sonoma | yes | TCC dialogs moved into System Settings — installer copy needs both UIs. |
| 15 Sequoia | yes | Some users report extra Automation re-prompts after updates. |
| 16+ | unknown until tested | Monitor `chat.db` schema each major release. |

The 4-min-TCC-cliff workaround in `chat_db.py` (read-from-backup-snapshot) was
verified on 12.7.6; it should generalize but each new major macOS warrants a
re-verification pass.

Outbound threaded replies, reactions, and read receipts remain unsupported —
they need newer Messages.app private APIs or Sequoia+ scripting bridges that
aren't worth the maintenance burden yet.

---

## Distribution: how people install it

Three paths, in increasing polish. Ship A first; add B when there's a small
user base; add C only if it earns the operating cost.

### A. Homebrew tap (primary path, ship first)

```
brew tap <org>/chat-bridge
brew install chat-bridge
chat-bridge setup     # opens http://localhost:8723/setup in default browser
```

Why this first:
- **Free to ship.** No Apple Developer Program enrollment required —
  Homebrew installs scripts and a Python venv, none of which goes through
  Gatekeeper. The $99/yr fee only applies to the signed DMG path (Option B).
- Familiar to the Mac developer audience that will be the early users.
- Upgrades are `brew upgrade chat-bridge` — no custom updater code.
- The formula installs a Python venv into `$HOMEBREW_PREFIX/opt/chat-bridge/`,
  drops a wrapper at `$HOMEBREW_PREFIX/bin/chat-bridge`, and *does not*
  auto-load launchd. That last bit matters: TCC needs a user-initiated launch
  to pop the Automation prompt where the user can see it.
- The `chat-bridge` CLI subcommands (`setup`, `install-agents`,
  `uninstall-agents`, `logs`, `doctor`) replace the current ad-hoc shell
  scripts.

Cost: a tap repo + a CI job to release a new formula on each git tag.

### B. Signed `.app` bundle in a DMG

```
download ChatBridge.dmg
drag to Applications
double-click → menu bar icon appears → web UI opens
```

This is the "non-technical user" path. It bundles:
- Python embedded (PyOxidizer / py2app — one freeze, less venv hassle)
- A Swift-or-Python menu bar shell (see "Menu bar app" below)
- [Sparkle](https://sparkle-project.org/) for in-place auto-updates

Costs:
- Apple Developer Program ($99/yr) for codesigning + notarization. Without
  notarization users have to right-click → Open and the Gatekeeper warning
  scares people off.
- Build pipeline maintenance — DMG layouts, dmgbuild config, notarization
  staples.
- Release engineering: every push needs to produce a signed DMG and a
  Sparkle appcast.xml hosted somewhere.

Defer until A has users who are asking for it.

### C. Curl-pipe-bash install script

```
curl -fsSL https://<host>/install.sh | sh
```

Cheap to ship; trades trust for convenience. The script:
- Detects `arch` and macOS major version, refuses on unsupported.
- Downloads a pinned tarball from the GitHub release.
- Drops files into `~/.local/share/chat-bridge/` and a wrapper into
  `~/.local/bin/`.
- Runs `chat-bridge setup` for the first-run wizard.

Useful for early adopters who don't have Homebrew. Document it but don't lead
with it — script-piping has a bad reputation for good reasons, and users that
trust it will trust `brew tap` too.

### Recommendation

Ship **A** at v0.1. Add **C** the same week (small effort, broadens reach). Add
**B** only when we've heard from enough users that DMG was a hard requirement.

---

## How updates work

| Mode | Update mechanism | User cost |
|---|---|---|
| Homebrew | `brew upgrade chat-bridge` (manual or via `brew autoupdate`) | one command |
| DMG / Sparkle | menu bar icon: "Update available — install" | one click |
| Curl script | re-run `curl ... | sh`, or `chat-bridge self-update` (downloads latest tarball) | one command |

Two pieces of UX glue the modes together:

- **Version check API.** A static `latest.json` file in the GitHub release
  tracks `{ "version": "...", "min_supported": "...", "release_notes_url": "..." }`.
  The running web UI fetches it on a 24h interval and surfaces an "Update
  available" banner in the top bar. The banner explains *how* to update for
  that user's install method.

- **Migration runner on startup.** Each release that changes config schema
  ships a tiny migrator (`migrations/0001_*.py`, etc.) that reads the on-disk
  config version and bumps it forward. Same idea as Django/Alembic. Lets us
  rename keys without breaking existing installs.

Auto-updating launchd-managed daemons is a known footgun — TCC grants are tied
to the binary path *and* its codesign identity, so any update that swaps either
re-prompts the user. Both Homebrew and Sparkle updates need to keep the
launched binary stable (e.g., the launchd plist points at a stable
`bin/chat-bridge` wrapper that itself execs the venv'd Python — the wrapper
path never changes; only the contents behind it do).

---

## What "parameterize the hardcoded stuff" actually means

A search through the repo turns up four buckets of hardcoded values. The plan
is to move each to a single source of truth.

### Bucket 1 — paths and identity (currently hardcoded user-specific paths)

Found in: both `.plist` files, `scripts/check-permissions.sh`, `scripts/deploy-web.sh`, README.

Plan: the installer renders the plists from a template, substituting:
- `${HOME}` for the home directory
- `${VENV_PYTHON}` for the venv'd Python path
- `${INSTALL_DIR}` for the repo / install directory
- `${LABEL_PREFIX}` for the launchd label (e.g., `dev.chatbridge` instead
  of `&lt;legacy-prefix&gt;`)

Drop the plists from git in their current form; commit `*.plist.template`
files. The CLI command `chat-bridge install-agents` renders + writes them
to `~/Library/LaunchAgents/` and loads them.

### Bucket 2 — runtime config (currently `~/.imessage-tg/.env`)

Already mostly env-driven (`TELEGRAM_BOT_TOKEN`, `SELF_HANDLES`,
`WHITELIST_HANDLES`, `WEB_PORT`, `VAPID_*`, `DEBUG_MIRROR_FILE`). Good. Two
changes:

1. **Move from `.env` to `~/.chat-bridge/config.json`.** Single source of
   truth, schema-versioned, easier to validate, easier to write from the web
   UI. Keep `.env` support as a fallback for one release for migration.

2. **Group keys by integration.** The current flat namespace gets unwieldy as
   we add Slack/Discord/etc. New shape:

   ```json
   {
     "version": 2,
     "self_handles": ["+15551234567", "you@icloud.com"],
     "default_outgoing_identity": "+15551234567",
     "web": {
       "enabled": true,
       "bind": "127.0.0.1",
       "port": 8723,
       "auth_mode": "none",
       "vapid": { "public": "...", "private": "...", "contact": "mailto:..." }
     },
     "integrations": {
       "telegram": {
         "enabled": true,
         "bot_token": "...",
         "allowed_user_ids": [123456789]
       }
     },
     "debug": {
       "mirror_file": "~/.chat-bridge/mirror.jsonl"
     }
   }
   ```

3. **Strict permissions on write.** The web UI must `chmod 600` the file every
   time it writes (Telegram tokens live there). Refuse to start if the
   permissions are weaker than that.

### Bucket 3 — VAPID + contact email (currently `mailto:admin@example.com` default)

Generated per install. The setup wizard generates a fresh VAPID keypair on
first run and stores it; nobody should be sharing keys with anyone.

### Bucket 4 — Telegram bot username (referenced by inline mode docs)

Pull from `bot.get_me()` at startup, cache in memory. README shouldn't name a
specific bot.

---

## First-run setup: web wizard, not env files

The user is right that this is the model competitors converge on. Mac users
double-click to install; the web UI does the rest.

```
$ chat-bridge setup     # (run automatically by `brew install` post-install hook)
opening http://localhost:8723/setup ...
```

### Wizard pages

1. **Permissions check.** Live status of FDA + Automation → Messages, with the
   exact "Open System Settings → Privacy & Security → Full Disk Access" deep
   link (via `x-apple.systempreferences:` URL scheme). Refuses to advance until
   both are green.

2. **Identity.** Reads the configured iMessage handles from `chat.db`, lets the
   user pick which ones are "self" (Phase A) and which is the default outgoing
   identity. Pre-fills from chat.db so most users just click "Next".

3. **Integrations.** Each enabled integration's setup card. For Telegram:
   - Walks through @BotFather (`/newbot` → paste token).
   - Walks through @userinfobot (paste user ID).
   - Test button: pings the bot, confirms it reaches the user's Telegram
     account.

4. **Whitelist.** Pull the contacts list from Contacts.app, present a search
   box, let the user pick whose messages should relay. Same UI as the existing
   web settings panel — just exposed earlier in the flow.

5. **Exposure.** How should the web UI be reachable?
   - **Local only** (default): bind 127.0.0.1, no auth needed, no exposure.
   - **Tailscale**: bind to the tailscale IP. UI shows the magic URL.
   - **Cloudflare Tunnel**: generate a tunnel via `cloudflared tunnel login`,
     paste a chosen subdomain, link a Cloudflare Access policy. Wizard
     drops the cloudflared LaunchAgent and walks the user through Access.
   - **Custom reverse proxy**: bind 0.0.0.0, document headers; user is on
     their own.

6. **Appearance.** Pick a color theme. Ship a curated list of permissively-
   licensed (MIT) ports: Dracula, Nord, Solarized Light/Dark, Tokyo Night,
   One Dark / One Light, Gruvbox, GitHub Light/Dark, Night Owl, plus pastel
   options Catppuccin (Latte/Frappé/Macchiato/Mocha) and Rosé Pine. Stored
   as `web.theme` in config; live-applied via CSS variables so switching is
   instant. Attribution + upstream URLs in `web/static/themes/THEMES.md`.
   Default to "system" (auto light/dark via `prefers-color-scheme`).

7. **Done.** Summary, links to logs, link to docs.

### Subsequent settings

After first run, `/setup` is no longer the landing page; it's accessible from
a gear icon in the web UI's top bar. Same wizard pages, but each is now a
standalone settings panel with its own save button.

---

## Integrations: turning Telegram from "the bridge" into "one of many"

Today `bridge.py` is a Telegram-shaped monolith. The data plane (chat.db
reader, AppleScript sender, contacts, whitelist, echo log) is already
factored out — the integration boundary is just the Telegram-specific glue.

### The Integration interface

```python
# integrations/base.py
class Integration(Protocol):
    NAME: str                 # "telegram", "slack", "ntfy", "webhook"
    SETTINGS_SCHEMA: dict     # JSON schema rendered in the web UI

    async def start(self, ctx: BridgeContext) -> None: ...
    async def stop(self) -> None: ...

    # Inbound: bridge -> integration
    async def on_inbound(self, msg: InboundMessage) -> None: ...

    # Outbound is initiated by the integration via ctx.send_text / ctx.send_file.
```

`BridgeContext` exposes the existing send/whitelist/echo APIs, so an
integration is purely additive — it doesn't need to know about the others.

### What ships in v0.1

- **Telegram** (already built).
- **Web UI** (already built — modeled the same way: it's an integration that
  also serves a setup wizard).
- **Webhook out**: POST every relayed message to a user-configured URL.
  Trivial to implement, opens the door to Zapier/n8n/etc. without us building
  per-service code.

### What lands later

- **Slack** (DM bridge: relay to a personal Slackbot DM).
- **Discord** (similar; DM-only to avoid a flood scenario).
- **Matrix** (high request from privacy-minded folks).
- **ntfy / Pushover** (native phone push, side-steps Telegram for users that
  don't want it).
- **Generic SMTP** (email-out only) — useful as an audit log mirror.

Each lives in `integrations/<name>/` with a `manifest.json` and a `__init__.py`
exposing an Integration class. The bridge auto-discovers them at startup;
absence of a `<name>` block in config means "not enabled". No wiring changes
in `bridge.py` per integration.

### Third-party integrations

Integrations don't have to live in this repo. The `pyproject.toml` declares
the entry-point group `chat_bridge.integrations`; any pip-installable package
can register against it:

```toml
# in chat-bridge-whatsapp/pyproject.toml
[project.entry-points."chat_bridge.integrations"]
whatsapp = "chat_bridge_whatsapp:WhatsAppIntegration"
```

After `pip install chat-bridge-whatsapp` the bridge picks the integration up
on next startup via `importlib.metadata.entry_points(group=…)` — same
discovery loop as the in-repo walker, just a second source. Built-ins win
on name collisions. This keeps the surface for "I want my one weird thing"
out of the main repo while preserving a single config schema.

---

## Login / auth

The current install gates auth at the network layer (Cloudflare Access bound
to two emails). For an open-source release we need to support installs where
users don't have a Cloudflare Zero Trust org.

`web.auth_mode` ∈ `{ "none", "magic-link", "tailscale", "cloudflare-access" }`:

- **none** (default): paired with `bind: 127.0.0.1`. The web UI is reachable
  only from the Mac itself — same security model as a local-only desktop app.
  We refuse to start with `auth_mode: none` and a non-loopback bind.
- **magic-link**: built-in. User pastes their email at `/login`, we email a
  one-click link via SMTP. Sessions are httpOnly cookies, 30-day. Requires
  outbound SMTP creds in config (Mailgun / SendGrid / Gmail app password).
- **tailscale**: read `Tailscale-User-Login` header from the embedded
  Tailscale Serve / Funnel, allowlist email-to-handle.
- **cloudflare-access**: read `CF-Access-Authenticated-User-Email` header.

The notification top bar (next section) shows the active mode so users notice
if they accidentally exposed an unauthed instance.

---

## Menu bar app (the "notification thing on the top bar")

Two ways to do it. Both are reasonable.

### Option A — `rumps` (Python)

Stays inside the existing toolchain. ~100-200 LOC. Looks native enough.
Loses some polish (animations, SF symbols) but trivial to maintain.

### Option B — Swift (SwiftUI MenuBarExtra)

Native polish, can host a tiny SwiftUI popover for "compose new message",
shows real macOS notification badges. Cost: a Swift codebase to maintain
alongside the Python one, and the build now has two languages.

Recommendation: **start with rumps**, gate option B behind "did anyone ask for
this?". Either way the menu bar app talks to the running bridge over its
local-only HTTP API — it has no special access of its own.

### What the menu bar shows

- **Status icon**: green (running, perms OK), yellow (running, missing
  Automation/FDA), red (not running). Clicking shows what's wrong.
- **Unread count badge** (optional, off by default — competes with the
  Telegram badge most users already have).
- **Recent messages submenu**: last 5 inbound, click to open the web UI on
  that thread.
- **"Open Web UI"** → `http://127.0.0.1:8723`.
- **"Show Logs"** → opens stdout/stderr in Console.app.
- **"Settings"** → opens the web UI's settings page.
- **"Pause relay for ..."** → 30m / 1h / 4h / until tomorrow. (Mirrors `/mute`.)
- **"Quit"** → unloads launchd agents.
- **"About / Update available"** → version info, surfaces the update banner.

---

## Serving / subdomains: copying mainline app patterns

The mainline `homelab-docker` apps share a single Cloudflare Tunnel and
Traefik for HTTP routing — that infra is server-side and won't fit on a Mac
laptop. But the *user-facing* pattern (each app has a stable subdomain,
TLS-terminated, gated by Cloudflare Access) is exactly what we want to
replicate. We just do it without Traefik, because there's only one app to
expose.

The wizard's "Exposure" page maps directly to mainline conventions:

| Mode | Equivalent in mainline | Cost / who is this for |
|---|---|---|
| Local-only loopback | n/a (mainline always exposes) | Default. Power users on tailnet who don't need a URL. |
| Tailscale Serve / Funnel | n/a in mainline (homelab uses Tailscale separately) | Anyone with a tailnet — zero ops. |
| Cloudflare Tunnel + Access | the whole mainline pattern (see homelab-docker README "Networking architecture") | Users who want a stable public URL like `messages.example.com` and have a Cloudflare zone. |
| Custom reverse proxy | Traefik labels (mainline) | Self-hosters who already run nginx/caddy/traefik. |

For Cloudflare Tunnel mode the wizard does the same shape of work the mainline
README describes manually:

1. `cloudflared tunnel login` → browser pops, user auths to their CF account.
2. `cloudflared tunnel create chat-bridge-<hostname>` → creates a tunnel.
3. Wizard prompts: "what hostname?" (default `messages.<your-domain>`).
4. Wizard creates a CNAME (`<hostname> → <tunnel-id>.cfargotunnel.com`,
   proxied) via the Cloudflare API token the user paste-confirms.
5. Wizard writes `~/.chat-bridge/cloudflared/config.yml` with the ingress
   rule pointing at `http://localhost:8723`, drops a launchd plist, loads it.
6. Wizard prompts the user to attach an Access policy in the CF dashboard
   (we can't fully script Access policy creation; we link them straight to
   the right page).

So: same end state as `messages.&lt;your-domain&gt;`, configured per-user, gated by
their own Access policy. No Traefik because there's only the one service to
route to.

The README's distinction between "services that bypass Traefik" vs. "services
behind Traefik" doesn't apply here — the Mac install is a single service, no
fan-out. If we ever ship a multi-Mac / household-server variant we'd
revisit this and add Traefik to the picture.

---

## Sequenced rollout

This is the order I'd actually do the work in. Each phase ends in something
shippable.

### Phase 1 — de-personalize

- Move config to `~/.chat-bridge/config.json` with a one-shot migration
  from `~/.imessage-tg/.env`.
- Plist templates + `chat-bridge install-agents` CLI command.
- Rename plist labels `&lt;legacy-prefix&gt;.*` → `dev.chatbridge.*`.
- Strip personal handles, hostnames, and bot usernames from README.
- Replace the two ad-hoc shell scripts with `chat-bridge {logs, doctor,
  install-agents, uninstall-agents}` subcommands.
- Outcome: someone who clones the repo can run it on their own Mac with no
  search-and-replace.

### Phase 2 — first-run wizard

- Web wizard pages 1–4 (permissions, identity, Telegram, whitelist).
- VAPID keygen on first run.
- Migration runner skeleton.
- Outcome: install + setup is a 5-minute task; no terminal needed after
  `brew install`.

### Phase 3 — distribution

- Homebrew tap repo, formula, GitHub Actions release pipeline.
- Curl install script + GitHub release tarballs.
- Update banner in the web UI.
- Outcome: `brew install <tap>/chat-bridge` works.

### Phase 4 — extensibility

- ✅ Integration interface (`integrations/base.py`) and the webhook-out
  integration as the first "third party"-shaped one.
- ✅ Refactor Telegram into the Integration interface
  (`integrations/telegram/`); `bridge.py` slimmed to a runtime core.
- ✅ Auto-discovery walker + nested `integrations: {<name>: {...}}` config
  shape (config v2; migrations/0002_integration_split.py). JSON Schema
  validation per integration block at startup.
- ✅ `WebIntegration` runs the FastAPI app in-process via `uvicorn.Server`
  (`integrations/web/__init__.py`). Standalone `web/main.py:main()` still
  works for launchd-driven installs; in-process is opt-in.
- ✅ Web UI's `/send` redirected through `ctx.send_text` / `ctx.send_file`
  when in-process; standalone mode keeps the direct `chat_send` +
  `echo_log` path. `SendOutcome` widened with `error` / `original_error`
  so the UI surfaces SMS-fallback diagnostics through the Protocol.
- Outcome: `integrations/<name>/` is the only place new integrations need to
  touch code. ✅

### Phase 5 — polish

- Menu bar app (rumps).
- Exposure wizard (Tailscale + Cloudflare Tunnel paths).
- Magic-link auth.
- macOS version compatibility test pass on 13/14/15.

### Phase 6 — when there's an audience

- Signed `.app` + DMG + Sparkle.
- Slack / Discord / Matrix / Pushover integrations as users request them.
- Apple Developer Program enrollment.

---

## Build host

`the author's Mac` (the live relay) is also available as a build host over SSH. That
matters in two places:

- **Homebrew bottle builds.** Bottles need to be built on macOS; the author's Mac
  is Intel Monterey, which gives us the *oldest* supported bottle. Apple
  Silicon bottles can be cross-built with `--bottle-arch` flags on Intel for
  many Python packages, but anything with native deps (e.g., a future
  binary integration) wants a real arm64 builder. Path of least resistance:
  Intel bottle from the author's Mac now, add an arm64 GitHub Actions runner
  (the `macos-14` runner is arm64) when we need it.
- **DMG signing / notarization.** Once we enroll in Apple Developer Program,
  the codesign + notarytool steps need a Mac. the author's Mac can run them
  unattended via SSH, kicked off by a GitHub Actions workflow that scp's the
  built binary, runs the sign+notarize+staple sequence, and scp's the DMG
  back. This is the standard pattern; it removes the Mac-mini-as-CI cost
  that usually blocks small projects from shipping signed builds.

Practical implication: **Phase 6 (signed DMG) is cheaper than estimated** —
we don't need to buy or rent a Mac CI runner, just the $99/yr developer
account. Defer the cost only until we have users; don't defer because of build
infrastructure.

---

## Where to break up the work (context-management markers)

For multi-session work, these are the natural points where a Claude Code
session can `/compact` (preserve plan, drop noise) or `/clear` (start
fresh — next phase doesn't need the prior context).

| Boundary | Action | Why |
|---|---|---|
| Inside Phase 1, after task 7 (README rewrite) | `/compact` | Same phase, same files. Compact preserves direction. |
| End of Phase 1 (merged to main, Mac install verified) | `/clear` | Phase 2 is a different mental model (web wizard) and shares almost no files with the depersonalize work. |
| Phase 2, wizard pages 1–3 → 4–6 | `/compact` | Same UI codebase, halfway natural rest point. |
| End of Phase 2 (wizard ships) | `/clear` | Phase 3 is build/release tooling, not feature work. |
| End of Phase 3 (Homebrew formula published) | `/clear` | Phase 4 is the integration refactor; different surface area. |
| End of Phase 4 (Telegram extracted, webhook integration lands) | `/clear` | Phase 5 polish items are small and individual. |
| Each Phase 5 item (menu bar, exposure wizard, magic-link auth, version pass) | `/compact` after; `/clear` between | Each is self-contained. |

Rule of thumb: `/compact` when the next work builds directly on the current
work. `/clear` when the next phase doesn't share files, doesn't share mental
model, and the debug-log scrollback would just be dead weight.

## Open questions to come back to

- **Naming.** "chat-bridge" is descriptive but generic. A real product
  name (BeeperLite? OpenBridge? Postlite?) opens the door to a landing page
  and a memorable Homebrew tap. Doesn't block phase 1.
- **License.** MIT vs. Apache-2.0 vs. AGPL — AGPL would discourage a
  commercial competitor from forking and SaaS-ifying, at the cost of scaring
  off contributors. Defaulting to MIT unless there's a reason to pick
  otherwise.
- **Telemetry / opt-in stats.** Useful for knowing what macOS versions are in
  the wild. Hard to do without trust hits. Defer.
- **Group chat naming collisions.** If two whitelisted groups have the same
  display name the reply-routing tag is ambiguous. Existing code falls back
  to a chat-id suffix; we should surface the collision in the web UI.
- **Backup / migration between Macs.** If someone replaces their Mac, what's
  the export/import story? Probably `chat-bridge export` → tarball of
  config + whitelist + push subs, then `chat-bridge import` on the new
  box. Not urgent for v0.1.
