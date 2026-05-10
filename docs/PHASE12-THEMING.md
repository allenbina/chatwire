# Phase 12: Cadillac Theme System — shadcn HSL Native

> The current theme system uses hex colors, triple indirection, and gets
> purged by Tailwind v4. This phase rebuilds it the way shadcn/Tailwind v4
> is designed to work: HSL custom properties, zero bridge layers,
> standard shadcn utility classes throughout.

## The Problem

Current stack:
1. `schemes.css` defines `--color-bg-primary: #282a36` (hex)
2. `index.css` bridges: `--background: var(--color-bg-primary)`
3. `@theme` block re-registers for Tailwind utilities
4. Components use `bg-[--color-bg-primary]` (arbitrary value syntax)
5. Tailwind purges `[data-theme="nord"]` blocks (no class references)

Result: only `:root` (Dracula) colors survive the build. Every other
theme is stripped. The UI looks like an unstyled wireframe.

## The Solution

shadcn's native convention. One layer, no bridges:

```css
:root {
  --background: 231 15% 18%;      /* Dracula bg — HSL values only */
  --foreground: 60 30% 96%;
  --primary: 265 89% 78%;
  --primary-foreground: 231 15% 18%;
  --muted: 232 14% 13%;
  --muted-foreground: 225 14% 60%;
  --card: 231 15% 18%;
  --card-foreground: 60 30% 96%;
  --border: 232 14% 31%;
  --input: 232 14% 31%;
  --ring: 265 89% 78%;
  --radius: 0.5rem;
  /* chatwire-specific (not shadcn standard) */
  --msg-me: 232 14% 31%;
  --msg-them: 231 15% 18%;
  --sidebar-bg: 232 14% 13%;
}

[data-theme="nord"] {
  --background: 220 16% 22%;
  --foreground: 218 27% 94%;
  --primary: 193 43% 67%;
  /* ... same variable names, different HSL values */
}
```

Components use standard Tailwind/shadcn classes:
```tsx
// Before (arbitrary syntax, fragile):
<div className="bg-[--color-bg-primary] text-[--color-text-primary]">

// After (standard shadcn classes, just works):
<div className="bg-background text-foreground">
```

Tailwind v4 generates `bg-background`, `text-foreground`, `bg-primary`,
etc. from the CSS custom properties automatically. No `@theme` registration
needed. Theme switching via `data-theme` attribute works because all
themes use the same variable names.

## Why This Won't Get Purged

Tailwind v4 doesn't purge CSS custom property definitions — it only
purges utility classes. The `[data-theme="nord"]` block defines
`--background`, `--foreground`, etc. as properties, not classes. The
class `bg-background` references `--background` via Tailwind's built-in
mapping. Both survive the build.

## Variable List

### Standard shadcn variables (all themes must define these):
```
--background           Main page background
--foreground           Primary text color
--card                 Card/elevated surface background
--card-foreground      Text on cards
--popover              Dropdown/popover background
--popover-foreground   Text in dropdowns
--primary              Accent/brand color (buttons, links, badges)
--primary-foreground   Text on primary color
--secondary            Secondary surface (subtle bg)
--secondary-foreground Text on secondary surface
--muted                Muted surface (disabled, subtle)
--muted-foreground     Text on muted surface (hints, placeholders)
--accent               Hover/active surface (menu items, list hover)
--accent-foreground    Text on accent surface
--destructive          Error/danger color
--destructive-foreground Text on destructive color
--border               Default border color
--input                Input field border/bg
--ring                 Focus ring color
--radius               Default border radius
```

### Chatwire-specific variables (extend shadcn):
```
--msg-me               Outgoing message bubble background
--msg-them             Incoming message bubble background
--sidebar-bg           Sidebar background (if different from --background)
--success              Success state color
--warning              Warning state color
--info                 Info state color
```

### Structural variables (from themes.css, independent of color):
```
--radius-bubble        Message bubble border radius
--radius-input         Input field border radius
--spacing-message      Vertical gap between messages
--spacing-sidebar      Conversation list row padding
--font-size-message    Message text size
--font-size-sidebar    Sidebar text size
--shadow-card          Card shadow
--sidebar-width        Sidebar width
```

## Hex → HSL Conversion

Each old theme hex value converts to HSL. Example for Dracula:
```
#282a36 → 231 15% 18%
#f8f8f2 → 60 30% 96%
#bd93f9 → 265 89% 78%
#44475a → 232 14% 31%
#21222c → 232 14% 15%
#6272a4 → 225 14% 51%
#50fa7b → 135 94% 65%
#f1fa8c → 65 92% 76%
#ff5555 → 0 100% 67%
#8be9fd → 191 95% 77%
```

## Chunk Breakdown

### Chunk 1: Convert schemes.css to HSL + fix purging

1. Rewrite `web/frontend/src/styles/schemes.css`:
   - Convert ALL 21 themes from hex to HSL (space-separated, no `hsl()` wrapper)
   - Use standard shadcn variable names directly (--background, --foreground, etc.)
   - Add chatwire-specific vars (--msg-me, --msg-them, --sidebar-bg, --success, etc.)
   - `:root` = Dracula defaults
   - Each other theme: `[data-theme="name"] { ... }`
   - Read hex values from `web/static/themes/*.css` and convert to HSL

   For hex→HSL conversion, use Python:
   ```python
   def hex_to_hsl(h):
       r, g, b = int(h[1:3],16)/255, int(h[3:5],16)/255, int(h[5:7],16)/255
       mx, mn = max(r,g,b), min(r,g,b)
       l = (mx+mn)/2
       if mx == mn: return "0 0% {:.0f}%".format(l*100)
       d = mx-mn
       s = d/(2-mx-mn) if l > 0.5 else d/(mx+mn)
       if mx == r: h = ((g-b)/d + (6 if g<b else 0))/6
       elif mx == g: h = ((b-r)/d + 2)/6
       else: h = ((r-g)/d + 4)/6
       return "{:.0f} {:.0f}% {:.0f}%".format(h*360, s*100, l*100)
   ```

2. Rewrite `web/frontend/src/index.css`:
   - `@import "tailwindcss";`
   - `@import "./styles/themes.css";`
   - `@import "./styles/schemes.css";`
   - Keep sr-only utility
   - REMOVE the entire `@theme` block — not needed with shadcn convention
   - REMOVE any `:root` color definitions — they're in schemes.css now

3. Verify: `npm run build` — check that ALL theme blocks survive in the
   output CSS. `grep -c 'data-theme' dist/assets/index-*.css` should
   show 20+ occurrences (one per theme).

4. Run: `npm run build && npm test -- --run`
   Commit. Push.

### Chunk 2: Convert all components to shadcn utility classes

Every component that uses `bg-[--color-*]` or `text-[--color-*]` must
switch to standard shadcn classes. This is a search-and-replace:

```
bg-[--color-bg-primary]     → bg-background
bg-[--color-bg-secondary]   → bg-card
bg-[--color-bg-tertiary]    → bg-muted
bg-[--color-sidebar-bg]     → bg-[--sidebar-bg] (chatwire-specific, keep arbitrary)
bg-[--color-sidebar-hover]  → bg-accent
bg-[--color-sidebar-active] → bg-accent
bg-[--color-accent]         → bg-primary
bg-[--color-input-bg]       → bg-input
bg-[--color-msg-me]         → bg-[--msg-me]
bg-[--color-msg-them]       → bg-[--msg-them]
text-[--color-text-primary]   → text-foreground
text-[--color-text-secondary] → text-muted-foreground
text-[--color-text-muted]     → text-muted-foreground
text-[--color-accent]         → text-primary
text-[--color-error]          → text-destructive
border-[--color-border]       → border-border
border-[--color-accent]       → border-primary
```

Files to update (grep for `--color-` in each):
- `src/components/Layout.tsx`
- `src/components/ConversationList.tsx`
- `src/components/MessageList.tsx`
- `src/components/MessageBubble.tsx`
- `src/components/ComposeBox.tsx`
- `src/components/ExportDropdown.tsx`
- `src/components/MediaGallery.tsx`
- `src/components/UpdateBanner.tsx`
- `src/pages/ChatPage.tsx`
- `src/pages/SettingsPage.tsx`
- `src/pages/LoginPage.tsx`
- `src/pages/PopoutPage.tsx`
- Any other file with `--color-` references

Run: `npm run build && npm test -- --run`
Fix any broken tests (class name changes in snapshots/assertions).
Commit. Push.

### Chunk 3: Update useTheme + SettingsPage + deploy

1. Simplify `useTheme.ts`:
   - `applyTheme(name)` just sets `data-theme` attribute (already does this)
   - `allSchemes` list: `{name, label, isLight, swatch}` — swatch is the
     `--primary` HSL value for the picker preview
   - Remove any remaining hex-based logic

2. Update `SettingsPage.tsx` theme picker:
   - Color scheme swatches should render correctly with HSL values
   - Verify clicking a swatch switches `data-theme` and colors change live

3. Full test suite: `npm run build && npm test -- --run`

4. Deploy to mbair:
   ```bash
   SITE="/Users/allen/.local/pipx/venvs/chatwire/lib/python3.14/site-packages/web"
   ssh mbair "rm -rf $SITE/frontend/dist"
   scp -r web/frontend/dist mbair:"$SITE/frontend/dist"
   ssh mbair "/bin/launchctl kickstart -k gui/501/dev.chatwire.web"
   ssh mbair "/usr/bin/curl -sf localhost:8723/healthz"
   ```

5. Notify:
   ```bash
   curl -s -d "Phase 12 complete — Cadillac theme system. HSL native, all 21 themes working, zero purging." ntfy.sh/p9SKpYzY70LlyK1N
   ```

## Verification Checklist

After all chunks:
- [ ] `grep -c 'data-theme' dist/assets/index-*.css` shows 20+ (all themes in output)
- [ ] No `--color-` arbitrary syntax remaining in any component
- [ ] Theme picker in Settings switches colors live
- [ ] All 21 themes render correctly (spot-check: Dracula, Nord, GitHub Light)
- [ ] Light themes have readable text (not white-on-white)
- [ ] Build clean, all tests pass
- [ ] Deployed to mbair, healthz green
