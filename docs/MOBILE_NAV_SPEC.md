# Mobile Navigation Redesign

> Spec drafted 2026-05-15. Implements in the next phase after current plugin work.

## Summary

Replace the hamburger + slide-over drawer mobile navigation with a **stack-based
full-screen model**. The conversations list becomes the home screen. Tapping a
conversation or footer link navigates to a full-screen page with a back button
in the header. Swipe-from-left-edge gesture provides an alternative back action.

Desktop (>= 768px) is **unchanged** — two-panel sidebar + main layout.

## Current state (what changes)

| Element | Current behavior | New behavior |
|---|---|---|
| Hamburger button (☰) | Opens Sheet drawer over chat | **Removed** |
| "Chatwire" branding bar | Shown on mobile above chat | **Removed** |
| Sidebar Sheet (slide-over) | Overlays main content, partial width | **Removed** — conversations list is full-screen home |
| `← Back` links (Logs, Plugins) | Top-left text link, inconsistent across pages | **Removed** — replaced by unified header back button |
| Mobile close button (✕ in sidebar) | Closes Sheet drawer | **Removed** — no drawer to close |

## Navigation model

```
/ (Conversations list — home screen, full-screen, no header)
├── /chat/:handle   → full-screen conversation, back → /
├── /chat/:guid     → full-screen group conversation, back → /
├── /settings       → full-screen settings, back → /
├── /logs           → full-screen logs, back → /
├── /plugins        → full-screen plugins, back → /
└── /debug          → full-screen debug/style guide, back → /
```

All back navigation goes to `/`. No multi-level back stack. Simple and predictable.

## Conversations list (home screen)

- **No header.** The conversation list starts at the top of the viewport.
- Full-screen, edge-to-edge.
- Scrollable conversation list with plugin slot (`sidebar.panel`) below it.
- Hiatus banner and offline banner render above the footer (same as current).
- **Sticky footer** at bottom: settings, plugins, appearance, logs, mark-all-read,
  theme toggle, pinned setting toggles, logout. Same content as current sidebar
  footer — no changes to the footer itself.

## Sub-pages (conversation, settings, logs, plugins, debug)

Every page that is not the conversations list has a header bar. Each header gets
a **back button on the left side** on mobile (< 768px). The back button navigates
to `/`.

- **Mobile only** (`md:hidden`). On desktop the sidebar is always visible so back
  is unnecessary. This keeps it simple — one CSS class controls visibility, no
  conditional logic.
- Back button is a `<Link to="/">` with a left-chevron or `←` icon.
- Each page keeps its existing header content (page title, status indicators, etc.)
  — the back button is prepended to the left side.

### Conversation view header

```
┌───────────────────────────────┐
│ ←  Jane Williams    📌 ...   │  ← back button added left of contact name
│───────────────────────────────│
│                               │
│   message bubbles             │
│                               │
│   [compose box]               │
└───────────────────────────────┘
```

### Settings / Logs / Plugins header

```
┌───────────────────────────────┐
│ ←  Settings                   │  ← back button replaces old `← Back` text
│───────────────────────────────│
│                               │
│   page content                │
│                               │
└───────────────────────────────┘
```

## Swipe-from-left-edge gesture

- Swipe from the left edge of the screen navigates to `/`.
- Active on mobile only (< 768px).
- Active on all sub-pages (not on the conversations list itself).
- Touch start must begin within ~20px of the left edge.
- Drag threshold: ~75px horizontal movement before committing the navigation.
- Optional: subtle slide-right animation (150-200ms) on the current view during
  the swipe to give tactile feedback. Can be deferred to a polish pass.
- Does not conflict with fullscreen photo overlay (which uses swipe-down-to-dismiss
  on the Y axis).

## Implementation approach

All changes are in the existing codebase — no new routes, no separate mobile app.

### Layout.tsx changes

1. **Remove** the mobile top bar (hamburger + "Chatwire" branding), lines ~437-446.
2. **Remove** the Sheet (mobile sidebar drawer), lines ~418-429.
3. **Remove** the mobile close button (✕) in SidebarContent.
4. On mobile (< 768px), **conditionally render** based on current route:
   - If route is `/` → render `<SidebarContent />` as full-screen (with footer).
   - If route is anything else → render `{children}` (the sub-page) full-screen.
5. On desktop (>= 768px), behavior is unchanged: sidebar + main side-by-side.

### Sub-page header changes

Each page adds a mobile back button to its header:

- `ChatPage.tsx` — add `←` link before contact name/avatar in the header.
- `SettingsPage.tsx` — add `←` link in header (currently has no back button).
- `LogsPage.tsx` — replace `← Back` text link with consistent back button.
- `PluginsPage.tsx` — replace `← Back` text link with consistent back button.
- `DebugPage.tsx` — add `←` link in a new minimal header.

All back buttons: `<Link to="/" className="md:hidden ...">`.

### Shared BackButton component (optional)

Could extract a small reusable component:

```tsx
function MobileBackButton() {
  return (
    <Link
      to="/"
      className="md:hidden p-2 -ml-2 text-muted-foreground hover:text-foreground transition-colors"
      aria-label="Back to conversations"
    >
      <ChevronLeft style={{ width: 'var(--icon-size-md)', height: 'var(--icon-size-md)' }} />
    </Link>
  )
}
```

### Swipe gesture hook

New hook `useSwipeBack()` — attaches touch listeners to the page container:

```tsx
function useSwipeBack(enabled: boolean) {
  // touchstart within 20px of left edge → track
  // touchmove > 75px horizontal → navigate('/')
  // Cleanup on unmount
}
```

Applied in Layout.tsx for sub-pages, or in each page individually.

### Store changes

- `sidebarOpen` / `setSidebarOpen` in the Zustand store become unused on mobile.
  Keep them for now (desktop Sheet is removed, desktop sidebar is always visible).
  Can clean up in a follow-up.

## Breakpoint

Uses the existing Tailwind `md:` breakpoint (768px). No changes.

- iPhone (any): mobile layout
- iPad Mini portrait (744px): mobile layout
- iPad Air/Pro portrait (820px+): desktop layout
- iPad landscape: desktop layout
- Desktop browser: desktop layout
- Narrow desktop window (< 768px): mobile layout

## Scope exclusions

- **Popout page** (`/popout`): not affected — standalone chat window, no Layout.
- **Fullscreen photo overlay**: not a route, not affected. Keeps its own ✕ close
  button. Swipe-down-to-dismiss is a separate enhancement (not in this spec).
- **Transition animations**: nice-to-have slide animation during swipe. Can be
  deferred to a polish pass. Initial implementation uses instant navigation.
- **PWA standalone mode**: the back button becomes the only way to navigate back
  (no Safari chrome). This spec covers that — the header back button is always
  visible on mobile sub-pages.

## Testing

- Vitest: update Layout tests if they exist; verify MobileBackButton renders
  only on mobile (mock matchMedia or test CSS class presence).
- Manual QA on mbair: test in Safari (phone width), confirm:
  - Conversations list renders full-screen with no header
  - Tapping conversation navigates to full-screen chat with back in header
  - Back button returns to conversations list
  - Settings/logs/plugins all have back button
  - Swipe from left edge navigates back
  - Desktop layout is unchanged
  - Browser back button works (route-based gives this for free)
  - PWA standalone mode: back button works without Safari chrome
