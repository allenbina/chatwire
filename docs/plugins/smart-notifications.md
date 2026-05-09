# Smart Notifications

## What it does

Smart Notifications gives you fine-grained control over which web-push notifications chatwire sends to your browser and PWA. Three complementary features work together: **Hiatus mode** suppresses notifications when you're already actively in a conversation, **Reminder timers** ping you when you haven't heard from someone in N days, and the **contact picker** lets you whitelist specific contacts or mute individual ones so you only get notified by the people that matter.

All notification logic runs locally — no push service account is required beyond the browser's built-in Web Push API.

## Install command

Smart Notifications is a built-in web UI feature — no plugin install is required.

```
# Already available in Settings → Notifications
```

## Configuration walkthrough

1. Open chatwire → **Settings** → **Notifications** (expand the accordion).
2. Configure each sub-section as needed:
   - **Notification detail** — choose how much info appears in the notification.
   - **Who can notify you** — all contacts or a hand-picked selection.
   - **Mute contacts** — silence specific contacts without removing them from the whitelist.
   - **Hiatus mode** — suppress notifications after you send a message.
   - **Reminder timers** — get nudged when a contact goes quiet for too long.
3. Each section has its own **Save** button; changes take effect immediately.

## Usage guide

### Notification detail

Controls the content of web-push notifications:

| Level | What appears |
|-------|-------------|
| Rich | Sender name + first ~100 characters of the message |
| Sender only | Sender name only, no message text |
| Private | Generic "New message" — no name, no text |

Use **Private** on shared or workplace computers where others might see notification banners.

### Who can notify you

- **All contacts** (default) — every whitelisted contact triggers notifications.
- **Selected contacts only** — only the contacts you check in the list generate notifications. Useful if you have many whitelist entries but only care about a few.

Changes take effect immediately without a page reload.

### Mute contacts

Muted contacts generate no web-push notification at all, even if they are in the "selected contacts" list. Muting is per-contact and toggles with a single checkbox. Muted contacts still appear in the sidebar and their messages are still relayed — they just don't buzz your phone.

### Hiatus mode

Suppresses notifications from a contact if you sent them a message within the last **N minutes**. Useful when you're mid-conversation and don't need your phone buzzing every time the other person replies.

| Setting | Description |
|---------|-------------|
| **Enable hiatus mode** | Master toggle for the feature |
| **Silence window (minutes)** | How long after your last outbound message notifications are suppressed. Range: 1–1440 (1 day). Default: 30. |

### Reminder timers

Sends a web-push notification when you haven't received a message from a contact in N days. Checks once per day.

| Setting | Description |
|---------|-------------|
| **Enable reminders** | Master toggle for the feature |
| **Remind after (days)** | Threshold before the reminder fires. Range: 1–365. Default: 7. |

Reminders are sent for all whitelisted contacts that are not muted and have not messaged you within the configured window.

## Settings reference

These settings are stored in `~/.chatwire/config.json` and are editable via the web UI:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `notification_detail` | enum | `"rich"` | Notification verbosity: `rich`, `sender_only`, or `private`. |
| `notify_mode` | enum | `"all"` | `all` or `selected` — who can trigger notifications. |
| `notification_selected_contacts` | list | `[]` | Handles that can notify you when `notify_mode` is `selected`. |
| `notification_muted_contacts` | list | `[]` | Handles that never trigger notifications. |
| `hiatus_enabled` | boolean | `false` | Enable hiatus mode. |
| `hiatus_duration_minutes` | integer | `30` | Silence window in minutes (1–1440). |
| `reminder_enabled` | boolean | `false` | Enable reminder timers. |
| `reminder_days` | integer | `7` | Remind after N days of silence (1–365). |

## Troubleshooting / FAQ

**I'm not receiving any notifications at all.**
First, ensure you've granted notification permission to chatwire in your browser (the browser will prompt once when you open the web UI). On iOS, add chatwire to your home screen (PWA) and enable notifications in iOS Settings → chatwire. Then confirm **Notification detail** is not set to **Private** (which is valid but easy to forget).

**Hiatus mode is blocking notifications for too long.**
Reduce the **Silence window** value. At 30 minutes (the default), you'll be suppressed for half an hour after every message you send.

**Reminders aren't firing.**
Check that **Enable reminders** is ON and that the chatwire web service has been running continuously (reminders check once per day while the service is alive). Also make sure the contact is whitelisted and not muted.

**"Selected contacts only" mode shows no contacts in the list.**
The contact list is populated from your whitelist. Go to Settings → Whitelist and add contacts, then return to Notifications.

**I muted a contact but I'm still getting notifications from them.**
Hard-refresh the settings page and re-check the mute toggle. If the issue persists, check `~/.chatwire/config.json` — the handle in `notification_muted_contacts` must exactly match the handle format used in the whitelist (e.g., `+15551234567` vs `15551234567`).
