# Handoff — Wave 3: API, Security & Content (12 chunks)

> Anti-spam guardrails, REST API, MCP plugin, bad word filter, tinfoil hat,
> PWA support, web notification improvements, advanced settings, popout
> messages, and quick wins. Ship as v1.3.0.

## 1. State

- **PyPI**: chatwire 1.2.0 (wave 2 shipped: wizard cleanup, doctor, sig
  verification, marketplace, update system, transform pipeline, uninstall).
- **mbair**: running latest, healthz green.
- **Plugin system**: mature — sig verification, marketplace browse page,
  update banners, transform pipeline all in place.
- **Tests**: all green.

## 2. Architecture decisions (locked in from prior waves)

- **Plugin settings**: auto-generated from `SETTINGS_SCHEMA` JSON Schema.
- **Plugin distribution**: 4 tiers (built-in, official, community, custom).
  Signature verification gates community/custom installs.
- **Transform pipeline**: `transform_inbound()` / `transform_outbound()`
  optional methods on Integration Protocol, `TRANSFORM_SCOPE` control.
- **Anti-spam design** (new this wave):
  - Normalized hash for broadcast detection: lowercase, strip
    punctuation/whitespace, strip whitelisted contact names, then hash.
  - Track hash → set of recipients.
  - 3+ recipients on same hash = warning notification (ntfy).
  - 5+ = timeout. Escalating: 5min → 15min → 60min → 6h → disable.
  - Whitelist is immutable from plugin perspective (read-only via
    BridgeContext, only web UI can modify).
  - Global rate limit (20/min) in `chat_send.py`.
  - Send audit log.

## 3. Task list

1. [ ] Message load count setting — configurable HISTORY_LIMIT in Appearance
2. [ ] Licensing/attribution — About section at bottom of settings accordion
3. [ ] Android PWA manifest + badge — manifest.json, app icons, badge API
4. [ ] Anti-spam / send guardrails — normalized hash broadcast detection,
   escalating timeouts, immutable whitelist, global rate limit, audit log
5. [ ] REST API plugin — FastAPI sub-app at /api/v1/, API key auth,
   send/read/list/events endpoints. Depends on #4.
6. [ ] MCP plugin — expose chatwire as MCP tools (send_message,
   read_messages, list_conversations, search_messages)
7. [ ] Bad word filter + category filtering — uses transform pipeline,
   category word lists as JSON, checkbox grid in settings
8. [ ] Web notification improvements — rich/sender-only/private detail
   levels, per-contact follow/mute
9. [ ] Advanced settings — port, bind address, reverse proxy support,
   service control (launchd status + toggle), keepawake indicator
10. [ ] Popout messages — pop-out icon in conversation header, opens
    stripped-down view in new window (/popout?handle=...)
11. [ ] Tinfoil hat (E2E encryption) — AES-256-GCM with shared passphrase,
    messages prefixed with lock marker, PBKDF2 key derivation
12. [ ] Custom CSS textarea — textarea in Appearance settings, injected as
    `<style>` after theme CSS, saved to `web.custom_css` config key

## 4. Follow-ups (wave 4+)

- Custom CSS textarea in Appearance
- Smart notifications (per-contact picker, hiatus mode, reminder timers)
- Export plugin (JSON/TXT/CSV, photos as ZIP)
- Home Assistant plugin (keyword → HA service call)
- Media improvements (gallery grid, lightbox, bundled photos with +N overlay,
  thumbnail size setting, time-window grouping heuristic)
- XMPP relay (slixmpp, same plugin structure as telegram)
- Mac toolbar icon (rumps, negative priority)
- Onboarding docs (needs Allen's screenshots)
- Plugin READMEs

## 5. Chunks

### Chunk 1: Message load count setting

**Goal**: Make HISTORY_LIMIT configurable from Settings → Appearance.

**Steps**:
- Find the current `HISTORY_LIMIT` constant in `web/main.py`.
- Add a dropdown to the Appearance settings card: 25 / 50 / 100 / 200 messages.
- Persist to `web.history_limit` in config.json.
- Read from config instead of constant in conversation load and "load more".
- Default: current hardcoded value.

**Files**: `web/main.py`, `web/templates/_appearance_card.html` (or wherever
Appearance settings live)

**Verify**: Change setting, reload conversation, correct number of messages
load. Tests pass.

---

### Chunk 2: Licensing/attribution

**Goal**: "About" expandable at the bottom of settings accordion.

**Content**:
- chatwire version (from `_version.py`)
- MIT license notice
- Key dependencies with links
- "Made by Allen Bina"
- Link to GitHub repo

**Files**: `web/templates/_settings.html` (add accordion section at bottom)

**Verify**: About section renders. Version matches. Tests pass.

---

### Chunk 3: Android PWA manifest + badge

**Goal**: Improve mobile experience with web app manifest and badge API.

**Steps**:
- Create `web/static/manifest.json`:
  - `name`: "chatwire", `short_name`: "chatwire"
  - `display`: "standalone"
  - `theme_color` / `background_color`: match current theme
  - `start_url`: "/"
  - App icons: generate 192x192 and 512x512 PNGs (simple text-based icon
    or use an SVG converted to PNG)
- Add `<link rel="manifest" href="/static/manifest.json">` to `<head>`
- Add `<meta name="apple-mobile-web-app-capable" content="yes">` for iOS
- Call `navigator.setAppBadge(count)` alongside existing title unread count
  update. Clear with `navigator.clearAppBadge()` on focus.

**Files**: `web/static/manifest.json` (new), app icon PNGs (new),
`web/templates/index.html` (link + badge JS)

**Verify**: Chrome DevTools → Application → Manifest looks correct. Badge
updates on unread. Tests pass.

---

### Chunk 4: Anti-spam / send guardrails

**Goal**: Rate limiting and broadcast detection in the send path.

**Design**:
All enforcement lives in `chat_send.py` — the single gateway for ALL
outbound messages. No plugin can bypass it.

1. **Normalized hash**: Before hashing outbound text, normalize: lowercase,
   strip punctuation, collapse whitespace, strip any whitelisted contact
   names (load from config). Hash the result.

2. **Broadcast tracking**: In-memory dict: `{hash: set(recipients)}`.
   Rolling window (e.g., 1 hour). When a hash reaches 3 unique recipients,
   send a warning via ntfy. At 5, start timeout escalation.

3. **Escalating timeouts**: 5min → 15min → 60min → 6h → disable.
   Persist timeout state to `~/.chatwire/rate_limit_state.json` so restarts
   don't reset it. The "disable" state requires manual re-enable in settings.

4. **Global rate limit**: Token bucket, 20 messages/minute. Returns error
   to caller when exhausted.

5. **Immutable whitelist**: In `BridgeContext`, the whitelist accessor
   returns a frozen copy. No `add`/`remove` methods exposed to plugins.
   Only `web/main.py` settings routes can modify the whitelist.

6. **Send audit log**: Append-only log at `~/.chatwire/send_audit.log`.
   Each line: ISO timestamp, recipient, source (plugin name or "web"),
   message hash (not full text for privacy).

**Files**: `chat_send.py` (rate limiting, broadcast detection, audit log),
`bridge.py` or `whitelist.py` (immutable whitelist in BridgeContext),
config loading for rate limit settings

**Verify**: Send same message to 3+ recipients → warning. 5+ → timeout.
Global rate limit blocks rapid sends. Whitelist is read-only from plugin.
Tests pass.

---

### Chunk 5: REST API plugin

**Goal**: REST API for programmatic access to chatwire.

**Depends on**: Chunk 4 (anti-spam guardrails must be in place).

**Design**:
- FastAPI sub-app mounted at `/api/v1/` on the same port as web server.
- Auth: API key in `X-API-Key` header. Key generated in settings (show
  once, can regenerate). Stored hashed in config.json.
- Endpoints:
  - `POST /api/v1/send` — send message (handle + text). Goes through
    `chat_send.py` so all anti-spam protections apply.
  - `GET /api/v1/messages?handle=...&since=...` — read messages
  - `GET /api/v1/conversations` — list conversations
  - `GET /api/v1/events` — SSE stream (same as `/events` but API-key auth)
- Rate limiting: same global limits as everything else via `chat_send.py`.
- Settings UI: auto-generated from schema. API key display + regenerate
  button needs a small custom template fragment.

**Files**: `web/main.py` (mount sub-app, API key routes), new
`web/api_v1.py` (FastAPI router with endpoints), settings schema

**Verify**: Generate API key in settings. curl endpoints with key. Send
message via API, verify it arrives. Anti-spam protections apply. Tests pass.

---

### Chunk 6: MCP plugin

**Goal**: Expose chatwire as MCP tools for LLM agents.

**Design**:
- Built-in integration in `integrations/mcp/`.
- Serves MCP over stdio (for local agents like Claude Code) or SSE
  (for remote MCP clients).
- Tools:
  - `send_message(handle, text)` — send iMessage (through `chat_send.py`)
  - `read_messages(handle, since, limit)` — pull recent messages
  - `list_conversations(limit)` — active chats with last message preview
  - `search_messages(query, handle?)` — full-text search across chat.db
- Auth: same API key as REST API (for SSE transport). Stdio is local-only.
- Settings: enabled toggle, transport choice (stdio/SSE), API key reference.
- Uses `mcp` Python SDK for protocol handling.

**Files**: `integrations/mcp/__init__.py` (MCP server + tool definitions),
`chatwire_cli.py` (add `mcp` subcommand for stdio mode),
settings schema in the integration class

**Verify**: Connect Claude Code to chatwire MCP server. List conversations,
read messages, send a message. Anti-spam protections apply. Tests pass.

---

### Chunk 7: Bad word filter + category filtering

**Goal**: Content filter plugin using the transform pipeline.

**Design**:
- Built-in integration in `integrations/content_filter/`.
- Uses `transform_inbound()` to replace filtered words with random emoji.
- Original messages in chat.db untouched — transforms are display-only.
- Category word lists ship as JSON files in the plugin package
  (`data/profanity.json`, `data/politics.json`, etc.).
- Built-in categories: profanity, politics, religion, sex/porn,
  money/finance, weight/body, drugs, gossip/celebrities, gambling,
  social media, gaming, dietary choices.
- Settings UI:
  - Checkbox grid: one per category, all off by default
  - Custom words textarea (newline-separated)
  - Emoji pool picker (default: various face emoji)
  - Mode: exact / loose (catch common substitutions)
  - Scope: all surfaces / web only

**Files**: `integrations/content_filter/__init__.py`,
`integrations/content_filter/data/*.json` (category word lists),
settings schema

**Verify**: Enable a category, send a message containing a filtered word,
verify replacement in web UI. Original in chat.db unchanged. Tests pass.

---

### Chunk 8: Web notification improvements

**Goal**: Rich/sender-only/private notification detail levels.

**Design**:
- Add `web.notification_detail` setting with options:
  - **Rich**: full message text + sender name + avatar
  - **Sender only**: "Message from {contact}" + avatar
  - **Private**: "New iMessage received" (no name, no text)
- Per-contact follow/mute: bookmark icon on each contact in notification
  settings. Muted contacts don't trigger web push.
- Apply detail level in service worker `push` event handler.

**Files**: `web/main.py` (settings routes), service worker JS (detail
level logic), `web/templates/_settings.html` or notification settings
template

**Verify**: Change detail level, receive notification, verify content
matches setting. Mute a contact, verify no notification. Tests pass.

---

### Chunk 9: Advanced settings

**Goal**: Consolidate network config + service control into one accordion.

**Design**:
- **Port**: number input (default 8723)
- **Listen on**: dropdown — localhost / all interfaces / custom. Warning
  for all-interfaces.
- **Reverse proxy**: checkbox. When on: `proxy_headers=True` +
  `forwarded_allow_ips="*"` in uvicorn.
- **Service control**: show launchd agent status for bridge, web, keepawake.
  Toggle buttons call `launchctl bootout`/`bootstrap` via subprocess.
- **Keepawake indicator**: small icon in header or footer showing active
  (coffee cup) or inactive (moon).
- Persist to `web.port`, `web.bind`, `web.proxy_headers` in config.json.

**Files**: `web/main.py` (new routes, launchctl subprocess calls, uvicorn
config), `web/templates/_settings.html` (new accordion section)

**Verify**: Change port in settings (requires restart toast). Proxy toggle
persists. Service status shows correctly. Tests pass.

---

### Chunk 10: Popout messages

**Goal**: Pop-out conversation in a new browser window.

**Design**:
- Pop-out icon (square with arrow) on far right of conversation header,
  next to the info (i) button.
- Clicking opens `/popout?handle=...` or `/popout?chat=...` in a new window.
- Stripped-down view: messages + composer, no sidebar, no nav.
- Reuses `_messages.html` and composer from `_conversation.html`.
- SSE events still work in popout window.

**Files**: `web/main.py` (new `/popout` route), `web/templates/_popout.html`
(new template), `web/templates/_conversation.html` (add popout icon)

**Verify**: Click popout icon, new window opens with messages + composer.
Send/receive works. Tests pass.

---

### Chunk 11: Tinfoil hat (E2E encryption)

**Goal**: Symmetric encryption for messages between chatwire users.

**Design**:
- AES-256-GCM with shared passphrase.
- Key derivation: passphrase → PBKDF2-SHA256 → 256-bit AES key.
- Encrypted messages prefixed with a marker (e.g., `🔒` + base64 ciphertext).
- On inbound: if message starts with `🔒`, attempt decryption with
  configured key. If decryption succeeds, show plaintext. If fails,
  show "[Encrypted message — wrong key or not for you]".
- On outbound: if tinfoil hat is enabled for a contact, encrypt before
  sending via AppleScript.
- Per-contact key configuration in settings (different contacts can have
  different shared passphrases).
- Both parties need chatwire (or a compatible decoder) installed.
- Uses `cryptography` library (already a dependency from sig verification).

**Settings**:
- Global enable/disable toggle
- Per-contact passphrase entries (password fields)
- "Encrypt by default" toggle (encrypt all outbound to configured contacts)

**Files**: `integrations/tinfoil/__init__.py` (encryption/decryption logic,
transform hooks), settings schema

**Verify**: Configure shared passphrase for a test contact. Send encrypted
message, verify ciphertext in chat.db, plaintext in web UI. Receive
encrypted message, verify decryption. Wrong key shows error. Tests pass.

---

### Chunk 12: Custom CSS textarea

**Goal**: User-defined CSS injected after theme styles.

**Steps**:
- Add textarea to Appearance settings.
- Content saved to `web.custom_css` in config.json.
- Injected as `<style>` block after theme CSS in base template.
- No validation needed — if CSS is broken, user can clear it.

**Files**: `web/main.py` (save route), `web/templates/index.html` (inject
style block), Appearance settings template (textarea)

**Verify**: Add custom CSS (e.g., change background color). Verify it
applies. Clear it, verify reset. Tests pass.

## 6. Next prompt

```
Read docs/HANDOFF.md. You are starting wave 3. Pick up chunk 1: Message
load count setting. Make HISTORY_LIMIT configurable from Settings →
Appearance. Add a dropdown (25/50/100/200), persist to web.history_limit
in config.json, read from config instead of the hardcoded constant.
Default to the current value. Run pytest. Commit. Then update HANDOFF.md:
mark chunk 1 done in §3, write §6 with the prompt for chunk 2
(licensing/attribution), and commit.
```

## 7. Verbatim opening prompt for next session

```
Read docs/HANDOFF.md. You are starting wave 3. Pick up chunk 1: Message
load count setting. Make HISTORY_LIMIT configurable from Settings →
Appearance. Add a dropdown (25/50/100/200), persist to web.history_limit
in config.json, read from config instead of the hardcoded constant.
Default to the current value. Run pytest. Commit. Then update HANDOFF.md:
mark chunk 1 done in §3, write §6 with the prompt for chunk 2
(licensing/attribution), and commit.
```
