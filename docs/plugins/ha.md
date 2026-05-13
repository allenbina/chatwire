# Home Assistant

## What it does

The Home Assistant plugin lets you control your smart home by texting keywords to yourself (or a shared group chat). Each inbound iMessage is checked against a list of keyword → HA service mappings. On a match, the plugin POSTs to the Home Assistant services API and replies with a confirmation.

Examples of what you can do:

- Text **"lights off"** → `light.turn_off` fires on `light.living_room`
- Text **"good night"** → `scene.turn_on` fires on `scene.night_mode`
- Text **"coffee"** → `switch.turn_on` fires on `switch.coffee_maker`

You can restrict each command to a list of trusted senders, so only your phone number (or family members) can trigger HA actions even if someone else texts the bridge number.

## Install command

```bash
pipx inject chatwire chatwire-ha
# or inside the chatwire venv:
pip install chatwire-ha
```

Then restart the chatwire bridge:

```bash
launchctl kickstart -k gui/$(id -u)/dev.chatwire.bridge
```

## Configuration walkthrough

1. Open chatwire in your browser (`http://localhost:8723`).
2. Go to **Settings** → **Plugins** → **Home Assistant**.
3. Toggle **Enabled** to ON.
4. Enter your **Home Assistant URL** (e.g. `http://homeassistant.local:8123`).
5. Paste a **Long-lived access token** (create one in HA under **Profile → Long-Lived Access Tokens**).
6. Add one or more **Command mappings** (see below).
7. Changes save automatically. The integration is active immediately.

## Settings reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `false` | Master switch. |
| `ha_url` | string | *(required)* | Base URL of your HA instance. |
| `access_token` | string | *(required)* | HA long-lived access token. |
| `commands` | array | `[]` | List of keyword → HA service mappings (see below). |

### Command mapping fields

Each entry in `commands` is an object with these fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `keyword` | string | yes | Exact phrase the sender types (matched case-insensitively, whitespace-stripped). |
| `domain` | string | yes | HA domain, e.g. `light`, `switch`, `scene`, `automation`. |
| `service` | string | yes | HA service, e.g. `turn_on`, `turn_off`, `trigger`. |
| `entity_id` | string | yes | Target entity, e.g. `light.living_room`, `scene.night_mode`. |
| `description` | string | yes | Human-readable label sent back as the confirmation reply. |
| `allowed_senders` | array of strings | no | Optional list of handles that may trigger this command. Empty or absent = any sender. |

Config file path: `~/.chatwire/config.json` under `integrations.chatwire_ha`.

## Minimal config

```json
{
  "integrations": {
    "chatwire_ha": {
      "enabled": true,
      "ha_url": "http://homeassistant.local:8123",
      "access_token": "<long-lived token>",
      "commands": [
        {
          "keyword": "lights off",
          "domain": "light",
          "service": "turn_off",
          "entity_id": "light.living_room",
          "description": "Living room lights off"
        }
      ]
    }
  }
}
```

## Full config with allowed_senders

```json
{
  "integrations": {
    "chatwire_ha": {
      "enabled": true,
      "ha_url": "http://homeassistant.local:8123",
      "access_token": "<long-lived token>",
      "commands": [
        {
          "keyword": "lights off",
          "domain": "light",
          "service": "turn_off",
          "entity_id": "light.living_room",
          "description": "Living room lights off",
          "allowed_senders": ["+15551234567", "+15559876543"]
        },
        {
          "keyword": "good night",
          "domain": "scene",
          "service": "turn_on",
          "entity_id": "scene.night_mode",
          "description": "Night mode activated"
        },
        {
          "keyword": "coffee",
          "domain": "switch",
          "service": "turn_on",
          "entity_id": "switch.coffee_maker",
          "description": "Coffee maker on",
          "allowed_senders": ["+15551234567"]
        }
      ]
    }
  }
}
```

In this example:

- **"lights off"**: only `+15551234567` or `+15559876543` can trigger it.
- **"good night"**: any sender can trigger it (no `allowed_senders` restriction).
- **"coffee"**: only `+15551234567` can trigger it.

## How allowed_senders works

- The filter is per-command. Commands without `allowed_senders` (or with an empty list) are open to any sender.
- Matching is **case-insensitive** — useful for email-format handles (`Alice@Example.com` matches `alice@example.com`).
- Phone number handles are matched exactly as they arrive from the bridge (e.g. `+15551234567`).
- If a sender is not in the list, the message is silently ignored — no reply is sent.

## Keyword matching rules

- The full message text is stripped of leading/trailing whitespace and lowercased before comparison.
- Matching is **exact** — `"lights"` does not match the command `"lights off"`.
- There is no substring or regex matching; each keyword is a complete, literal phrase.

## Home Assistant automation example

You can also trigger HA automations directly. In HA, create an automation with a webhook trigger, then map a keyword to it:

```json
{
  "keyword": "run morning routine",
  "domain": "automation",
  "service": "trigger",
  "entity_id": "automation.morning_routine",
  "description": "Morning routine triggered"
}
```

Or use a scene:

```json
{
  "keyword": "movie time",
  "domain": "scene",
  "service": "turn_on",
  "entity_id": "scene.movie_mode",
  "description": "Movie mode activated"
}
```

## Troubleshooting / FAQ

**The command fires but HA returns 401 Unauthorized.**
Your `access_token` is invalid or expired. Generate a new one under **Profile → Long-Lived Access Tokens** in Home Assistant.

**The command fires but HA returns 404 Not Found.**
Check `domain`, `service`, and `entity_id`. Run the service manually in HA **Developer Tools → Services** to verify the call syntax.

**I sent the keyword but got no reply.**
- Confirm the integration is enabled and the bridge was restarted after saving config.
- Check that `ha_url` is reachable from the Mac running chatwire: `curl -sf http://homeassistant.local:8123/api/`.
- If you set `allowed_senders`, verify your handle is in the list.

**Keyword matching isn't working.**
The match is exact after stripping and lowercasing. Type the keyword exactly as configured. Leading/trailing spaces are ignored but interior spaces are significant.

**I want to trigger the same HA action from multiple keywords.**
Add multiple command entries that share the same `domain`/`service`/`entity_id` but different `keyword` values.

**How do I find the right entity_id?**
In Home Assistant go to **Settings → Devices & Services → Entities**. Search for the device; the entity ID is shown in the detail panel.
