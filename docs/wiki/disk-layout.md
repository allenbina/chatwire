# Disk Layout

Every file and directory that chatwire creates, reads, or writes.

## Package (read-only after install)

| Path | Contents |
|---|---|
| `<venv>/lib/pythonX.Y/site-packages/` | All chatwire source modules |
| `<venv>/bin/chatwire` | CLI entry point |

Where `<venv>` is typically `~/.local/pipx/venvs/chatwire/`.

---

## `~/.chatwire/` — runtime data

Created on first run. All secrets live here; protect with `chmod 700 ~/.chatwire`.

| Path | Description |
|---|---|
| `config.json` | Main configuration file (chmod 600) |
| `state/state.json` | Bridge cursor — last-seen chat.db ROWID |
| `state/bridge.pid` | PID lock file (active while bridge is running) |
| `chatwire.jsonl` | Structured log (Log Viewer source) |
| `chatwire.1.jsonl` | Previous log (auto-rotation backup) |
| `read_state.db` | SQLite — which conversations have been read |
| `send_audit.log` | TSV — timestamp, recipient, source, msg hash |
| `fuse_state.json` | Anti-spam fuse state (step, cooldown_until) |
| `lockout.json` | Unlock code for fuse step 4+ |
| `thumb_cache/` | Attachment thumbnail cache |
| `plugins/<name>/` | Per-plugin data directory |
| `plugins/<name>/plugin.log` | Plugin private log (when `LOGS_VISIBLE=False`) |
| `echo_log.db` | Bridge-echo dedup — prevents outbound bouncing back |

### `config.json` top-level keys

```jsonc
{
  "SELF_HANDLES": "+15550001234",      // your Apple ID handle(s)
  "WEB_PORT": 8723,                    // HTTP listen port
  "WEB_BIND": "127.0.0.1",             // listen address
  "NTFY_TOPIC": "yourTopic",           // ntfy.sh push topic
  "web": {
    "theme": "dracula",                // active color scheme
    "accent_color": "",                // hex override or ""
    "style": "default"                 // structural style
  },
  "integrations": {
    "telegram": { "enabled": true, "bot_token": "..." },
    "webhook":   { "enabled": false, "url": "..." }
  },
  "notifications": {
    "notification_depth": { "default": "sender" }
  }
}
```

---

## `~/Library/LaunchAgents/`

| File | Agent label |
|---|---|
| `dev.chatwire.bridge.plist` | `dev.chatwire.bridge` |
| `dev.chatwire.web.plist` | `dev.chatwire.web` |
| `dev.chatwire.keepawake.plist` | `dev.chatwire.keepawake` |

Installed by `chatwire install-agents`. Removed by `chatwire uninstall --purge`.

---

## `~/Library/Logs/chatwire/`

| File | Contents |
|---|---|
| `stderr.log` | Bridge process stdout/stderr (launchd redirect) |
| `web-stderr.log` | Web process stdout/stderr |
| `keepawake-stderr.log` | Keepawake process stdout/stderr |

---

## Source files (read-only at runtime)

| Path | Role |
|---|---|
| `bridge.py` | Poll loop and integration fan-out |
| `chat_send.py` | AppleScript send + anti-spam guard |
| `chat_db.py` | chat.db reader |
| `contacts.py` | AddressBook handle → display name |
| `config.py` | Config load/save |
| `web/main.py` | FastAPI app entry |
| `web/log_stream.py` | JSONL structured logger |
| `integrations/` | Built-in integration modules |
| `templates/launchd/` | Plist templates |
