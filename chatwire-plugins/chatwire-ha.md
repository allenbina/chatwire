# chatwire-ha

Control your Home Assistant automations, scenes, and services by typing keywords into iMessage. When a mapped keyword arrives from any whitelisted contact, chatwire calls the corresponding HA service and replies with a confirmation.

## What it does

`chatwire-ha` listens to the chatwire bridge's inbound message stream and checks every message against a user-defined keyword list. When a match is found, it POSTs to the Home Assistant services REST API to trigger a domain/service/entity combination — then replies to the sender with `Done: <description>`. Works in both 1:1 conversations and group chats.

Use cases:
- Text `"lights off"` from bed → turns off the living room lights.
- Text `"good night"` → activates a nighttime scene.
- Text `"lock up"` → runs a lock-all automation.
- Any iMessage contact on your whitelist can trigger the actions (or restrict to specific contacts in HA automations using the reply source).

## Install command

```bash
# Install inside the chatwire pipx environment:
pipx inject chatwire chatwire-ha

# Or if using a regular venv:
pip install chatwire-ha
```

## Configuration walkthrough

### Step 1 — Create a Home Assistant long-lived access token

1. In Home Assistant, click your username in the bottom-left → **Profile**.
2. Scroll to **Long-Lived Access Tokens** → **Create Token**.
3. Name it `chatwire` and copy the token. You won't see it again.

### Step 2 — Find your entity IDs and service calls

In Home Assistant, go to **Developer Tools → Services** to browse available services and entity IDs. Note:
- **Domain**: the integration type (e.g., `light`, `switch`, `scene`, `automation`, `script`).
- **Service**: the action (e.g., `turn_on`, `turn_off`, `trigger`).
- **Entity ID**: the specific device or scene (e.g., `light.living_room`, `scene.night_mode`).

### Step 3 — Configure chatwire

In `~/.chatwire/config.json`:

```json
{
  "integrations": {
    "chatwire_ha": {
      "enabled": true,
      "ha_url": "http://homeassistant.local:8123",
      "access_token": "<your-long-lived-token>",
      "commands": [
        {
          "keyword": "lights off",
          "domain": "light",
          "service": "turn_off",
          "entity_id": "light.living_room",
          "description": "Living room lights off"
        },
        {
          "keyword": "good night",
          "domain": "scene",
          "service": "turn_on",
          "entity_id": "scene.night_mode",
          "description": "Night mode activated"
        },
        {
          "keyword": "lock up",
          "domain": "automation",
          "service": "trigger",
          "entity_id": "automation.lock_all_doors",
          "description": "Locking all doors"
        }
      ]
    }
  }
}
```

Or use Settings → Plugins → Home Assistant in the chatwire web UI.

### Step 4 — Restart the bridge

```bash
/bin/launchctl kickstart -k gui/501/dev.chatwire.bridge
```

### Step 5 — Test

Send one of your configured keywords via iMessage (from any whitelisted contact). You should receive a reply like `Done: Living room lights off` within a second or two.

## Usage guide

### Keyword matching

- Keywords are matched **exactly** against the entire message text (stripped of leading/trailing whitespace, lowercased).
- `"lights off"` matches only the message `"lights off"` (case-insensitive) — not `"turn lights off"` or `"lights off please"`.
- To match variations, add separate command entries for each variant.

### Reply behaviour

On a successful HA API call, the bridge sends back: `Done: <description>` to the sender. On failure (HTTP error or network timeout), the error is logged but no reply is sent to the sender.

### Group chats

Commands work in group chats. The reply goes to the group chat, not a direct message to the sender.

### Security considerations

Any contact in your chatwire whitelist can trigger HA commands by sending a keyword. Consider:
- Using obscure, hard-to-guess keywords (e.g., `"xk-lights-off-7831"` instead of `"lights off"`).
- Keeping sensitive automations (door locks, alarm systems) behind keywords that only you know.
- Restricting the whitelist to trusted contacts only.

### Remote access

If Home Assistant is not on your local network (e.g., you're accessing via Nabu Casa or a VPN), set `ha_url` to your external HA URL:

```json
"ha_url": "https://your-instance.ui.nabu.casa"
```

## Settings reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `false` | Master switch. |
| `ha_url` | string | — | **Required.** Base URL of your Home Assistant instance, e.g. `http://homeassistant.local:8123`. |
| `access_token` | string | — | **Required.** Long-lived access token from HA Profile → Long-Lived Access Tokens. |
| `commands` | list | `[]` | Array of keyword → HA service mappings (see below). |
| `commands[].keyword` | string | — | **Required.** Exact phrase (case-insensitive) to match against the full message text. |
| `commands[].domain` | string | — | **Required.** HA service domain, e.g. `light`, `switch`, `scene`, `automation`, `script`. |
| `commands[].service` | string | — | **Required.** HA service name, e.g. `turn_on`, `turn_off`, `trigger`. |
| `commands[].entity_id` | string | — | **Required.** HA entity ID, e.g. `light.living_room`, `scene.night_mode`. |
| `commands[].description` | string | — | **Required.** Human-readable label used in the confirmation reply: `Done: <description>`. |

## Troubleshooting / FAQ

**No reply after sending a keyword.**
1. Confirm the bridge is running.
2. Check the bridge log for errors: `chatwire logs` or the launchd log file.
3. Confirm the keyword in the log matches exactly what you typed (check for trailing spaces or punctuation).
4. Try the HA service call manually from Developer Tools to rule out HA issues.

**`403` or `401` errors in the log.**
The access token is invalid or expired. Generate a new long-lived token in HA and update `access_token` in the config.

**`Connection refused` or timeout errors.**
`ha_url` is not reachable from your Mac. Confirm HA is running and that your Mac can reach it on the configured port. If HA is on a different VLAN or behind a VPN, ensure routing is in place.

**The keyword triggers but HA returns an error.**
Use HA's Developer Tools → Services to test the domain/service/entity_id combination directly. Common mistakes: wrong entity_id format, service not available for that entity, or entity not found.

**I want multiple entities triggered by one keyword.**
Create an HA script or automation that controls multiple entities, then map the keyword to `script.turn_on` or `automation.trigger` pointing at that script/automation.

**Can I trigger commands from a specific contact only?**
Not directly in chatwire-ha — the keyword matches any whitelisted sender. As a workaround, create a HA automation triggered by the keyword that also checks additional conditions (time of day, device tracker state, etc.) to add validation on the HA side.
