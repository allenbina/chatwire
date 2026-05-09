# Content Filter

## What it does

The Content Filter plugin replaces matched words and phrases in inbound messages with a randomly-chosen emoji — keeping your chat history readable without exposing you to content you'd rather not see. It operates as a display-only transform: `chat.db` is never modified, and the original text is preserved on disk. Filtering can be scoped to the web UI only or applied globally to all integrations (Telegram relay, webhook output, etc.).

Twelve built-in word-list categories ship with chatwire. You can enable any combination, add your own custom words, tune the emoji pool, and choose between an exact whole-word match or a loose mode that also catches common l33tspeak substitutions (`@→a`, `3→e`, `1→i`, `0→o`, `$→s`).

## Install command

Content Filter ships with chatwire. No additional install step is required.

```
# Already available — enable it in Settings → Plugins → Content Filter
```

## Configuration walkthrough

1. Open chatwire → **Settings** → **Plugins** → **Content Filter**.
2. Toggle **Enabled** to ON.
3. Enable one or more **Filter categories** using the individual toggles.
4. Optionally add **Custom words** — one word or phrase per line.
5. Adjust the **Emoji pool** if you want different replacement characters.
6. Set **Matching mode** to `exact` (default) or `loose`.
7. Set **Apply to** — `all` (bridge + web) or `web` (web UI only).
8. All changes save automatically on field change.

## Usage guide

### Categories

The following categories are available. Each maps to a bundled word list in `integrations/content_filter/data/`:

| Category | What it covers |
|----------|---------------|
| `profanity` | Common expletives and slurs |
| `politics` | Political terms and hot-button phrases |
| `religion` | Religious terminology |
| `sex` | Sexual language and innuendo |
| `money` | Financial/gambling slang |
| `body` | Body-related terms |
| `drugs` | Drug names and slang |
| `gossip` | Rumour and gossip vocabulary |
| `gambling` | Betting and casino terms |
| `social_media` | Platform names and viral slang |
| `gaming` | Gaming insults and toxic language |
| `dietary` | Diet-culture and food-related terms |

All categories are disabled by default.

### Custom words

Enter one word or phrase per line in the **Custom words** field. Phrases (containing spaces) are matched as whole units. Custom words are combined with any enabled category lists before matching.

### Emoji pool

A space-separated list of emoji that replacements are drawn from at random. Default: `😤 🤬 💢 🙈 🚫 ⚠️ 🤐`. Add or remove emoji to taste.

### Matching modes

- **exact** (default) — whole-word, case-insensitive (`\b` boundaries). `"hell"` matches `"Hell"` but not `"hello"`.
- **loose** — also normalises common l33tspeak substitutions before matching, so `"h3ll"` also matches `"hell"`.

### Scope

- **all** — the transform runs on all surfaces: the bridge relay (so Telegram/webhook relays see filtered text) and the web UI.
- **web** — the transform runs in the web UI only; the bridge relay sees original text.

## Settings reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `categories` | object | all `false` | Map of category name → boolean. Enable one or more. |
| `custom_words` | string | `""` | Newline-separated words/phrases to filter in addition to categories. |
| `emoji_pool` | string | `"😤 🤬 💢 🙈 🚫 ⚠️ 🤐"` | Space-separated emoji drawn at random for replacements. |
| `mode` | enum | `"exact"` | Matching mode: `exact` (whole-word) or `loose` (l33tspeak-aware). |
| `scope` | enum | `"all"` | Where to apply the filter: `all` (everywhere) or `web` (web UI only). |

Config file: `~/.chatwire/config.json` under `integrations.content_filter`.

```json
{
  "integrations": {
    "content_filter": {
      "enabled": true,
      "categories": {
        "profanity": true,
        "drugs": true
      },
      "custom_words": "badword\nanother phrase",
      "emoji_pool": "🚫 🙈 😶",
      "mode": "loose",
      "scope": "web"
    }
  }
}
```

## Troubleshooting / FAQ

**No words are being replaced even though I enabled categories.**
Make sure the plugin **Enabled** toggle is ON. Also confirm the category toggle is checked, not just that the accordion is open.

**The filter is replacing words it shouldn't.**
Switch **Matching mode** to `exact` (the default). `loose` mode normalises digits and symbols before matching, which can cause over-matching in some contexts.

**I want to filter my own outbound messages too.**
The current implementation only transforms inbound messages (messages received from others). Outbound filtering is not supported.

**The emoji pool only shows one emoji.**
If the `emoji_pool` field ends up empty after saving, chatwire falls back to the default pool. Ensure there is at least one space-separated emoji in the field.

**How do I see the original unfiltered text?**
The original is always in `chat.db` — open the Messages app or run `chatwire export` to retrieve unmodified history.
