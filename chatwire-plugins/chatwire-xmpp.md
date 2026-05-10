# chatwire-xmpp

Two-way iMessage ↔ XMPP (Jabber) bridge for whitelisted contacts. iMessages from mapped contacts are relayed to their corresponding XMPP JIDs, and XMPP messages flow back as iMessages.

## What it does

`chatwire-xmpp` runs an XMPP client inside the chatwire bridge using the `slixmpp` library. You give it a dedicated XMPP account for the bridge bot (e.g., `bridge@example.com`) and a list of contact mappings that pair iMessage handles with XMPP JIDs. When a mapped contact sends you an iMessage, the bridge forwards it to their XMPP JID. When they reply in XMPP, the bridge delivers it as an iMessage from your Mac. Only mapped (whitelisted) contacts are relayed; all others are silently ignored.

This release supports 1:1 conversations only (no MUC/group chat bridge). Group chat support is planned for a future release.

## Install command

```bash
# Install inside the chatwire pipx environment:
pipx inject chatwire chatwire-xmpp

# Or if using a regular venv:
pip install chatwire-xmpp
```

`chatwire-xmpp` depends on `slixmpp` (installed automatically).

## Configuration walkthrough

### Step 1 — Set up a bridge XMPP account

Create a dedicated XMPP account for the chatwire bridge. This is the account the bridge logs in as — not your personal account. Most public XMPP servers (e.g., `jabber.org`, `xmpp.jp`) allow free registration. Self-hosting an XMPP server (Prosody, Ejabberd) gives you the most control.

Example: `bridge@example.com` with password `s3cr3t`.

### Step 2 — Identify your contacts' XMPP JIDs

For each iMessage contact you want to bridge, find their bare XMPP JID (e.g., `alice@jabber.org`). They need to have an XMPP account and be reachable on the server.

### Step 3 — Configure chatwire

In `~/.chatwire/config.json`:

```json
{
  "integrations": {
    "chatwire_xmpp": {
      "enabled": true,
      "jid": "bridge@example.com",
      "password": "s3cr3t",
      "server_url": "",
      "contact_mappings": [
        {
          "imessage_handle": "+15551234567",
          "xmpp_jid": "alice@jabber.org"
        },
        {
          "imessage_handle": "bob@icloud.com",
          "xmpp_jid": "bob@example.com"
        }
      ]
    }
  }
}
```

Or use Settings → Plugins → XMPP Relay in the web UI.

### Step 4 — Restart the bridge

```bash
# launchd (standard install):
/bin/launchctl kickstart -k gui/501/dev.chatwire.bridge

# Or:
chatwire restart
```

The bridge logs will show `xmpp integration started` when the connection is established.

## Usage guide

### Message flow

**iMessage → XMPP:**
- A mapped contact sends you an iMessage.
- The bridge receives it and calls `xmpp.send_message(to=<their xmpp_jid>, body=<text>)`.
- The message appears in their XMPP client from the bridge JID.

**XMPP → iMessage:**
- A mapped contact (identified by their bare JID) sends an XMPP message to the bridge account.
- The bridge delivers it as an iMessage from your Mac to the mapped iMessage handle.

### Contact mappings

Each entry in `contact_mappings` requires:
- `imessage_handle`: phone number in E.164 format (`+15551234567`) or email (`user@icloud.com`).
- `xmpp_jid`: bare JID of the contact (`alice@server.example`). Resource suffixes (`/mobile`) are stripped automatically.

### Unmapped contacts

iMessage contacts without an XMPP mapping and XMPP contacts without an iMessage mapping are silently ignored. No error is thrown; the message is dropped.

### Text-only

This release relays text messages only. iMessage photos, videos, and other attachments are not forwarded to XMPP. A future release will support sending attachments as XMPP file transfers (XEP-0363).

### XMPP server override

The bridge uses the domain part of the JID as the server hostname by default (standard XMPP service discovery via SRV records). If your server uses a non-standard hostname, set `server_url` explicitly:

```json
"server_url": "xmpp.internal.example.com"
```

## Settings reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `false` | Master switch. |
| `jid` | string | — | **Required.** Full JID of the bridge bot account, e.g. `bridge@example.com`. |
| `password` | string | — | **Required.** Password for the bridge XMPP account. |
| `server_url` | string | `""` | Override the XMPP server hostname. Leave blank to use the domain part of `jid`. |
| `contact_mappings` | list | `[]` | Array of `{imessage_handle, xmpp_jid}` objects. Only mapped contacts are relayed. |
| `contact_mappings[].imessage_handle` | string | — | iMessage phone (E.164) or email. |
| `contact_mappings[].xmpp_jid` | string | — | Bare XMPP JID of the contact (no resource). |

## Troubleshooting / FAQ

**The bridge logs show `xmpp: failed to connect` or `AuthenticationError`.**
Double-check the `jid` and `password`. Confirm the account exists on the XMPP server and the password is correct. If the server requires TLS, make sure port 5222 is reachable from your Mac.

**iMessages from a mapped contact aren't reaching XMPP.**
1. Confirm the contact is in your chatwire whitelist (Settings → Whitelist).
2. Confirm the `imessage_handle` in the mapping exactly matches the handle (including `+` prefix for phone numbers).
3. Check bridge logs for errors from `chatwire.xmpp`.

**XMPP messages aren't being delivered as iMessages.**
1. Confirm the sender's bare JID (stripped of resource) matches the `xmpp_jid` in the mapping.
2. The bridge must receive the XMPP message while connected — confirm the XMPP session is active (check logs for `session started`).
3. Verify the corresponding `imessage_handle` is in the chatwire whitelist.

**`slixmpp is not installed` error at startup.**
Run `pipx inject chatwire chatwire-xmpp` again — slixmpp should be installed as a dependency. If you're using a regular venv, run `pip install slixmpp`.

**Photos from iMessage aren't showing up in XMPP.**
Photo relay is not supported in this release — text only. The iMessage will be silently dropped if it has no text body.
