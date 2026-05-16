# Theming Hooks Spec — Easy + Medium Tiers

## Goal

Make every visual property in Chatwire overridable by themes via CSS custom
properties and (for medium-tier) component-level registries. Zero visual
regressions — defaults must match current appearance exactly.

---

## Tier 1: Easy (CSS vars only)

### 1a. Icon sizing + stroke

Add to `themes.css` in each `[data-style]` block:

```css
--icon-size-sm: 0.875rem;   /* 14px — ConversationList camera, Layout logout */
--icon-size-md: 1rem;        /* 16px — most icons */
--icon-size-lg: 1.25rem;     /* 20px — ContactInfoSheet, Layout nav */
--icon-stroke: 2;            /* stroke-width for inline SVGs */
```

**Apply to inline SVGs:** Replace hardcoded `className="w-4 h-4"` /
`strokeWidth={2}` with inline styles reading the vars:

```tsx
style={{
  width: 'var(--icon-size-md)',
  height: 'var(--icon-size-md)',
}}
strokeWidth="var(--icon-stroke)"
```

Files to change (inline SVGs only — NOT DebugPage.tsx, leave that as-is):
- `MessageBubble.tsx` — file/download icons (lines ~60, ~119), reply/edit/unsend
  in HoverActionBar (lines ~517, ~531, ~546)
- `ExportDropdown.tsx` — export icon (line ~54)
- `ConversationList.tsx` — camera icon (line ~119)
- `ContactInfoSheet.tsx` — chevron icon (line ~75)
- `ChatPage.tsx` — info icon (line ~148)
- `SettingsPage.tsx` — all 9 inline icon functions (UserIcon through ZapIcon,
  lines ~3861–3925)

**Lucide icons:** Lucide components accept a `size` prop and `strokeWidth` prop.
Wrap them in a shared size by passing these props. However, Lucide can't read
CSS vars natively for `size` (it sets width/height attributes, not CSS). Instead,
apply the CSS var via className override:

```tsx
<Settings className="text-foreground" style={{ width: 'var(--icon-size-lg)', height: 'var(--icon-size-lg)' }} />
```

Files to change (lucide imports):
- `Layout.tsx` — Settings/Puzzle/Palette/ScrollText (lg), PauseCircle/Bell/
  CheckCheck/Sun/Moon/LogOut/TriangleAlert (md/sm)
- `ComposeBox.tsx` — ImagePlus/Send/Smile/TriangleAlert
- `DataWarningModal.tsx` — ShieldAlert
- `SettingsPage.tsx` — LogOut/Pin/PinOff

**Do NOT change:** `MediaGallery.tsx` spinner (animated, keep hardcoded),
`DebugPage.tsx` (reference page, keep explicit sizes).

### 1b. Font family

Add to `themes.css` in each `[data-style]` block:

```css
--font-family: 'Inter', ui-sans-serif, system-ui, -apple-system, sans-serif;
```

Apply once in `index.css` (or a new base layer):

```css
body {
  font-family: var(--font-family);
}
```

Also update `LockoutOverlay.tsx` line 60 to use `var(--font-family)` instead
of the hardcoded `fontFamily="Inter, system-ui, sans-serif"`.

### 1c. Scrollbar theming

Add to `index.css`:

```css
/* Themed scrollbar — respects scheme colors */
::-webkit-scrollbar {
  width: var(--scrollbar-width, 8px);
}
::-webkit-scrollbar-track {
  background: hsl(var(--muted));
}
::-webkit-scrollbar-thumb {
  background: hsl(var(--border));
  border-radius: var(--radius);
}
::-webkit-scrollbar-thumb:hover {
  background: hsl(var(--muted-foreground));
}
```

Add `--scrollbar-width: 8px;` to `themes.css` defaults.

### 1d. Sidebar / header background image

Add to `themes.css`:

```css
--sidebar-bg-image: none;
--header-bg-image: none;
```

Apply in Layout.tsx sidebar wrapper and header elements via
`style={{ backgroundImage: 'var(--sidebar-bg-image)' }}` (additive —
bg-color still shows through if image is `none`).

### 1e. Update DebugPage

Add new sections to `/debug`:
- **Icon Theming** — show icons at each size var, current stroke width
- **Font Family** — show current `--font-family` value
- **Scrollbar** — a scrollable box demonstrating themed scrollbar

---

## Tier 2: Medium (component-level hooks)

### 2a. Icon registry

Create `src/lib/icon-registry.tsx`:

```tsx
const IconContext = createContext<IconRegistry>(defaultRegistry)

interface IconRegistry {
  resolve(name: string, size?: 'sm' | 'md' | 'lg'): React.ReactNode
}
```

Default registry returns lucide icons. A theme bundle can provide its own
registry (e.g., Phosphor, Heroicons, custom SVG sprites) via:

```json
// theme.json
{ "iconSet": "phosphor" }
```

Theme loader wraps the app in `<IconContext.Provider value={phosphorRegistry}>`.

Components call `useIcon('settings', 'lg')` instead of `<Settings className="w-5 h-5" />`.

**Migration:** Replace all icon usage in Layout, ComposeBox, MessageBubble,
SettingsPage, etc. with `useIcon()` calls. Keep the debug page showing both
the registry output and the raw lucide/inline sets for comparison.

### 2b. Avatar clip paths

Add to `themes.css`:

```css
--avatar-clip: none;  /* e.g., circle(), polygon(), url(#hexagon) */
```

When set, apply as `clipPath: var(--avatar-clip)` on avatar elements,
overriding `border-radius`. Requires an inline `<svg><defs><clipPath>` block
in Layout or App for custom shapes like hexagons, squircles, etc.

### 2c. Bubble shapes

Add to `themes.css`:

```css
--bubble-clip: none;        /* SVG clip-path for non-rectangular bubbles */
--bubble-tail-svg: none;    /* url() to an SVG tail shape */
```

When set, MessageBubble applies `clipPath` and appends the tail SVG as a
positioned pseudo-element or inline element.

### 2d. Custom emoji rendering

Create `src/lib/emoji-renderer.tsx`:

```tsx
interface EmojiRenderer {
  render(emoji: string, size?: number): React.ReactNode
}
```

Default: returns the raw emoji string (native rendering).
Theme override: returns `<img src="twemoji/..." />` or similar.

Apply in TapbackBar, HoverActionBar, and any future emoji picker.

### 2e. Sound themes

Add to theme.json manifest:

```json
{
  "sounds": {
    "send": "sounds/send.mp3",
    "receive": "sounds/receive.mp3",
    "notification": "sounds/notification.mp3"
  }
}
```

Create `src/lib/sound-manager.ts` that loads sounds from the active theme
bundle. Components call `playSound('send')` — no-op if theme has no sounds.

---

## Implementation order

1. **1a** (icon vars) — biggest surface area, most visible
2. **1b** (font family) — trivial
3. **1c** (scrollbars) — trivial, nice visual win
4. **1d** (bg images) — small, enables creative themes
5. **1e** (debug page updates) — after 1a–1d land
6. **2a** (icon registry) — biggest medium-tier item, unlocks icon set swapping
7. **2b–2e** — defer until icon registry proves the pattern

## Files changed (Tier 1 only)

- `src/styles/themes.css` — new vars
- `src/index.css` — scrollbar styles, body font-family
- `src/components/MessageBubble.tsx` — icon var usage
- `src/components/ExportDropdown.tsx` — icon var usage
- `src/components/ConversationList.tsx` — icon var usage
- `src/components/ContactInfoSheet.tsx` — icon var usage
- `src/components/Layout.tsx` — icon var usage, sidebar bg-image
- `src/components/ComposeBox.tsx` — icon var usage
- `src/components/DataWarningModal.tsx` — icon var usage
- `src/components/LockoutOverlay.tsx` — font-family var
- `src/pages/ChatPage.tsx` — icon var usage
- `src/pages/SettingsPage.tsx` — icon var usage
- `src/pages/DebugPage.tsx` — new sections
