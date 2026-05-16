# chatwire-theme-rosepine
# Rosé Pine color family — three variants:
#   rose-pine       dark (original)
#   rose-pine-moon  dark (slightly lighter)
#   rose-pine-dawn  light
#
# Registered via the chatwire.themes entry-point group.
# The Chatwire host reads SCHEMES for the picker UI and CSS for injection.

SCHEMES = [
    {
        "name": "rose-pine",
        "label": "Rosé Pine",
        "isLight": False,
        "swatch": "#c4a7e7",
    },
    {
        "name": "rose-pine-moon",
        "label": "Rosé Pine Moon",
        "isLight": False,
        "swatch": "#c4a7e7",
    },
    {
        "name": "rose-pine-dawn",
        "label": "Rosé Pine Dawn",
        "isLight": True,
        "swatch": "#907aa9",
    },
]

CSS = """\
/* ── rose-pine ───────────────────────────────────────────────────────────── */
[data-theme="rose-pine"] {
  /* shadcn standard */
  --background:                  249 22% 12%;
  --foreground:                  245 50% 91%;
  --card:                        249 15% 28%;
  --card-foreground:             245 50% 91%;
  --popover:                     249 15% 28%;
  --popover-foreground:          245 50% 91%;
  --primary:                     267 57% 78%;
  --primary-foreground:          249 22% 12%;
  --secondary:                   249 15% 28%;
  --secondary-foreground:        245 50% 91%;
  --muted:                       247 23% 15%;
  --muted-foreground:            248 15% 61%;
  --accent:                      249 15% 28%;
  --accent-foreground:           245 50% 91%;
  --destructive:                 343 76% 68%;
  --destructive-foreground:      245 50% 91%;
  --border:                      249 15% 28%;
  --input:                       249 15% 28%;
  --ring:                        267 57% 78%;
  /* Sidebar (shadcn sidebar tokens) */
  --sidebar:                     247 23% 15%;
  --sidebar-foreground:          245 50% 91%;
  --sidebar-primary:             267 57% 78%;
  --sidebar-primary-foreground:  249 22% 12%;
  --sidebar-accent:              249 15% 28%;
  --sidebar-accent-foreground:   245 50% 91%;
  --sidebar-border:              249 15% 28%;
  --sidebar-ring:                267 57% 78%;
  /* Chatwire-specific */
  --msg-me:                      248 25% 18%;
  --msg-them:                    248 25% 18%;
  --msg-sms:                     189 43% 73%;
  --msg-sms-text:                249 22% 12%;
  --sidebar-bg:                  247 23% 15%;
  --success:                     189 43% 73%;
  --warning:                     35 88% 72%;
  --info:                        197 49% 38%;
}

/* ── rose-pine-dawn ──────────────────────────────────────────────────────── */
[data-theme="rose-pine-dawn"] {
  /* shadcn standard */
  --background:                  32 57% 95%;
  --foreground:                  248 19% 40%;
  --card:                        315 4% 80%;
  --card-foreground:             248 19% 40%;
  --popover:                     315 4% 80%;
  --popover-foreground:          248 19% 40%;
  --primary:                     268 21% 57%;
  --primary-foreground:          32 57% 95%;
  --secondary:                   315 4% 80%;
  --secondary-foreground:        248 19% 40%;
  --muted:                       28 40% 92%;
  --muted-foreground:            248 12% 52%;
  --accent:                      315 4% 80%;
  --accent-foreground:           248 19% 40%;
  --destructive:                 343 35% 55%;
  --destructive-foreground:      248 19% 40%;
  --border:                      315 4% 80%;
  --input:                       315 4% 80%;
  --ring:                        268 21% 57%;
  /* Sidebar (shadcn sidebar tokens) */
  --sidebar:                     28 40% 92%;
  --sidebar-foreground:          248 19% 40%;
  --sidebar-primary:             268 21% 57%;
  --sidebar-primary-foreground:  32 57% 95%;
  --sidebar-accent:              315 4% 80%;
  --sidebar-accent-foreground:   248 19% 40%;
  --sidebar-border:              315 4% 80%;
  --sidebar-ring:                268 21% 57%;
  /* Chatwire-specific */
  --msg-me:                      30 27% 90%;
  --msg-them:                    28 40% 92%;
  --msg-sms:                     197 53% 34%;
  --msg-sms-text:                0 0% 100%;
  --sidebar-bg:                  28 40% 92%;
  --success:                     197 53% 34%;
  --warning:                     35 81% 56%;
  --info:                        189 30% 48%;
}

/* ── rose-pine-moon ──────────────────────────────────────────────────────── */
[data-theme="rose-pine-moon"] {
  /* shadcn standard */
  --background:                  246 24% 17%;
  --foreground:                  245 50% 91%;
  --card:                        247 16% 30%;
  --card-foreground:             245 50% 91%;
  --popover:                     247 16% 30%;
  --popover-foreground:          245 50% 91%;
  --primary:                     267 57% 78%;
  --primary-foreground:          246 24% 17%;
  --secondary:                   247 16% 30%;
  --secondary-foreground:        245 50% 91%;
  --muted:                       248 24% 20%;
  --muted-foreground:            248 15% 61%;
  --accent:                      247 16% 30%;
  --accent-foreground:           245 50% 91%;
  --destructive:                 343 76% 68%;
  --destructive-foreground:      245 50% 91%;
  --border:                      247 16% 30%;
  --input:                       247 16% 30%;
  --ring:                        267 57% 78%;
  /* Sidebar (shadcn sidebar tokens) */
  --sidebar:                     248 24% 20%;
  --sidebar-foreground:          245 50% 91%;
  --sidebar-primary:             267 57% 78%;
  --sidebar-primary-foreground:  246 24% 17%;
  --sidebar-accent:              247 16% 30%;
  --sidebar-accent-foreground:   245 50% 91%;
  --sidebar-border:              247 16% 30%;
  --sidebar-ring:                267 57% 78%;
  /* Chatwire-specific */
  --msg-me:                      248 21% 26%;
  --msg-them:                    248 21% 26%;
  --msg-sms:                     189 43% 73%;
  --msg-sms-text:                246 24% 17%;
  --sidebar-bg:                  248 24% 20%;
  --success:                     189 43% 73%;
  --warning:                     35 88% 72%;
  --info:                        197 48% 47%;
}
"""
