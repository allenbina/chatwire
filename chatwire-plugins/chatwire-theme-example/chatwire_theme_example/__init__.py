# ─────────────────────────────────────────────────────────────────────────────
# chatwire-theme-example  ·  Community theme plugin template
# ─────────────────────────────────────────────────────────────────────────────
#
# HOW IT WORKS
# ────────────
# Chatwire discovers theme plugins via the "chatwire.themes" entry-point group
# (declared in pyproject.toml).  When found, it reads two module-level
# attributes from this file:
#
#   SCHEMES  — list of dicts; each dict describes one color scheme.
#   CSS      — string of raw CSS injected into the browser <head>.
#
# The CSS is inserted AFTER the built-in schemes.css, so your rules win.
# The SCHEMES list is merged into the theme picker dropdown.
#
# QUICKSTART
# ──────────
# 1.  Copy this directory, rename it (e.g. chatwire-theme-midnight).
# 2.  Update pyproject.toml: change `name`, `description`, and the
#     entry-point key to match your package name.
# 3.  Edit SCHEMES and CSS below.
# 4.  Install locally: pip install -e ./chatwire-theme-midnight
# 5.  Restart Chatwire — your theme appears in Settings → Theme.
# 6.  Publish to PyPI: `hatch build && twine upload dist/*`
#     (or skip PyPI and install from git+https://...)
#
# COLOR FORMAT
# ────────────
# Chatwire uses Tailwind v4's space-separated HSL triplets WITHOUT the
# hsl() wrapper.  Example: "249 22% 12%"  (not "#1f1d30" or "hsl(249,22%,12%)").
# A quick converter: https://www.w3schools.com/colors/colors_hsl.asp
#
# REQUIRED CSS VARIABLES
# ──────────────────────
# Shadcn standard (must be defined):
#   --background        page background
#   --foreground        primary text
#   --card              card / panel background
#   --card-foreground   text on cards
#   --popover           dropdown / popover background
#   --popover-foreground
#   --primary           accent / button color
#   --primary-foreground
#   --secondary         secondary button / background
#   --secondary-foreground
#   --muted             subtle background (used for inactive areas)
#   --muted-foreground  subtle text
#   --accent            hover highlight background
#   --accent-foreground
#   --destructive       danger / delete color
#   --destructive-foreground
#   --border            border color
#   --input             input field border / background
#   --ring              focus ring color
#
# Sidebar tokens (sidebar uses these):
#   --sidebar           sidebar background
#   --sidebar-foreground
#   --sidebar-primary   active sidebar item highlight
#   --sidebar-primary-foreground
#   --sidebar-accent    hovered sidebar item background
#   --sidebar-accent-foreground
#   --sidebar-border    sidebar right-edge border
#   --sidebar-ring      focus ring inside sidebar
#
# Chatwire-specific:
#   --msg-me            sent-message bubble background
#   --msg-them          received-message bubble background
#   --msg-sms           SMS message bubble background
#   --msg-sms-text      SMS message bubble text color
#   --sidebar-bg        sidebar background (alias — keep in sync with --sidebar)
#   --success           success / online indicator
#   --warning           warning color
#   --info              informational color
#
# ─────────────────────────────────────────────────────────────────────────────

SCHEMES = [
    # Each dict must have: name, label, isLight, swatch
    #
    #   name     — CSS slug; must match the [data-theme="..."] selector below.
    #   label    — Human-readable name shown in the theme picker.
    #   isLight  — True for light themes, False for dark themes.
    #              Controls which picker section (Dark / Light) the theme appears in,
    #              and which slot it fills when Day/Night auto-switch is enabled.
    #   swatch   — Hex color shown as a dot in the picker (use your --primary color).
    {
        "name": "my-custom-theme",
        "label": "My Custom Theme",
        "isLight": False,
        "swatch": "#7c6af7",
    },
    # Add more variants here.  Each needs its own [data-theme="..."] block in CSS.
]

CSS = """\
/* ── my-custom-theme ─────────────────────────────────────────────────────── */
/* Replace all values below with your own HSL triplets.                       */
[data-theme="my-custom-theme"] {
  /* shadcn standard --------------------------------------------------------- */
  --background:                  240 10% 10%;
  --foreground:                  240 5% 90%;
  --card:                        240 8% 18%;
  --card-foreground:             240 5% 90%;
  --popover:                     240 8% 18%;
  --popover-foreground:          240 5% 90%;
  --primary:                     258 80% 70%;
  --primary-foreground:          240 10% 10%;
  --secondary:                   240 8% 24%;
  --secondary-foreground:        240 5% 90%;
  --muted:                       240 8% 14%;
  --muted-foreground:            240 5% 55%;
  --accent:                      240 8% 24%;
  --accent-foreground:           240 5% 90%;
  --destructive:                 0 72% 60%;
  --destructive-foreground:      240 5% 90%;
  --border:                      240 8% 24%;
  --input:                       240 8% 24%;
  --ring:                        258 80% 70%;
  /* sidebar (shadcn sidebar tokens) ---------------------------------------- */
  --sidebar:                     240 8% 14%;
  --sidebar-foreground:          240 5% 90%;
  --sidebar-primary:             258 80% 70%;
  --sidebar-primary-foreground:  240 10% 10%;
  --sidebar-accent:              240 8% 24%;
  --sidebar-accent-foreground:   240 5% 90%;
  --sidebar-border:              240 8% 24%;
  --sidebar-ring:                258 80% 70%;
  /* Chatwire-specific ------------------------------------------------------- */
  --msg-me:                      240 8% 22%;
  --msg-them:                    240 8% 18%;
  --msg-sms:                     258 40% 65%;
  --msg-sms-text:                240 10% 10%;
  --sidebar-bg:                  240 8% 14%;
  --success:                     142 60% 55%;
  --warning:                     38 90% 60%;
  --info:                        200 70% 55%;
}

/* Add more [data-theme="..."] blocks here for additional variants. */
"""
