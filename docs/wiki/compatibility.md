# macOS Compatibility Matrix

This page tracks which chatwire features work on which macOS versions and
hardware configurations.

Legend: ✅ works · ⚠️ works with caveats · ❌ not supported · 🔬 untested

---

## macOS version support

| Feature | 12 Monterey | 13 Ventura | 14 Sonoma | 15 Sequoia |
|---------|:-----------:|:----------:|:---------:|:----------:|
| Bridge (read chat.db) | ✅ | ✅ | ✅ | ✅ |
| Send iMessage (AppleScript) | ✅ | ✅ | ✅ | ✅ |
| Send SMS / RCS (AppleScript) | ✅ | ✅ | ✅ | ⚠️ [1] |
| Contact name resolution | ✅ | ✅ | ✅ | ✅ |
| Group chat support | ✅ | ✅ | ✅ | ✅ |
| Photo / video attachments | ✅ | ✅ | ✅ | ✅ |
| HEIC → JPEG conversion (sips) | ✅ | ✅ | ✅ | ✅ |
| Tapbacks / reactions (read) | ✅ | ✅ | ✅ | ✅ |
| Tapbacks / reactions (send) | ❌ [2] | ✅ | ✅ | ✅ |
| Edit message (send) | ❌ [2] | ✅ | ✅ | ✅ |
| Unsend message | ❌ [2] | ✅ | ✅ | ✅ |
| Edit history (`date_edited`) | ❌ [3] | ✅ | ✅ | ✅ |
| Read receipts | ✅ | ✅ | ✅ | ✅ |
| Inline replies | ✅ | ✅ | ✅ | ✅ |
| Location share cards | ✅ | ✅ | ✅ | ✅ |
| Sticker / Memoji display | ✅ | ✅ | ✅ | ✅ |
| launchd agents (auto-start) | ✅ | ✅ | ✅ | ✅ |
| `chatwire doctor` TCC checks | ✅ | ✅ | ✅ | ✅ |
| Notifications (ntfy/Telegram) | ✅ | ✅ | ✅ | ✅ |
| Web UI (all features) | ✅ | ✅ | ✅ | ✅ |
| Plugin system | ✅ | ✅ | ✅ | ✅ |

**Notes**

[1] On macOS 15 Sequoia, Apple changed how RCS messages are handled in
Messages.app. The AppleScript interface for SMS/RCS `send text` commands
behaves differently for green-bubble contacts in some configurations. iMessage
(blue bubble) is unaffected. Watch issue #87 for updates.

[2] macOS 13 Ventura added the `react with reaction` and `edit message`
AppleScript commands to Messages.app. On macOS 12, these features are not
available via AppleScript — no known workaround. The web UI hides
Edit/Unsend buttons on macOS < 13; tapback reactions should also be hidden
(currently shown but fail with a toast error — fix pending).

[3] The `date_edited` column in chat.db was added in macOS 13. On macOS 12,
edited messages show their final text but no edit history is available.

---

## Minimum macOS requirement

**macOS 12.0 (Monterey)** — this is the oldest version the author has tested.
Older versions may work but are not supported.

macOS 11 (Big Sur) is missing some TCC privacy APIs that chatwire's `doctor`
command checks. The bridge itself may work, but `chatwire doctor` will report
unexpected results.

---

## Hardware / architecture

| | Intel (x86_64) | Apple Silicon (arm64) |
|-|:--------------:|:---------------------:|
| Bridge | ✅ | ✅ |
| sips HEIC conversion | ✅ | ✅ |
| AppleScript send | ✅ | ✅ |
| Rosetta 2 (Intel on AS) | ✅ | n/a |
| Performance | ✅ | ✅ faster |

chatwire is a pure-Python package. It runs natively on both Intel and Apple
Silicon Macs without any native extensions.

The reference install (see `docs/REFERENCE_INSTALL.md`) was first developed
on an **Intel MacBook Air (2017) running macOS 12 Monterey**. Apple Silicon
is tested on M1/M2/M3 machines running macOS 13–15.

---

## Python version support

| Python | Supported | Notes |
|--------|:---------:|-------|
| 3.9 | ⚠️ | Might work; not tested |
| 3.10 | ⚠️ | Might work; not tested |
| 3.11 | ✅ | Supported |
| 3.12 | ✅ | Supported; recommended |
| 3.13 | ✅ | Supported; default for pipx installs on macOS 15 |
| 3.14+ | 🔬 | Untested |

The `pipx install chatwire` path uses whichever Python `pipx` resolves,
typically the newest available. Homebrew installs use the brew-managed Python.
Both are ≥ 3.11 on any macOS version chatwire supports.

---

## Permissions by macOS version

Permissions are granted via **System Settings → Privacy & Security**.
See [`docs/wiki/permissions.md`](permissions.md) for grant instructions.

| Permission | 12 Monterey | 13 Ventura | 14 Sonoma | 15 Sequoia |
|------------|:-----------:|:----------:|:---------:|:----------:|
| Full Disk Access | System Prefs | System Settings | System Settings | System Settings |
| Automation → Messages | System Prefs | System Settings | System Settings | System Settings |
| Contacts | System Prefs | System Settings | System Settings | System Settings |

> **Monterey note**: The UI is still called "System Preferences" (not "System
> Settings") on macOS 12. The permission paths are otherwise identical.

---

## iMessage feature history

Each row shows when Apple introduced the feature and which macOS versions
still support it. "Introduced" = first macOS version. "Supported" = range
of macOS versions where it works (features are never removed once added).

| Feature | Introduced | Supported | iOS | Notes |
|---------|:----------:|:---------:|:---:|-------|
| iMessage (text + photo) | 10.8 Mountain Lion (2012) | 10.8 – 15 | 5+ | Core messaging |
| Read receipts | 10.8 Mountain Lion (2012) | 10.8 – 15 | 5+ | Per-conversation toggle |
| Group chat | 10.8 Mountain Lion (2012) | 10.8 – 15 | 5+ | |
| Photo/video/file attachments | 10.8 Mountain Lion (2012) | 10.8 – 15 | 5+ | |
| Send via AppleScript | 10.8 Mountain Lion (2012) | 10.8 – 15 | — | `send "text" to buddy` |
| Audio messages | 10.10 Yosemite (2014) | 10.10 – 15 | 8+ | Stored as .caf attachments |
| Tapback reactions (UI + chat.db) | 10.12 Sierra (2016) | 10.12 – 15 | 10+ | ❤️ 👍 👎 😂 ‼️ ❓ |
| Stickers / Memoji | 10.14 Mojave (2018) | 10.14 – 15 | 12+ | Stored as image attachments |
| Link previews | 10.14 Mojave (2019) | 10.14 – 15 | 13+ | `balloon_bundle_id` metadata |
| Inline replies (UI) | 10.15 Catalina (2020) | 10.15 – 15 | 14+ | Thread view in Messages.app |
| Location sharing | 10.15 Catalina (2019) | 10.15 – 15 | 13+ | Maps link cards |
| Inline replies (chat.db `reply_to_guid`) | 13 Ventura (2022) | 13 – 15 | — | Column added to chat.db |
| Tapback reactions (AppleScript) | 13 Ventura (2022) | 13 – 15 | — | `react with reaction` command |
| Edit sent messages (UI) | 13 Ventura (2022) | 13 – 15 | 16+ | 15-min window, 5 edits max |
| Edit messages (AppleScript) | 13 Ventura (2022) | 13 – 15 | — | `edit message` command |
| Unsend messages (UI) | 13 Ventura (2022) | 13 – 15 | 16+ | 2-minute window |
| Unsend messages (AppleScript) | 13 Ventura (2022) | 13 – 15 | — | |
| `date_edited` in chat.db | 13 Ventura (2022) | 13 – 15 | — | Tracks edit history |
| Check In (safety) | 14 Sonoma (2023) | 14 – 15 | 17+ | Not accessible via AppleScript |
| RCS support | 15 Sequoia (2024) | 15 | 18+ | Green-bubble interop |

> **Key takeaway for chatwire**: macOS 13 Ventura is the dividing line.
> Reading messages, tapbacks, and attachments works on macOS 12+, but
> *sending* reactions, edits, and unsends requires macOS 13+ due to
> AppleScript API additions. macOS 12 is read + send-text only.

---

## chat.db schema notes

The chat.db SQLite schema has evolved across macOS versions. Chatwire handles
these differences internally:

| Field / behavior | 12 Monterey | 13 Ventura | 14+ Sonoma |
|-----------------|:-----------:|:----------:|:----------:|
| `message.is_read` | ✅ | ✅ | ✅ |
| `message.date_read` | ✅ | ✅ | ✅ |
| `message.associated_message_type` (tapbacks) | ✅ | ✅ | ✅ |
| `message.reply_to_guid` | ⚠️ [4] | ✅ | ✅ |
| `message.balloon_bundle_id` (location) | ✅ | ✅ | ✅ |
| RCS messages in chat.db | ❌ | ⚠️ | ✅ |

[4] `reply_to_guid` was added in macOS 13. On macOS 12, inline reply context
is not available from chat.db; messages still display normally, just without
the quoted-reply block.

---

## Known issues

| Issue | Affected | Status |
|-------|----------|--------|
| RCS/SMS AppleScript on Sequoia | macOS 15 | Investigating (#87) |
| Tapback send buttons shown but fail on Monterey | macOS 12 | Fix pending — hide when < 13 |
| `reply_to_guid` absent on Monterey | macOS 12 | By design — field didn't exist |
| `date_edited` absent on Monterey | macOS 12 | By design — field didn't exist |
| TCC prompts on first run require GUI session | All | By design — macOS requirement |
| `chatwire doctor` may show stale binary path after Python upgrade | All | Re-grant FDA to new binary |

---

## Testing matrix

The following configurations are actively tested before each release:

| Hardware | macOS | Python | Status |
|----------|-------|--------|--------|
| MacBook Air 2017 (Intel) | 12.7.x Monterey | 3.12 | ✅ reference install |
| MacBook Pro M2 | 14.x Sonoma | 3.13 | ✅ author's daily driver |
| MacBook Pro M3 | 15.x Sequoia | 3.13 | ✅ CI target |

Contributions with test results on other configurations are welcome — open an
issue with your hardware, macOS version, and `chatwire doctor` output.
