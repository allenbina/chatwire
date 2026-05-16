# Chatwire Privacy Policy

**Last updated: May 2025**

Chatwire is self-hosted software.  It runs entirely on your Mac.  There
is no Chatwire cloud, no Chatwire account, and no Chatwire server that
your data ever touches.

---

## Data Accessed Locally

| What | Where | How |
|---|---|---|
| iMessage database | `~/Library/Messages/chat.db` | Read-only.  Never modified. |
| Configuration | `~/.chatwire/config.json` | Read/write.  Stored with `600` permissions. |
| Attachment files | `~/Library/Messages/Attachments/` | Read-only.  Only fetched when relaying a specific attachment you received. |

Chatwire does not read your Contacts database, your Photos library, your
Mail, your Calendar, or any other system data store.

---

## Data Transmitted

Chatwire relays messages to the integration destinations **you configure**
— for example, a Telegram bot you own, or an ntfy server you run.  No
message content, metadata, or any other data is sent to the Chatwire
project or any third party.

What leaves your Mac, and where it goes, is entirely determined by the
integrations you enable in your own config.

---

## Telemetry

**None.**  Chatwire collects no analytics, no crash reports, no usage
statistics, and no metrics of any kind.  There is no telemetry code in
the project.  You can verify this yourself — the source is fully open.

---

## macOS Permissions Required

Chatwire requests exactly two macOS TCC permissions:

**Full Disk Access**
Required to read `chat.db`.  macOS does not provide a narrower TCC
scope for files under `~/Library/Messages/` — Full Disk Access is the
only mechanism available.  The grant is tied to the specific Python
binary chatwire runs under (the one in its pipx venv), not to Python
globally on your system.

**Automation → Messages**
Required to send iMessages via AppleScript.  This permission is scoped
by macOS to Messages.app only — it does not grant chatwire control over
any other application.

Chatwire does not request and does not use:

- Contacts
- Camera or Microphone
- Location Services
- Photos
- Calendar or Reminders
- Any accessibility or input-monitoring permission

---

## Data at Rest

Your config file (`~/.chatwire/config.json`) contains your integration
credentials (e.g. a Telegram bot token).  Chatwire enforces `600`
permissions on this file at startup and will refuse to run if the file
is world- or group-readable.  The file never leaves your machine.

Logs are written to `~/Library/Logs/chatwire/` and contain bridge
activity (message routing events, errors).  They do not contain message
body content by default.  Logs are never uploaded anywhere.

---

## Third-Party Dependencies

Chatwire's Python dependencies are listed in `pyproject.toml`.  None of
them phone home or collect data as part of normal operation.  The web UI
loads no external fonts, scripts, or resources — it is fully self-contained.

---

## Open Source

Chatwire is MIT-licensed and fully open source.  Every claim in this
document can be verified by reading the code:
<https://github.com/allenbina/chatwire>
