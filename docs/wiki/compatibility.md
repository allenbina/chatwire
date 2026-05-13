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
| Tapbacks / reactions | ✅ | ✅ | ✅ | ✅ |
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

## chat.db schema notes

The chat.db SQLite schema has evolved across macOS versions. Chatwire handles
these differences internally:

| Field / behavior | 12 Monterey | 13 Ventura | 14+ Sonoma |
|-----------------|:-----------:|:----------:|:----------:|
| `message.is_read` | ✅ | ✅ | ✅ |
| `message.date_read` | ✅ | ✅ | ✅ |
| `message.associated_message_type` (tapbacks) | ✅ | ✅ | ✅ |
| `message.reply_to_guid` | ⚠️ [2] | ✅ | ✅ |
| `message.balloon_bundle_id` (location) | ✅ | ✅ | ✅ |
| RCS messages in chat.db | ❌ | ⚠️ | ✅ |

[2] `reply_to_guid` was added in macOS 13. On macOS 12, inline reply context
is not available from chat.db; messages still display normally, just without
the quoted-reply block.

---

## Known issues

| Issue | Affected | Status |
|-------|----------|--------|
| RCS/SMS AppleScript on Sequoia | macOS 15 | Investigating (#87) |
| `reply_to_guid` absent on Monterey | macOS 12 | By design — field didn't exist |
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
