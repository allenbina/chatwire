# Popout View

## What it does

Popout view opens any 1:1 or group conversation in a standalone browser window stripped of the sidebar, header navigation, and settings UI. The result is a minimal, distraction-free chat panel that you can resize, position alongside other windows, or pin to a corner of your screen. It is ideal for keeping a single conversation always visible while you work in other apps.

The popout window is fully functional: you can send messages, view photos, and receive real-time updates via the same Server-Sent Events feed as the main UI.

## Install command

Popout is a built-in web UI feature — no plugin install is required.

```
# Available via the conversation header or direct URL
```

## Configuration walkthrough

Popout has no settings panel. It is launched directly from the conversation:

1. Open any conversation in chatwire.
2. Click the **popout icon** (overlapping squares / external window icon) in the conversation header toolbar.
3. A new browser window opens showing only that conversation.
4. Resize and position the window to your preference.

Or navigate directly:

```
http://localhost:8723/popout?handle=+15551234567
```

For a group chat, use the `chat` parameter with the group GUID:

```
http://localhost:8723/popout?chat=chat123456abcdef
```

## Usage guide

### Launching a popout

- **From the UI**: conversation header → popout icon.
- **Via URL**: `http://localhost:8723/popout?handle=<handle>`.
- **Keyboard shortcut**: none by default — create a browser bookmark to your most-used popout URL.

### What's included in the popout

- Full message history with the same scroll behaviour as the main view.
- The message compose box — type and send messages normally.
- Inline photo/video previews and the lightbox gallery.
- Real-time message delivery via SSE (same poll interval as the main UI).
- Dark/light theme follows your appearance preference.

### What's not included

- Sidebar (contact list).
- Settings, whitelist, or plugin panels.
- Favorites or notification controls.

### Multiple popouts

You can open multiple popout windows simultaneously — one per conversation. Each is an independent browser tab/window pointing to a different handle or chat GUID.

### Mobile / PWA

On iOS and Android, navigate to the popout URL in Safari/Chrome and use **Add to Home Screen** to create a dedicated icon for a single conversation. This gives you a PWA-style shortcut that opens directly to that chat.

### Bookmark tip

For frequently-used popouts, bookmark the URL with a descriptive name:

```
http://localhost:8723/popout?handle=+15551234567
```

Name it something like "Popout — Alice" so you can open it from your browser bookmarks bar instantly.

## Settings reference

Popout has no config-file settings. The route accepts these query parameters:

| Parameter | Required | Description |
|-----------|----------|-------------|
| `handle` | one of | Phone number (E.164) or email for a 1:1 conversation. |
| `chat` | one of | Group chat GUID for a group conversation. |

Exactly one of `handle` or `chat` must be supplied. If both or neither are provided, the page shows an error.

## Troubleshooting / FAQ

**The popout shows "conversation not found" or a blank page.**
The handle or chat GUID must be in your whitelist. Add the contact in Settings → Whitelist, then reload the popout URL.

**The popout doesn't receive new messages in real time.**
Check that the chatwire bridge and web services are running (Settings → Advanced → Service status). The popout uses SSE, which requires the web service to be alive. Hard-refresh the popout window (`Cmd+Shift+R`) to re-establish the SSE connection.

**The popout window opened but then closed by itself.**
Some browsers (especially Safari in certain configurations) close windows opened by JavaScript `window.open()` immediately. Try pasting the URL directly into a new browser window or tab instead of using the popout icon.

**Can I set the popout as my browser's home page?**
Yes. Set your browser's home/new-tab URL to `http://localhost:8723/popout?handle=+15551234567` and it will open directly to that conversation.

**The compose box is missing.**
If you loaded the popout URL for a handle not in your whitelist, the page renders in a read-only mode. Add the handle to the whitelist and reload.
