# Architecture

chatwire runs as two separate processes controlled by launchd, plus a keepawake
helper. They communicate via files on disk — there is no inter-process socket.

---

## Process model

```
launchd
├── dev.chatwire.bridge   → python bridge.py
├── dev.chatwire.web      → python -m uvicorn web.main:app
└── dev.chatwire.keepawake
```

### Bridge process (`bridge.py`)

Polls `~/Library/Messages/chat.db` every 2 seconds. For each new inbound
message it:

1. Checks the relay scope (SELF_HANDLES + whitelist + groups).
2. Runs inbound transform plugins (e.g. content filter, tinfoil decrypt).
3. Fans out to all enabled integrations (gated by tier).
4. Records the message in the debug mirror (if configured).

**No HTTP server**. The bridge is a long-running async process.

### Web process (`web/main.py`)

FastAPI app serving:

- `/` — React SPA (built to `web/static/`)
- `/api/*` — REST endpoints for settings, conversations, send, plugins
- `/api/logs` — SSE stream from `chatwire.jsonl`
- `/setup` — wizard for first-time config
- `/healthz` — health probe

The web process reads `chat.db` independently (its own SQLite connection) for
conversation history, search, and contact photos. It does **not** relay messages
— the bridge does that.

### Communication between processes

| Channel | Direction | Purpose |
|---|---|---|
| `~/.chatwire/config.json` | Both read | Shared runtime config |
| `~/.chatwire/state/state.json` | Bridge writes | Last-seen ROWID cursor |
| `~/.chatwire/chatwire.jsonl` | Bridge+web write, web reads | Structured log |
| `~/.chatwire/echo_log.db` | Both write | Bridge-echo dedup |
| `~/.chatwire/read_state.db` | Web writes, bridge reads | Conversation read state |
| `~/Library/Messages/chat.db` | Both read | Source of truth (Apple) |

---

## Config format (`~/.chatwire/config.json`)

```jsonc
{
  // Core — bridge reads these on startup via config.py
  "SELF_HANDLES": "+15550001234",       // comma-separated, or a single string
  "POLL_INTERVAL_S": 2,
  "WHITELIST_HANDLES": "+15559876543",  // comma-separated

  // Web
  "WEB_PORT": 8723,
  "WEB_BIND": "127.0.0.1",
  "web": {
    "theme": "dracula",
    "accent_color": "#bd93f9",
    "style": "default",
    "custom_css": "",
    "ntfy_topic": "yourTopic",
    "password_hash": "argon2:...",
    "proxy_headers": false
  },

  // Integrations
  "integrations": {
    "telegram": {
      "enabled": true,
      "bot_token": "...",
      "allowed_user_ids": []
    },
    "webhook": {
      "enabled": false,
      "url": "https://example.com/hook",
      "secret": "",
      "timeout_s": 10
    }
  },

  // Notifications
  "notifications": {
    "notification_depth": {
      "default": "sender",      // "minimal" | "sender" | "preview"
      "my_plugin": "preview"
    }
  }
}
```

The file is chmod 600. The bridge re-reads it on every restart (not hot-reloaded
at runtime). The web server reads it on every relevant API call.

---

## Structured log (`chatwire.jsonl`)

Every log entry is one JSON object per line:

```json
{"ts": "2026-05-10T18:00:00Z", "source": "bridge", "level": "info", "msg": "bridge started"}
```

**Sources** (by convention):

| Source | Emitter |
|---|---|
| `bridge` | bridge.py poll loop, fan-out, startup/shutdown |
| `webhook` | Webhook integration |
| `mcp` | MCP integration |
| `tinfoil` | Tinfoil encryption integration |
| `content_filter` | Content filter |
| `anti_spam` | Anti-spam fuse and rate limiter |
| `contacts` | Contacts sync |
| `<plugin_name>` | Any plugin calling `self.log_info()` |
| `core` | Internal web/API events |

The file auto-rotates to `chatwire.1.jsonl` at 10 MB.

---

## LaunchAgents

Agents are plist files rendered from `templates/launchd/*.plist.template`.
Variables substituted at `chatwire install-agents` time:

| Variable | Default |
|---|---|
| `LABEL_PREFIX` | `dev.chatwire` |
| `INSTALL_DIR` | Path to the repo / venv site-packages |
| `VENV_PYTHON` | Path to venv's `python3.X` binary |
| `LOG_DIR` | `~/Library/Logs/chatwire` |

Agents run as the current user (GUI domain), start on login, and restart
automatically on crash (`KeepAlive: true`).

---

## Plugin sandbox (tier system)

Plugins run inside `SandboxedContext`, which wraps the real `BridgeContextImpl`
and blocks any attribute not explicitly allowed for that tier:

```
BridgeContextImpl
    ↕ SandboxedContext (official tier)
        send_text(conversation_id, body)  # opaque UUID, not raw handle
        send_file(conversation_id, data, mime)
        log_info/warn/error(msg)
        plugin_config                     # isolated config dict
        mirror(event, **fields)           # debug mirror

    ↕ SandboxedContext (notify tier)
        log_info/warn/error(msg)
        plugin_config
        mirror(event, **fields)
```

ConversationMap maps opaque UUIDs ↔ real handles. Only the bridge core holds a
ConversationMap instance — plugins never learn raw phone numbers or emails.
