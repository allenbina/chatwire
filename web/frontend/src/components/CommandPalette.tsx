/**
 * Global command palette (Cmd+K / Ctrl+K).
 *
 * Provides fuzzy-search navigation to all pages and Settings sections.
 * Built on shadcn Command (wraps cmdk) — same pattern as VS Code, Linear, Notion.
 */
import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  CommandDialog,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
  CommandSeparator,
} from '@/components/ui/command'
import {
  Settings,
  Puzzle,
  ScrollText,
  Bug,
  MessageSquare,
  User,
  List,
  Sun,
  Bell,
  Shield,
  Lock,
  Wrench,
} from 'lucide-react'

interface PaletteItem {
  label: string
  keywords?: string
  icon: React.ReactNode
  action: () => void
}

export function CommandPalette() {
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()

  // Global Cmd+K / Ctrl+K listener
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        setOpen((prev) => !prev)
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [])

  const go = useCallback(
    (path: string) => {
      setOpen(false)
      navigate(path)
    },
    [navigate],
  )

  const pages: PaletteItem[] = [
    {
      label: 'Chat',
      keywords: 'messages conversations home',
      icon: <MessageSquare className="w-4 h-4" />,
      action: () => go('/'),
    },
    {
      label: 'Settings',
      keywords: 'preferences config',
      icon: <Settings className="w-4 h-4" />,
      action: () => go('/settings'),
    },
    {
      label: 'Plugins',
      keywords: 'extensions marketplace install',
      icon: <Puzzle className="w-4 h-4" />,
      action: () => go('/plugins'),
    },
    {
      label: 'Logs',
      keywords: 'events activity log stream',
      icon: <ScrollText className="w-4 h-4" />,
      action: () => go('/logs'),
    },
    {
      label: 'Debug',
      keywords: 'developer tools diagnostics',
      icon: <Bug className="w-4 h-4" />,
      action: () => go('/debug'),
    },
  ]

  const settingsSections: PaletteItem[] = [
    {
      label: 'Self handles',
      keywords: 'phone email identity handles',
      icon: <User className="w-4 h-4" />,
      action: () => go('/settings#self-handles'),
    },
    {
      label: 'Whitelist',
      keywords: 'allowed contacts filter relay',
      icon: <List className="w-4 h-4" />,
      action: () => go('/settings#whitelist'),
    },
    {
      label: 'Appearance',
      keywords: 'theme style color dark light scheme css sounds',
      icon: <Sun className="w-4 h-4" />,
      action: () => go('/settings#appearance'),
    },
    {
      label: 'Notifications',
      keywords: 'alerts hiatus reminder push sounds',
      icon: <Bell className="w-4 h-4" />,
      action: () => go('/settings#notifications'),
    },
    {
      label: 'Content filter',
      keywords: 'profanity censor block words categories',
      icon: <Shield className="w-4 h-4" />,
      action: () => go('/settings#content-filter'),
    },
    {
      label: 'MCP Server',
      keywords: 'mcp model context protocol tools agents claude',
      icon: <Settings className="w-4 h-4" />,
      action: () => go('/settings#mcp'),
    },
    {
      label: 'Advanced',
      keywords: 'port bind proxy api keys image cache server',
      icon: <Wrench className="w-4 h-4" />,
      action: () => go('/settings#advanced'),
    },
    {
      label: 'Password',
      keywords: 'auth login security lock',
      icon: <Lock className="w-4 h-4" />,
      action: () => go('/settings#password'),
    },
  ]

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder="Search settings, pages..." />
      <CommandList>
        <CommandEmpty>No results found.</CommandEmpty>
        <CommandGroup heading="Pages">
          {pages.map((item) => (
            <CommandItem
              key={item.label}
              keywords={item.keywords ? [item.keywords] : undefined}
              onSelect={item.action}
            >
              {item.icon}
              <span>{item.label}</span>
            </CommandItem>
          ))}
        </CommandGroup>
        <CommandSeparator />
        <CommandGroup heading="Settings">
          {settingsSections.map((item) => (
            <CommandItem
              key={item.label}
              keywords={item.keywords ? [item.keywords] : undefined}
              onSelect={item.action}
            >
              {item.icon}
              <span>{item.label}</span>
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  )
}
