# chatwire-telegram

Two-way iMessage ↔ Telegram bridge. Every iMessage you receive is relayed to a Telegram bot, and messages you send to the bot are delivered as iMessages — giving you a full iMessage client inside Telegram.

## What it does

`chatwire-telegram` connects chatwire to a Telegram bot you create via BotFather. Inbound iMessages are forwarded to your Telegram account (or a dedicated group) with the sender's name and a message preview. Replies you send in Telegram are routed back through the chatwire bridge and delivered as iMessages from your Mac. Group chat support is included: each iMessage group maps to a Telegram group.

The bridge is two-way and stateful: chatwire maintains a mapping between iMessage handles and Telegram chat IDs so replies go to the right conversation.

## Install command

```bash
# Install inside the chatwire pipx environment:
pipx inject chatwire chatwire-telegram

# Or if using a regular venv:
pip install chatwire-telegram
```

After installing, create a Telegram bot and add the config to chatwire.

## Configuration walkthrough

### Step 1 — Create a Telegram bot

1. Open Telegram and search for **@BotFather**.
2. Send `/newbot` and follow the prompts to name your bot.
3. BotFather gives you a **bot token** (looks like `123456789:ABCdef...`). Save it.

### Step 2 — Get your Telegram user ID

1. Search Telegram for **@userinfobot** and send it any message.
2. It replies with your user ID (a number like `987654321`). Save it.

### Step 3 — Configure chatwire

In `~/.chatwire/config.json`:

```json
{
  "integrations": {
    "chatwire_telegram": {
      "enabled": true,
      "bot_token": "123456789:ABCdef...",
      "allowed_user_ids": [987654321],
      "relay_outbound": true,
      "group_mode": "map",
      "thread_per_contact": true
    }
  }
}
```

Or fill in the fields in Settings → Plugins → Telegram.

### Step 4 — Start the bot

1. Search Telegram for your bot by its username and send `/start`.
2. Restart the chatwire bridge.
3. Send yourself an iMessage from another device — it should appear in the bot chat within seconds.

## Usage guide

### Inbound relay (iMessage → Telegram)

Every relayed iMessage appears in your bot chat formatted as:

```
Alice (+15551234567):
Hey, are you around?
```

Photos and videos are forwarded as Telegram media messages. Attachments that can't be sent as media (e.g., files) are sent as document uploads.

### Outbound relay (Telegram → iMessage)

Reply to any bot message (using Telegram's reply-to feature) to send an iMessage back to that contact. Or use the format:

```
/send +15551234567 Your message here
```

### Group chats

With `group_mode: "map"`, each iMessage group chat maps to a Telegram group. The first time a group message arrives, chatwire creates a corresponding Telegram group (or uses one you pre-configured) and adds your bot to it.

### Thread mode

With `thread_per_contact: true`, each contact gets a separate thread inside the bot chat (requires a Telegram group with Topics enabled). This keeps conversations organised without creating separate groups per contact.

### Security

Only Telegram user IDs in `allowed_user_ids` can interact with the bot. Never share your bot token — anyone with the token can impersonate the bot and relay iMessages.

## Settings reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `false` | Master switch. |
| `bot_token` | string | — | **Required.** Token from BotFather (format: `<id>:<hash>`). |
| `allowed_user_ids` | list[int] | — | **Required.** List of Telegram user IDs allowed to send commands and receive messages. |
| `relay_outbound` | boolean | `true` | When `true`, messages sent in Telegram are relayed as outbound iMessages. Set to `false` for receive-only mode. |
| `group_mode` | enum | `"map"` | How group chats are handled: `map` (auto-create Telegram groups), `single` (all groups in one bot chat, prefixed with group name). |
| `thread_per_contact` | boolean | `false` | Use Telegram forum topics (threads) to separate contacts within a single group. Requires a supergroup with Topics enabled. |

## Troubleshooting / FAQ

**The bot doesn't respond when I send `/start`.**
Confirm the bridge is running and the `bot_token` is correct. Check chatwire logs (`chatwire logs` or `journalctl -u dev.chatwire.bridge`) for Telegram connection errors.

**iMessages aren't arriving in Telegram.**
1. Check that the sender is in your whitelist (Settings → Whitelist).
2. Confirm the bridge is running.
3. Look for errors in the bridge log that mention `chatwire_telegram`.

**I replied in Telegram but no iMessage was sent.**
Confirm `relay_outbound: true`. Also confirm your Telegram user ID is in `allowed_user_ids` — unauthorised users' messages are silently dropped.

**The bot sends messages but Photos aren't showing up.**
Large attachments may time out uploading to Telegram. Try sending the file as a document. Video files over Telegram's 50 MB limit cannot be forwarded.

**Can multiple people use the same bot?**
You can add multiple user IDs to `allowed_user_ids`. All of them will see all relayed messages and can send iMessages through the bot. Use with caution — everyone in the list has full send access.
