# chatwire

Access your iMessages from anywhere — your phone, your laptop, your browser,
wherever you are. A lightweight bridge that runs on your Mac and gives you
a web UI, a Telegram relay, push notifications, and a plugin system for
extending it however you want.

This is the product Apple should have come out with years ago. iMessage is
the best messaging platform out there, but Apple locks it to their devices
and offers no remote access, no API, no way to check your messages when
you're away from your Mac. chatwire fixes that.

> **Status:** beta — actively looking for testers. The author runs this daily
> and it's stable, but you'll be among the first to install it on a fresh
> machine. If you hit a wall, [open an issue](https://github.com/allenbina/chatwire/issues).
> See [`docs/OPEN_SOURCE_PLAN.md`](docs/OPEN_SOURCE_PLAN.md) for the roadmap.

## What it does

- **Inbound.** A lightweight Python service watches `~/Library/Messages/chat.db`,
  resolves senders against Contacts.app, and forwards messages (text, photos,
  videos, attachments) to your configured integrations.
- **Outbound.** Reply from anywhere — your phone, a browser tab, a Telegram
  chat. The service drives Messages.app via AppleScript to send back as you.
- **Group chats.** First-class support. Replies route by chat GUID so group
  conversations stay intact across surfaces.
- **Plugins.** Extend chatwire with notification services (ntfy, Pushover),
  messaging stats, favorites, and more. Plugins get auto-generated settings
  sections in the web UI. [Build your own](docs/OPEN_SOURCE_PLAN.md) or
  install community plugins with `pipx inject`.

## Requirements

iMessage is Mac-only, so the bridge needs a Mac with your Apple ID logged
into Messages.app. macOS requires two permission grants — Full Disk Access
(to read `chat.db`) and Automation→Messages (to send). The setup wizard
walks you through both, but you will click through a couple of system
prompts on first run.

Tested on macOS 12 Monterey. macOS 13-15 should work. Run `chatwire doctor`
to verify your system is ready.

## Install

Recommended path: **pipx**, against python.org's Python.

```bash
# Install python.org Python first if you don't have it:
#   https://www.python.org/downloads/macos/
# (Homebrew Python works but TCC treats it as a different identity —
# you'd have to grant Full Disk Access + Automation to that binary
# specifically. python.org is the well-trodden path.)

# Install pipx if you don't have it (once per machine):
python3 -m pip install --user pipx
python3 -m pipx ensurepath

# Install chatwire from PyPI:
pipx install --python /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
    chatwire

# Wire it up:
chatwire install-agents
chatwire setup
```

The setup wizard walks you through the macOS permission grants (Full Disk
Access + Automation→Messages), identity, contact whitelist, and optional
web UI password. It writes `~/.chatwire/config.json`.

### Alternate install methods

**Homebrew tap.** Convenient if you already use brew.

```bash
brew install allenbina/tap/chatwire
chatwire install-agents
chatwire setup
```

Tap source: <https://github.com/allenbina/homebrew-tap>.

**curl-pipe-bash.** No PyPI access, no Homebrew, just a shell.

```bash
curl -fsSL https://raw.githubusercontent.com/allenbina/chatwire/main/scripts/install.sh | bash
```

Pin to a specific version with `CHATWIRE_REF=v1.1.0`. The script refuses
Xcode CLT's Python stub and warns on Homebrew Python (TCC identity
protection). Same post-install steps (`chatwire install-agents` etc.).

**Developer / git-clone path.** For hacking on the bridge itself:

```bash
git clone https://github.com/allenbina/chatwire.git ~/projects/chatwire
cd ~/projects/chatwire
python3 -m venv .venv
.venv/bin/pip install -e .

# Render and load the launchd agents:
.venv/bin/chatwire install-agents

# Sanity check:
.venv/bin/chatwire doctor
```

The setup wizard writes `~/.chatwire/config.json` (chmod 600) for you.
For manual edits or headless installs, see
[`docs/REFERENCE_INSTALL.md`](docs/REFERENCE_INSTALL.md).

## macOS permissions

Both the FDA grant and the Automation→Messages grant need to be given to the
**python.org Python binary** (not Homebrew's), because the python.org
installer ships two Mach-O binaries with different code-signing identities
that TCC tracks separately. See
[`docs/REFERENCE_INSTALL.md`](docs/REFERENCE_INSTALL.md) section 5 for the
full walkthrough — that section was the reason the bridge worked at all on
the first install, and it's the same on every Mac.

`scripts/check-permissions.sh` (or `chatwire doctor`) will tell you
which prompts you still need to click.

## Web UI access

By default the web UI has no auth — anyone who can reach the URL can read
and send messages. The intended posture is to gate access at the network
layer (Tailscale, LAN-only, Cloudflare Access, etc.).

For setups where the URL leaks past that boundary, the wizard's **Security**
step (or Settings → Web UI password) sets an optional shared password.
It's a single password (not multi-user) stored as a PBKDF2-SHA256 hash in
`~/.chatwire/config.json`; sessions are signed cookies that expire after
30 days. Forgot it? Stop the web agent, edit `config.json` (already
`chmod 600`), drop the `web.auth` block, restart.

## Privacy

**Zero telemetry. Period.** chatwire collects no analytics, sends no usage
data, phones home to nobody, and includes no third-party SDKs that report
back. You run this on your own hardware and your data stays on your hardware.
Your messages, contacts, and `chat.db` never leave your Mac — outbound
traffic only goes to integrations you explicitly configure (your Telegram
bot, your ntfy server, etc.).

Two narrow third-party requests the web UI makes, neither carrying any of
your data:

- An update-check fetches `api.github.com/repos/<repo>/releases/latest`
  once a day to surface new-version notices. Disable by setting
  `UPDATE_CHECK_REPO=""` in the launchd agent's environment.
- Static assets (htmx, emoji-picker-element) load from `unpkg.com` and
  `cdn.jsdelivr.net`.

## Repo layout

```
bridge.py             message relay loop + integration dispatcher
chat_db.py            reads chat.db, HEIC -> JPEG via sips
chat_send.py          osascript wrappers (send_text, send_file)
config.py             config.json loader
chatwire_cli.py       CLI: setup / install-agents / doctor / logs / migrate
contacts.py           Contacts.app -> handle/name lookup
echo_log.py           cross-process echo dedup
whitelist.py          runtime-mutable contact allowlist
_version.py           semver source of truth
integrations/         built-in plugins (web, webhook, stats, favorites)
web/                  FastAPI web UI + setup wizard + plugin settings
migrations/           config-schema migration runner
templates/launchd/    plist templates rendered by install-agents
scripts/              install.sh, chatwire-loop.sh (dev automation)
docs/                 OPEN_SOURCE_PLAN.md, REFERENCE_INSTALL.md, HANDOFF.md
```

## Trademarks

iMessage, Messages, macOS, and AppleScript are trademarks of Apple Inc.,
referenced here in their descriptive sense — this project relays to and
from Apple's iMessage service. **chatwire is not affiliated with,
endorsed by, or sponsored by Apple Inc.**

## License

MIT — see [`LICENSE`](LICENSE). Copy it, fork it, put your thang down, flip
it, and reverse it. Just follow the MIT requirements and give credit to the
original project.

## Contributing

Pull requests are welcome. Whether it's a bug fix, a new feature, or a whole
plugin — get involved. Check the [plugin system docs](docs/OPEN_SOURCE_PLAN.md)
if you want to build an integration, or browse the
[open issues](https://github.com/allenbina/chatwire/issues) to find something
to pick up.

**Looking for beta testers.** If you have a Mac with iMessage and want to
try chatwire, [open an issue](https://github.com/allenbina/chatwire/issues)
with your setup details and we'll get you running.

## Sponsors

If chatwire is useful to you, consider
[sponsoring the project](https://github.com/sponsors/allenbina).
