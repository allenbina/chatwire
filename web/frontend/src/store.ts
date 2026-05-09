/**
 * Global client state via Zustand.
 *
 * Kept deliberately small: only state that genuinely crosses component
 * boundaries (selected conversation, optimistic messages, sidebar open on
 * mobile) lives here. Everything else is local component state or
 * react-query cache.
 */
import { create } from 'zustand'
import type { Message } from './api'

interface OptimisticMessage extends Message {
  pending: true
}

interface ChatState {
  /** Currently open conversation handle, or null for the list view. */
  activeHandle: string | null
  setActiveHandle: (handle: string | null) => void

  /**
   * Optimistic messages keyed by handle. These are displayed immediately
   * on send and removed when the SSE event confirms delivery (matching by
   * text + approximate timestamp).
   */
  optimistic: Record<string, OptimisticMessage[]>
  addOptimistic: (handle: string, msg: OptimisticMessage) => void
  clearOptimistic: (handle: string, rowid: number) => void

  /** Mobile: is the sidebar drawer open? */
  sidebarOpen: boolean
  setSidebarOpen: (open: boolean) => void
}

let _nextOptId = -1

export const useChatStore = create<ChatState>((set) => ({
  activeHandle: null,
  setActiveHandle: (handle) => set({ activeHandle: handle }),

  optimistic: {},
  addOptimistic: (handle, msg) =>
    set((s) => ({
      optimistic: {
        ...s.optimistic,
        [handle]: [...(s.optimistic[handle] ?? []), msg],
      },
    })),
  clearOptimistic: (handle, rowid) =>
    set((s) => ({
      optimistic: {
        ...s.optimistic,
        [handle]: (s.optimistic[handle] ?? []).filter((m) => m.rowid !== rowid),
      },
    })),

  sidebarOpen: false,
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
}))

/** Create a temporary (negative) rowid for an optimistic message. */
export function nextOptimisticId(): number {
  return _nextOptId--
}
