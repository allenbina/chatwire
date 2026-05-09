# Export

## What it does

The Export feature lets you download your iMessage history from chatwire in three formats — JSON, plain text, and CSV — and export all photos and videos as a ZIP archive organised into dated folders. Exports are generated on demand from `chat.db` and delivered as file downloads; no data is sent to any server.

Export works for both 1:1 conversations and whitelisted group chats, and supports an optional date filter so you can narrow the export to a specific time range.

## Install command

Export is a built-in feature — no plugin install is required.

```
# Available via the API or the conversation header export button
```

## Configuration walkthrough

Export has no dedicated settings panel — it is invoked directly via URL or from the web UI:

**From the conversation header:**
1. Open any conversation in chatwire.
2. Click the export icon (arrow-down icon in the conversation header toolbar).
3. Choose the format and optional date filter.
4. Click **Download**. The file saves to your Downloads folder.

**Via direct URL (API):**

Message export:
```
GET http://localhost:8723/api/export/messages?handle=+15551234567&format=json
```

Photo export:
```
GET http://localhost:8723/api/export/photos?handle=+15551234567
```

## Usage guide

### Message export formats

| Format | Extension | Description |
|--------|-----------|-------------|
| `json` | `.json` | Array of message objects with full metadata. |
| `txt` | `.txt` | Plain text, one line per message: `TIMESTAMP SENDER: text [attachments]`. |
| `csv` | `.csv` | Spreadsheet-ready: `timestamp, sender_name, sender_handle, text, attachments`. |

### Photo / video export

Photos and videos are bundled into a ZIP file. Inside the ZIP, files are organised into `YYYY-MM-DD/` folders by the date the attachment was received. Filenames are preserved where possible; duplicates within the same date folder are disambiguated with a numeric suffix.

### Date filtering

Append `?since=YYYY-MM-DD` to either endpoint to limit the export to messages on or after that date:

```
GET /api/export/messages?handle=+15551234567&format=csv&since=2025-01-01
```

### Group chats

Replace `handle` with `chat` and pass the group chat GUID:

```
GET /api/export/messages?chat=chat123456abcdef&format=json
```

The GUID is visible in the conversation header when a group is open.

### Authentication

If you have an API key set (Settings → API), add it to the request:

```
curl -H "X-API-Key: <your-key>" "http://localhost:8723/api/export/messages?handle=+15551234567&format=csv" -o export.csv
```

Requests from the chatwire web UI (same browser session) are authenticated automatically via session cookie.

## Settings reference

Export has no config-file settings. Access is controlled by the existing whitelist and API key settings.

**Endpoint reference:**

| Endpoint | Method | Query params | Response |
|----------|--------|-------------|----------|
| `/api/export/messages` | GET | `handle` or `chat` (required), `format` (json/txt/csv, default json), `since` (YYYY-MM-DD, optional) | File download |
| `/api/export/photos` | GET | `handle` or `chat` (required), `since` (YYYY-MM-DD, optional) | ZIP file download |

## Troubleshooting / FAQ

**Export returns 403.**
The requested handle or group chat is not in your whitelist. Add it in Settings → Whitelist and try again.

**The JSON export is missing some messages.**
Deleted messages may not be in `chat.db` depending on your macOS version and Messages sync settings. Export reflects what is currently in the database.

**Photos are missing from the ZIP.**
Attachments that were never fully downloaded to your Mac (e.g., they expired from iCloud) won't be included. Open the Messages app to force-download missing attachments, then re-export.

**The export stalls on very large conversations.**
Large exports (thousands of messages or many photos) can take tens of seconds. The request is synchronous — keep the browser tab open until the download starts.

**`since` parameter is ignored.**
Ensure the date is in `YYYY-MM-DD` format (e.g., `2025-06-01`). Other formats (e.g., `06/01/2025`) return a 400 error.
