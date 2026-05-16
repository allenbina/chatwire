# Reaction Panel + Shared Emoji Picker — Spec

## Goal

Replace the current fragmented message interaction UI (tiny tapback bar +
separate hover action bar + tooltip) with a single unified **reaction popover
panel**, and add a shared **emoji picker component** used in both the reaction
panel and the compose box.

## What gets replaced

1. **HoverActionBar** in MessageBubble.tsx — the floating bar with emoji buttons
   + reply/edit/unsend that appears on hover. REMOVED entirely.
2. **TapbackBar tooltip** — the Radix Tooltip on tapback reactions. REMOVED.
   The TapbackBar itself (showing who reacted) STAYS but gets no tooltip.
3. **EmojiPickerButton** in ComposeBox.tsx — the hardcoded 60-emoji grid.
   REPLACED with the shared EmojiPicker component.

## Part 1: Shared EmojiPicker component

### Install emoji-mart

```bash
npm install @emoji-mart/react @emoji-mart/data
```

### Create `src/components/EmojiPicker.tsx`

A wrapper around emoji-mart that applies our theme:

```tsx
import data from '@emoji-mart/data'
import Picker from '@emoji-mart/react'

interface EmojiPickerProps {
  onSelect: (emoji: string) => void
}

export function EmojiPicker({ onSelect }: EmojiPickerProps) {
  // Read current scheme colors from CSS vars for emoji-mart theming
  const style = getComputedStyle(document.documentElement)
  const bg = style.getPropertyValue('--popover').trim()  // HSL triplet
  const fg = style.getPropertyValue('--popover-foreground').trim()
  // ... etc

  return (
    <Picker
      data={data}
      onEmojiSelect={(emoji: { native: string }) => onSelect(emoji.native)}
      theme="dark"  // or detect from scheme
      // Apply CSS var colors via emoji-mart's custom CSS properties
      // See: https://github.com/missive/emoji-mart#custom-css
    />
  )
}
```

Key points:
- emoji-mart handles categories, search, frequently-used, skin tones
- Theme it via emoji-mart's CSS custom properties to match our scheme
- The component is stateless — it just calls `onSelect` with the native
  emoji string

### Theming emoji-mart

emoji-mart exposes CSS custom properties. Override them in our CSS:

```css
em-emoji-picker {
  --em-rgb-background: var(--popover);  /* may need hsl conversion */
  --em-rgb-input: var(--input);
  --em-rgb-color: var(--popover-foreground);
}
```

If emoji-mart's theming doesn't map cleanly to our HSL vars, wrap the
picker in a container div and use our own CSS to override.

## Part 2: Reaction Popover Panel

### Create `src/components/ReactionPanel.tsx`

A Radix Popover (install `@radix-ui/react-popover`) anchored to the
message bubble. Opens on:
- **Desktop**: hover (with 200ms delay, same as current HoverActionBar)
- **Mobile**: long-press (500ms, same as current)

### Layout

```
┌──────────────────────────────────────┐
│  ❤️   👍   👎   😂   ‼️   ❓   [+]   │  ← quick reactions (large)
├──────────────────────────────────────┤
│  📋  Copy                            │
│  ↩️  Reply                           │
│  ✏️  Edit            (from_me only)  │
│  🗑️  Unsend          (from_me only)  │
└──────────────────────────────────────┘
```

- Quick reaction emojis: sized at `--font-size-message` (same as bubble text)
  so they're easy to tap on mobile
- [+] button: opens the shared `<EmojiPicker>` inline (panel expands).
  Picking an emoji sends `sendTapback(rowid, emoji)` and closes panel.
- Action rows: full-width clickable rows with icon + text label
- Edit and Unsend only shown when `fromMe && ventura`

### Positioning

Use Radix Popover's built-in collision detection:
- `side="top"` preferred (panel above the bubble)
- `collisionPadding={16}` — if near top of viewport, flips to bottom
- `align`: `"end"` for outgoing (right-aligned), `"start"` for incoming

This handles the "if bubble is low, panel goes high" requirement
automatically via Radix's collision avoidance.

### CSS vars (independently themeable)

Add to schemes.css `:root` block:

```css
--reaction-panel-bg: hsl(var(--card));
--reaction-panel-text: hsl(var(--card-foreground));
--reaction-panel-border: hsl(var(--border) / 0.6);
```

### Interaction flow

1. User hovers message (desktop) or long-presses (mobile)
2. Popover opens with quick reactions + actions
3. User taps a quick reaction → `sendTapback()` → popover closes
4. User taps [+] → emoji picker expands inline → pick → `sendTapback()` → close
5. User taps Copy → copies text to clipboard → toast "Copied" → close
6. User taps Reply → calls `onReply(msg)` → close
7. User taps Edit → inline edit input appears (same as current) → close
8. User taps Unsend → confirm dialog → `unsendMessage()` → close
9. Click outside → close

## Part 3: Compose Box Emoji Picker

### Replace the current `EmojiPickerButton`

Remove the hardcoded `EMOJI_SECTIONS` grid. Replace with:

```tsx
import { EmojiPicker } from './EmojiPicker'

// In ComposeBox, the Smile button opens a Radix Popover containing <EmojiPicker>
<Popover>
  <PopoverTrigger asChild>
    <Button variant="ghost" size="icon" ...>
      <Smile />
    </Button>
  </PopoverTrigger>
  <PopoverContent side="top" align="start" className="p-0 border-0 bg-transparent">
    <EmojiPicker onSelect={(emoji) => insertAtCursor(emoji)} />
  </PopoverContent>
</Popover>
```

- Picker stays open for multiple picks (user might insert several emojis)
- Closes on outside click
- Remove the `localStorage.getItem('chatwire:emoji-picker') === 'true'`
  gate — emoji picker is always available now

## Part 4: Clean up MessageBubble.tsx

### Remove from MessageBubble.tsx:
- `HoverActionBar` component (entire function ~150 lines)
- `QUICK_REACTIONS` constant
- All hover/longpress state + handlers (`showBar`, `handleMouseEnter`,
  `handleMouseLeave`, `handleTouchStart`, `handleTouchEnd`, `hideTimer`,
  `longPressTimer`)
- The `{showBar && !pending && <HoverActionBar ... />}` render block
- Imports: `sendTapback`, `unsendMessage`, `editMessage` (move to ReactionPanel)
- Imports: `toast` (if only used by HoverActionBar)

### Keep in MessageBubble.tsx:
- `TapbackBar` component — still renders the small emoji + count overlay
  on the bubble corner. But REMOVE the `<Tooltip>` wrapper and
  `TooltipContent` — no more tooltip on hover. The reaction panel
  replaces that interaction.
- `ReplyQuote` component
- `DeliveryBadge` component
- All attachment renderers

### Add to MessageBubble.tsx:
- Import and render `<ReactionPanel>` — wrap the bubble content so the
  popover anchors to the bubble. Pass `msg`, `fromMe`, `ventura`,
  `onReply`, `isGroup`.

## Files changed

### New files:
- `src/components/EmojiPicker.tsx` — shared emoji picker wrapping emoji-mart
- `src/components/ReactionPanel.tsx` — unified reaction + action popover
- `src/components/ui/popover.tsx` — shadcn Radix Popover primitive

### Modified files:
- `package.json` — add `@emoji-mart/react`, `@emoji-mart/data`,
  `@radix-ui/react-popover`
- `src/components/MessageBubble.tsx` — remove HoverActionBar, add
  ReactionPanel, simplify TapbackBar (no tooltip)
- `src/components/ComposeBox.tsx` — replace EmojiPickerButton with
  shared EmojiPicker in a Popover
- `src/styles/schemes.css` — add `--reaction-panel-*` vars
- `src/pages/DebugPage.tsx` — update Hover Action Bar section to show
  new Reaction Panel, add Emoji Picker section

### Test impact:
- `MessageBubble.test.tsx` — update to reflect removed HoverActionBar
- `ComposeBox.test.tsx` — update emoji picker tests
- Run `npx vitest run` — all tests must pass
- Run `npx tsc --noEmit` — clean
- Run `npx vite build` — clean

## Implementation order

1. `npm install` deps
2. Create `ui/popover.tsx` (shadcn primitive)
3. Create `EmojiPicker.tsx`
4. Create `ReactionPanel.tsx`
5. Update `MessageBubble.tsx` (remove old, add new)
6. Update `ComposeBox.tsx` (swap emoji picker)
7. Update `schemes.css` (new vars)
8. Update/fix tests
9. Update `DebugPage.tsx`
10. Build + verify
