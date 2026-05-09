/**
 * All 21 selectable themes as TypeScript design-token objects.
 *
 * Colors are extracted from web/static/themes/*.css and mapped to the
 * --color-* CSS custom-property names used by the React frontend.
 * The useTheme hook (hooks/useTheme.ts) applies these to :root at runtime.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ThemeColors {
  'bg-primary': string
  'bg-secondary': string
  'bg-tertiary': string
  'text-primary': string
  'text-secondary': string
  'text-muted': string
  accent: string
  'accent-hover': string
  success: string
  warning: string
  error: string
  info: string
  border: string
  'input-bg': string
  'msg-me': string
  'msg-them': string
  'sidebar-bg': string
  'sidebar-active': string
  'sidebar-hover': string
}

export interface ThemeDefinition {
  name: string
  label: string
  /** True for light / "clean" themes (used for swatch contrast) */
  isLight?: boolean
  colors: ThemeColors
  /** System theme only: dark-mode variant to use when prefers-color-scheme: dark */
  darkColors?: ThemeColors
}

// ---------------------------------------------------------------------------
// Theme definitions
// ---------------------------------------------------------------------------

const catppuccinFrappe: ThemeDefinition = {
  name: 'catppuccin-frappe',
  label: 'Catppuccin Frappé',
  colors: {
    'bg-primary':       '#303446',
    'bg-secondary':     '#51576d',
    'bg-tertiary':      '#292c3c',
    'text-primary':     '#c6d0f5',
    'text-secondary':   '#838ba7',
    'text-muted':       '#838ba7',
    accent:             '#ca9ee6',
    'accent-hover':     '#b288ce',
    success:            '#a6d189',
    warning:            '#e5c890',
    error:              '#e78284',
    info:               '#8caaee',
    border:             '#51576d',
    'input-bg':         '#51576d',
    'msg-me':           '#414559',
    'msg-them':         '#303446',
    'sidebar-bg':       '#292c3c',
    'sidebar-active':   '#414559',
    'sidebar-hover':    '#414559',
  },
}

const catppuccinLatte: ThemeDefinition = {
  name: 'catppuccin-latte',
  label: 'Catppuccin Latte',
  isLight: true,
  colors: {
    'bg-primary':       '#eff1f5',
    'bg-secondary':     '#bcc0cc',
    'bg-tertiary':      '#e6e9ef',
    'text-primary':     '#4c4f69',
    'text-secondary':   '#8c8fa1',
    'text-muted':       '#6c6f85',
    accent:             '#8839ef',
    'accent-hover':     '#6c2dc0',
    success:            '#40a02b',
    warning:            '#df8e1d',
    error:              '#d20f39',
    info:               '#1e66f5',
    border:             '#bcc0cc',
    'input-bg':         '#bcc0cc',
    'msg-me':           '#ccd0da',
    'msg-them':         '#eff1f5',
    'sidebar-bg':       '#e6e9ef',
    'sidebar-active':   '#ccd0da',
    'sidebar-hover':    '#ccd0da',
  },
}

const catppuccinMacchiato: ThemeDefinition = {
  name: 'catppuccin-macchiato',
  label: 'Catppuccin Macchiato',
  colors: {
    'bg-primary':       '#24273a',
    'bg-secondary':     '#494d64',
    'bg-tertiary':      '#1e2030',
    'text-primary':     '#cad3f5',
    'text-secondary':   '#8087a2',
    'text-muted':       '#8087a2',
    accent:             '#c6a0f6',
    'accent-hover':     '#ad88de',
    success:            '#a6da95',
    warning:            '#eed49f',
    error:              '#ed8796',
    info:               '#8aadf4',
    border:             '#494d64',
    'input-bg':         '#494d64',
    'msg-me':           '#363a4f',
    'msg-them':         '#24273a',
    'sidebar-bg':       '#1e2030',
    'sidebar-active':   '#363a4f',
    'sidebar-hover':    '#363a4f',
  },
}

const catppuccinMocha: ThemeDefinition = {
  name: 'catppuccin-mocha',
  label: 'Catppuccin Mocha',
  colors: {
    'bg-primary':       '#1e1e2e',
    'bg-secondary':     '#45475a',
    'bg-tertiary':      '#181825',
    'text-primary':     '#cdd6f4',
    'text-secondary':   '#7f849c',
    'text-muted':       '#7f849c',
    accent:             '#cba6f7',
    'accent-hover':     '#b290e0',
    success:            '#a6e3a1',
    warning:            '#f9e2af',
    error:              '#f38ba8',
    info:               '#89b4fa',
    border:             '#45475a',
    'input-bg':         '#45475a',
    'msg-me':           '#313244',
    'msg-them':         '#1e1e2e',
    'sidebar-bg':       '#181825',
    'sidebar-active':   '#313244',
    'sidebar-hover':    '#313244',
  },
}

const defaultTheme: ThemeDefinition = {
  name: 'default',
  label: 'Default',
  isLight: true,
  colors: {
    'bg-primary':       '#f7f7f8',
    'bg-secondary':     '#d4d4d8',
    'bg-tertiary':      '#fafbfc',
    'text-primary':     '#111827',
    'text-secondary':   '#9ca3af',
    'text-muted':       '#6b7280',
    accent:             '#3b82f6',
    'accent-hover':     '#2563eb',
    success:            '#137333',
    warning:            '#795700',
    error:              '#b91c1c',
    info:               '#3b82f6',
    border:             '#d4d4d8',
    'input-bg':         '#ffffff',
    'msg-me':           '#e5e5ea',
    'msg-them':         '#f7f7f8',
    'sidebar-bg':       '#fafbfc',
    'sidebar-active':   '#e5e5ea',
    'sidebar-hover':    '#eef2ff',
  },
}

const dracula: ThemeDefinition = {
  name: 'dracula',
  label: 'Dracula',
  colors: {
    'bg-primary':       '#282a36',
    'bg-secondary':     '#44475a',
    'bg-tertiary':      '#21222c',
    'text-primary':     '#f8f8f2',
    'text-secondary':   '#6272a4',
    'text-muted':       '#6272a4',
    accent:             '#bd93f9',
    'accent-hover':     '#a679f0',
    success:            '#50fa7b',
    warning:            '#f1fa8c',
    error:              '#ff5555',
    info:               '#8be9fd',
    border:             '#44475a',
    'input-bg':         '#44475a',
    'msg-me':           '#44475a',
    'msg-them':         '#282a36',
    'sidebar-bg':       '#21222c',
    'sidebar-active':   '#44475a',
    'sidebar-hover':    '#343746',
  },
}

const githubDark: ThemeDefinition = {
  name: 'github-dark',
  label: 'GitHub Dark',
  colors: {
    'bg-primary':       '#0d1117',
    'bg-secondary':     '#3d444d',
    'bg-tertiary':      '#010409',
    'text-primary':     '#f0f6fc',
    'text-secondary':   '#6a7282',
    'text-muted':       '#9198a1',
    accent:             '#4493f8',
    'accent-hover':     '#2f7ad8',
    success:            '#3fb950',
    warning:            '#d29922',
    error:              '#f85149',
    info:               '#4493f8',
    border:             '#3d444d',
    'input-bg':         '#3d444d',
    'msg-me':           '#151b23',
    'msg-them':         '#0d1117',
    'sidebar-bg':       '#010409',
    'sidebar-active':   '#151b23',
    'sidebar-hover':    '#151b23',
  },
}

const githubLight: ThemeDefinition = {
  name: 'github-light',
  label: 'GitHub Light',
  isLight: true,
  colors: {
    'bg-primary':       '#ffffff',
    'bg-secondary':     '#d1d9e0',
    'bg-tertiary':      '#f6f8fa',
    'text-primary':     '#1f2328',
    'text-secondary':   '#8c959f',
    'text-muted':       '#6e7781',
    accent:             '#0969da',
    'accent-hover':     '#0858bc',
    success:            '#1a7f37',
    warning:            '#9a6700',
    error:              '#d1242f',
    info:               '#0969da',
    border:             '#d1d9e0',
    'input-bg':         '#ffffff',
    'msg-me':           '#eaeef2',
    'msg-them':         '#ffffff',
    'sidebar-bg':       '#f6f8fa',
    'sidebar-active':   '#eaeef2',
    'sidebar-hover':    '#eaeef2',
  },
}

const gruvbox: ThemeDefinition = {
  name: 'gruvbox',
  label: 'Gruvbox',
  colors: {
    'bg-primary':       '#282828',
    'bg-secondary':     '#504945',
    'bg-tertiary':      '#1d2021',
    'text-primary':     '#ebdbb2',
    'text-secondary':   '#928374',
    'text-muted':       '#a89984',
    accent:             '#d65d0e',
    'accent-hover':     '#b3490a',
    success:            '#b8bb26',
    warning:            '#fabd2f',
    error:              '#fb4934',
    info:               '#458588',
    border:             '#504945',
    'input-bg':         '#504945',
    'msg-me':           '#3c3836',
    'msg-them':         '#282828',
    'sidebar-bg':       '#1d2021',
    'sidebar-active':   '#3c3836',
    'sidebar-hover':    '#3c3836',
  },
}

const gruvboxLight: ThemeDefinition = {
  name: 'gruvbox-light',
  label: 'Gruvbox Light',
  isLight: true,
  colors: {
    'bg-primary':       '#fbf1c7',
    'bg-secondary':     '#d5c4a1',
    'bg-tertiary':      '#f9f5d7',
    'text-primary':     '#3c3836',
    'text-secondary':   '#928374',
    'text-muted':       '#7c6f64',
    accent:             '#af3a03',
    'accent-hover':     '#8a2e02',
    success:            '#79740e',
    warning:            '#b57614',
    error:              '#9d0006',
    info:               '#076678',
    border:             '#d5c4a1',
    'input-bg':         '#fbf1c7',
    'msg-me':           '#f2e5bc',
    'msg-them':         '#fbf1c7',
    'sidebar-bg':       '#f9f5d7',
    'sidebar-active':   '#f2e5bc',
    'sidebar-hover':    '#f2e5bc',
  },
}

const nightOwl: ThemeDefinition = {
  name: 'night-owl',
  label: 'Night Owl',
  colors: {
    'bg-primary':       '#011627',
    'bg-secondary':     '#1d3b53',
    'bg-tertiary':      '#010d1a',
    'text-primary':     '#d6deeb',
    'text-secondary':   '#637777',
    'text-muted':       '#8a93ad',
    accent:             '#82aaff',
    'accent-hover':     '#618fec',
    success:            '#addb67',
    warning:            '#ecc48d',
    error:              '#ff5874',
    info:               '#82aaff',
    border:             '#1d3b53',
    'input-bg':         '#1d3b53',
    'msg-me':           '#1d3b53',
    'msg-them':         '#011627',
    'sidebar-bg':       '#010d1a',
    'sidebar-active':   '#1d3b53',
    'sidebar-hover':    '#0e293f',
  },
}

const nord: ThemeDefinition = {
  name: 'nord',
  label: 'Nord',
  colors: {
    'bg-primary':       '#2e3440',
    'bg-secondary':     '#4c566a',
    'bg-tertiary':      '#292e39',
    'text-primary':     '#eceff4',
    'text-secondary':   '#6c7589',
    'text-muted':       '#a8b1c0',
    accent:             '#88c0d0',
    'accent-hover':     '#6fb1c4',
    success:            '#a3be8c',
    warning:            '#ebcb8b',
    error:              '#bf616a',
    info:               '#5e81ac',
    border:             '#4c566a',
    'input-bg':         '#4c566a',
    'msg-me':           '#3b4252',
    'msg-them':         '#2e3440',
    'sidebar-bg':       '#292e39',
    'sidebar-active':   '#3b4252',
    'sidebar-hover':    '#3b4252',
  },
}

const oneDark: ThemeDefinition = {
  name: 'one-dark',
  label: 'One Dark',
  colors: {
    'bg-primary':       '#282c34',
    'bg-secondary':     '#3e4451',
    'bg-tertiary':      '#21252b',
    'text-primary':     '#abb2bf',
    'text-secondary':   '#5c6370',
    'text-muted':       '#828997',
    accent:             '#61afef',
    'accent-hover':     '#4a96d6',
    success:            '#98c379',
    warning:            '#e5c07b',
    error:              '#e06c75',
    info:               '#61afef',
    border:             '#3e4451',
    'input-bg':         '#3e4451',
    'msg-me':           '#3e4451',
    'msg-them':         '#282c34',
    'sidebar-bg':       '#21252b',
    'sidebar-active':   '#3e4451',
    'sidebar-hover':    '#2c313a',
  },
}

const oneLight: ThemeDefinition = {
  name: 'one-light',
  label: 'One Light',
  isLight: true,
  colors: {
    'bg-primary':       '#fafafa',
    'bg-secondary':     '#d3d3d3',
    'bg-tertiary':      '#f5f5f5',
    'text-primary':     '#383a42',
    'text-secondary':   '#a0a1a7',
    'text-muted':       '#696c77',
    accent:             '#4078f2',
    'accent-hover':     '#305dc7',
    success:            '#50a14f',
    warning:            '#986801',
    error:              '#e45649',
    info:               '#4078f2',
    border:             '#d3d3d3',
    'input-bg':         '#ffffff',
    'msg-me':           '#e5e5e6',
    'msg-them':         '#fafafa',
    'sidebar-bg':       '#f5f5f5',
    'sidebar-active':   '#e5e5e6',
    'sidebar-hover':    '#ececed',
  },
}

const rosePine: ThemeDefinition = {
  name: 'rose-pine',
  label: 'Rosé Pine',
  colors: {
    'bg-primary':       '#191724',
    'bg-secondary':     '#403d52',
    'bg-tertiary':      '#1f1d2e',
    'text-primary':     '#e0def4',
    'text-secondary':   '#6e6a86',
    'text-muted':       '#908caa',
    accent:             '#c4a7e7',
    'accent-hover':     '#a888d0',
    success:            '#9ccfd8',
    warning:            '#f6c177',
    error:              '#eb6f92',
    info:               '#31748f',
    border:             '#403d52',
    'input-bg':         '#403d52',
    'msg-me':           '#26233a',
    'msg-them':         '#191724',
    'sidebar-bg':       '#1f1d2e',
    'sidebar-active':   '#26233a',
    'sidebar-hover':    '#26233a',
  },
}

const rosePineDawn: ThemeDefinition = {
  name: 'rose-pine-dawn',
  label: 'Rosé Pine Dawn',
  isLight: true,
  colors: {
    'bg-primary':       '#faf4ed',
    'bg-secondary':     '#cecacd',
    'bg-tertiary':      '#f2e9e1',
    'text-primary':     '#575279',
    'text-secondary':   '#9893a5',
    'text-muted':       '#797593',
    accent:             '#907aa9',
    'accent-hover':     '#7a649a',
    success:            '#286983',
    warning:            '#ea9d34',
    error:              '#b4637a',
    info:               '#286983',
    border:             '#cecacd',
    'input-bg':         '#fffaf3',
    'msg-me':           '#f2e9e1',
    'msg-them':         '#faf4ed',
    'sidebar-bg':       '#f2e9e1',
    'sidebar-active':   '#ece5de',
    'sidebar-hover':    '#ece5de',
  },
}

const rosePineMoon: ThemeDefinition = {
  name: 'rose-pine-moon',
  label: 'Rosé Pine Moon',
  colors: {
    'bg-primary':       '#232136',
    'bg-secondary':     '#44415a',
    'bg-tertiary':      '#2a273f',
    'text-primary':     '#e0def4',
    'text-secondary':   '#6e6a86',
    'text-muted':       '#908caa',
    accent:             '#c4a7e7',
    'accent-hover':     '#a888d0',
    success:            '#9ccfd8',
    warning:            '#f6c177',
    error:              '#eb6f92',
    info:               '#3e8fb0',
    border:             '#44415a',
    'input-bg':         '#44415a',
    'msg-me':           '#393552',
    'msg-them':         '#232136',
    'sidebar-bg':       '#2a273f',
    'sidebar-active':   '#393552',
    'sidebar-hover':    '#393552',
  },
}

const solarizedDark: ThemeDefinition = {
  name: 'solarized-dark',
  label: 'Solarized Dark',
  colors: {
    'bg-primary':       '#002b36',
    'bg-secondary':     '#586e75',
    'bg-tertiary':      '#001f27',
    'text-primary':     '#93a1a1',
    'text-secondary':   '#586e75',
    'text-muted':       '#657b83',
    accent:             '#268bd2',
    'accent-hover':     '#1d6fa5',
    success:            '#859900',
    warning:            '#b58900',
    error:              '#dc322f',
    info:               '#268bd2',
    border:             '#586e75',
    'input-bg':         '#586e75',
    'msg-me':           '#073642',
    'msg-them':         '#002b36',
    'sidebar-bg':       '#001f27',
    'sidebar-active':   '#073642',
    'sidebar-hover':    '#073642',
  },
}

const solarizedLight: ThemeDefinition = {
  name: 'solarized-light',
  label: 'Solarized Light',
  isLight: true,
  colors: {
    'bg-primary':       '#fdf6e3',
    'bg-secondary':     '#93a1a1',
    'bg-tertiary':      '#f5eed4',
    'text-primary':     '#586e75',
    'text-secondary':   '#93a1a1',
    'text-muted':       '#839496',
    accent:             '#268bd2',
    'accent-hover':     '#1d6fa5',
    success:            '#859900',
    warning:            '#b58900',
    error:              '#dc322f',
    info:               '#268bd2',
    border:             '#93a1a1',
    'input-bg':         '#fdf6e3',
    'msg-me':           '#eee8d5',
    'msg-them':         '#fdf6e3',
    'sidebar-bg':       '#f5eed4',
    'sidebar-active':   '#eee8d5',
    'sidebar-hover':    '#eee8d5',
  },
}

const tokyoNight: ThemeDefinition = {
  name: 'tokyo-night',
  label: 'Tokyo Night',
  colors: {
    'bg-primary':       '#1a1b26',
    'bg-secondary':     '#414868',
    'bg-tertiary':      '#16161e',
    'text-primary':     '#c0caf5',
    'text-secondary':   '#565f89',
    'text-muted':       '#828bb8',
    accent:             '#7aa2f7',
    'accent-hover':     '#5d87e0',
    success:            '#9ece6a',
    warning:            '#e0af68',
    error:              '#f7768e',
    info:               '#7aa2f7',
    border:             '#414868',
    'input-bg':         '#414868',
    'msg-me':           '#292e42',
    'msg-them':         '#1a1b26',
    'sidebar-bg':       '#16161e',
    'sidebar-active':   '#292e42',
    'sidebar-hover':    '#292e42',
  },
}

// System theme: uses Default (light) + One Dark (dark) via prefers-color-scheme
const system: ThemeDefinition = {
  name: 'system',
  label: 'System',
  // Light variant (default palette)
  colors: {
    'bg-primary':       '#f7f7f8',
    'bg-secondary':     '#d4d4d8',
    'bg-tertiary':      '#fafbfc',
    'text-primary':     '#111827',
    'text-secondary':   '#9ca3af',
    'text-muted':       '#6b7280',
    accent:             '#3b82f6',
    'accent-hover':     '#2563eb',
    success:            '#137333',
    warning:            '#795700',
    error:              '#b91c1c',
    info:               '#3b82f6',
    border:             '#d4d4d8',
    'input-bg':         '#ffffff',
    'msg-me':           '#e5e5ea',
    'msg-them':         '#f7f7f8',
    'sidebar-bg':       '#fafbfc',
    'sidebar-active':   '#e5e5ea',
    'sidebar-hover':    '#eef2ff',
  },
  // Dark variant (One Dark palette)
  darkColors: {
    'bg-primary':       '#282c34',
    'bg-secondary':     '#3e4451',
    'bg-tertiary':      '#21252b',
    'text-primary':     '#abb2bf',
    'text-secondary':   '#5c6370',
    'text-muted':       '#828997',
    accent:             '#61afef',
    'accent-hover':     '#4a96d6',
    success:            '#98c379',
    warning:            '#e5c07b',
    error:              '#e06c75',
    info:               '#61afef',
    border:             '#3e4451',
    'input-bg':         '#3e4451',
    'msg-me':           '#3e4451',
    'msg-them':         '#282c34',
    'sidebar-bg':       '#21252b',
    'sidebar-active':   '#3e4451',
    'sidebar-hover':    '#2c313a',
  },
}

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

/** All theme definitions, pinned order: system, default, then alphabetical. */
export const ALL_THEMES: ThemeDefinition[] = [
  system,
  defaultTheme,
  catppuccinFrappe,
  catppuccinLatte,
  catppuccinMacchiato,
  catppuccinMocha,
  dracula,
  githubDark,
  githubLight,
  gruvbox,
  gruvboxLight,
  nightOwl,
  nord,
  oneDark,
  oneLight,
  rosePine,
  rosePineDawn,
  rosePineMoon,
  solarizedDark,
  solarizedLight,
  tokyoNight,
]

/** Lookup map: theme name → ThemeDefinition. */
export const THEME_MAP: Record<string, ThemeDefinition> = Object.fromEntries(
  ALL_THEMES.map((t) => [t.name, t]),
)

/** Resolve the actual colors to apply for a theme, respecting dark-mode preference for "system". */
export function resolveThemeColors(theme: ThemeDefinition): ThemeColors {
  if (theme.darkColors && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    return theme.darkColors
  }
  return theme.colors
}
