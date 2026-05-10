# Handoff — Wave 5: Polish & Documentation (3 chunks)

> Mac toolbar icon, onboarding docs, plugin READMEs. Ship as v1.5.0.
> Allen will do a fresh install on a clean Mac and capture screenshots
> for onboarding docs during this wave.

## 1. State

- **PyPI**: chatwire 1.4.0 (wave 4 shipped: custom CSS, smart notifications,
  export, Home Assistant, media improvements, XMPP relay).
- **mbair**: running latest, healthz green.
- **Tests**: all green.
- **Full feature set**: web UI, Telegram, XMPP, ntfy, REST API, MCP,
  stats, favorites, export, content filter, tinfoil hat, HA integration,
  smart notifications, gallery/lightbox, PWA, popout, custom CSS,
  advanced settings, anti-spam guardrails.

## 2. Architecture decisions

All prior decisions carry forward. No new architecture in this wave — it's
polish and documentation.

## 3. Task list

1. [ ] Mac toolbar icon — rumps library, macOS menu bar app
2. [ ] Onboarding docs — full walkthrough with screenshot placeholders
3. [ ] Plugin READMEs — each plugin gets install + config + troubleshooting

## 4. Follow-ups

None planned. This is the final wave of the current roadmap.

## 5. Chunks

### Chunk 1: Mac toolbar icon

**Goal**: macOS menu bar icon for quick access and status.

**Design**:
- Uses `rumps` library (lightweight macOS menu bar apps in Python).
- Menu items:
  - Status line: "chatwire v1.5.0 — running" or "stopped"
  - Separator
  - "Open web UI" → opens browser to localhost:8723
  - "Services" submenu:
    - Bridge: running/stopped + restart button
    - Web: running/stopped + restart button
    - Keepawake: running/stopped + toggle
  - "Plugins" submenu: list installed plugins
  - Separator
  - "Settings" → opens browser to settings page
  - "Quit" → stops menu bar app (not services)
- Icon: small wire/chat icon in menu bar (SF Symbols or bundled PNG).
- Runs as a separate process, optional. Not a launchd agent by default
  but can be added with `chatwire install-agents --toolbar`.
- Checks service status via launchctl list and healthz endpoint.

**Files**: `chatwire_toolbar.py` (new, rumps app), `pyproject.toml`
(add rumps dependency, add `chatwire-toolbar` console script entry point),
optionally a launchd plist template

**Verify**: Run `chatwire-toolbar`. Icon appears in menu bar. Menu items
work. Status reflects actual service state. Tests pass (unit tests for
status checking logic, not the GUI).

---

### Chunk 2: Onboarding docs

**Goal**: Full installation + setup walkthrough with screenshot placeholders.

**Design**:
- `docs/onboarding.md` — step-by-step guide:
  1. Prerequisites (macOS version, Python)
  2. Run `chatwire doctor` — pre-flight checks
  3. Install: `pipx install chatwire`
  4. `chatwire install-agents` — set up launchd services
  5. `chatwire setup` — wizard walkthrough:
     - Permissions step (FDA + Automation grants)
     - Identity step (your phone number / email)
     - Whitelist step (add contacts)
     - Security step (optional password)
  6. First web login
  7. Sending your first message
  8. Installing a plugin: `pipx inject chatwire chatwire-ntfy`
  9. Configuring a plugin in Settings
  10. Mobile setup (PWA add-to-homescreen)
- Each step has a screenshot placeholder: `![Step N: description](img/onboarding-N.png)`
- Allen will take the actual screenshots during a fresh install and
  replace the placeholders.
- `docs/img/` directory for screenshot files.

**Files**: `docs/onboarding.md` (new), `docs/img/.gitkeep` (new)

**Verify**: Markdown renders correctly. All steps are accurate against
current codebase. No broken links. Tests pass.

---

### Chunk 3: Plugin READMEs

**Goal**: Each plugin gets documentation.

**Plugins to document**:

**Built-in plugins** (in main repo under `docs/plugins/`):
- `docs/plugins/stats.md` — what stats are shown, how to generate
- `docs/plugins/favorites.md` — how to add/remove favorites
- `docs/plugins/content-filter.md` — categories, custom words, modes
- `docs/plugins/export.md` — formats, options, how to use
- `docs/plugins/mcp.md` — setup for Claude Code, available tools
- `docs/plugins/tinfoil.md` — how E2E works, key setup, limitations
- `docs/plugins/smart-notifications.md` — hiatus, reminders, contact picker
- `docs/plugins/popout.md` — how to use popout view

**Separate repos** (README.md in each):
- `chatwire-ntfy` — ntfy.sh setup, topic creation, auth
- `chatwire-telegram` — BotFather setup, user ID, group support
- `chatwire-xmpp` — server setup, JID config, MUC mapping
- `chatwire-ha` — HA access token, command mapping examples

Each README follows the same structure:
1. What it does (one paragraph)
2. Install command
3. Configuration walkthrough
4. Plugin-specific setup guide
5. Settings reference (all fields explained)
6. Troubleshooting / FAQ

**Files**: `docs/plugins/*.md` (new), README.md in each plugin repo

**Verify**: All docs render correctly. Install commands are accurate.
Settings field descriptions match actual schemas. Tests pass.

## 6. Next prompt

```
Read docs/HANDOFF.md. You are starting wave 5 (final wave). Pick up
chunk 1: Mac toolbar icon using rumps. Create chatwire_toolbar.py with
a rumps menu bar app showing: status, open web UI, services submenu
(bridge/web/keepawake with status + restart), plugins list, settings
link, quit. Add rumps to pyproject.toml dependencies and a
chatwire-toolbar console script entry point. Run pytest. Commit. Then
update HANDOFF.md: mark chunk 1 done in §3, write §6 with the prompt
for chunk 2 (onboarding docs), and commit.
```

## 7. Verbatim opening prompt for next session

```
Read docs/HANDOFF.md. You are starting wave 5 (final wave). Pick up
chunk 1: Mac toolbar icon using rumps. Create chatwire_toolbar.py with
a rumps menu bar app showing: status, open web UI, services submenu
(bridge/web/keepawake with status + restart), plugins list, settings
link, quit. Add rumps to pyproject.toml dependencies and a
chatwire-toolbar console script entry point. Run pytest. Commit. Then
update HANDOFF.md: mark chunk 1 done in §3, write §6 with the prompt
for chunk 2 (onboarding docs), and commit.
```
