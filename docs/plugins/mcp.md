# MCP Server

## What it does

The MCP (Model Context Protocol) integration exposes chatwire as a set of tools that LLM agents — such as Claude Code — can call to send iMessages, read conversation history, list active conversations, and search messages. The transport is stdio: you start the MCP server with `chatwire mcp` and point your MCP client at it. All outbound sends go through chatwire's existing anti-spam guardrails (rate limiting and broadcast detection), so the LLM cannot be used as a spam vector.

Four tools are available: `send_message`, `read_messages`, `list_conversations`, and `search_messages`.

## Install command

MCP ships with chatwire. No additional package is required. However the `mcp` Python package must be present:

```bash
# Inside the chatwire venv (pipx users):
~/.local/pipx/venvs/chatwire/bin/python -m pip install mcp

# Or if using a regular venv:
pip install mcp
```

Then enable the integration in Settings and start the server:

```bash
chatwire mcp
```

## Configuration walkthrough

1. Open chatwire → **Settings** → **Plugins** → **MCP Server**.
2. Toggle **Enabled** to ON. This registers the integration with the bridge and makes the enabled state visible in the UI.
3. Start the MCP stdio server in a terminal:
   ```bash
   chatwire mcp
   ```
4. Configure your MCP client (e.g., Claude Code) to connect to the process.

### Claude Code setup

Add chatwire to Claude Code's MCP config (`~/.claude/mcp_servers.json` or via `claude mcp add`):

```json
{
  "mcpServers": {
    "chatwire": {
      "command": "chatwire",
      "args": ["mcp"]
    }
  }
}
```

Or using the CLI:
```bash
claude mcp add chatwire -- chatwire mcp
```

Restart Claude Code. The `send_message`, `read_messages`, `list_conversations`, and `search_messages` tools will appear in the tool list.

## Usage guide

### Available tools

#### `send_message`

Send an iMessage to a contact.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `handle` | string | yes | Phone number (E.164) or email, e.g. `+15551234567` |
| `text` | string | yes | Message text to send |

Returns `{status, hint, service}` on success, or an error dict with `error` and `detail` on failure.

Rate limits and broadcast detection apply. If the guardrail fires, you'll receive `{error: "rate_limited"}` or `{error: "broadcast_blocked"}`.

#### `read_messages`

Read recent messages for a 1:1 conversation.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `handle` | string | yes | — | Contact handle |
| `since` | integer | no | `0` | Return only messages with ROWID > since (for pagination) |
| `limit` | integer | no | `50` | Maximum number of messages |

Returns `{handle, messages: [...], has_more}`.

#### `list_conversations`

List active conversations with last-message preview.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `limit` | integer | no | `20` | Maximum number of conversations |

Returns `{conversations: [{handle, name, last_text, last_ts, unread_count}]}`.

#### `search_messages`

Full-text search across all messages using SQL LIKE (up to 100 results, newest first).

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | string | yes | — | Search string |
| `handle` | string | no | `""` | Restrict results to this contact |

Returns `{query, results: [{rowid, date, from_me, text, handle}]}`.

## Settings reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `false` | Show the integration in the settings UI. Does not start the server — run `chatwire mcp` separately. |

Config file: `~/.chatwire/config.json` under `integrations.mcp`.

```json
{
  "integrations": {
    "mcp": {
      "enabled": true
    }
  }
}
```

## Troubleshooting / FAQ

**`ImportError: No module named 'mcp'`**
The `mcp` package is not installed in the chatwire environment. Run:
```bash
~/.local/pipx/venvs/chatwire/bin/python -m pip install mcp
```

**Claude Code doesn't see the chatwire tools.**
Confirm the MCP server process is running (`chatwire mcp` in a terminal) and that the `mcp_servers.json` path to the `chatwire` command is correct. Run `which chatwire` to verify the binary is on your PATH.

**`send_message` returns `{error: "rate_limited"}`.**
chatwire's anti-spam guardrails are throttling outbound sends. Wait a moment and try again. If you're testing, send to a single handle — sending identical text to many handles triggers broadcast detection.

**Messages returned by `read_messages` are truncated.**
Increase `limit` (max is not capped in the tool, but very large values will be slow). Use `since` to paginate: pass the `rowid` of the last message you received as the next call's `since` value.

**The stdio server exits immediately.**
Check that the chatwire bridge is running (`chatwire status` or Settings → Advanced → Service status). The MCP tools import from `web.main` and `chat_send`, which require the bridge to be started for send operations. Read-only tools (`read_messages`, `list_conversations`, `search_messages`) work without the bridge.
