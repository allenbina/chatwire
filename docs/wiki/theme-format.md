# Chatwire Theme Package Format

Theme packages are JSON files placed in `~/.chatwire/themes/`. Each file describes
a set of visual overrides — colors, structure, decorations, and optional custom CSS —
that Chatwire applies on top of any base theme.

## File naming

Files must end in `.json`. The `name` field inside the JSON (not the filename) is
used as the identifier in the UI and as the `data-theme-pack` CSS attribute.

```
~/.chatwire/themes/
  my-dark-theme.json
  compact-mono.json
```

## Top-level schema

All fields are optional except `name`.

```json
{
  "name":       "my-theme",
  "author":     "Your Name",
  "version":    "1.0.0",
  "colors":     { ... },
  "structure":  { ... },
  "decorations":{ ... },
  "custom_css": "..."
}
```

| Field        | Type   | Required | Description |
|--------------|--------|----------|-------------|
| `name`       | string | **yes**  | Lowercase kebab-case slug (`[a-z0-9][a-z0-9-]*`). Used as CSS selector. |
| `author`     | string | no       | Display name shown in the UI. |
| `version`    | string | no       | Semver string, shown in the UI. |
| `colors`     | object | no       | CSS color variable overrides. |
| `structure`  | object | no       | Spacing, radius, and font overrides. |
| `decorations`| object | no       | Avatar, bubble, and shadow overrides. |
| `custom_css` | string | no       | Arbitrary CSS injected into the document. |

A colors-only pack is valid. A structure-only pack is valid. All sections can
be combined freely.

---

## `colors` section

Maps semantic color token names to CSS color values. Any valid CSS color syntax
works: hex, `rgb()`, `hsl()`, color names, etc.

| Key                    | Used for |
|------------------------|----------|
| `background`           | App background |
| `foreground`           | Default text color |
| `card`                 | Card / panel background |
| `card-foreground`      | Text on cards |
| `popover`              | Dropdown / popover background |
| `popover-foreground`   | Text in popovers |
| `primary`              | Primary action color (buttons, highlights) |
| `primary-foreground`   | Text on primary-colored elements |
| `secondary`            | Secondary UI elements |
| `secondary-foreground` | Text on secondary elements |
| `muted`                | Muted background (subtle panels) |
| `muted-foreground`     | Muted / de-emphasized text |
| `accent`               | Accent highlights |
| `accent-foreground`    | Text on accent elements |
| `destructive`          | Destructive action color (delete, error) |
| `destructive-foreground` | Text on destructive elements |
| `border`               | Border color |
| `input`                | Input field background |
| `ring`                 | Focus ring color |
| `sidebar-bg`           | Sidebar background (can differ from `background`) |
| `info`                 | Info state color |
| `warning`              | Warning state color |
| `success`              | Success state color |
| `msg-me`               | Sent message bubble background |
| `msg-me-text`          | Sent message text color |
| `msg-them`             | Received message bubble background |
| `msg-them-text`        | Received message text color |
| `msg-sms`              | SMS/RCS message bubble background |
| `msg-sms-text`         | SMS/RCS message text color |

Example:

```json
"colors": {
  "background": "#0d1117",
  "foreground": "#c9d1d9",
  "primary": "#58a6ff",
  "msg-me": "#1f6feb",
  "msg-me-text": "#ffffff"
}
```

---

## `structure` section

Controls spacing, sizing, and typography. Values must be valid CSS length/value
strings (e.g. `0.5rem`, `8px`, `1`).

| Key                  | Used for |
|----------------------|----------|
| `radius`             | Base border-radius for UI elements |
| `radius-bubble`      | Message bubble corner radius |
| `radius-input`       | Input field corner radius |
| `spacing-message`    | Vertical gap between messages |
| `spacing-sidebar`    | Vertical gap between sidebar items |
| `font-size-message`  | Message text font size |
| `font-size-sidebar`  | Sidebar text font size |
| `shadow-card`        | Box shadow for cards |
| `sidebar-width`      | Sidebar panel width |

Example:

```json
"structure": {
  "radius-bubble": "4px",
  "spacing-message": "2px",
  "font-size-message": "0.9rem",
  "sidebar-width": "280px"
}
```

---

## `decorations` section

Fine-grained visual details.

| Key                | Used for |
|--------------------|----------|
| `avatar-shape`     | Avatar border-radius (use `50%` for circles, `0` for squares) |
| `avatar-size`      | Avatar width/height |
| `avatar-border`    | CSS border for avatars |
| `bubble-shadow`    | Box shadow on message bubbles |
| `bubble-tail`      | Custom CSS for the message tail decoration |
| `header-shadow`    | Box shadow on the chat header bar |
| `header-border`    | Border on the chat header bar |
| `sidebar-divider`  | Divider between sidebar items |
| `border-width`     | Global border width |
| `transition-speed` | Animation/transition duration |

Example:

```json
"decorations": {
  "avatar-shape": "8px",
  "bubble-shadow": "0 2px 6px rgba(0,0,0,0.25)",
  "transition-speed": "150ms"
}
```

---

## `custom_css` section

A string of arbitrary CSS injected verbatim into a `<style>` block.
Use this for anything not covered by the variable system.

```json
"custom_css": ".message-timestamp { font-style: italic; }"
```

### Security restrictions

Chatwire automatically sanitizes `custom_css` before injection:

- **`@import` rules are stripped** — external stylesheets cannot be loaded.
- **`url()` references to `http://` or `https://` URLs are replaced with
  `url(about:blank)`** — prevents tracking pixels and external network requests.

Everything else (selectors, animations, custom properties, `var()`, etc.)
is preserved unchanged. If sanitization occurs, the UI shows a notice:
_"This theme includes custom CSS (some external references were sanitized)."_

`data:` URIs and fragment references (`url(#id)`) are always preserved.

---

## How themes are activated

1. Drop your `.json` file into `~/.chatwire/themes/`.
2. Open Settings → **Theme Packages**.
3. Select the package from the dropdown.
4. The package CSS is injected and the `data-theme-pack="<name>"` attribute
   is set on `<html>`, activating all variable overrides.
5. Individual accent-color or custom-CSS overrides in Settings still take
   precedence over theme-pack variables.

---

## Sharing themes

Theme packages are self-contained JSON files. Share them as-is.
Recipients place the file in `~/.chatwire/themes/` and restart or reload.

See `docs/examples/` for ready-to-use example packs.
