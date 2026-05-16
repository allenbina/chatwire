/**
 * Style guide / debug page — renders every themed token, component variant,
 * and icon in one scrollable reference so theme authors can see what's
 * available and how it responds to scheme + style changes.
 *
 * Route: /debug  (lazy-loaded from App.tsx)
 */

import { Link } from 'react-router-dom'
import {
  Bell, Check, ChevronDown, ChevronLeft, ChevronRight, ChevronUp, Circle,
  CircleCheck, ImagePlus, Info, LoaderCircle, LogOut, Moon,
  OctagonX, Palette, PauseCircle, Pin, PinOff, Puzzle,
  ScrollText, Send, Settings, ShieldAlert, Smile, Sun,
  TriangleAlert, X,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
import { toast } from 'sonner'
import { EmojiPicker } from '@/components/emoji'

// ---------------------------------------------------------------------------
// Section wrapper
// ---------------------------------------------------------------------------

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-10">
      <h2 className="text-lg font-semibold text-foreground border-b border-border pb-1 mb-4">
        {title}
      </h2>
      {children}
    </section>
  )
}

// ---------------------------------------------------------------------------
// Color swatch
// ---------------------------------------------------------------------------

function Swatch({ name, value, textClass }: { name: string; value: string; textClass?: string }) {
  return (
    <div className="flex flex-col items-center gap-1">
      <div
        className={`w-14 h-14 rounded-lg border border-border shadow-sm ${textClass ?? ''}`}
        style={{ backgroundColor: value }}
        title={name}
      />
      <span className="text-[10px] text-muted-foreground text-center leading-tight max-w-[70px] truncate">
        {name}
      </span>
    </div>
  )
}

function CSSVarSwatch({ varName }: { varName: string }) {
  return <Swatch name={varName} value={`hsl(var(--${varName}))`} />
}

// ---------------------------------------------------------------------------
// Inline SVG icons (duplicated from SettingsPage — shown here for audit)
// ---------------------------------------------------------------------------

function UserIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
    </svg>
  )
}
function ListIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
      <line x1="8" y1="6" x2="21" y2="6" /><line x1="8" y1="12" x2="21" y2="12" /><line x1="8" y1="18" x2="21" y2="18" /><line x1="3" y1="6" x2="3.01" y2="6" /><line x1="3" y1="12" x2="3.01" y2="12" /><line x1="3" y1="18" x2="3.01" y2="18" />
    </svg>
  )
}
function SunIconInline() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="5" /><line x1="12" y1="1" x2="12" y2="3" /><line x1="12" y1="21" x2="12" y2="23" /><line x1="4.22" y1="4.22" x2="5.64" y2="5.64" /><line x1="18.36" y1="18.36" x2="19.78" y2="19.78" /><line x1="1" y1="12" x2="3" y2="12" /><line x1="21" y1="12" x2="23" y2="12" /><line x1="4.22" y1="19.78" x2="5.64" y2="18.36" /><line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
    </svg>
  )
}
function BellIconInline() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  )
}
function SettingsIconInline() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  )
}
function CodeIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="16 18 22 12 16 6" /><polyline points="8 6 2 12 8 18" />
    </svg>
  )
}
function LockIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  )
}
function PuzzleIconInline() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
      <path d="M19.439 7.85c-.049.322.059.648.289.878l1.568 1.568c.47.47.706 1.087.706 1.704s-.235 1.233-.706 1.704l-1.611 1.611a.98.98 0 0 1-.837.276c-.47-.07-.802-.48-.968-.925a2.501 2.501 0 1 0-3.214 3.214c.446.166.855.497.925.968a.979.979 0 0 1-.276.837l-1.61 1.61a2.404 2.404 0 0 1-1.705.707 2.402 2.402 0 0 1-1.704-.706l-1.568-1.568a1.026 1.026 0 0 0-.877-.29c-.493.074-.84.504-1.02.968a2.5 2.5 0 1 1-3.237-3.237c.464-.18.894-.527.967-1.02a1.026 1.026 0 0 0-.289-.877l-1.568-1.568A2.402 2.402 0 0 1 1.998 12c0-.617.236-1.234.706-1.704L4.315 8.685a.98.98 0 0 1 .837-.276c.47.07.802.48.968.925a2.501 2.501 0 1 0 3.214-3.214c-.446-.166-.855-.497-.925-.968a.979.979 0 0 1 .276-.837l1.61-1.61a2.404 2.404 0 0 1 1.705-.707c.618 0 1.234.236 1.704.706l1.568 1.568c.23.23.556.338.877.29.493-.074.84-.504 1.02-.968a2.5 2.5 0 1 1 3.237 3.237c-.464.18-.894.527-.967 1.02Z" />
    </svg>
  )
}
function ZapIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
    </svg>
  )
}

// Inline SVGs from MessageBubble (reply, edit, unsend, file, download)
function ReplyIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="9 17 4 12 9 7" /><path d="M20 18v-2a4 4 0 0 0-4-4H4" />
    </svg>
  )
}
function EditIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
    </svg>
  )
}
function TrashIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    </svg>
  )
}
function FileIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  )
}
function CameraIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
      <circle cx="8.5" cy="8.5" r="1.5" /><polyline points="21 15 16 10 5 21" />
    </svg>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function DebugPage() {
  // -- Scheme colors --
  const schemeColors = [
    'background', 'foreground',
    'card', 'card-foreground',
    'popover', 'popover-foreground',
    'primary', 'primary-foreground',
    'secondary', 'secondary-foreground',
    'muted', 'muted-foreground',
    'accent', 'accent-foreground',
    'destructive', 'destructive-foreground',
    'border', 'input', 'ring',
  ]
  const sidebarColors = [
    'sidebar', 'sidebar-foreground',
    'sidebar-primary', 'sidebar-primary-foreground',
    'sidebar-accent', 'sidebar-accent-foreground',
    'sidebar-border', 'sidebar-ring',
  ]
  const chatwireColors = [
    'msg-me', 'msg-them', 'msg-sms', 'msg-sms-text',
    'sidebar-bg', 'success', 'warning', 'info',
  ]

  // -- Structural vars --
  const structuralVars = [
    '--radius', '--radius-bubble', '--radius-input',
    '--spacing-message', '--spacing-sidebar',
    '--font-size-message', '--font-size-sidebar',
    '--shadow-card', '--sidebar-width',
  ]
  const decorationVars = [
    '--avatar-shape', '--avatar-size', '--avatar-border',
    '--bubble-shadow', '--bubble-tail',
    '--header-shadow', '--header-border',
    '--sidebar-divider', '--sidebar-active-radius',
    '--border-width', '--transition-speed',
  ]

  // -- Lucide icons --
  const lucideIcons = [
    { name: 'Bell', icon: <Bell className="w-5 h-5" /> },
    { name: 'Check', icon: <Check className="w-5 h-5" /> },
    { name: 'ChevronDown', icon: <ChevronDown className="w-5 h-5" /> },
    { name: 'ChevronRight', icon: <ChevronRight className="w-5 h-5" /> },
    { name: 'ChevronUp', icon: <ChevronUp className="w-5 h-5" /> },
    { name: 'Circle', icon: <Circle className="w-5 h-5" /> },
    { name: 'CircleCheck', icon: <CircleCheck className="w-5 h-5" /> },
    { name: 'ImagePlus', icon: <ImagePlus className="w-5 h-5" /> },
    { name: 'Info', icon: <Info className="w-5 h-5" /> },
    { name: 'LoaderCircle', icon: <LoaderCircle className="w-5 h-5" /> },
    { name: 'LogOut', icon: <LogOut className="w-5 h-5" /> },
    { name: 'Moon', icon: <Moon className="w-5 h-5" /> },
    { name: 'OctagonX', icon: <OctagonX className="w-5 h-5" /> },
    { name: 'Palette', icon: <Palette className="w-5 h-5" /> },
    { name: 'PauseCircle', icon: <PauseCircle className="w-5 h-5" /> },
    { name: 'Pin', icon: <Pin className="w-5 h-5" /> },
    { name: 'PinOff', icon: <PinOff className="w-5 h-5" /> },
    { name: 'Puzzle', icon: <Puzzle className="w-5 h-5" /> },
    { name: 'ScrollText', icon: <ScrollText className="w-5 h-5" /> },
    { name: 'Send', icon: <Send className="w-5 h-5" /> },
    { name: 'Settings', icon: <Settings className="w-5 h-5" /> },
    { name: 'ShieldAlert', icon: <ShieldAlert className="w-5 h-5" /> },
    { name: 'Smile', icon: <Smile className="w-5 h-5" /> },
    { name: 'Sun', icon: <Sun className="w-5 h-5" /> },
    { name: 'TriangleAlert', icon: <TriangleAlert className="w-5 h-5" /> },
    { name: 'X', icon: <X className="w-5 h-5" /> },
  ]

  // -- Inline SVG icons --
  const inlineIcons = [
    { name: 'User', icon: <UserIcon /> },
    { name: 'List', icon: <ListIcon /> },
    { name: 'Sun (inline)', icon: <SunIconInline /> },
    { name: 'Bell (inline)', icon: <BellIconInline /> },
    { name: 'Settings (inline)', icon: <SettingsIconInline /> },
    { name: 'Code', icon: <CodeIcon /> },
    { name: 'Lock', icon: <LockIcon /> },
    { name: 'Puzzle (inline)', icon: <PuzzleIconInline /> },
    { name: 'Zap', icon: <ZapIcon /> },
    { name: 'Reply', icon: <ReplyIcon /> },
    { name: 'Edit', icon: <EditIcon /> },
    { name: 'Trash', icon: <TrashIcon /> },
    { name: 'File', icon: <FileIcon /> },
    { name: 'Camera', icon: <CameraIcon /> },
  ]

  // -- Tapback emojis --
  const tapbackEmojis = ['❤️', '👍', '👎', '😂', '‼️', '❓']

  return (
    <div className="min-h-screen bg-background text-foreground max-w-5xl mx-auto">
      {/* Header with mobile back button */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-border bg-background md:border-0 md:px-8 md:pt-8 md:pb-0">
        <Link
          to="/"
          className="md:hidden p-2 -ml-3 -my-1 text-muted-foreground hover:text-foreground transition-colors"
          aria-label="Back to conversations"
        >
          <ChevronLeft className="w-6 h-6" />
        </Link>
        <h1 className="text-2xl font-bold">Style Guide</h1>
      </div>
      <div className="p-8 pt-4 md:pt-2">
      <p className="text-sm text-muted-foreground mb-8">
        Current scheme: <code className="text-primary">{document.documentElement.getAttribute('data-theme') ?? 'dracula'}</code>
        {' '}&middot;{' '}
        Current style: <code className="text-primary">{document.documentElement.getAttribute('data-style') ?? 'default'}</code>
      </p>

      {/* ── Colors: Scheme ── */}
      <Section title="Scheme Colors (shadcn standard)">
        <div className="flex flex-wrap gap-3">
          {schemeColors.map((v) => <CSSVarSwatch key={v} varName={v} />)}
        </div>
      </Section>

      <Section title="Sidebar Colors">
        <div className="flex flex-wrap gap-3">
          {sidebarColors.map((v) => <CSSVarSwatch key={v} varName={v} />)}
        </div>
      </Section>

      <Section title="Chatwire Colors">
        <div className="flex flex-wrap gap-3">
          {chatwireColors.map((v) => <CSSVarSwatch key={v} varName={v} />)}
        </div>
      </Section>

      {/* ── Surfaces ── */}
      <Section title="Surfaces">
        <div className="flex flex-wrap gap-4">
          {[
            { label: 'bg-background', cls: 'bg-background text-foreground' },
            { label: 'bg-card', cls: 'bg-card text-card-foreground' },
            { label: 'bg-popover', cls: 'bg-popover text-popover-foreground' },
            { label: 'bg-muted', cls: 'bg-muted text-muted-foreground' },
            { label: 'bg-accent', cls: 'bg-accent text-accent-foreground' },
            { label: 'bg-primary', cls: 'bg-primary text-primary-foreground' },
            { label: 'bg-secondary', cls: 'bg-secondary text-secondary-foreground' },
            { label: 'bg-destructive', cls: 'bg-destructive text-destructive-foreground' },
          ].map((s) => (
            <div key={s.label} className={`${s.cls} border border-border rounded-lg px-4 py-3 text-sm min-w-[160px]`}>
              <p className="font-medium">{s.label}</p>
              <p className="text-xs opacity-70 mt-0.5">Sample text</p>
            </div>
          ))}
        </div>
      </Section>

      {/* ── Typography ── */}
      <Section title="Typography">
        <div className="space-y-3">
          <div>
            <p className="text-xs text-muted-foreground mb-1">Font family: Inter (inherited)</p>
          </div>
          <div className="flex flex-wrap gap-6">
            {[300, 400, 500, 600, 700].map((w) => (
              <p key={w} style={{ fontWeight: w }} className="text-foreground">
                Weight {w}
              </p>
            ))}
          </div>
          <div className="flex flex-wrap gap-6 items-baseline">
            <p style={{ fontSize: 'var(--font-size-sidebar)' }} className="text-foreground">
              --font-size-sidebar
            </p>
            <p style={{ fontSize: 'var(--font-size-message)' }} className="text-foreground">
              --font-size-message
            </p>
            <p className="text-xs text-foreground">text-xs (0.75rem)</p>
            <p className="text-sm text-foreground">text-sm (0.875rem)</p>
            <p className="text-base text-foreground">text-base (1rem)</p>
            <p className="text-lg text-foreground">text-lg (1.125rem)</p>
            <p className="text-xl text-foreground">text-xl (1.25rem)</p>
            <p className="text-2xl text-foreground">text-2xl (1.5rem)</p>
          </div>
          <div>
            <p className="text-[10px] text-muted-foreground">text-[10px] — used for timestamps, tapback counts</p>
          </div>
        </div>
      </Section>

      {/* ── Structural vars ── */}
      <Section title="Structural Variables (style)">
        <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-sm">
          {[...structuralVars, ...decorationVars].map((v) => (
            <div key={v} className="flex justify-between gap-2 bg-muted rounded px-3 py-1.5">
              <code className="text-primary text-xs">{v}</code>
              <span className="text-muted-foreground text-xs font-mono">
                {getComputedStyle(document.documentElement).getPropertyValue(v).trim() || '(empty)'}
              </span>
            </div>
          ))}
        </div>
      </Section>

      {/* ── Radii ── */}
      <Section title="Border Radii">
        <div className="flex flex-wrap gap-4">
          {[
            { label: '--radius-sm', cls: 'rounded-sm' },
            { label: '--radius-md', cls: 'rounded-md' },
            { label: '--radius-lg', cls: 'rounded-lg' },
            { label: '--radius-xl', cls: 'rounded-xl' },
            { label: '--radius-bubble', style: { borderRadius: 'var(--radius-bubble)' } },
            { label: '--radius-input', style: { borderRadius: 'var(--radius-input)' } },
            { label: '--avatar-shape', style: { borderRadius: 'var(--avatar-shape)' } },
          ].map((r) => (
            <div key={r.label} className="flex flex-col items-center gap-1">
              <div
                className={`w-14 h-14 bg-primary/30 border border-border ${r.cls ?? ''}`}
                style={r.style}
              />
              <span className="text-[10px] text-muted-foreground">{r.label}</span>
            </div>
          ))}
        </div>
      </Section>

      {/* ── Bubbles ── */}
      <Section title="Message Bubbles">
        <div className="flex flex-col gap-4 max-w-md">
          {/* iMessage outgoing */}
          <div className="self-end">
            <div
              className="bg-primary text-primary-foreground px-4 py-2 break-words"
              style={{
                borderRadius: 'var(--radius-bubble)',
                borderBottomRightRadius: 'var(--bubble-tail)',
                boxShadow: 'var(--bubble-shadow)',
                fontSize: 'var(--font-size-message)',
              }}
            >
              Outgoing iMessage bubble
            </div>
            <p className="text-[10px] text-muted-foreground text-right mt-0.5">bg-primary</p>
          </div>
          {/* Incoming */}
          <div className="self-start">
            <div
              className="text-foreground px-4 py-2 break-words"
              style={{
                backgroundColor: 'hsl(var(--msg-them))',
                borderRadius: 'var(--radius-bubble)',
                borderBottomLeftRadius: 'var(--bubble-tail)',
                boxShadow: 'var(--bubble-shadow)',
                fontSize: 'var(--font-size-message)',
              }}
            >
              Incoming message bubble
            </div>
            <p className="text-[10px] text-muted-foreground mt-0.5">--msg-them</p>
          </div>
          {/* SMS outgoing */}
          <div className="self-end">
            <div
              className="px-4 py-2 break-words"
              style={{
                backgroundColor: 'hsl(var(--msg-sms))',
                color: 'hsl(var(--msg-sms-text))',
                borderRadius: 'var(--radius-bubble)',
                borderBottomRightRadius: 'var(--bubble-tail)',
                boxShadow: 'var(--bubble-shadow)',
                fontSize: 'var(--font-size-message)',
              }}
            >
              Outgoing SMS bubble (green)
            </div>
            <p className="text-[10px] text-muted-foreground text-right mt-0.5">--msg-sms / --msg-sms-text</p>
          </div>
        </div>
      </Section>

      {/* ── Tapback bar ── */}
      <Section title="Tapback Bar + Tooltip">
        <p className="text-xs text-muted-foreground mb-2">Hover each emoji to see the themed Radix tooltip (bg-popover).</p>
        <div className="inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 bg-card shadow-sm border border-border/60 text-sm leading-none">
          {tapbackEmojis.map((emoji) => (
            <Tooltip key={emoji}>
              <TooltipTrigger asChild>
                <span className="inline-flex items-center gap-[2px] cursor-default">
                  {emoji}
                  <span className="text-[10px] text-muted-foreground">2</span>
                </span>
              </TooltipTrigger>
              <TooltipContent side="bottom" className="text-xs">
                <div>Jane Doe &middot; 2026-05-10 12:34 PM</div>
                <div>John Smith &middot; 2026-05-10 12:45 PM</div>
              </TooltipContent>
            </Tooltip>
          ))}
        </div>
        <p className="text-[10px] text-muted-foreground mt-2">
          Note: Emojis are OS-native (Apple Color Emoji / Segoe UI Emoji) and cannot be themed via CSS.
        </p>
      </Section>

      {/* ── Badges ── */}
      <Section title="Badges">
        <div className="flex flex-wrap gap-3 items-center">
          <Badge>default</Badge>
          <Badge variant="secondary">secondary</Badge>
          <Badge variant="outline">outline</Badge>
          <Badge variant="destructive">destructive</Badge>
          <Badge variant="outline" className="text-warning">ghost/warning</Badge>
          <Badge variant="destructive" className="text-[10px] px-1.5 py-0.5">failed (small)</Badge>
        </div>
      </Section>

      {/* ── Buttons ── */}
      <Section title="Buttons">
        <div className="flex flex-wrap gap-3 items-center">
          <Button>Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="outline">Outline</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="destructive">Destructive</Button>
          <Button size="sm">Small</Button>
          <Button size="icon"><Settings className="w-4 h-4" /></Button>
        </div>
      </Section>

      {/* ── Avatars ── */}
      <Section title="Avatars">
        <div className="flex gap-4 items-end">
          <div className="flex flex-col items-center gap-1">
            <div
              className="bg-card text-primary font-semibold text-sm flex items-center justify-center"
              style={{
                width: 'var(--avatar-size)',
                height: 'var(--avatar-size)',
                borderRadius: 'var(--avatar-shape)',
              }}
            >
              AB
            </div>
            <span className="text-[10px] text-muted-foreground">1:1 (round)</span>
          </div>
          <div className="flex flex-col items-center gap-1">
            <div
              className="bg-card text-primary font-semibold text-sm flex items-center justify-center rounded-lg"
              style={{
                width: 'var(--avatar-size)',
                height: 'var(--avatar-size)',
              }}
            >
              GC
            </div>
            <span className="text-[10px] text-muted-foreground">Group (square-ish)</span>
          </div>
        </div>
      </Section>

      {/* ── Tooltip (standalone) ── */}
      <Section title="Tooltip">
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="text-sm text-primary underline cursor-default">Hover me</span>
          </TooltipTrigger>
          <TooltipContent>
            <p>This uses bg-popover + text-popover-foreground</p>
          </TooltipContent>
        </Tooltip>
      </Section>

      {/* ── Link preview card ── */}
      <Section title="Link Preview Card">
        <div className="max-w-xs">
          <div className="rounded-lg overflow-hidden">
            <div className="w-full h-24 bg-muted flex items-center justify-center text-muted-foreground text-xs">
              [preview image]
            </div>
            <div className="px-3 py-2 bg-muted/80">
              <p className="text-sm font-medium text-foreground">Page Title</p>
              <p className="text-xs text-muted-foreground mt-0.5">A short description of the linked page content.</p>
              <p className="text-xs text-muted-foreground mt-1">example.com</p>
            </div>
          </div>
        </div>
      </Section>

      {/* ── Reply quote ── */}
      <Section title="Reply Quote (Ghost Bubble)">
        <div className="flex gap-8">
          <div className="flex flex-col items-start">
            <button
              className="text-left rounded-2xl px-3 py-1.5 max-w-[200px] bg-muted/70 border border-border/50"
              style={{ fontSize: '0.8em' }}
            >
              <p className="line-clamp-2 whitespace-pre-wrap break-words text-foreground/60">
                Original message text here...
              </p>
            </button>
            <div className="w-0.5 h-3 rounded-full self-start ml-3.5 bg-muted-foreground/20" />
            <div
              className="text-foreground px-4 py-2"
              style={{
                backgroundColor: 'hsl(var(--msg-them))',
                borderRadius: 'var(--radius-bubble)',
                borderBottomLeftRadius: 'var(--bubble-tail)',
                fontSize: 'var(--font-size-message)',
              }}
            >
              Reply to that
            </div>
            <p className="text-[10px] text-muted-foreground mt-0.5">Incoming reply</p>
          </div>
          <div className="flex flex-col items-end">
            <button
              className="text-left rounded-2xl px-3 py-1.5 max-w-[200px] bg-primary/15 border border-primary/25"
              style={{ fontSize: '0.8em' }}
            >
              <p className="line-clamp-2 whitespace-pre-wrap break-words text-primary/65">
                My original message...
              </p>
            </button>
            <div className="w-0.5 h-3 rounded-full self-end mr-3.5 bg-primary/30" />
            <div
              className="bg-primary text-primary-foreground px-4 py-2"
              style={{
                borderRadius: 'var(--radius-bubble)',
                borderBottomRightRadius: 'var(--bubble-tail)',
                fontSize: 'var(--font-size-message)',
              }}
            >
              My reply
            </div>
            <p className="text-[10px] text-muted-foreground text-right mt-0.5">Outgoing reply</p>
          </div>
        </div>
      </Section>

      {/* ── Sidebar item ── */}
      <Section title="Sidebar Items">
        <div className="bg-muted rounded-lg p-2 max-w-xs space-y-1">
          {/* Active */}
          <div className="flex items-center gap-3 px-3 py-2 bg-accent rounded" style={{ borderRadius: 'var(--sidebar-active-radius)' }}>
            <div className="w-8 h-8 rounded-full bg-card text-primary text-xs font-semibold flex items-center justify-center" style={{ borderRadius: 'var(--avatar-shape)' }}>JW</div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-foreground truncate">
                <span className="mr-1 text-xs text-warning">&#9733;</span>
                Jane Williams
              </p>
              <p className="text-xs text-muted-foreground truncate">Hey, how&apos;s it going?</p>
            </div>
          </div>
          {/* Group */}
          <div className="flex items-center gap-3 px-3 py-2">
            <div className="w-8 h-8 rounded-lg bg-card text-primary text-xs font-semibold flex items-center justify-center">FM</div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-foreground truncate">
                <span className="mr-1 text-xs opacity-60">[G]</span>
                Family Group
              </p>
              <p className="text-xs text-muted-foreground truncate">Mom: Happy Mother&apos;s Day!</p>
            </div>
          </div>
          {/* With unread dot */}
          <div className="flex items-center gap-3 px-3 py-2">
            <div className="w-8 h-8 rounded-full bg-card text-primary text-xs font-semibold flex items-center justify-center" style={{ borderRadius: 'var(--avatar-shape)' }}>KB</div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-foreground truncate">Klaus Butheau</p>
              <p className="text-xs text-muted-foreground truncate">Check this out</p>
            </div>
            <div className="w-2.5 h-2.5 rounded-full bg-primary flex-shrink-0" />
          </div>
        </div>
      </Section>

      {/* ── Icons: Lucide ── */}
      <Section title="Icons: Lucide React (library)">
        <div className="flex flex-wrap gap-4">
          {lucideIcons.map((i) => (
            <div key={i.name} className="flex flex-col items-center gap-1 text-foreground">
              {i.icon}
              <span className="text-[10px] text-muted-foreground">{i.name}</span>
            </div>
          ))}
        </div>
      </Section>

      {/* ── Icons: Inline SVG ── */}
      <Section title="Icons: Inline SVGs (hand-rolled)">
        <p className="text-xs text-muted-foreground mb-2">
          These duplicate some lucide icons. All use currentColor so they theme correctly.
        </p>
        <div className="flex flex-wrap gap-4">
          {inlineIcons.map((i) => (
            <div key={i.name} className="flex flex-col items-center gap-1 text-muted-foreground">
              {i.icon}
              <span className="text-[10px] text-muted-foreground">{i.name}</span>
            </div>
          ))}
        </div>
      </Section>

      {/* ── Reaction panel ── */}
      <Section title="Reaction Panel">
        <p className="text-xs text-muted-foreground mb-2">Unified Radix popover — hover (200ms) / long-press (500ms). Quick reactions + action rows + existing reactions summary.</p>
        <div className="flex flex-wrap gap-8">
          {/* Normal state */}
          <div>
            <p className="text-[10px] text-muted-foreground mb-1">Normal</p>
            <div
              className="inline-block rounded-xl border shadow-md overflow-hidden"
              style={{
                backgroundColor: 'var(--reaction-panel-bg)',
                color: 'var(--reaction-panel-text)',
                borderColor: 'var(--reaction-panel-border)',
              }}
            >
              {/* Quick reactions row — 8-col grid matching ReactionPanel.tsx */}
              <div
                className="grid gap-0.5 px-1.5 pt-2 pb-1"
                style={{ gridTemplateColumns: 'repeat(8, 1fr)' }}
              >
                {tapbackEmojis.map((emoji) => (
                  <button
                    key={emoji}
                    type="button"
                    className="flex items-center justify-center rounded-lg hover:bg-accent transition-colors leading-none aspect-square"
                    style={{ fontSize: '1.75rem' }}
                  >
                    {emoji}
                  </button>
                ))}
                {/* More reactions — opens full emoji picker */}
                <button
                  type="button"
                  className="flex items-center justify-center rounded-lg hover:bg-accent transition-colors leading-none aspect-square"
                  style={{ fontSize: '1.75rem' }}
                >
                  ☺
                </button>
                {/* Empty 8th cell for grid alignment */}
              </div>

              {/* Action rows — uses --icon-size-md / --icon-stroke */}
              <div className="flex flex-col py-1 min-w-[160px]" style={{ fontSize: 'var(--font-size-message)' }}>
                <button type="button" className="flex items-center gap-2 px-3 py-1.5 hover:bg-accent transition-colors text-left">
                  <svg className="shrink-0" style={{ width: 'var(--icon-size-md)', height: 'var(--icon-size-md)' }} fill="none" stroke="currentColor" strokeWidth="var(--icon-stroke)" viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" /></svg>
                  Copy
                </button>
                <button type="button" className="flex items-center gap-2 px-3 py-1.5 hover:bg-accent transition-colors text-left">
                  <svg className="shrink-0" style={{ width: 'var(--icon-size-md)', height: 'var(--icon-size-md)' }} fill="none" stroke="currentColor" strokeWidth="var(--icon-stroke)" viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round"><polyline points="9 17 4 12 9 7" /><path d="M20 18v-2a4 4 0 0 0-4-4H4" /></svg>
                  Reply
                </button>
                <button type="button" className="flex items-center gap-2 px-3 py-1.5 hover:bg-accent transition-colors text-left">
                  <svg className="shrink-0" style={{ width: 'var(--icon-size-md)', height: 'var(--icon-size-md)' }} fill="none" stroke="currentColor" strokeWidth="var(--icon-stroke)" viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>
                  Edit
                </button>
                <button type="button" className="flex items-center gap-2 px-3 py-1.5 text-destructive hover:bg-destructive/10 transition-colors text-left">
                  <svg className="shrink-0" style={{ width: 'var(--icon-size-md)', height: 'var(--icon-size-md)' }} fill="none" stroke="currentColor" strokeWidth="var(--icon-stroke)" viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /></svg>
                  Unsend
                </button>
              </div>

              {/* Existing reactions summary */}
              <div className="border-t border-border/40 mx-2" />
              <div className="px-3 py-1.5" style={{ fontSize: 'var(--font-size-message)' }}>
                <div className="py-1">
                  <div className="flex items-center gap-1.5 font-medium">
                    <span>❤️</span><span>Loved</span>
                  </div>
                  <div className="ml-6 text-muted-foreground">
                    <div>Jane Doe</div>
                    <div>John Smith</div>
                  </div>
                </div>
                <div className="py-1">
                  <div className="flex items-center gap-1.5 font-medium">
                    <span>😂</span><span>Laughed</span>
                  </div>
                  <div className="ml-6 text-muted-foreground">
                    <div>Jane Doe</div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Edit mode */}
          <div>
            <p className="text-[10px] text-muted-foreground mb-1">Edit mode (fromMe + ventura)</p>
            <div
              className="inline-block rounded-xl border shadow-md overflow-hidden"
              style={{
                backgroundColor: 'var(--reaction-panel-bg)',
                color: 'var(--reaction-panel-text)',
                borderColor: 'var(--reaction-panel-border)',
              }}
            >
              <div className="p-2 flex gap-1 min-w-[260px]">
                <input
                  className="flex-1 rounded-lg border border-border bg-input px-2 py-1 text-foreground min-w-0"
                  style={{ fontSize: 'var(--font-size-message)' }}
                  defaultValue="Edited message text"
                  readOnly
                />
                <button
                  type="button"
                  className="px-2 py-1 rounded-lg bg-primary text-primary-foreground text-xs hover:opacity-90"
                >
                  Save
                </button>
                <button
                  type="button"
                  className="px-2 py-1 rounded-lg bg-muted text-muted-foreground text-xs hover:text-foreground"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      </Section>

      {/* ── Emoji Picker ── */}
      <Section title="Emoji Picker">
        <p className="text-xs text-muted-foreground mb-2">Custom emoji picker — no external libraries. Search, categories, recently used (localStorage).</p>
        <div
          className="rounded-xl border overflow-hidden"
          style={{
            backgroundColor: 'var(--reaction-panel-bg)',
            borderColor: 'var(--reaction-panel-border)',
            width: 350,
          }}
        >
          <EmojiPicker onSelect={(emoji) => console.log('picked:', emoji)} />
        </div>
      </Section>

      {/* ── Inputs ── */}
      <Section title="Inputs">
        <div className="flex flex-wrap gap-4 max-w-md">
          <input
            type="text"
            placeholder="Text input"
            className="flex-1 min-w-[200px] bg-input border border-border text-foreground placeholder:text-muted-foreground px-3 py-2 text-sm"
            style={{ borderRadius: 'var(--radius-input)' }}
            readOnly
          />
          <textarea
            placeholder="Textarea / compose box"
            className="w-full bg-input border border-border text-foreground placeholder:text-muted-foreground px-3 py-2 text-sm rounded-lg resize-none"
            rows={2}
            readOnly
          />
        </div>
      </Section>

      {/* ── Icon Theming ── */}
      <Section title="Icon Theming (CSS vars)">
        <p className="text-xs text-muted-foreground mb-3">
          Icons sized via <code className="text-primary">--icon-size-sm/md/lg</code> and stroked via <code className="text-primary">--icon-stroke</code>.
          Current values:{' '}
          sm={getComputedStyle(document.documentElement).getPropertyValue('--icon-size-sm').trim() || '(empty)'},{' '}
          md={getComputedStyle(document.documentElement).getPropertyValue('--icon-size-md').trim() || '(empty)'},{' '}
          lg={getComputedStyle(document.documentElement).getPropertyValue('--icon-size-lg').trim() || '(empty)'},{' '}
          stroke={getComputedStyle(document.documentElement).getPropertyValue('--icon-stroke').trim() || '(empty)'}
        </p>
        <div className="flex flex-wrap gap-6">
          {/* sm */}
          <div className="flex flex-col items-center gap-1">
            <Bell className="text-foreground" style={{ width: 'var(--icon-size-sm)', height: 'var(--icon-size-sm)' }} />
            <span className="text-[10px] text-muted-foreground">--icon-size-sm</span>
          </div>
          <div className="flex flex-col items-center gap-1">
            <svg className="text-foreground" style={{ width: 'var(--icon-size-sm)', height: 'var(--icon-size-sm)' }} fill="none" stroke="currentColor" strokeWidth="var(--icon-stroke)" viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="9 17 4 12 9 7" /><path d="M20 18v-2a4 4 0 0 0-4-4H4" />
            </svg>
            <span className="text-[10px] text-muted-foreground">Reply (sm)</span>
          </div>
          {/* md */}
          <div className="flex flex-col items-center gap-1">
            <Settings className="text-foreground" style={{ width: 'var(--icon-size-md)', height: 'var(--icon-size-md)' }} />
            <span className="text-[10px] text-muted-foreground">--icon-size-md</span>
          </div>
          <div className="flex flex-col items-center gap-1">
            <svg className="text-foreground" style={{ width: 'var(--icon-size-md)', height: 'var(--icon-size-md)' }} fill="none" stroke="currentColor" strokeWidth="var(--icon-stroke)" viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" />
            </svg>
            <span className="text-[10px] text-muted-foreground">File (md)</span>
          </div>
          {/* lg */}
          <div className="flex flex-col items-center gap-1">
            <Puzzle className="text-foreground" style={{ width: 'var(--icon-size-lg)', height: 'var(--icon-size-lg)' }} />
            <span className="text-[10px] text-muted-foreground">--icon-size-lg</span>
          </div>
          <div className="flex flex-col items-center gap-1">
            <svg className="text-foreground" style={{ width: 'var(--icon-size-lg)', height: 'var(--icon-size-lg)' }} fill="none" stroke="currentColor" strokeWidth="var(--icon-stroke)" viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
            </svg>
            <span className="text-[10px] text-muted-foreground">Zap (lg)</span>
          </div>
        </div>
      </Section>

      {/* ── Font Family ── */}
      <Section title="Font Family (CSS var)">
        <div className="bg-muted rounded px-3 py-1.5 inline-block">
          <code className="text-primary text-xs">--font-family</code>
          <span className="text-muted-foreground text-xs font-mono ml-2">
            {getComputedStyle(document.documentElement).getPropertyValue('--font-family').trim() || '(empty)'}
          </span>
        </div>
        <p className="text-sm text-foreground mt-2" style={{ fontFamily: 'var(--font-family)' }}>
          The quick brown fox jumps over the lazy dog. 0123456789
        </p>
      </Section>

      {/* ── Scrollbar ── */}
      <Section title="Scrollbar Theming">
        <p className="text-xs text-muted-foreground mb-2">
          Scrollbar width: <code className="text-primary">{getComputedStyle(document.documentElement).getPropertyValue('--scrollbar-width').trim() || '8px'}</code>.
          Track uses <code className="text-primary">--muted</code>, thumb uses <code className="text-primary">--border</code>, hover uses <code className="text-primary">--muted-foreground</code>.
        </p>
        <div
          className="w-64 h-32 overflow-y-auto rounded-lg border border-border bg-background p-3 text-sm text-foreground"
        >
          {Array.from({ length: 20 }, (_, i) => (
            <p key={i} className="py-0.5">Scrollable line {i + 1}</p>
          ))}
        </div>
      </Section>

      {/* ── Background Images ── */}
      <Section title="Background Images (CSS vars)">
        <div className="grid grid-cols-2 gap-2 text-sm max-w-md">
          <div className="flex justify-between gap-2 bg-muted rounded px-3 py-1.5">
            <code className="text-primary text-xs">--sidebar-bg-image</code>
            <span className="text-muted-foreground text-xs font-mono">
              {getComputedStyle(document.documentElement).getPropertyValue('--sidebar-bg-image').trim() || '(empty)'}
            </span>
          </div>
          <div className="flex justify-between gap-2 bg-muted rounded px-3 py-1.5">
            <code className="text-primary text-xs">--header-bg-image</code>
            <span className="text-muted-foreground text-xs font-mono">
              {getComputedStyle(document.documentElement).getPropertyValue('--header-bg-image').trim() || '(empty)'}
            </span>
          </div>
        </div>
      </Section>

      {/* ── Toasts (Sonner) ── */}
      <Section title="Toasts (Sonner)">
        <p className="text-xs text-muted-foreground mb-3">
          Themed via scheme vars: bg-background, text-foreground, border-border.
          Action button uses bg-primary / text-primary-foreground.
        </p>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => toast.success('Settings saved.')}>
            Success
          </Button>
          <Button size="sm" variant="outline" onClick={() => toast.error('Failed to send message.')}>
            Error
          </Button>
          <Button size="sm" variant="outline" onClick={() => toast.info('3 new messages')}>
            Info
          </Button>
          <Button size="sm" variant="outline" onClick={() => toast.warning('Connection unstable')}>
            Warning
          </Button>
          <Button size="sm" variant="outline" onClick={() => toast('App updated in background', {
            description: 'Reload to activate the new version.',
            duration: Infinity,
            action: { label: 'Reload', onClick: () => {} },
          })}>
            Persistent + Action
          </Button>
          <Button size="sm" variant="outline" onClick={() => toast('Copied to clipboard')}>
            Default
          </Button>
        </div>
      </Section>

      {/* footer */}
      <div className="mt-12 pt-4 border-t border-border text-xs text-muted-foreground">
        Switch themes from <a href="/settings" className="text-primary underline">Settings</a> to see this page update live.
      </div>
      </div>{/* end content wrapper */}
    </div>
  )
}
