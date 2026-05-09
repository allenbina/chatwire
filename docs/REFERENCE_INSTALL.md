# Reference install — worked example

> This is the original author's literal install. Personal identifiers are
> kept as `<placeholders>` so this doc is safe to read without leaking
> contact info, but the *shape* of the install is unchanged. New users
> should follow the [README](../README.md) quickstart, which uses the same
> approach with `chatwire install-agents` instead of the hand-rolled
> commands below.

Personal bridge: iMessage (via a macOS relay) ↔ Telegram bot. POC scope.

- **Phase A:** only relays iMessages from `SELF_HANDLES` (your own Apple ID) — closed loop for testing.
- **Phase B:** add `WHITELIST_HANDLES` to relay specific contacts.

## Deployment specifics (this install)

| | |
| --- | --- |
| Relay host | `<your-mac>.local` (LAN: `<lan-ip>`) |
| Hardware | MacBook Air 13" 2017, 8 GB RAM, Intel x86_64 |
| OS | macOS 12.7.6 (Monterey) |
| Mac user | `<user>` |
| SSH alias from dev box | `<host-alias>` |
| GitHub repo | `<owner>/imessage-tg-bridge` (private during bring-up) |
| Telegram bot | `@<your_bridge_bot>` |
| Telegram user (allowlist) | numeric Telegram user ID from `@userinfobot` |
| iMessage handles (`SELF_HANDLES`) | your phone + Apple ID emails, comma-separated |
| Default outgoing iMessage identity | one of the SELF_HANDLES |
| Python on Mac | `/usr/local/bin/python3` (Intel Homebrew path) |
| Repo clone target on Mac | `/Users/<user>/projects/imessage-tg-bridge` |
| State + secrets dir on Mac | `~/.chatwire/` (`config.json` chmod 600). Legacy: `~/.imessage-tg/.env`. |
| Logs on Mac | `~/Library/Logs/chatwire/` |

## Layout

```
bridge.py              telegram app + outbound (TG -> iMessage)
chat_db.py             reads ~/Library/Messages/chat.db, HEIC->JPEG via sips
chat_send.py       osascript wrappers (send_text, send_file)
prefix.py              "From <name> (<handle>): ..." formatter + reply parser
pyproject.toml         dep manifest + entry point + package metadata
.env.example           template for ~/.imessage-tg/.env
&lt;label-prefix&gt;.bridge.plist   launchd user agent (with caffeinate wrapper)
```

## Mac setup

### 1. SSH from the dev box (Windows) — already done

Mac side: `System Preferences -> Sharing -> Remote Login: ON` (restrict to user `allen`).

Windows side, `~/.ssh/config`:

```
Host &lt;your-mac&gt;
  HostName &lt;mac-lan-ip&gt;
  User allen
```

Connect: `ssh &lt;your-mac&gt;`. Public key (`~/.ssh/id_ed25519.pub` on Windows) is in `~/.ssh/authorized_keys` on the Mac.

Optional: install Tailscale on the Mac for off-LAN reach without port-forwarding.

### 2. Clone (private repo via deploy key) + Python

Because the repo is private and the launchd agent runs non-interactively, use a per-host SSH deploy key (read-only, scoped to this repo).

On the Mac:

```bash
ssh-keygen -t ed25519 -N "" -C "&lt;host&gt;-chat-bridge-deploy" -f ~/.ssh/id_ed25519_imessage-tg
cat >> ~/.ssh/config << 'EOF'

Host github.com-imessage-tg
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_ed25519_imessage-tg
  IdentitiesOnly yes
EOF
ssh-keyscan -t ed25519 github.com >> ~/.ssh/known_hosts
cat ~/.ssh/id_ed25519_imessage-tg.pub
```

From the dev box (or GitHub UI), add that public key as a **deploy key** on the repo (read-only):

```bash
gh repo deploy-key add ~/.ssh/id_ed25519_imessage-tg.pub --repo &lt;owner&gt;/imessage-tg-bridge --title "&lt;host&gt;-chat-bridge"
```

Clone + venv. This install uses **Python 3.14** (already present at `/usr/local/bin/python3` from the python.org installer). `bridge.py` includes a small shim for the Python 3.14 `asyncio.get_event_loop()` change so `python-telegram-bot 21.x` works — no need for an extra Python install.

```bash
mkdir -p ~/projects && cd ~/projects
git clone git@github.com-imessage-tg:&lt;owner&gt;/imessage-tg-bridge.git
cd imessage-tg-bridge
/usr/local/bin/python3 -m venv .venv
.venv/bin/pip install -e .
```

FDA note: Full Disk Access is granted per binary. On this install it's already granted to `/usr/local/bin/python3`. The venv's `.venv/bin/python` symlinks back to the same framework binary, so FDA inherits — confirmed by the smoke test in step 5.

### 3. Bot creation

1. In Telegram, message `@BotFather`, `/newbot`, name like `<you>-chat-bridge-bot`. Save token.
2. Message `@userinfobot` from your own Telegram account; copy the numeric user ID.

### 4. Secrets

```bash
mkdir -p ~/.imessage-tg
cp .env.example ~/.imessage-tg/.env
chmod 600 ~/.imessage-tg/.env
# Fill in TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_IDS, SELF_HANDLES.
```

For Phase A `SELF_HANDLES`: include both forms iMessage might use for you, e.g.
`+15551234567,you@icloud.com`. Lowercase, comma-separated.

### 5. macOS permissions

#### Full Disk Access (needed to read `chat.db`)

**Gotcha:** python.org's installer ships **two** Mach-O binaries with different code-signing identities, and TCC grants are per-identity. Launchd-spawned python can exec through either. Add **both**:

1. `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14` (identity `python3`)
2. `/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app` (identity `org.python.python` — whole bundle)

How:

- **System Preferences → Security & Privacy → Privacy → Full Disk Access**
- Click the lock, unlock.
- Click `+`, press `⌘⇧G`, paste each path above, add it. Enable the checkbox.
- Restart the launchd agent afterward.

Why both: when invoked over SSH, TCC sees the `bin/python3.14` binary's identity (`python3`). When invoked from launchd, Python sometimes re-exec's itself through `Python.app` (the `org.python.python` identity) for Dock/GUI reasons. If only one is granted FDA, the launchd path fails with `sqlite3.OperationalError: unable to open database file`.

Verify with: `codesign -dv /path/to/binary 2>&1 | grep Identifier`

**Diagnostic script:** `bash scripts/check-permissions.sh` runs on the Mac, queries `TCC.db` (no sudo), smoke-tests chat.db read + Messages Automation, and prints an actionable checklist. Run this any time the bridge stops working after a macOS update or permission change. It cannot *grant* permissions — macOS 12+ forbids that via CLI — but it tells you exactly what to click in System Preferences.

#### Automation → Messages (needed to send iMessages)

The first time the launchd-spawned bridge tries to reach Messages.app (either to send, or just `check-permissions.sh`'s `tell application "Messages" to count of services` probe), macOS pops a dialog on the Mac screen:

> "python" wants to use "Messages."

Click **Allow**. This stays granted from then on and appears in System Preferences → Privacy → Automation under python → Messages.

**Important:** Because TCC tracks the *responsible* process per launch context, the Automation grant from an interactive SSH session does **not** automatically cover the launchd-spawned process. If you previously allowed Automation while testing from Terminal/SSH, launchd's first attempt will still re-prompt. Approve again.

To pre-grant (not usually needed — let the prompt happen):

- **System Preferences → Security & Privacy → Privacy → Automation**
- Find the python entry, check the **Messages** box under it.

After granting, restart the service (`launchctl unload && launchctl load -w ...`).

**This install:** Automation → Messages approved 2026-04-14 after the first launchd start.

### 6. Keep the Mac awake

Run once on the Mac (sudo, requires interactive password):

```bash
sudo pmset -a sleep 0 disksleep 0 disablesleep 1 displaysleep 10
sudo pmset -a powernap 1 autorestart 1 womp 1
pmset -g
```

What each flag does:

| Flag | Effect |
| --- | --- |
| `sleep 0` | Disable idle system sleep |
| `disksleep 0` | Disable spin-down of internal storage |
| `disablesleep 1` | Disable lid-close sleep (no external display required for this Air) |
| `displaysleep 10` | Allow the screen to turn off after 10 min (saves power, harmless) |
| `powernap 1` | Periodic wake for system maintenance |
| `autorestart 1` | Auto-reboot after power loss |
| `womp 1` | Wake on network (Intel only; harmless on Apple Silicon) |

Also enable **System Preferences -> Users & Groups -> Login Options -> automatic login** so the agent restarts unattended after a power blip. (Incompatible with FileVault — pick one.)

The plist wraps the service in `caffeinate -dimsu`, which holds power-management assertions while the bridge process is alive — belt-and-suspenders if `pmset` settings ever drift.

Practical: always on AC; keep the lid open in cool airflow if you can.

**This install:** pmset bundle applied 2026-04-14.

**Dedicated keep-awake agent:** install `&lt;label-prefix&gt;.keepawake.plist` as a second launchd user agent. It runs `caffeinate -dims` standalone, which holds `PreventUserIdleSystemSleep`, `PreventUserIdleDisplaySleep`, and `PreventSystemSleep` for its lifetime.

```bash
cp &lt;label-prefix&gt;.keepawake.plist ~/Library/LaunchAgents/
launchctl load -w ~/Library/LaunchAgents/&lt;label-prefix&gt;.keepawake.plist
pmset -g assertions | grep caffeinate   # should show the three assertions
```

**Why a separate agent instead of wrapping the bridge in caffeinate?** We tried that first. It breaks the bridge: when launchd runs `caffeinate … python bridge.py`, TCC treats `caffeinate` as the responsible process, and caffeinate has no FDA, so `chat.db` opens fail with "unable to open database file". Splitting keep-awake into its own agent sidesteps that — the bridge agent runs python directly, TCC sees python as responsible, FDA works.

Ad-hoc keep-awake over SSH (if both agents are down): `nohup caffeinate -dims > /dev/null 2>&1 &` then `disown`. Kill later with `pkill -f 'caffeinate -dims'`.

### 7. Install + start the launchd agent

```bash
mkdir -p ~/Library/Logs/imessage-tg
# Edit the plist if your python path differs from /usr/local/bin/python3.
cp &lt;label-prefix&gt;.bridge.plist ~/Library/LaunchAgents/
launchctl load -w ~/Library/LaunchAgents/&lt;label-prefix&gt;.bridge.plist
launchctl list | grep imessage-tg
tail -f ~/Library/Logs/imessage-tg/stderr.log
```

`bridge.py` loads `~/.imessage-tg/.env` at import time (chmod 600), so no
secrets need to live in the world-readable plist.

## Phase A verification

1. iMessage yourself "phase A test 1" from your iPhone -> arrives in the bot DM as `From <handle>: phase A test 1`.
2. In Telegram, reply to that message with "phase A test 2" -> appears on your iPhone Messages.
3. (Or use `/send +15551234567 phase A test 3`.)
4. Send a photo iPhone -> self -> bot DM receives `send_photo` (HEIC auto-converted to JPEG).
5. Send a photo in Telegram (reply-to a relayed inbound) -> Messages.app sends it.
6. `tail ~/Library/Logs/imessage-tg/stderr.log` should be quiet.

## Commands

| Command | What |
| --- | --- |
| `/start` | Sanity check, prints help. |
| `/whoami` | Your TG user ID + chat ID. |
| `/handles` | Show current SELF + WHITELIST handles. |
| `/refresh_contacts` | Reload the AddressBook → display-name lookup (use after editing Contacts.app). |
| `/send <handle> <body>` | Explicit outbound send. |
| `/mute <duration>` | Stop relaying inbound for a window. e.g. `/mute 1h`, `/mute 30m`, `/mute 2d`. Default `1h` if no arg. |
| `/unmute` | Resume relaying immediately. |
| (reply to a relayed inbound) | Sends back to that contact (no `/send` needed). |
| (photo + caption with reply or `/send`) | Outbound photo. |

## CLI observer (debug mirror)

Set `DEBUG_MIRROR_FILE=~/.imessage-tg/mirror.jsonl` in `~/.imessage-tg/.env` and restart the agent. Every relayed inbound and successful outbound gets one JSONL line:

```json
{"t":"2026-04-14T19:12:14","event":"inbound","handle":"you@example.com","is_from_me":true,"text":"Emoji movie","attachments":[]}
{"t":"2026-04-14T19:14:02","event":"outbound","kind":"text","handle":"+1XXXXXXXXXX","text":"hi back"}
```

Tail from anywhere the box is reachable:

```bash
ssh &lt;your-mac&gt; 'tail -F ~/.imessage-tg/mirror.jsonl | jq .'
```

Doesn't touch Telegram's poller — safe to tail concurrently with normal operation. Rotate/truncate manually (`> mirror.jsonl`) when it gets big.

## Deferred / future ideas

Real things still on the list:

- **Security split (Mac-local API + cluster-hosted bot/web).** Shrink the Mac side to a small local-only HTTP API (~150–300 lines, the only thing with FDA + Automation), move the Telegram bot and web UI into containers on plinux/k3s. Bot/web call the Mac over Tailscale with a bearer token. Real isolation requires the off-Mac hop OR running the unprivileged side under a different Python binary that doesn't have FDA — the OS checks per-binary, not per-process. Designed but not started; ~1 day for the on-laptop split (steps 1–3), separate evening for the second-Python or cross-host isolation (step 4). User chose to defer until plinux/k3s is more stable.
- **Firefox-compatible video playback on the web.** Status 2026-04-15: static ffmpeg 8.1 from https://evermeet.cx/ffmpeg/ is installed at `/usr/local/bin/ffmpeg` (quarantine cleared). `web/main.py` has the transcode path wired (`_mov_to_mp4` — `-c copy` for H.264, `libx264 -crf 23 -preset veryfast -pix_fmt yuv420p` for HEVC, atomic rename via `.tmp`) but `/attachment` currently bypasses it after a 500 incident; Chrome works because it accepts the .mov relabeled as `video/mp4`. To resume: re-wire `/attachment` to call `_mov_to_mp4` for HEVC sources, smoke-test in Firefox, watch `~/Library/Logs/imessage-tg/web-stderr.log`. Transcode is CPU-heavy on a 2017 Air (~25s per 95s clip); result is cached in the Attachments dir as `*.served.mp4`.
- **Group chats.** Currently the bridge only knows about handles, not conversations. Messages from whitelisted contacts in group chats *will* relay (because the sender's handle matches), but you can't tell it's a group and replying lands as a 1:1 message back to the sender, NOT to the whole group. To do this properly: join the `chat` table in `chat_db.py`, track `chat_id` per relayed message, render `From <sender> in [<group>]:`, and on outbound use AppleScript's `send to text chat <chat>` to target the group. Few hours, deferred until you actually use group chats through the bridge.
- **Topics layout (Telegram).** Per-contact Telegram topics if the single-chat firehose gets noisy. The dynamic `/<contact>` slash commands plus the web UI cover most of what topics would.

Decided NOT to pursue:

- **iOS threaded replies (outbound).** macOS 12 AppleScript's Messages dictionary doesn't expose threaded sends. Would need private APIs or direct chat.db writes. Wait for a newer Mac — same story for iMessage reactions.
- **Mobile web push.** Telegram already gives always-on phone push; the web UI's mobile notification story doesn't earn its complexity. The desktop push backend would still work for Android if needed (only need to add a PWA manifest + install prompt on the frontend).
- **Reactions, read receipts.** Same general bucket as outbound threaded replies — macOS 12 AppleScript can't drive them. Defer to newer Mac.
- **Power-outage auto-recovery.** `pmset -a autorestart 1` covers AC flicker, but MacBook Air laptops can't firmware-auto-power-on after a full battery drain (Mac mini / iMac feature). Mitigation: keep on AC always (battery is a natural UPS for short blips). Permanent fix: move the relay role to a Mac mini.

Already shipped (kept as a record so we don't re-plan):

- Web frontend with avatars, multi-handle merging, inline attachments, contact-aware sidebar
- Display names from Contacts.app (AddressBook-v22.abcddb, joined across multiple sources)
- iOS threaded replies (inbound) — quoted snippet + Telegram `reply_to_message_id`
- Cloudflare tunnel + Access (`messages.&lt;your-domain&gt;`, locked to two emails)
- Web push notifications (desktop, VAPID, service worker, mirror-tail fan-out)
- CLI observer (mirror.jsonl) — every relay event as a JSONL line, tailable from anywhere
- Runtime whitelist add/remove from Telegram (`/whitelist`, `/whitelist_add`, `/whitelist_remove`) and the web settings panel — both accept a contact name or a raw handle
- Contact-name autocomplete on the whitelist add input: web uses a native `<datalist>` sourced from Contacts.app (instant typeahead, substring match); Telegram uses inline mode (`@&lt;your_bridge_bot&gt; <query>`) to filter and prefill `/whitelist_add <Name>`

## Phase B: adding people to the whitelist

The bridge filters by **handle**, not by Contacts entry. A "handle" is whatever iMessage uses to identify a sender: a phone number in E.164 format (`+15551234567`) or an email (Apple ID email like `alice@icloud.com`). One person can have many handles, and iMessage records whichever one they happened to send from on a given message.

### To whitelist someone

The whitelist is a runtime-mutable file at `~/.imessage-tg/whitelist.json`. First-time deploys seed it from `WHITELIST_HANDLES` in `.env`; after that the file is the source of truth and env is only consulted when the file is missing. Both the bridge and the web read through `whitelist.py` with mtime-based caching, so changes apply within a couple of seconds — no reload needed.

**From Telegram** (preferred):

```
/whitelist                  ← list current whitelist
/whitelist_add Alice        ← if Alice is in Contacts, adds all her handles
/whitelist_add +14155550100 ← raw handle works too
/whitelist_remove Alice     ← name or handle
```

The contact-name form is the easy path — it expands to every handle Contacts.app knows for that person, so you don't have to chase down each phone/email separately.

**Telegram inline typeahead:** instead of typing a name from scratch, type `@&lt;your_bridge_bot&gt; <query>` in any chat (e.g. DM the bot, or use the Saved Messages chat). A popup shows up to 30 matching contacts with `✓ already on whitelist` markers; picking one drops `/whitelist_add <Name>` into the input, press send to confirm. Requires inline mode enabled on the bot in BotFather (`/mybots` → bot → Bot Settings → Inline Mode).

**From the web UI:** click the ⚙ gear in the sidebar header → settings page has an add form (handle or name — with browser-native autocomplete against your Contacts names) and remove buttons on each row.

**From the file directly** (rare, e.g. bulk import): edit `~/.imessage-tg/whitelist.json`:

```json
{
  "handles": [
    "+14155550100",
    "alice@icloud.com",
    "alice@gmail.com"
  ]
}
```

Both processes pick it up on the next read (mtime change). No agent reload needed.

### What "Contacts" does and doesn't do

- **Doesn't** affect what gets relayed. The bridge never looks at Contacts.app — only at the raw handle on each iMessage row.
- **Does** affect display names. iMessage internally resolves a handle to a Contacts entry to show "Alice" instead of "+14155550100" in Messages.app. The bridge currently uses the handle itself as the prefix (`From +14155550100:`). A future enhancement could query Contacts via AppleScript to swap in display names, but it's not in the POC.

### Self-messages are special (Phase A only)

When you iMessage your own Apple ID, macOS records **only one row** in `chat.db` — `is_from_me=1`, `handle_id` = your own handle. There is no separate "received" row on the same account. The bridge therefore relays `is_from_me=1` messages *only* when the handle is in `SELF_HANDLES`. For whitelisted contacts (Phase B) only `is_from_me=0` rows are relayed.

### Echo suppression

When you `/send` from Telegram, the bridge writes to chat.db via osascript → Messages, which produces an `is_from_me=1` row. Without suppression we'd relay that row straight back to Telegram as "you received: \<the message you just sent\>". The bridge remembers every outbound `(handle, body)` tuple it just dispatched for 30s and drops matching inbound rows. Timestamps aren't compared — in the rare event you genuinely iMessage yourself the same literal text from iPhone within 30s of the bridge sending it, that one will be dropped as well.

### Heads-up: missing a handle = silent drop

If Alice texts you from her gmail-Apple-ID and you only whitelisted her phone, her message arrives in `chat.db` but the bridge skips it (no error, no Telegram message). To debug: tail `~/Library/Logs/imessage-tg/stdout.log` — there's no entry for skipped handles by default. (Add a `log.debug` in `_should_relay` if you want to see them.)

### Helper: list all handles you've ever talked to

Quick query to see every distinct handle in your `chat.db` so you can pick which to add:

```bash
sqlite3 ~/Library/Messages/chat.db \
  "SELECT DISTINCT id FROM handle ORDER BY id;"
```

### To bulk-whitelist everyone

Set `WHITELIST_HANDLES=*` — **not currently supported in code**. If you want it, change `_should_relay` in `bridge.py` to return `True` when `WHITELIST_HANDLES` contains `*`. Skipped for the POC because the whole point is to not get firehosed.
