/**
 * Two-pane shell: fixed sidebar on the left, scrollable main area on
 * the right. On narrow viewports the sidebar collapses into a drawer
 * toggled by the hamburger button. The sidebar always renders — it is
 * hidden via CSS on mobile when sidebarOpen is false.
 */
import { ReactNode } from 'react'
import { useChatStore } from '../store'
import { ConversationList } from './ConversationList'

interface LayoutProps {
  children: ReactNode
}

export function Layout({ children }: LayoutProps) {
  const { sidebarOpen, setSidebarOpen } = useChatStore()

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[--color-bg-primary] text-[--color-text-primary]">
      {/* ── Sidebar ── */}
      <aside
        className={[
          'flex-shrink-0 w-72 h-full flex flex-col',
          'bg-[--color-sidebar-bg] border-r border-[--color-border]',
          // Mobile: hidden by default, slide in as overlay when open
          'max-md:fixed max-md:inset-y-0 max-md:left-0 max-md:z-40',
          'max-md:transition-transform max-md:duration-200',
          sidebarOpen ? 'max-md:translate-x-0' : 'max-md:-translate-x-full',
        ].join(' ')}
      >
        {/* Sidebar header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[--color-border]">
          <span className="font-semibold text-[--color-accent]">Chatwire</span>
          <button
            className="md:hidden text-[--color-text-secondary] hover:text-[--color-text-primary]"
            onClick={() => setSidebarOpen(false)}
            aria-label="Close sidebar"
          >
            &#x2715;
          </button>
        </div>

        {/* Conversation list */}
        <div className="flex-1 overflow-y-auto">
          <ConversationList />
        </div>

        {/* Sidebar footer */}
        <div className="px-4 py-2 border-t border-[--color-border] flex items-center gap-2">
          <a
            href="/settings"
            className="text-xs text-[--color-text-muted] hover:text-[--color-accent] transition-colors"
          >
            Settings
          </a>
          <span className="text-[--color-border]">|</span>
          <a
            href="/app/settings"
            className="text-xs text-[--color-text-muted] hover:text-[--color-accent] transition-colors"
          >
            Themes
          </a>
        </div>
      </aside>

      {/* ── Mobile backdrop ── */}
      {sidebarOpen && (
        <div
          className="md:hidden fixed inset-0 z-30 bg-black/50"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* ── Main content area ── */}
      <main className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        {/* Mobile top bar */}
        <div className="md:hidden flex items-center px-3 py-2 bg-[--color-sidebar-bg] border-b border-[--color-border]">
          <button
            className="text-[--color-text-secondary] hover:text-[--color-text-primary] mr-3"
            onClick={() => setSidebarOpen(true)}
            aria-label="Open sidebar"
          >
            &#9776;
          </button>
          <span className="font-semibold text-[--color-accent]">Chatwire</span>
        </div>

        {children}
      </main>
    </div>
  )
}
