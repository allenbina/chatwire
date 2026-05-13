# macOS Permissions

chatwire requires three macOS permissions to function. Grant them to the **Python
binary** that chatwire runs as — shown in `chatwire doctor`.

---

## Full Disk Access (required)

**Why**: chatwire reads `~/Library/Messages/chat.db` to detect new iMessages. FDA
is required because `chat.db` is in a TCC-protected location.

**How to grant**:

1. Open **System Settings → Privacy & Security → Full Disk Access**
2. Click **+** and navigate to the chatwire Python binary
   - pipx install: `~/.local/pipx/venvs/chatwire/bin/python3.13`
   - Homebrew: `/usr/local/bin/python3` (or wherever brew installed it)
3. Toggle the entry on

**Diagnosis**: `chatwire doctor` will show `✗ Full Disk Access — not granted` if missing.

### Common pitfall: wrong Python binary

macOS TCC tracks grants per-binary. If you upgrade Python or reinstall chatwire
with a different Python, you must re-grant FDA to the new binary. Use the output
of `chatwire doctor` to identify the exact binary.

---

## Automation → Messages (required)

**Why**: The bridge sends iMessages via AppleScript to `Messages.app`. The
Automation permission allows the Python binary to control Messages.

**How to grant**:

1. Open **System Settings → Privacy & Security → Automation**
2. Find your Python binary and expand it
3. Enable **Messages**

**Diagnosis**: `chatwire doctor` will show `✗ Automation → Messages — not granted`
if missing. On first run, macOS prompts automatically.

### AppleScript send flow

```
chatwire bridge → osascript -e 'tell application "Messages" ...' → Messages.app → iMessage/SMS
```

---

## Contacts (optional)

**Why**: Resolves phone numbers and email addresses to display names from
Contacts.app. Without this, chatwire shows raw handles instead of names.

**How to grant**:

1. Open **System Settings → Privacy & Security → Contacts**
2. Toggle on your Python binary

chatwire reads the Contacts database directly from
`~/Library/Application Support/AddressBook/Sources/*/AddressBook-v22.abcddb`
(read-only, no Apple Events required). FDA covers this path on macOS 13+.

---

## Accessibility (not required)

chatwire does not use Accessibility APIs. If something asks for Accessibility
access, deny it — chatwire doesn't need it.

---

## Summary

| Permission | Required | Purpose |
|---|---|---|
| Full Disk Access | Yes | Read chat.db |
| Automation → Messages | Yes | Send via AppleScript |
| Contacts | Recommended | Name resolution |
| Accessibility | No | Not used |

---

## TCC reset (troubleshooting)

If permissions are stuck, reset them:

```bash
# Reset automation grants (requires SIP disabled or recovery mode on some macOS versions)
tccutil reset Automation

# Reset full disk access
tccutil reset SystemPolicyAllFiles
```

Then re-grant in System Settings. Run `chatwire doctor` to verify.
