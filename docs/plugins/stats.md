# Message Statistics

## What it does

The Stats plugin generates a local messaging analytics report from your `chat.db` — no data leaves your Mac. It counts messages sent and received per contact, shows your busiest days and hours, and surfaces top conversations over a configurable date window. The report is rendered as a web page inside chatwire and updates on demand.

## Install command

Stats ships with chatwire. No additional install step is required.

```
# Already available — just enable it in Settings → Plugins → Message statistics
```

## Configuration walkthrough

1. Open chatwire in your browser (`http://localhost:8723`).
2. Go to **Settings** (gear icon or sidebar footer).
3. Scroll to the **Plugins** section and expand **Message statistics**.
4. Toggle **Enabled** to ON.
5. Choose a **Date range** from the dropdown.
6. Changes save automatically. Click **View stats →** to open the report.

## Usage guide

After enabling the plugin:

- The **View stats →** link appears below the settings fields. Click it to open the analytics report in the main content area.
- The report shows message counts, top contacts, and activity heatmaps for the selected date window.
- All computation happens locally against `~/Library/Messages/chat.db`. The report refreshes each time you visit the page.
- Stats are read-only — no messages are modified or uploaded.

## Settings reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `false` | Master switch. When off, the stats route is not registered. |
| `date_range` | enum | `"30d"` | How far back to include messages. Options: `30d` (last 30 days), `90d` (last 90 days), `365d` (last year), `all` (full history). |

Config file path: `~/.chatwire/config.json` under the key `integrations.stats`.

```json
{
  "integrations": {
    "stats": {
      "enabled": true,
      "date_range": "90d"
    }
  }
}
```

## Troubleshooting / FAQ

**The report is blank or shows zero messages.**
Confirm chatwire has Full Disk Access in System Settings → Privacy & Security → Full Disk Access. Without FDA, reading `chat.db` fails silently.

**Stats feel slow to load.**
With `date_range: "all"` on a large chat history, the SQL query can take several seconds. Switch to `30d` or `90d` for snappier load times.

**The "View stats →" link is not showing.**
The link only appears when the plugin is enabled. Toggle **Enabled** to ON and the link will appear below the date range field.

**Numbers don't match what I see in the Messages app.**
Stats count database rows, which may differ from what Messages displays (e.g., deleted messages may persist in `chat.db` or be fully purged depending on macOS version).
