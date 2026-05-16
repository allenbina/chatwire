# XMPP Relay

## What it does

The XMPP plugin bridges iMessage and XMPP (Jabber) for a whitelisted set of contacts. Messages flow in both directions:

- **iMessage → XMPP**: when a mapped contact texts you, the message is forwarded to their XMPP JID.
- **XMPP → iMessage**: when a mapped contact sends you an XMPP message, it is delivered back as an iMessage.

Only contacts listed in `contact_mappings` are relayed. All other senders are silently ignored — the bridge never forwards messages from unknown parties. This is a 1:1 relay (MVP); group chats are not yet supported.

Useful for staying in a single messaging client, for automation pipelines that speak XMPP, or for bridging a corporate Jabber account to your personal iMessage thread.

## Install command

```bash
pipx inject chatwire chatwire-xmpp
# or inside the chatwire venv:
pip install chatwire-xmpp
```

Then restart the chatwire bridge:

```bash
launchctl kickstart -k gui/$(id -u)/dev.chatwire.bridge
```

## Configuration walkthrough

1. Open chatwire in your browser (`http://localhost:8723`).
2. Go to **Settings** → **Plugins** → **XMPP Relay**.
3. Toggle **Enabled** to ON.
4. Enter the **Bridge JID** — the full Jabber ID the bridge will log in as (e.g. `bridge@example.com`). This should be a dedicated account, not your personal JID.
5. Enter the **Password** for that account.
6. If your server hostname differs from the JID domain (e.g. you use SRV records or a non-standard host), fill in **XMPP server**. Otherwise leave it blank.
7. Add one or more **Contact mappings** — each maps an iMessage handle (phone number or iCloud email) to the corresponding XMPP JID.
8. Changes save automatically. The plugin connects immediately upon save.

## Settings reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `false` | Master switch. |
| `jid` | string | *(required)* | Full JID for the bridge bot, e.g. `bridge@example.com`. |
| `password` | string | *(required)* | Password for the bridge XMPP account. |
| `server_url` | string | `""` | XMPP server hostname. Blank = domain part of `jid`. |
| `contact_mappings` | array | `[]` | List of iMessage ↔ XMPP mappings (see below). |

### Contact mapping fields

Each entry in `contact_mappings` is an object with two required fields:

| Field | Type | Description |
|-------|------|-------------|
| `imessage_handle` | string | Phone number in E.164 format (`+15551234567`) or iCloud email (`bob@icloud.com`). |
| `xmpp_jid` | string | Bare JID of the XMPP contact, e.g. `alice@example.com`. Matched case-insensitively. |

Config file path: `~/.chatwire/config.json` under `integrations.chatwire_xmpp`.

## Minimal config

```json
{
  "integrations": {
    "chatwire_xmpp": {
      "enabled": true,
      "jid": "bridge@example.com",
      "password": "s3cr3t",
      "contact_mappings": [
        {"imessage_handle": "+15551234567", "xmpp_jid": "alice@example.com"}
      ]
    }
  }
}
```

## Full config (custom server + multiple contacts)

```json
{
  "integrations": {
    "chatwire_xmpp": {
      "enabled": true,
      "jid": "bridge@corp.example.com",
      "password": "s3cr3t",
      "server_url": "xmpp.corp.example.com",
      "contact_mappings": [
        {"imessage_handle": "+15551234567", "xmpp_jid": "alice@corp.example.com"},
        {"imessage_handle": "bob@icloud.com",  "xmpp_jid": "bob@corp.example.com"},
        {"imessage_handle": "+15559876543", "xmpp_jid": "carol@jabber.org"}
      ]
    }
  }
}
```

## How the relay works

### iMessage → XMPP

When an inbound iMessage arrives from a mapped handle, `on_inbound()` looks up the sender's `imessage_handle` in the mapping table and calls `slixmpp.send_message()` to the corresponding XMPP JID. Photo-only messages (no text body) are not relayed in this release.

### XMPP → iMessage

slixmpp runs in a background thread (`chatwire-xmpp-thread`). When a `chat` or `normal` message arrives from a mapped JID, the plugin calls `ctx.send_text()` on the bridge's asyncio loop via `asyncio.run_coroutine_threadsafe()`, delivering the message as an iMessage to the mapped handle.

### Matching rules

- `contact_mappings` is bidirectional: each entry creates both an outbound (`imessage_handle → xmpp_jid`) and an inbound (`xmpp_jid → imessage_handle`) lookup.
- XMPP JID matching strips the resource part and lowercases — `Alice@Example.com/Home` resolves to `alice@example.com`.
- iMessage handle matching is exact (as delivered by the bridge); phone numbers should be in E.164 format.
- Unmapped senders in either direction are silently ignored.

## Troubleshooting / FAQ

**The plugin fails to start with "slixmpp is not installed".**
Run `pip install slixmpp` (or `pipx inject chatwire slixmpp`) and restart the bridge.

**Connection fails or times out.**
Check that the XMPP server is reachable from the Mac: `nc -zv xmpp.example.com 5222`. If your server uses a non-standard hostname, set `server_url` explicitly.

**Messages arrive on XMPP but don't come back to iMessage.**
Confirm the XMPP contact is sending from the exact bare JID listed in `contact_mappings`. The JID is matched after stripping the resource; check the debug log (`chatwire bridge --log-level debug`) for the sender JID being received.

**I see "xmpp: failed to relay message" in the logs.**
The slixmpp client may have disconnected. Restarting the bridge reconnects: `launchctl kickstart -k gui/$(id -u)/dev.chatwire.bridge`.

**Photos / attachments are not forwarded.**
Media relay is not implemented in the MVP. Only text messages are bridged.

**I want to relay a group chat.**
Group chat (MUC) support is planned but not yet implemented. Each entry in `contact_mappings` currently maps a single 1:1 iMessage thread to a single XMPP JID.

**How do I create a dedicated bridge account on Prosody / ejabberd?**
Create a regular user account on your XMPP server (e.g. `bridge@example.com`) and enter those credentials in the plugin settings. The bridge account does not need admin privileges.
