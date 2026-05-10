# chatwire-ntfy

Push notifications to your phone or desktop via [ntfy.sh](https://ntfy.sh) (or a self-hosted ntfy server) for every inbound iMessage relayed by chatwire.

## What it does

`chatwire-ntfy` listens to the chatwire bridge's inbound message stream and fires an HTTP POST to your ntfy topic whenever a new message arrives. Notifications appear instantly on any device subscribed to the same topic — Android, iOS (via the ntfy app), desktop, or any webhook-capable service. You can use the public ntfy.sh server or self-host ntfy for complete privacy.

Notification payloads include the sender name, a preview of the message text, and an optional click action that opens the chatwire web UI directly to that conversation.

## Install command

```bash
# Install inside the chatwire pipx environment:
pipx inject chatwire chatwire-ntfy

# Or if using a regular venv:
pip install chatwire-ntfy
```

After installing, enable the integration in chatwire Settings → Plugins → ntfy, or add it to `config.json` manually.

## Configuration walkthrough

1. **Create an ntfy topic.**
   - Public: visit [ntfy.sh](https://ntfy.sh) and pick a topic name (e.g., `my-imessages-abc123`). Use a long random string — topics are public by default.
   - Self-hosted: set up [ntfy server](https://docs.ntfy.sh/install/) and create a topic there.

2. **Subscribe on your devices.**
   - iOS/Android: install the ntfy app → Subscribe to topic → enter your topic name (and server URL if self-hosted).
   - Desktop: use ntfy's web UI at `https://ntfy.sh/<topic>`.

3. **Add the integration to chatwire.**

   In `~/.chatwire/config.json`:
   ```json
   {
     "integrations": {
       "chatwire_ntfy": {
         "enabled": true,
         "topic": "my-imessages-abc123",
         "server": "https://ntfy.sh",
         "username": "",
         "password": "",
         "priority": "default",
         "click_url": "http://localhost:8723"
       }
     }
   }
   ```

   Or open Settings → Plugins → ntfy and fill in the fields via the UI.

4. Restart the chatwire bridge: `chatwire restart` or restart the launchd agents.

## Usage guide

Once configured, every inbound message relayed by the bridge generates an ntfy notification:

- **Title**: sender name (resolved from Contacts if available, otherwise the phone/email handle).
- **Body**: message text preview (truncated at ~200 characters).
- **Click action**: opens `click_url` (default: `http://localhost:8723`) in your browser, landing on the conversation.
- **Priority**: controls urgency in the ntfy app (how it interrupts you).

### Access control

By default ntfy.sh topics are open to anyone who knows the name. To restrict access:
- Use a long random topic name (hard to guess).
- Self-host ntfy with access control: add `username` and `password` to the config.
- Subscribe to the topic via a trusted ntfy account.

### Self-hosted ntfy

Set `server` to your ntfy instance URL, e.g. `https://ntfy.example.com`. If your server requires auth, add `username` and `password`.

### Message attachments

Photos and videos do not appear in ntfy notifications — only text is included. A note like `[photo]` is appended to the notification body when an attachment is present.

## Settings reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `false` | Master switch. |
| `topic` | string | — | **Required.** ntfy topic name. Use a long, random string for privacy on the public server. |
| `server` | string | `"https://ntfy.sh"` | ntfy server base URL. Change if self-hosting. |
| `username` | string | `""` | Username for ntfy access control (leave blank for public topics). |
| `password` | string | `""` | Password for ntfy access control. |
| `priority` | enum | `"default"` | Notification urgency: `min`, `low`, `default`, `high`, `urgent`. See [ntfy priority docs](https://docs.ntfy.sh/publish/#message-priority). |
| `click_url` | string | `"http://localhost:8723"` | URL opened when the user taps the notification. Use your Tailscale/LAN URL if accessing chatwire remotely. |

## Troubleshooting / FAQ

**Notifications aren't arriving.**
1. Confirm the bridge is running: `chatwire status` or Settings → Advanced.
2. Check the ntfy topic: visit `https://ntfy.sh/<your-topic>` in a browser — you should see messages arrive there when a new iMessage comes in.
3. Confirm the ntfy app is subscribed to the exact same topic name.

**I get a 401 or 403 error in the chatwire logs.**
Your ntfy server requires authentication. Set `username` and `password` in the config.

**Notifications arrive for every message — how do I filter?**
Use ntfy app filters (keyword filters in the app settings) to suppress notifications for contacts or keywords. Alternatively, configure the `notification_muted_contacts` list in chatwire's built-in smart notifications to suppress certain contacts from the bridge entirely.

**The click URL opens to the wrong address.**
Update `click_url` to the URL you actually use to access chatwire — e.g., your Tailscale hostname or local IP (`http://192.168.1.10:8723`).

**Can I use this alongside the browser Web Push notifications?**
Yes. chatwire's built-in web-push and chatwire-ntfy are independent. You can run both simultaneously or use one or the other.
