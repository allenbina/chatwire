/**
 * Export dropdown for the conversation header.
 *
 * Provides download links for:
 *  - JSON export   (/api/export/messages?format=json)
 *  - TXT export    (/api/export/messages?format=txt)
 *  - CSV export    (/api/export/messages?format=csv)
 *  - Photos ZIP    (/api/export/photos)
 *
 * These are direct download hrefs — the server returns file responses.
 * For group chats the `chat` query param is used instead of `handle`.
 */
import { useState, useRef, useEffect } from 'react'

interface ExportDropdownProps {
  handle: string
  isGroup: boolean
}

export function ExportDropdown({ handle, isGroup }: ExportDropdownProps) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // Close on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const param = isGroup ? `chat=${encodeURIComponent(handle)}` : `handle=${encodeURIComponent(handle)}`

  const links = [
    { label: 'Export as JSON', href: `/api/export/messages?${param}&format=json` },
    { label: 'Export as TXT',  href: `/api/export/messages?${param}&format=txt` },
    { label: 'Export as CSV',  href: `/api/export/messages?${param}&format=csv` },
    { label: 'Download photos (ZIP)', href: `/api/export/photos?${param}` },
  ]

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="Export conversation"
        aria-haspopup="menu"
        aria-expanded={open}
        className="p-2 rounded-lg text-[--color-text-muted] hover:bg-[--color-sidebar-hover]
                   transition-colors flex items-center gap-1 text-sm"
        title="Export"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24"
             strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <polyline points="7 10 12 15 17 10"/>
          <line x1="12" y1="15" x2="12" y2="3"/>
        </svg>
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full mt-1 z-20 min-w-[180px] rounded-lg shadow-lg
                     bg-[--color-bg-tertiary] border border-[--color-border] py-1 text-sm"
        >
          {links.map(({ label, href }) => (
            <a
              key={label}
              href={href}
              role="menuitem"
              download
              onClick={() => setOpen(false)}
              className="block px-4 py-2 text-[--color-text-primary] hover:bg-[--color-sidebar-hover]
                         transition-colors"
            >
              {label}
            </a>
          ))}
        </div>
      )}
    </div>
  )
}
