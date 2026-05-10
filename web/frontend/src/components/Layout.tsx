/**
 * Two-pane shell: fixed sidebar on the left, scrollable main area on
 * the right. On narrow viewports the sidebar collapses into a shadcn
 * Sheet (slide-over drawer) toggled by the hamburger button.
 *
 * Accessibility:
 *  - Skip-nav link at top (visible on focus via .sr-only:focus)
 *  - Sidebar is <nav aria-label="Conversations"> (inside ConversationList)
 *  - Main content area is <main aria-label="Chat">
 *  - Mobile Sheet uses a Radix Dialog — focus-trapping and aria-modal
 *    are inherited from Radix automatically.
 */
import { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useChatStore } from '../store'
import { ConversationList } from './ConversationList'
import { SlotRenderer } from '../plugins/SlotRenderer'
import {
  Sheet,
  SheetContent,
  SheetTitle,
} from '@/components/ui/sheet'

interface LayoutProps {
  children: ReactNode
}

function SidebarContent() {
  const setSidebarOpen = useChatStore((s) => s.setSidebarOpen)
  return (
    <div className="flex flex-col h-full bg-[--sidebar-bg]">
      {/* Mobile close button — hidden on desktop, sits in top-right corner */}
      <button
        className="md:hidden self-end mt-2 mr-3 text-muted-foreground hover:text-foreground"
        onClick={() => setSidebarOpen(false)}
        aria-label="Close sidebar"
      >
        &#x2715;
      </button>
      {/* Conversation list — starts immediately, no header */}
      <div className="flex-1 overflow-y-auto">
        <ConversationList />
        <SlotRenderer slot="sidebar.panel" />
      </div>
      {/* Sidebar footer */}
      <div className="px-4 py-2 border-t border-border flex items-center gap-2">
        <Link
          to="/settings"
          className="text-xs text-muted-foreground hover:text-primary transition-colors"
        >
          Settings
        </Link>
        <span className="text-border">|</span>
        <Link
          to="/settings#appearance"
          className="text-xs text-muted-foreground hover:text-primary transition-colors"
        >
          Appearance
        </Link>
      </div>
    </div>
  )
}

export function Layout({ children }: LayoutProps) {
  const { sidebarOpen, setSidebarOpen } = useChatStore()

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
      {/* Skip-nav link */}
      <a
        href="#messages"
        className="sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50
                   focus:px-4 focus:py-2 focus:rounded-lg
                   focus:bg-primary focus:text-primary-foreground
                   focus:text-sm focus:font-medium"
      >
        Skip to messages
      </a>

      {/* ── Desktop sidebar (always visible on md+) ── */}
      <aside className="hidden md:flex flex-col flex-shrink-0 w-[var(--sidebar-width)] h-full
                        bg-[--sidebar-bg] border-r border-border">
        <SidebarContent />
      </aside>

      {/* ── Mobile sidebar — shadcn Sheet ── */}
      <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
        <SheetContent
          side="left"
          className="p-0 w-[var(--sidebar-width)] border-r border-border bg-[--sidebar-bg]
                     [&>button]:hidden"
        >
          {/* SheetTitle is required by Radix for aria-labelledby */}
          <SheetTitle className="sr-only">Conversations</SheetTitle>
          <SidebarContent />
        </SheetContent>
      </Sheet>

      {/* ── Main content area ── */}
      <main
        aria-label="Chat"
        className="flex-1 flex flex-col min-w-0 h-full overflow-hidden"
      >
        {/* Mobile top bar */}
        <div className="md:hidden flex items-center px-3 py-2 bg-[--sidebar-bg] border-b border-border">
          <button
            className="text-muted-foreground hover:text-foreground mr-3"
            onClick={() => setSidebarOpen(true)}
            aria-label="Open sidebar"
          >
            &#9776;
          </button>
          <span className="font-semibold text-primary">Chatwire</span>
        </div>

        {children}
      </main>
    </div>
  )
}
