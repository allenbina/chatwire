# Favorites

## What it does

Favorites lets you pin any contact or group chat to the top of the chatwire sidebar. Pinned conversations always appear first, separated from the rest of the list, and are marked with a gold star (★) badge so they stand out at a glance. Favorites are stored locally and persist across restarts.

## Install command

Favorites is a built-in web UI feature — no plugin install is required.

```
# Already available in Settings → Favorites
```

## Configuration walkthrough

1. Open chatwire in your browser (`http://localhost:8723`).
2. Go to **Settings** → **Favorites** (expand the accordion section).
3. Type a contact name, phone number, or email into the **Add favorite** field. The field autocompletes against your whitelisted contacts.
4. Click **Add**. The contact moves to the top of the sidebar immediately.
5. To remove a favorite, expand the Favorites section and click the trash icon next to the contact.

Alternatively, you can favorite a contact directly from a conversation: open any chat and look for the star icon in the conversation header.

## Usage guide

- **Pinned contacts** appear above the full contact list in the sidebar with a ★ badge.
- **Ordering**: Favorites are shown in the order they were added. The most recently added favorite appears last in the favorites group.
- **Groups**: Group chats can be favorited the same way as 1:1 contacts — enter the group's display name.
- **Sidebar sync**: The sidebar updates instantly via HTMX when you add or remove a favorite; no page reload needed.
- **Mobile (PWA)**: Favorites are reflected in the PWA sidebar on your phone as well, since it hits the same web UI.

## Settings reference

Favorites have no config-file fields — they are managed entirely through the web UI. The underlying data is stored in `~/.chatwire/config.json` under the key `favorites` as a list of handles:

```json
{
  "favorites": [
    "+15551234567",
    "alice@example.com",
    "group:chat-guid-here"
  ]
}
```

You can edit this list manually if needed; restart the web service for changes to take effect.

## Troubleshooting / FAQ

**A contact I favorited doesn't appear at the top.**
Make sure the contact is also in your **Whitelist** (Settings → Whitelist). Contacts not in the relay scope are hidden from the sidebar even if favorited.

**The autocomplete dropdown is empty.**
Click **Sync contacts** (the rotate icon in the Whitelist section) to refresh the Contacts lookup table, then try again.

**I favorited a contact but the star badge isn't showing.**
Hard-refresh the page (`Cmd+Shift+R` in Safari/Chrome). The HTMX swap occasionally misses the sidebar update on slow connections.

**Can I reorder favorites?**
Not yet — the order is insertion order. Edit `~/.chatwire/config.json` manually and restart the web service to reorder.
