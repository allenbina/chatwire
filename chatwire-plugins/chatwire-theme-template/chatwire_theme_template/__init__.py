"""chatwire-theme-template — Community template for Chatwire color-scheme plugins.

=== HOW IT WORKS ===

Chatwire discovers theme plugins via the ``chatwire.themes`` entry-point group
(see pyproject.toml).  On startup, the web server loads each registered module
and reads two top-level attributes:

  SCHEMES — list of dicts, one per color variant the plugin ships.
            Each dict must have: name, label, isLight, swatch.

  CSS     — a CSS string with ``[data-theme="<slug>"] { … }`` blocks.
            Injected into the browser *after* built-in schemes.css so your
            variables override any defaults with the same name.

The browser receives both from ``GET /api/ui/plugin-themes``.  It injects
the CSS and merges SCHEMES into the theme-picker dropdown.  When the plugin
is uninstalled, the schemes disappear and users fall back to the default.

=== HOW TO SHIP YOUR OWN THEME ===

1.  Copy this file and pyproject.toml.
2.  Rename the package (e.g., chatwire-theme-mycolor).
3.  Fill in your colors below.
4.  Publish to PyPI:  pipx run build && twine upload dist/*

Community themes show up in the Chatwire marketplace when you open a PR
to add your package to plugins.json in allenbina/chatwire-dev.

=== COLOR FORMAT ===

All values use space-separated HSL triplets WITHOUT hsl() wrapper:
    --background: 220 16% 22%;   ← correct (Tailwind v4 format)
    --background: hsl(220, 16%, 22%);  ← WRONG

=== REQUIRED VARIABLES ===

shadcn core:
    --background, --foreground
    --card, --card-foreground
    --popover, --popover-foreground
    --primary, --primary-foreground
    --secondary, --secondary-foreground
    --muted, --muted-foreground
    --accent, --accent-foreground
    --destructive, --destructive-foreground
    --border, --input, --ring

shadcn sidebar tokens (used by Chatwire's sidebar):
    --sidebar, --sidebar-foreground
    --sidebar-primary, --sidebar-primary-foreground
    --sidebar-accent, --sidebar-accent-foreground
    --sidebar-border, --sidebar-ring

Chatwire-specific:
    --msg-me         — background of outgoing message bubbles
    --msg-them       — background of incoming message bubbles
    --msg-sms        — accent color for SMS-flagged bubbles
    --msg-sms-text   — text color inside SMS bubbles
    --sidebar-bg     — sidebar background (mirrors --sidebar)
    --success        — positive status color
    --warning        — caution status color
    --info           — informational status color
"""

# ---------------------------------------------------------------------------
# SCHEMES — one entry per color variant you ship
# ---------------------------------------------------------------------------
# Required keys per dict:
#   name     — CSS slug, must match [data-theme="<slug>"] in CSS below
#   label    — human-readable name shown in the theme picker
#   isLight  — True for light themes, False for dark themes
#   swatch   — hex color shown as the accent dot in the picker (#rrggbb)
# ---------------------------------------------------------------------------

SCHEMES = [
    {
        "name": "my-dark-theme",
        "label": "My Dark Theme",
        "isLight": False,
        "swatch": "#7c3aed",         # pick a representative accent color
    },
    # Add more variants here, e.g. a light sibling:
    # {
    #     "name": "my-light-theme",
    #     "label": "My Light Theme",
    #     "isLight": True,
    #     "swatch": "#6d28d9",
    # },
]

# ---------------------------------------------------------------------------
# CSS — one [data-theme="<slug>"] block per entry in SCHEMES above
# ---------------------------------------------------------------------------

CSS = """\
/* ── my-dark-theme ──────────────────────────────────────────────────────── */
[data-theme="my-dark-theme"] {
  /* Core — replace all values with your colors (space-separated HSL, no hsl()) */
  --background:                  220 16% 22%;   /* main page background      */
  --foreground:                  218 27% 94%;   /* main text                 */
  --card:                        220 16% 36%;   /* card / panel surface      */
  --card-foreground:             218 27% 94%;
  --popover:                     220 16% 36%;
  --popover-foreground:          218 27% 94%;
  --primary:                     193 43% 67%;   /* accent / link color       */
  --primary-foreground:          220 16% 22%;
  --secondary:                   220 16% 36%;
  --secondary-foreground:        218 27% 94%;
  --muted:                       221 16% 19%;   /* subtle background         */
  --muted-foreground:            218 16% 71%;   /* de-emphasized text        */
  --accent:                      220 16% 36%;
  --accent-foreground:           218 27% 94%;
  --destructive:                 354 42% 56%;   /* error / danger            */
  --destructive-foreground:      218 27% 94%;
  --border:                      220 16% 36%;
  --input:                       220 16% 36%;
  --ring:                        193 43% 67%;

  /* Sidebar */
  --sidebar:                     221 16% 19%;
  --sidebar-foreground:          218 27% 94%;
  --sidebar-primary:             193 43% 67%;
  --sidebar-primary-foreground:  220 16% 22%;
  --sidebar-accent:              220 16% 36%;
  --sidebar-accent-foreground:   218 27% 94%;
  --sidebar-border:              220 16% 36%;
  --sidebar-ring:                193 43% 67%;

  /* Chatwire-specific */
  --msg-me:                      222 16% 28%;   /* outgoing bubble bg        */
  --msg-them:                    222 16% 28%;   /* incoming bubble bg        */
  --msg-sms:                     92 28% 65%;    /* SMS accent (green-ish)    */
  --msg-sms-text:                220 16% 22%;
  --sidebar-bg:                  221 16% 19%;
  --success:                     92 28% 65%;
  --warning:                     40 71% 73%;
  --info:                        210 34% 63%;
}
"""
