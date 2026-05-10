#!/usr/bin/env python3
"""
Generate web/frontend/src/styles/schemes.css with HSL-native values.

Tailwind v4 purges [data-theme="..."] blocks that contain hex values.
HSL custom property definitions are not purged — they're just properties.
This script converts all theme hex colors to HSL and emits the new CSS.
"""

OUTPUT = "web/frontend/src/styles/schemes.css"


def hex_to_hsl(h):
    h = h.lstrip("#")
    r, g, b = int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255
    mx, mn = max(r, g, b), min(r, g, b)
    lum = (mx + mn) / 2
    if mx == mn:
        return f"0 0% {lum * 100:.0f}%"
    d = mx - mn
    s = d / (2 - mx - mn) if lum > 0.5 else d / (mx + mn)
    if mx == r:
        hue = ((g - b) / d + (6 if g < b else 0)) / 6
    elif mx == g:
        hue = ((b - r) / d + 2) / 6
    else:
        hue = ((r - g) / d + 4) / 6
    return f"{hue * 360:.0f} {s * 100:.0f}% {lum * 100:.0f}%"


# Each theme: (selector, is_root, colors_dict)
# Colors keys:
#   bg_primary, bg_secondary, bg_tertiary
#   text_primary, text_muted
#   accent, primary_fg
#   success, warning, error, info
#   border, msg_me, msg_them
#   sidebar_bg, sidebar_active
THEMES = [
    (":root,\n[data-theme=\"dracula\"]", {
        "bg_primary":     "#282a36",
        "bg_secondary":   "#44475a",
        "bg_tertiary":    "#21222c",
        "text_primary":   "#f8f8f2",
        "text_muted":     "#a8a8a2",
        "accent":         "#bd93f9",
        "primary_fg":     "#282a36",
        "success":        "#50fa7b",
        "warning":        "#f1fa8c",
        "error":          "#ff5555",
        "info":           "#8be9fd",
        "border":         "#44475a",
        "msg_me":         "#343746",
        "msg_them":       "#44475a",
        "sidebar_bg":     "#21222c",
        "sidebar_active": "#44475a",
    }),
    ("[data-theme=\"default\"]", {
        "bg_primary":     "#f7f7f8",
        "bg_secondary":   "#d4d4d8",
        "bg_tertiary":    "#fafbfc",
        "text_primary":   "#111827",
        "text_muted":     "#6b7280",
        "accent":         "#3b82f6",
        "primary_fg":     "#ffffff",
        "success":        "#137333",
        "warning":        "#795700",
        "error":          "#b91c1c",
        "info":           "#0ea5e9",
        "border":         "#d4d4d8",
        "msg_me":         "#eef2ff",
        "msg_them":       "#e5e5ea",
        "sidebar_bg":     "#fafbfc",
        "sidebar_active": "#d4d4d8",
    }),
    ("[data-theme=\"catppuccin-frappe\"]", {
        "bg_primary":     "#303446",
        "bg_secondary":   "#51576d",
        "bg_tertiary":    "#292c3c",
        "text_primary":   "#c6d0f5",
        "text_muted":     "#a5adce",
        "accent":         "#ca9ee6",
        "primary_fg":     "#303446",
        "success":        "#a6d189",
        "warning":        "#e5c890",
        "error":          "#e78284",
        "info":           "#99d1db",
        "border":         "#51576d",
        "msg_me":         "#414559",
        "msg_them":       "#414559",
        "sidebar_bg":     "#292c3c",
        "sidebar_active": "#51576d",
    }),
    ("[data-theme=\"catppuccin-latte\"]", {
        "bg_primary":     "#eff1f5",
        "bg_secondary":   "#bcc0cc",
        "bg_tertiary":    "#e6e9ef",
        "text_primary":   "#4c4f69",
        "text_muted":     "#6c6f85",
        "accent":         "#8839ef",
        "primary_fg":     "#ffffff",
        "success":        "#40a02b",
        "warning":        "#df8e1d",
        "error":          "#d20f39",
        "info":           "#04a5e5",
        "border":         "#bcc0cc",
        "msg_me":         "#ccd0da",
        "msg_them":       "#ccd0da",
        "sidebar_bg":     "#e6e9ef",
        "sidebar_active": "#bcc0cc",
    }),
    ("[data-theme=\"catppuccin-macchiato\"]", {
        "bg_primary":     "#24273a",
        "bg_secondary":   "#494d64",
        "bg_tertiary":    "#1e2030",
        "text_primary":   "#cad3f5",
        "text_muted":     "#a5adcb",
        "accent":         "#c6a0f6",
        "primary_fg":     "#24273a",
        "success":        "#a6da95",
        "warning":        "#eed49f",
        "error":          "#ed8796",
        "info":           "#91d7e3",
        "border":         "#494d64",
        "msg_me":         "#363a4f",
        "msg_them":       "#363a4f",
        "sidebar_bg":     "#1e2030",
        "sidebar_active": "#494d64",
    }),
    ("[data-theme=\"catppuccin-mocha\"]", {
        "bg_primary":     "#1e1e2e",
        "bg_secondary":   "#45475a",
        "bg_tertiary":    "#181825",
        "text_primary":   "#cdd6f4",
        "text_muted":     "#a6adc8",
        "accent":         "#cba6f7",
        "primary_fg":     "#1e1e2e",
        "success":        "#a6e3a1",
        "warning":        "#f9e2af",
        "error":          "#f38ba8",
        "info":           "#89dceb",
        "border":         "#45475a",
        "msg_me":         "#313244",
        "msg_them":       "#313244",
        "sidebar_bg":     "#181825",
        "sidebar_active": "#45475a",
    }),
    ("[data-theme=\"github-dark\"]", {
        "bg_primary":     "#0d1117",
        "bg_secondary":   "#3d444d",
        "bg_tertiary":    "#010409",
        "text_primary":   "#f0f6fc",
        "text_muted":     "#9198a1",
        "accent":         "#4493f8",
        "primary_fg":     "#0d1117",
        "success":        "#3fb950",
        "warning":        "#d29922",
        "error":          "#f85149",
        "info":           "#4493f8",
        "border":         "#3d444d",
        "msg_me":         "#151b23",
        "msg_them":       "#151b23",
        "sidebar_bg":     "#010409",
        "sidebar_active": "#3d444d",
    }),
    ("[data-theme=\"github-light\"]", {
        "bg_primary":     "#ffffff",
        "bg_secondary":   "#d1d9e0",
        "bg_tertiary":    "#f6f8fa",
        "text_primary":   "#1f2328",
        "text_muted":     "#6e7781",
        "accent":         "#0969da",
        "primary_fg":     "#ffffff",
        "success":        "#1a7f37",
        "warning":        "#9a6700",
        "error":          "#d1242f",
        "info":           "#0969da",
        "border":         "#d1d9e0",
        "msg_me":         "#eaeef2",
        "msg_them":       "#eaeef2",
        "sidebar_bg":     "#f6f8fa",
        "sidebar_active": "#d1d9e0",
    }),
    ("[data-theme=\"gruvbox\"]", {
        "bg_primary":     "#282828",
        "bg_secondary":   "#504945",
        "bg_tertiary":    "#1d2021",
        "text_primary":   "#ebdbb2",
        "text_muted":     "#a89984",
        "accent":         "#d65d0e",
        "primary_fg":     "#282828",
        "success":        "#b8bb26",
        "warning":        "#fabd2f",
        "error":          "#fb4934",
        "info":           "#83a598",
        "border":         "#504945",
        "msg_me":         "#3c3836",
        "msg_them":       "#3c3836",
        "sidebar_bg":     "#1d2021",
        "sidebar_active": "#504945",
    }),
    ("[data-theme=\"gruvbox-light\"]", {
        "bg_primary":     "#fbf1c7",
        "bg_secondary":   "#d5c4a1",
        "bg_tertiary":    "#f9f5d7",
        "text_primary":   "#3c3836",
        "text_muted":     "#7c6f64",
        "accent":         "#af3a03",
        "primary_fg":     "#fbf1c7",
        "success":        "#79740e",
        "warning":        "#b57614",
        "error":          "#9d0006",
        "info":           "#458588",
        "border":         "#d5c4a1",
        "msg_me":         "#f2e5bc",
        "msg_them":       "#f2e5bc",
        "sidebar_bg":     "#f9f5d7",
        "sidebar_active": "#d5c4a1",
    }),
    ("[data-theme=\"night-owl\"]", {
        "bg_primary":     "#011627",
        "bg_secondary":   "#1d3b53",
        "bg_tertiary":    "#010d1a",
        "text_primary":   "#d6deeb",
        "text_muted":     "#8a93ad",
        "accent":         "#82aaff",
        "primary_fg":     "#011627",
        "success":        "#addb67",
        "warning":        "#ecc48d",
        "error":          "#ff5874",
        "info":           "#7fdbca",
        "border":         "#1d3b53",
        "msg_me":         "#0e293f",
        "msg_them":       "#1d3b53",
        "sidebar_bg":     "#010d1a",
        "sidebar_active": "#1d3b53",
    }),
    ("[data-theme=\"nord\"]", {
        "bg_primary":     "#2e3440",
        "bg_secondary":   "#4c566a",
        "bg_tertiary":    "#292e39",
        "text_primary":   "#eceff4",
        "text_muted":     "#a8b1c0",
        "accent":         "#88c0d0",
        "primary_fg":     "#2e3440",
        "success":        "#a3be8c",
        "warning":        "#ebcb8b",
        "error":          "#bf616a",
        "info":           "#81a1c1",
        "border":         "#4c566a",
        "msg_me":         "#3b4252",
        "msg_them":       "#3b4252",
        "sidebar_bg":     "#292e39",
        "sidebar_active": "#4c566a",
    }),
    ("[data-theme=\"one-dark\"]", {
        "bg_primary":     "#282c34",
        "bg_secondary":   "#3e4451",
        "bg_tertiary":    "#21252b",
        "text_primary":   "#abb2bf",
        "text_muted":     "#828997",
        "accent":         "#61afef",
        "primary_fg":     "#282c34",
        "success":        "#98c379",
        "warning":        "#e5c07b",
        "error":          "#e06c75",
        "info":           "#56b6c2",
        "border":         "#3e4451",
        "msg_me":         "#2c313a",
        "msg_them":       "#3e4451",
        "sidebar_bg":     "#21252b",
        "sidebar_active": "#3e4451",
    }),
    ("[data-theme=\"one-light\"]", {
        "bg_primary":     "#fafafa",
        "bg_secondary":   "#d3d3d3",
        "bg_tertiary":    "#f5f5f5",
        "text_primary":   "#383a42",
        "text_muted":     "#696c77",
        "accent":         "#4078f2",
        "primary_fg":     "#ffffff",
        "success":        "#50a14f",
        "warning":        "#986801",
        "error":          "#e45649",
        "info":           "#0184bc",
        "border":         "#d3d3d3",
        "msg_me":         "#ececed",
        "msg_them":       "#e5e5e6",
        "sidebar_bg":     "#f5f5f5",
        "sidebar_active": "#d3d3d3",
    }),
    ("[data-theme=\"rose-pine\"]", {
        "bg_primary":     "#191724",
        "bg_secondary":   "#403d52",
        "bg_tertiary":    "#1f1d2e",
        "text_primary":   "#e0def4",
        "text_muted":     "#908caa",
        "accent":         "#c4a7e7",
        "primary_fg":     "#191724",
        "success":        "#9ccfd8",
        "warning":        "#f6c177",
        "error":          "#eb6f92",
        "info":           "#31748f",
        "border":         "#403d52",
        "msg_me":         "#26233a",
        "msg_them":       "#26233a",
        "sidebar_bg":     "#1f1d2e",
        "sidebar_active": "#403d52",
    }),
    ("[data-theme=\"rose-pine-dawn\"]", {
        "bg_primary":     "#faf4ed",
        "bg_secondary":   "#cecacd",
        "bg_tertiary":    "#f2e9e1",
        "text_primary":   "#575279",
        "text_muted":     "#797593",
        "accent":         "#907aa9",
        "primary_fg":     "#faf4ed",
        "success":        "#286983",
        "warning":        "#ea9d34",
        "error":          "#b4637a",
        "info":           "#56949f",
        "border":         "#cecacd",
        "msg_me":         "#ece5de",
        "msg_them":       "#f2e9e1",
        "sidebar_bg":     "#f2e9e1",
        "sidebar_active": "#cecacd",
    }),
    ("[data-theme=\"rose-pine-moon\"]", {
        "bg_primary":     "#232136",
        "bg_secondary":   "#44415a",
        "bg_tertiary":    "#2a273f",
        "text_primary":   "#e0def4",
        "text_muted":     "#908caa",
        "accent":         "#c4a7e7",
        "primary_fg":     "#232136",
        "success":        "#9ccfd8",
        "warning":        "#f6c177",
        "error":          "#eb6f92",
        "info":           "#3e8fb0",
        "border":         "#44415a",
        "msg_me":         "#393552",
        "msg_them":       "#393552",
        "sidebar_bg":     "#2a273f",
        "sidebar_active": "#44415a",
    }),
    ("[data-theme=\"solarized-dark\"]", {
        "bg_primary":     "#002b36",
        "bg_secondary":   "#586e75",
        "bg_tertiary":    "#001f27",
        "text_primary":   "#93a1a1",
        "text_muted":     "#657b83",
        "accent":         "#268bd2",
        "primary_fg":     "#002b36",
        "success":        "#859900",
        "warning":        "#b58900",
        "error":          "#dc322f",
        "info":           "#2aa198",
        "border":         "#586e75",
        "msg_me":         "#073642",
        "msg_them":       "#073642",
        "sidebar_bg":     "#001f27",
        "sidebar_active": "#586e75",
    }),
    ("[data-theme=\"solarized-light\"]", {
        "bg_primary":     "#fdf6e3",
        "bg_secondary":   "#93a1a1",
        "bg_tertiary":    "#f5eed4",
        "text_primary":   "#586e75",
        "text_muted":     "#839496",
        "accent":         "#268bd2",
        "primary_fg":     "#fdf6e3",
        "success":        "#859900",
        "warning":        "#b58900",
        "error":          "#dc322f",
        "info":           "#2aa198",
        "border":         "#93a1a1",
        "msg_me":         "#eee8d5",
        "msg_them":       "#eee8d5",
        "sidebar_bg":     "#f5eed4",
        "sidebar_active": "#93a1a1",
    }),
    ("[data-theme=\"tokyo-night\"]", {
        "bg_primary":     "#1a1b26",
        "bg_secondary":   "#414868",
        "bg_tertiary":    "#16161e",
        "text_primary":   "#c0caf5",
        "text_muted":     "#828bb8",
        "accent":         "#7aa2f7",
        "primary_fg":     "#1a1b26",
        "success":        "#9ece6a",
        "warning":        "#e0af68",
        "error":          "#f7768e",
        "info":           "#7dcfff",
        "border":         "#414868",
        "msg_me":         "#292e42",
        "msg_them":       "#292e42",
        "sidebar_bg":     "#16161e",
        "sidebar_active": "#414868",
    }),
]

# System theme uses Dracula (dark) / GitHub Light (light)
SYSTEM_DARK = THEMES[0][1]   # dracula
SYSTEM_LIGHT = THEMES[7][1]  # github-light


LEGACY_BRIDGE = """  /* Legacy bridge — components using --color-* arbitrary syntax.
   * Defined only in :root; inherits correct values from [data-theme] blocks
   * at use-time because CSS var() is resolved at computed-style time.
   * Remove in Chunk 2 after all components switch to shadcn utility classes. */
  --color-bg-primary:     hsl(var(--background));
  --color-bg-secondary:   hsl(var(--card));
  --color-bg-tertiary:    hsl(var(--muted));
  --color-text-primary:   hsl(var(--foreground));
  --color-text-secondary: hsl(var(--muted-foreground));
  --color-text-muted:     hsl(var(--muted-foreground));
  --color-accent:         hsl(var(--primary));
  --color-accent-hover:   hsl(var(--primary));
  --color-error:          hsl(var(--destructive));
  --color-border:         hsl(var(--border));
  --color-input-bg:       hsl(var(--input));
  --color-msg-me:         hsl(var(--msg-me));
  --color-msg-them:       hsl(var(--msg-them));
  --color-sidebar-bg:     hsl(var(--sidebar-bg));
  --color-sidebar-active: hsl(var(--accent));
  --color-sidebar-hover:  hsl(var(--accent));
  --color-success:        hsl(var(--success));
  --color-warning:        hsl(var(--warning));
  --color-info:           hsl(var(--info));"""


def render_block(c):
    """Render a full shadcn + chatwire variable block from a colors dict."""
    bg     = hex_to_hsl(c["bg_primary"])
    fg     = hex_to_hsl(c["text_primary"])
    card   = hex_to_hsl(c["bg_secondary"])
    muted  = hex_to_hsl(c["bg_tertiary"])
    muted_fg = hex_to_hsl(c["text_muted"])
    primary  = hex_to_hsl(c["accent"])
    pri_fg   = hex_to_hsl(c["primary_fg"])
    destr    = hex_to_hsl(c["error"])
    border   = hex_to_hsl(c["border"])
    sidebar  = hex_to_hsl(c["sidebar_bg"])
    s_accent = hex_to_hsl(c["sidebar_active"])
    msg_me   = hex_to_hsl(c["msg_me"])
    msg_them = hex_to_hsl(c["msg_them"])
    success  = hex_to_hsl(c["success"])
    warning  = hex_to_hsl(c["warning"])
    info     = hex_to_hsl(c["info"])

    lines = [
        f"  /* shadcn standard */",
        f"  --background:                  {bg};",
        f"  --foreground:                  {fg};",
        f"  --card:                        {card};",
        f"  --card-foreground:             {fg};",
        f"  --popover:                     {card};",
        f"  --popover-foreground:          {fg};",
        f"  --primary:                     {primary};",
        f"  --primary-foreground:          {pri_fg};",
        f"  --secondary:                   {card};",
        f"  --secondary-foreground:        {fg};",
        f"  --muted:                       {muted};",
        f"  --muted-foreground:            {muted_fg};",
        f"  --accent:                      {s_accent};",
        f"  --accent-foreground:           {fg};",
        f"  --destructive:                 {destr};",
        f"  --destructive-foreground:      {fg};",
        f"  --border:                      {border};",
        f"  --input:                       {border};",
        f"  --ring:                        {primary};",
        f"  /* Sidebar (shadcn sidebar tokens) */",
        f"  --sidebar:                     {sidebar};",
        f"  --sidebar-foreground:          {fg};",
        f"  --sidebar-primary:             {primary};",
        f"  --sidebar-primary-foreground:  {pri_fg};",
        f"  --sidebar-accent:              {s_accent};",
        f"  --sidebar-accent-foreground:   {fg};",
        f"  --sidebar-border:              {border};",
        f"  --sidebar-ring:                {primary};",
        f"  /* Chatwire-specific */",
        f"  --msg-me:                      {msg_me};",
        f"  --msg-them:                    {msg_them};",
        f"  --sidebar-bg:                  {sidebar};",
        f"  --success:                     {success};",
        f"  --warning:                     {warning};",
        f"  --info:                        {info};",
    ]
    return "\n".join(lines)


def main():
    parts = [
        "/*",
        " * Color schemes — HSL-native, shadcn convention.",
        " *",
        " * All values are space-separated HSL numbers WITHOUT the hsl() wrapper.",
        " * This is required for Tailwind v4 utility generation:",
        " *   bg-background → background-color: hsl(var(--background))",
        " *",
        " * Tailwind v4 does NOT purge CSS custom property definitions.",
        " * [data-theme=\"nord\"] blocks survive the build because they define",
        " * properties (--background etc.), not utility classes.",
        " *",
        " * Standard shadcn variables: --background, --foreground, --primary, …",
        " * Chatwire-specific: --msg-me, --msg-them, --sidebar-bg, --success, …",
        " * Structural vars (--radius, --radius-bubble, etc.) live in themes.css.",
        " */",
        "",
    ]

    for i, (selector, colors) in enumerate(THEMES):
        # Section comment
        label = selector.replace(":root,\n", "").replace("[data-theme=\"", "").replace("\"]", "")
        parts.append(f"/* ── {label} {'─' * max(0, 70 - len(label))} */")
        parts.append(f"{selector} {{")
        parts.append(render_block(colors))
        if i == 0:  # :root block gets the legacy bridge
            parts.append(LEGACY_BRIDGE)
        parts.append("}\n")

    # System theme — @media blocks
    parts.append("/* ── System (OS preference) ─────────────────────────────────────────────── */")
    parts.append("@media (prefers-color-scheme: dark) {")
    parts.append("  [data-theme=\"system\"] {")
    # indent the block by 2 more spaces
    for line in render_block(SYSTEM_DARK).splitlines():
        parts.append("  " + line)
    parts.append("  }")
    parts.append("}\n")
    parts.append("@media (prefers-color-scheme: light) {")
    parts.append("  [data-theme=\"system\"] {")
    for line in render_block(SYSTEM_LIGHT).splitlines():
        parts.append("  " + line)
    parts.append("  }")
    parts.append("}")
    parts.append("")  # trailing newline

    output = "\n".join(parts)
    with open(OUTPUT, "w") as f:
        f.write(output)
    print(f"Wrote {OUTPUT} ({len(output)} bytes, {output.count(chr(10))} lines)")

    # Quick sanity check
    data_theme_count = output.count("data-theme")
    print(f"data-theme occurrences: {data_theme_count} (need 20+)")


if __name__ == "__main__":
    main()
