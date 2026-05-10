/**
 * Dracula-based color tokens for the mobile app.
 * Mirrors the CSS custom properties from the web app's Dracula theme.
 */
export const COLORS = {
  // Backgrounds
  bgPrimary: '#282a36',
  bgSecondary: '#21222c',
  bgTertiary: '#44475a',

  // Foreground
  fgPrimary: '#f8f8f2',
  fgMuted: '#6272a4',

  // Accent / brand
  accent: '#bd93f9',
  accentGreen: '#50fa7b',
  accentRed: '#ff5555',
  accentOrange: '#ffb86c',
  accentCyan: '#8be9fd',
  accentPink: '#ff79c6',
  accentYellow: '#f1fa8c',

  // Bubbles
  bubbleMe: '#44475a',
  bubbleThem: '#21222c',

  // Borders
  border: '#44475a',
} as const

export type ColorKey = keyof typeof COLORS
