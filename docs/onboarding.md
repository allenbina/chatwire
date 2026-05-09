# chatwire — Onboarding Guide

> A complete installation and setup walkthrough for chatwire on macOS.
> Screenshot placeholders mark every step; Allen will replace them with
> actual captures during a fresh install session.

---

## Prerequisites

Before you begin:

- **macOS 12 Monterey or later** (Ventura or Sonoma recommended).
- **Python 3.10+** from [python.org](https://www.python.org/downloads/macos/)
  — the official python.org *framework* installer is required so that macOS
  TCC grants (Full Disk Access, Automation) stick to the right binary.
  Homebrew Python works too, but you'll see a warning and may need to
  re-grant permissions.
- **pipx** — for isolated package installation:
  ```
  pip install pipx
  pipx ensurepath
  ```
  Or via Homebrew: `brew install pipx && pipx ensurepath`.
- **Messages.app** signed in with your Apple ID and with at least one
  conversation. The bridge reads `~/Library/Messages/chat.db`; if Messages
  has never been used on this Mac, sign in first.

![Step 0: Prerequisites checklist](img/onboarding-0.png)

---

## Step 1 — Run `chatwire doctor`

After installation (see Step 2), run the pre-flight checker any time to
confirm your system is ready:

```
chatwire doctor
```

It checks:

| Check | Critical? | What it verifies |
|---|---|---|
| macOS | — | Platform detection |
| Python | warn | Version ≥ 3.10 |
| Full Disk Access | **yes** | Can read `chat.db` |
| Automation → Messages | **yes** | Can send via AppleScript |
| pipx | warn | Needed for plugin installs |
| sips | warn | macOS image tool for thumbnails |
| config.json | warn | Exists and has mode 600 |
| Agent plists | warn | Each of bridge / web / keepawake |
| Loaded agents | warn | Each label in `launchctl list` |

A green `✓` on all critical checks means the bridge can function.
A red `✗` on Full Disk Access or Automation → Messages means the bridge
will start but can't read or send messages.

> **Run `doctor` before filing a bug** — it surfaces 90% of setup issues.

![Step 1: chatwire doctor all-green output](img/onboarding-1.png)

---

## Step 2 — Install chatwire via pipx

```
pipx install chatwire
```

This creates an isolated virtualenv, installs chatwire and all its
dependencies, and drops the `chatwire` and `chatwire-toolbar` console
scripts onto your PATH (via `~/.local/bin`).

To install a specific version:

```
pipx install chatwire==1.5.0
```

To upgrade later:

```
pipx upgrade chatwire
```

> **python.org Python tip**: If you see a warning about a non-framework
> Python, reinstall with the explicit interpreter path:
> ```
> pipx install --python \
>   /Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13 \
>   chatwire
> ```

![Step 2: pipx install chatwire terminal output](img/onboarding-2.png)

---

## Step 3 — Install launchd agents

chatwire runs as three background services managed by launchd:

| Agent label | What it does |
|---|---|
| `dev.chatwire.bridge` | Polls `chat.db`, relays to integrations |
| `dev.chatwire.web` | Serves the web UI on port 8723 |
| `dev.chatwire.keepawake` | Prevents the Mac from sleeping |

Install and start all three:

```
chatwire install-agents
```

The command renders plist templates, writes them to
`~/Library/LaunchAgents/`, and calls `launchctl load -w` on each.

Verify they loaded:

```
chatwire doctor
```

All three agent rows should show `✓`.

> Logs live at `~/Library/Logs/chatwire/`. Tail them with:
> ```
> chatwire logs -f
> ```

![Step 3: install-agents output and doctor confirming agents loaded](img/onboarding-3.png)

---

## Step 4 — Run the setup wizard

Open the web wizard:

```
chatwire setup
```

This prints (and opens) `http://127.0.0.1:8723/setup`.
The wizard has four steps — the sidebar on the left shows your progress.

### Step 4a — Permissions

The bridge needs two macOS privacy grants. The wizard shows the current
status of each and provides "Open Settings" buttons that deep-link to the
right pane in System Settings.

**Full Disk Access** — required to read `~/Library/Messages/chat.db`:

1. Click **Open Settings** next to *Full Disk Access*.
2. In System Settings → Privacy & Security → Full Disk Access, unlock
   the pane (padlock icon, bottom-left) and toggle on the Python entry.
3. Return to the wizard and click **Refresh all** (or wait — the page
   auto-polls every 30 seconds).

**Automation → Messages** — required to send messages via AppleScript:

1. Click **Open Settings** next to *Automation → Messages*.
2. Find Python in the list. Expand it and enable **Messages**.
3. Return and refresh.

Both rows must show `✓` before the **Next →** button activates.

> If you don't see Python in the Automation list, trigger it: open
> Script Editor, run `tell application "Messages" to get every service`,
> and macOS will prompt for the grant.

![Step 4a: Wizard permissions step — both checks green](img/onboarding-4a.png)

### Step 4b — Identity

Pick which iMessage handles are *you*. The bridge auto-detects handles
from `chat.db` (phone numbers and Apple IDs). Check all that apply.

If your handle isn't listed (uncommon on a freshly-signed-in account),
type it in the **Add another handle** field: `+15551234567` or
`you@icloud.com`.

Click **Save and continue →**.

![Step 4b: Wizard identity step with handles checked](img/onboarding-4b.png)

### Step 4c — Whitelist

Pick which contacts' messages should be relayed. Anyone not on the
whitelist is ignored — their messages stay in Messages.app on this Mac
and never reach the web UI or any integration.

Add contacts by phone number or Apple ID. You can add, remove, and
reorder them later from **Settings → Whitelist** in the main UI.

Click **Continue →**.

![Step 4c: Wizard whitelist step with a few contacts added](img/onboarding-4c.png)

### Step 4d — Security (optional)

Protect the web UI behind a password (6+ characters). Without one,
anyone on your LAN — or anyone who reaches this URL via Tailscale,
Cloudflare Access, etc. — can read and send messages.

Leave the field blank to skip. You can add or change the password later
in **Settings → Security**.

The hash is stored as PBKDF2-SHA256 in `~/.chatwire/config.json`
(mode 600). Forgot it? Edit that file and remove the `web.auth` block,
then restart the web agent.

Click **Save and continue →** (or just **Continue →** if skipping).

![Step 4d: Wizard security step with password field](img/onboarding-4d.png)

### Wizard complete

The final screen shows the restart commands. Run them in a terminal:

```
launchctl kickstart -k gui/$(id -u)/dev.chatwire.bridge
launchctl kickstart -k gui/$(id -u)/dev.chatwire.web
```

Then click **Open the bridge →**.

![Step 4e: Wizard done screen](img/onboarding-4e.png)

---

## Step 5 — First login

Navigate to [http://localhost:8723](http://localhost:8723).

If you set a password in Step 4d, you'll see a login screen. Enter the
password you chose.

Once logged in, the conversation list on the left populates as the bridge
syncs your recent messages. Initial sync may take 30–60 seconds depending
on the size of `chat.db`.

![Step 5: Login screen (if password set)](img/onboarding-5.png)

---

## Step 6 — Send your first message

1. Click a conversation in the left panel to open it.
2. Type in the message field at the bottom.
3. Press **Return** or click **Send**.

The bridge hands the message to Messages.app via AppleScript. The message
appears in Messages.app on this Mac and is delivered like any normal
iMessage or SMS.

> **Reactions**: tap the thumbs-up / heart / etc. icons on any message
> bubble to send a tapback reaction.

> **Photos**: click the attachment clip icon to pick an image. Thumbnails
> are generated by the macOS `sips` tool.

![Step 6: First message sent in the web UI](img/onboarding-6.png)

---

## Step 7 — Install a plugin

chatwire's plugin system lets you add integrations without touching the
core package. Plugins are injected into chatwire's pipx virtualenv:

```
pipx inject chatwire chatwire-ntfy
```

Plugins are discovered automatically at startup — no config file edit
needed to activate the package. After injecting, restart the bridge:

```
launchctl kickstart -k gui/$(id -u)/dev.chatwire.bridge
```

**Available plugins** (as of v1.5.0):

| Package | What it adds |
|---|---|
| `chatwire-ntfy` | Push notifications via ntfy.sh |
| `chatwire-telegram` | Relay messages to/from a Telegram bot |
| `chatwire-xmpp` | XMPP / Jabber relay |
| `chatwire-ha` | Home Assistant entity commands |

To remove a plugin:

```
pipx uninject chatwire chatwire-ntfy
```

![Step 7: pipx inject chatwire chatwire-ntfy terminal output](img/onboarding-7.png)

---

## Step 8 — Configure a plugin in Settings

1. Open [http://localhost:8723](http://localhost:8723) and click the
   **Settings** gear icon (bottom-left of the sidebar).
2. Scroll to the **Plugins** section. Installed plugins appear as
   collapsible cards.
3. Fill in the plugin-specific fields (e.g., ntfy topic URL, Telegram bot
   token) and click **Save**.

Plugin configuration is stored in `~/.chatwire/config.json` (mode 600).

> Each plugin has its own documentation in `docs/plugins/` (built-in
> plugins) or the plugin repository's `README.md`.

![Step 8: Settings page with a plugin card expanded](img/onboarding-8.png)

---

## Step 9 — Mobile PWA (add to Home Screen)

chatwire's web UI is a Progressive Web App. On iOS or Android, you can
add it to your Home Screen for a near-native experience:

**iOS / Safari**:

1. Open `http://<your-mac-ip>:8723` in Safari on your iPhone or iPad.
   (Your Mac and phone must be on the same Wi-Fi, or you must have
   Tailscale / VPN configured.)
2. Tap the **Share** button (box with arrow pointing up).
3. Tap **Add to Home Screen**.
4. Name it "iMessage" or "chatwire" and tap **Add**.

The icon appears on your Home Screen. Opening it launches a full-screen
web UI with no browser chrome.

**Android / Chrome**:

1. Open the URL in Chrome.
2. Tap the three-dot menu → **Add to Home screen**.
3. Confirm the name and tap **Add**.

> The service worker caches the app shell so the UI loads even on a slow
> connection. Messages still require the Mac to be reachable.

![Step 9: iOS Add to Home Screen dialog](img/onboarding-9.png)

---

## What's next

- **Logs**: `chatwire logs -f` — streams both bridge and web logs.
- **Health check**: `curl localhost:8723/healthz` — returns `ok` when
  the web agent is up.
- **Doctor**: run `chatwire doctor` any time to re-check permissions and
  service state.
- **Plugin docs**: see `docs/plugins/` for built-in plugin guides, or
  each plugin's own `README.md`.
- **Uninstall**: `chatwire uninstall --dry-run` to preview, then
  `chatwire uninstall` to remove everything.

---

## Troubleshooting

### Bridge starts but no messages appear

Run `chatwire doctor`. Check:
- Full Disk Access — must be `✓`.
- Automation → Messages — must be `✓`.
- If the grants were added recently, restart the bridge agent:
  `launchctl kickstart -k gui/$(id -u)/dev.chatwire.bridge`.

### Messages send from the web UI but don't arrive

- Confirm Messages.app is signed in on this Mac and not in Do Not Disturb.
- The bridge uses AppleScript; if Messages.app is force-quit or
  unresponsive, restart it.

### Web UI doesn't load

- Check the web agent is running: `launchctl list | grep chatwire`.
- Tail logs: `chatwire logs --service web -f`.
- Try a curl health check: `curl localhost:8723/healthz`.

### `chatwire: command not found`

- Run `pipx ensurepath` and restart your shell, or add
  `~/.local/bin` to your `PATH`.

### Wrong Python warning

See the python.org tip in Step 2. The warning message includes the exact
`pipx install --python ...` command to use.
