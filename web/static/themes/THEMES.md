# Themes

chatwire's web UI is themeable via CSS custom properties. Each theme is a
small file that sets `--app-*` variables; the bridge file
(`_bridge.css`) propagates those onto Shoelace's `--sl-*` tokens so
custom CSS and Shoelace components stay coherent.

Themes are picked up via the `data-theme` attribute on `<html>`, which
the server emits from the `web.theme` key in `config.json`:

```html
<html data-theme="dracula">
```

To pick a theme today, set `web.theme` to a slug from the table below
and restart the web agent. A future "Appearance" step in the setup
wizard + a settings-panel switcher (see `docs/OPEN_SOURCE_PLAN.md`)
will surface this without hand-editing config.

## Shipped themes

| Slug | Source | License | Notes |
|------|--------|---------|-------|
| `default` | (chatwire-internal) | — | Current look. Pre-redesign placeholder. |
| `dracula` | <https://draculatheme.com/> | MIT | Dark, purple primary. |
| `nord` | <https://www.nordtheme.com/> | MIT | Dark, frost-blue primary. |
| `tokyo-night` | <https://github.com/folke/tokyonight.nvim> | MIT | Dark (night variant), blue primary. |
| `one-dark` | <https://github.com/atom/atom/tree/master/packages/one-dark-ui> | MIT | Atom's One Dark. |
| `one-light` | <https://github.com/atom/atom/tree/master/packages/one-dark-ui> | MIT | Atom's One Light sibling. |
| `night-owl` | <https://github.com/sdras/night-owl-vscode-theme> | MIT | Deep-blue dark. |
| `solarized-dark` | <https://ethanschoonover.com/solarized/> | MIT | Schoonover's dark variant, blue primary. |
| `solarized-light` | <https://ethanschoonover.com/solarized/> | MIT | Schoonover's light variant. |
| `gruvbox` | <https://github.com/morhetz/gruvbox> | MIT | Dark variant; warm orange primary. |
| `gruvbox-light` | <https://github.com/morhetz/gruvbox> | MIT | Light variant; warm orange primary. |
| `github-light` | <https://primer.style/foundations/color> | MIT | Primer Light defaults. |
| `github-dark` | <https://primer.style/foundations/color> | MIT | Primer Dark defaults. |
| `catppuccin-latte` | <https://catppuccin.com/> | MIT | Light flavor, mauve primary. |
| `catppuccin-frappe` | <https://catppuccin.com/> | MIT | Mid-dark flavor. |
| `catppuccin-macchiato` | <https://catppuccin.com/> | MIT | Darker than Frappé. |
| `catppuccin-mocha` | <https://catppuccin.com/> | MIT | Darkest, most popular variant. |
| `rose-pine` | <https://rosepinetheme.com/> | MIT | Main (dark) variant; iris primary. |
| `rose-pine-moon` | <https://rosepinetheme.com/> | MIT | Moon variant — softer dark; iris primary. |
| `rose-pine-dawn` | <https://rosepinetheme.com/> | MIT | Dawn variant — light; iris primary. |

## Roadmap (post-Phase 2 — pickups for later)

The original OPEN_SOURCE_PLAN catalog is fully ported. No pending
easy-win theme siblings remain — all Rosé Pine variants now shipped.

## Adding a new theme

1. Copy `default.css` to `<slug>.css`. Use the upstream name as the slug
   wherever possible (no renames — "dracula", not "vampire").
2. Replace the `--app-color-*` values with the theme's palette. The
   bridge handles propagation onto Shoelace components; usually no
   `--sl-*` overrides are needed.
3. Add a `<link rel="stylesheet" href="/static/themes/<slug>.css">`
   tag in the base templates, or load it dynamically based on
   `web.theme`.
4. Register the theme in the table above with its source URL and
   license. Per most theme licenses, "attribution + don't rename" is
   the entire compliance bar.

## Why no `prefers-color-scheme` selectors here

Themes are explicit choices, not auto-toggles. The wizard will surface
a `system` option that flips between a paired light/dark theme based
on `prefers-color-scheme`, but each individual theme file commits to
one mode. Easier to reason about, easier to debug.
