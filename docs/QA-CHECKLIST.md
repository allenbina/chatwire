# Chatwire QA Checklist — Everything Shipped

Test at: https://messages.allenbina.uk

## Core Chat
- [ ] Auto-opens most recent conversation on load
- [ ] URL shows contact name slug (`/chat/sarah-chen` not phone number)
- [ ] Group chats load messages (Civi-kids, Redlands Parent Group)
- [ ] Self-chat shows alternating bubble alignment
- [ ] Sent messages are purple (accent color), received are grey
- [ ] SMS messages show green bubble color
- [ ] SMS fallback shows single bubble with "sent via SMS" note (not two bubbles)
- [ ] "Sent" badge removed — only shows sending/failed/delivered
- [ ] Message bubbles are rounded-2xl with tail corners (br-sm / bl-sm)
- [ ] Message bubble width scales with window (75% max)
- [ ] Link previews render with image + domain + URL card
- [ ] Video plays inline; if HEVC fails, shows download link fallback
- [ ] VCF contact cards render inline with name + phone + email
- [ ] Photo icon (ImagePlus) in compose box, not paperclip
- [ ] Popout button opens actual window (480x720), not a new tab
- [ ] Contact photos show in sidebar (1:1 conversations)

## Theme System
- [ ] 21 color schemes available in Settings → Appearance
- [ ] 3 structural styles: Default, Compact, Flat
- [ ] Switching color scheme recolors app instantly
- [ ] Switching structural style changes spacing/radius
- [ ] Custom accent color picker (hex input + swatch)
- [ ] Custom CSS textarea works
- [ ] Per-theme custom CSS scoping works

## Settings
- [ ] Settings link in sidebar footer works (goes to /settings)
- [ ] Appearance quick-link in sidebar footer
- [ ] Logs link in sidebar footer
- [ ] About section is plain text below accordion (not inside accordion)
- [ ] "Chatwire" header removed from sidebar top
- [ ] Password change form works
- [ ] Whitelist section shows contacts after sync
- [ ] "Sync contacts" loads 2000+ contacts
- [ ] Search/autocomplete works for contact names
- [ ] Self handles displayed (read-only)
- [ ] Notifications section with hiatus + reminders toggles
- [ ] ntfy config is in Plugins page, not Notifications section

## Plugins
- [ ] Plugins page accessible from sidebar
- [ ] Installed plugins listed with tier badges (🟢🟡🔵⚙️)
- [ ] Plugin accordion expands to show inline settings
- [ ] Marketplace browse section with search + tag filters
- [ ] Install button with progress overlay (download → verify → install → register)
- [ ] Disable/Remove buttons work
- [ ] Plugin health dots (green/yellow/red)
- [ ] Update badges (↑ arrow) when newer version available
- [ ] Consent dialog for official-tier plugins

## API Keys
- [ ] API Keys section in Settings
- [ ] "+ Add Key" generates and shows key once
- [ ] Key shown masked after creation
- [ ] Copy button works
- [ ] Scope checkboxes (trigger_actions, read_conversations, send_messages, manage_settings)
- [ ] Delete key works
- [ ] ❌ Edit/rename key — NOT SHIPPED (#63)
- [ ] ❌ Rescope key in place — NOT SHIPPED (#63)

## Anti-Spam
- [ ] No anti-spam section in Settings (removed — always on)
- [ ] Compose box shows cooldown banner when triggered (test: send same msg to many)
- [ ] Full lockout screen at step 4+ with logo + message
- [ ] Unlock code displayed (CW-XXXX-YYYY format)
- [ ] Unlock code input field on step 6
- [ ] Server blocks sends during cooldown (429 response)

## Read State
- [ ] Unread indicators on conversations with new messages
- [ ] "N new messages" pill in message list
- [ ] "Mark all read" button / Shift+Escape shortcut
- [ ] Opening a conversation marks it as seen

## Log Viewer
- [ ] Logs page accessible from sidebar
- [ ] Live log streaming
- [ ] Filter by source (Core / plugin name)
- [ ] Filter by level
- [ ] Search text filter
- [ ] Export button
- [ ] Pause button

## Security
- [ ] Plugin sandbox — tiers enforced (ui/notify/official/core)
- [ ] Frontend plugins in sandboxed iframe
- [ ] CSP headers present
- [ ] Consent dialog for official-tier plugins
- [ ] Audit log exists at ~/.chatwire/plugin-audit.jsonl

## Other
- [ ] Favicon shows purple "c" logo
- [ ] PWA installable with correct icon
- [ ] Logout icon visible when password is set
- [ ] Contact info sheet — click header name to see handles + media
- [ ] "Remove from whitelist" auto-redirects to next conversation
- [ ] Single-instance PID lock prevents duplicate bridge

## Known Issues / Not Yet Shipped
- #61 — Groups need to be manually added to whitelist
- #63 — API key rename + rescope not built
- #62 — Auto dark/light theme switching
- #53 — Hiatus mode + reminders (toggles exist, logic TBD)
- #44 — Apprise notification plugin
- #37 — Theme/scheme should be dropdowns not swatches
- #39 — Full semantic color picker with live editing
- #43 — Downloadable theme packages
- #20 — Automation engine
- #41 — Demo app on chatwire.app
