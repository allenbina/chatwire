# Handoff — Wave 4: Media, Integrations & UX (6 chunks)

> Custom CSS, smart notifications, export, Home Assistant, media
> improvements, XMPP relay. Ship as v1.4.0.

## 1. State

- **PyPI**: chatwire 1.3.0 (wave 3 shipped: anti-spam guardrails, REST API,
  MCP plugin, bad word filter, tinfoil hat, PWA, web notification
  improvements, advanced settings, popout, custom CSS, licensing).
- **mbair**: running latest, healthz green.
- **Tests**: all green.

## 2. Architecture decisions (locked in)

- All prior decisions carry forward.
- **Anti-spam**: normalized hash broadcast detection + escalating timeouts
  in `chat_send.py`. Whitelist immutable from plugins.
- **Transform pipeline**: `transform_inbound()` / `transform_outbound()`
  in place. Content filter plugin uses it.
- **REST API**: FastAPI sub-app at `/api/v1/`, API key auth.
- **MCP**: stdio + SSE transports, same API key for SSE.

## 3. Task list

1. [ ] Custom CSS textarea — textarea in Appearance, `<style>` injection
2. [ ] Smart notifications — per-contact picker (bookmark icons), hiatus
   mode (only notify after silence), reminder timers
3. [ ] Export plugin — contact page Export button, JSON/TXT/CSV messages,
   ZIP for photos
4. [ ] Home Assistant plugin — keyword → HA service call, long-lived access
   token auth, separate repo `chatwire-ha`
5. [ ] Media improvements — gallery grid (2=side-by-side, 3=1+2, 4=2x2,
   5+=2x2 with "+N" overlay), lightbox with nav + thumbnail strip,
   thumbnail size setting, time-window grouping (~3s same sender = bundle)
6. [ ] XMPP relay — slixmpp, same plugin structure as telegram, 1:1 relay
   + group chat (MUC) + media (HTTP upload XEP-0363)

## 4. Follow-ups (wave 5)

- Mac toolbar icon (rumps)
- Onboarding docs (Allen will do fresh install + screencaps)
- Plugin READMEs

## 5. Chunks

### Chunk 1: Custom CSS textarea

**Goal**: User-defined CSS injected after theme styles.

**Steps**:
- Add textarea to Appearance settings section.
- Content saved to `web.custom_css` in config.json via htmx POST.
- Injected as `<style>` block after theme CSS in base template `<head>`.
- No validation — broken CSS can be cleared by the user.

**Files**: `web/main.py` (save route, pass custom_css to template context),
`web/templates/index.html` (inject `<style>` block),
Appearance settings template (add textarea with monospace font)

**Verify**: Add CSS (e.g., `body { background: #1a1a2e !important; }`),
verify it applies immediately. Clear textarea, verify reset. Tests pass.

---

### Chunk 2: Smart notifications

**Goal**: Per-contact notification control with hiatus and reminder timers.

**Design**:
- Extends the shared notification settings framework used by ntfy and
  web push.
- New `notify_mode` option: "selected" — hand-pick which contacts trigger
  notifications.
- UI: in notification plugin settings, when mode="selected", show contact
  list with bookmark icons (filled=on, hollow=off). Tap to toggle.
- **Hiatus mode**: only notify after a configurable period of silence from
  that contact. Default: 30 minutes. If you're actively chatting, no buzz.
  Once conversation goes quiet for the hiatus duration and they text again,
  you get pinged.
- **Reminder timer**: "Haven't heard from {contact} in {N} days" nudge.
  Configurable per-contact or global. Checks once daily.
- Both stored in config under the notification plugin's settings.

**Settings schema additions**:
- `notify_mode`: enum "all" / "whitelist_only" / "selected"
- `selected_contacts`: array of handles (when mode=selected)
- `hiatus_enabled`: boolean
- `hiatus_duration_minutes`: integer (default 30)
- `reminder_enabled`: boolean
- `reminder_days`: integer (default 7)
- `reminder_contacts`: array of handles

**Files**: notification settings template (contact picker partial),
`bridge.py` or notification integration base (hiatus tracking logic,
reminder check), config schema updates

**Verify**: Set mode to "selected", pick contacts, verify only those
trigger notifications. Enable hiatus, verify rapid messages don't notify
but message after silence does. Tests pass.

---

### Chunk 3: Export plugin

**Goal**: Export conversation data from the contact/conversation page.

**Design**:
- "Export" button on conversation page header (next to popout icon).
- Dropdown: JSON | TXT | CSV for messages, ZIP for photos.
- Options modal: messages only, photos only, or both. Date range filter.
- Messages export includes: timestamp, sender (name + handle), text,
  attachment filenames.
- Photos export: ZIP file with original filenames, organized by date.
- Built-in integration in `integrations/export/`.
- Routes:
  - `GET /api/export/messages?handle=...&format=json|txt|csv&since=...`
  - `GET /api/export/photos?handle=...&since=...` (returns ZIP)

**Files**: `integrations/export/__init__.py` (integration class),
`web/main.py` (export routes, SQL queries, file generation),
conversation template (export button + dropdown)

**Verify**: Export messages as JSON, TXT, CSV — verify format and content.
Export photos as ZIP — verify files present. Date range filter works.
Tests pass.

---

### Chunk 4: Home Assistant plugin

**Goal**: Trigger HA automations/scenes via iMessage commands.

**Design**:
- Separate repo: `chatwire-ha/`
- Auth: HA long-lived access token + URL.
- MVP: exact keyword → HA service call mapping in settings.
  e.g., "lights off" → `light.turn_off` entity `light.living_room`
- `on_inbound()`: check if message text matches a registered keyword.
  Call `POST {ha_url}/api/services/{domain}/{service}` with token.
  Reply via `ctx.send_text()`: "Done: {action description}"
- Settings schema: ha_url (string), access_token (password), command
  mappings (array of objects: keyword, domain, service, entity_id, description)
- Whitelisted contacts only (inherits from bridge whitelist check).

**Files**: `chatwire-ha/chatwire_ha/__init__.py` (HAIntegration class),
`chatwire-ha/pyproject.toml` (entry point, deps: httpx)

**Verify**: Configure HA URL + token + a test command mapping. Send keyword
via iMessage, verify HA API called, reply received. Tests pass.

---

### Chunk 5: Media improvements (session 1 — gallery grid + lightbox)

**Goal**: Bundled photo display with grid layout and lightbox viewer.

**Design**:
- **Grouping logic**: Messages with same `message_id` in chat.db are
  already linked. For separate messages: same sender within 3 seconds
  and all-attachments (no text) = bundle. Grouping happens in
  `web/main.py` conversation loading.
- **Grid layout**:
  - 1 photo: full width (current behavior)
  - 2 photos: side by side (50/50)
  - 3 photos: one large left (66%), two stacked right (33% each)
  - 4 photos: 2x2 grid
  - 5+: 2x2 grid, 4th cell has dim overlay with "+N" text
- **Lightbox**: clicking any thumbnail opens a full-screen overlay with:
  - Current image centered
  - Left/right nav arrows
  - Thumbnail strip at bottom
  - Close button (X) or click outside
  - Keyboard nav (left/right arrows, Escape to close)
- Pure CSS + vanilla JS, no library dependency.

**Files**: `web/main.py` (grouping logic in conversation loader),
`web/templates/_messages.html` (grid layout markup),
`web/static/css/` or inline styles (grid CSS),
`web/static/js/` or inline script (lightbox JS)

**Verify**: Send 1, 2, 3, 4, 5+ photos. Verify grid layouts render
correctly. Click thumbnail, lightbox opens. Nav works. Tests pass.

---

### Chunk 6: Media improvements (session 2 — thumbnail sizes + XMPP relay)

**Goal**: Thumbnail size setting + XMPP relay plugin.

**Part A — Thumbnail size setting**:
- Add dropdown to Appearance settings: Small (360px) / Medium (720px) /
  Large (1080px) / Full (no resize).
- Persist to `web.thumbnail_max_size` in config.json.
- Apply in thumbnail generation (sips resize) and in CSS max-width on
  image elements.

**Part B — XMPP relay**:
- Separate repo: `chatwire-xmpp/`
- Uses `slixmpp` (async XMPP library).
- Config: JID, password, server URL (if different from JID domain),
  contact mappings (same pattern as chatwire-telegram).
- `start()`: connect to XMPP server, maintain presence.
- `on_inbound()`: forward iMessage to mapped XMPP JID.
- XMPP inbound handler: forward to iMessage via `ctx.send_text()`.
- Group chat: MUC (multi-user chat) rooms mapped to iMessage group GUIDs.
- Media: HTTP upload (XEP-0363) if server supports it, otherwise send
  download link.

**Files**:
- Appearance template (thumbnail size dropdown)
- `web/main.py` (thumbnail size config)
- `chatwire-xmpp/chatwire_xmpp/__init__.py` (XMPPIntegration class)
- `chatwire-xmpp/pyproject.toml` (entry point, deps: slixmpp)

**Verify**: Thumbnail size changes apply to images. XMPP: configure with
a test server, send/receive messages. Tests pass.

## 6. Next prompt

```
Read docs/HANDOFF.md. You are starting wave 4. Pick up chunk 1: Custom
CSS textarea. Add a textarea to Appearance settings. Content saved to
web.custom_css in config.json. Injected as a <style> block after theme
CSS in the base template <head>. No validation needed. Run pytest. Commit.
Then update HANDOFF.md: mark chunk 1 done in §3, write §6 with the prompt
for chunk 2 (smart notifications), and commit.
```

## 7. Verbatim opening prompt for next session

```
Read docs/HANDOFF.md. You are starting wave 4. Pick up chunk 1: Custom
CSS textarea. Add a textarea to Appearance settings. Content saved to
web.custom_css in config.json. Injected as a <style> block after theme
CSS in the base template <head>. No validation needed. Run pytest. Commit.
Then update HANDOFF.md: mark chunk 1 done in §3, write §6 with the prompt
for chunk 2 (smart notifications), and commit.
```
