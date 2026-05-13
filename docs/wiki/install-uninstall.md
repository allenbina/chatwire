# Install & Uninstall

## Install

### Recommended: pipx (python.org Python)

```bash
# Install python.org Python 3.13 first:
# https://www.python.org/downloads/macos/

pipx install --python /Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13 chatwire
chatwire install-agents
```

Using python.org Python ensures that macOS TCC grants (Full Disk Access,
Automation → Messages) apply to the exact binary chatwire runs as.

### Homebrew

```bash
brew install allenbina/homebrew-tap/chatwire
chatwire install-agents
```

### pipx (any Python, simplified)

```bash
pipx install chatwire
chatwire install-agents
```

Note: if your Python is not from python.org, TCC grants may not carry over.
Run `chatwire doctor` to diagnose permission issues.

---

## Required permissions (macOS)

After installing, grant the following in **System Settings → Privacy & Security**:

| Permission | Why |
|---|---|
| **Full Disk Access** | Read `~/Library/Messages/chat.db` |
| **Automation → Messages** | Send messages via AppleScript |
| **Contacts** (optional) | Resolve phone/email → display names |

Grant these to the specific Python binary that chatwire runs as
(shown in `chatwire doctor`).

---

## Launch Agents

`chatwire install-agents` installs three launchd agents in
`~/Library/LaunchAgents/`:

| Label | Role |
|---|---|
| `dev.chatwire.bridge` | iMessage poll loop |
| `dev.chatwire.web` | FastAPI web UI (default port 8723) |
| `dev.chatwire.keepawake` | Prevents macOS sleep during active use |

Agents start on login and restart automatically on crash.

---

## Uninstall

### Simple removal (config preserved)

```bash
chatwire uninstall          # prints pipx/brew instructions
pipx uninstall chatwire     # remove the package
# — or —
brew uninstall chatwire
```

Config and data at `~/.chatwire/` are **not** removed — reinstalling picks up
where you left off.

### Full purge (interactive)

```bash
chatwire uninstall --purge
```

Prompts you for each item:

- `~/.chatwire/config.json` — bridge configuration
- `~/.chatwire/plugins/` — plugin data and private logs
- `~/.chatwire/read_state.db` — conversation read state
- `~/.chatwire/*.jsonl` — structured log files
- LaunchAgents (`dev.chatwire.*`) — background services

Preview without changing anything:

```bash
chatwire uninstall --purge --dry-run
```

### Manual uninstall (what chatwire cannot remove automatically)

```bash
# Stop and remove agents
launchctl bootout gui/$(id -u)/dev.chatwire.bridge
launchctl bootout gui/$(id -u)/dev.chatwire.web
launchctl bootout gui/$(id -u)/dev.chatwire.keepawake
rm ~/Library/LaunchAgents/dev.chatwire.*.plist

# Remove data
rm -rf ~/.chatwire/
rm -rf ~/Library/Logs/chatwire/

# Remove the package
pipx uninstall chatwire
# — or —
brew uninstall chatwire
brew untap allenbina/homebrew-tap   # optional
```

`~/Library/Messages/` is Apple's database — chatwire never writes to it and
cannot remove it.
