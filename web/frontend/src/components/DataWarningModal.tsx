/**
 * DataWarningModal — first-run modal that informs the user chatwire exposes
 * their iMessages over a local HTTP server.
 *
 * Shown once on first load; permanently dismissed by clicking the acknowledge
 * button. Dismissal is persisted in localStorage so the modal never reappears.
 *
 * Issue: #23
 */
import { useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { ShieldAlert } from 'lucide-react'

const DISMISSED_KEY = 'chatwire-dismissed-data-warning'

export function DataWarningModal() {
  const [open, setOpen] = useState(() => !localStorage.getItem(DISMISSED_KEY))

  function dismiss() {
    localStorage.setItem(DISMISSED_KEY, '1')
    setOpen(false)
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) dismiss() }}>
      <DialogContent
        className="max-w-md"
        // Prevent closing by clicking the overlay — user must click the button.
        onInteractOutside={(e) => e.preventDefault()}
      >
        <DialogHeader>
          <div className="flex items-center gap-2 mb-1">
            <ShieldAlert className="w-5 h-5 text-warning flex-shrink-0" aria-hidden="true" />
            <DialogTitle>Your messages are accessible over the network</DialogTitle>
          </div>
          <DialogDescription asChild>
            <div className="space-y-2 text-sm text-muted-foreground">
              <p>
                chatwire serves your iMessages over HTTP on this device. Anyone
                on the same network who knows the port can read your
                conversations and attachments.
              </p>
              <p>
                To restrict access, set a password in{' '}
                <strong className="text-foreground">Settings → Security</strong>.
                Only run chatwire on networks you trust.
              </p>
            </div>
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <button
            type="button"
            onClick={dismiss}
            className="inline-flex items-center justify-center rounded-md
                       bg-primary text-primary-foreground hover:bg-primary/90
                       px-4 py-2 text-sm font-medium transition-colors
                       focus-visible:outline-none focus-visible:ring-2
                       focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            I understand
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
