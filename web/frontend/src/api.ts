/**
 * Typed wrappers around the /api/ui/* endpoints.
 *
 * All endpoints use the same session cookie as the Jinja2 UI — no API
 * key needed. Credentials are included automatically by the browser on
 * same-origin requests (and via the Vite dev proxy for localhost).
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Attachment {
  path: string
  name: string
  mime: string
  kind: 'image' | 'video' | 'audio' | 'file'
  ready: boolean
  is_plugin: boolean
  total_bytes: number
}

export interface LinkPreview {
  title?: string
  url?: string
  description?: string
  image_url?: string
}

export interface Message {
  rowid: number
  date: number
  from_me: boolean
  ts: string
  text: string
  attachments: Attachment[]
  link_preview: LinkPreview | null
  // delivery fields (from_me only)
  status?: string
  service?: string
  // group chat fields (incoming only)
  sender_handle?: string
  sender_name?: string
}

/** 1:1 conversation. */
export interface HandleConversation {
  kind: 'handle'
  handle: string
  name: string
  preview: string
  has_media: boolean
  last_dt: number
  n: number
  all_handles: string[]
  is_favorite: boolean
  last: string
}

/** Group chat conversation. */
export interface GroupConversation {
  kind: 'group'
  guid: string
  name: string
  preview: string
  has_media: boolean
  last_dt: number
  n: number
  is_favorite: boolean
  last: string
}

export type Conversation = HandleConversation | GroupConversation

/** Returns the routing key (URL-safe identifier) for a conversation. */
export function convRouteKey(c: Conversation): string {
  return c.kind === 'group' ? c.guid : c.handle
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { credentials: 'same-origin', ...init })
  if (res.status === 401) {
    // Session expired — redirect to the React login page preserving current location.
    window.location.href = `/app/login?next=${encodeURIComponent(window.location.pathname)}`
    throw new Error('Unauthenticated')
  }
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${body}`)
  }
  return res.json() as Promise<T>
}

// ---------------------------------------------------------------------------
// Conversations
// ---------------------------------------------------------------------------

export async function fetchConversations(): Promise<Conversation[]> {
  const data = await fetchJson<{ conversations: Conversation[] }>('/api/ui/conversations')
  return data.conversations
}

// ---------------------------------------------------------------------------
// Messages
// ---------------------------------------------------------------------------

export async function fetchMessages(
  id: string,
  isGroup: boolean,
  since = 0,
  limit = 100,
): Promise<{ messages: Message[]; has_more: boolean }> {
  const params = new URLSearchParams({
    ...(isGroup ? { guid: id } : { handle: id }),
    since: String(since),
    limit: String(limit),
  })
  return fetchJson(`/api/ui/messages?${params}`)
}

export async function fetchOlderMessages(
  id: string,
  isGroup: boolean,
  beforeDate: number,
  beforeRowid: number,
  limit = 50,
): Promise<{ messages: Message[]; has_more: boolean }> {
  const params = new URLSearchParams({
    ...(isGroup ? { guid: id } : { handle: id }),
    before_date: String(beforeDate),
    before_rowid: String(beforeRowid),
    limit: String(limit),
  })
  return fetchJson(`/api/ui/messages?${params}`)
}

// ---------------------------------------------------------------------------
// Send
// ---------------------------------------------------------------------------

export async function sendMessage(
  id: string,
  text: string,
  isGroup = false,
): Promise<{ status: string; hint: string; service: string }> {
  return fetchJson('/api/ui/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(isGroup ? { handle: '', guid: id, text } : { handle: id, text }),
  })
}

export async function sendFile(
  id: string,
  isGroup: boolean,
  file: File,
): Promise<{ status: string; hint: string; service: string }> {
  const fd = new FormData()
  if (isGroup) {
    fd.append('guid', id)
  } else {
    fd.append('handle', id)
  }
  fd.append('file', file)
  const res = await fetch('/api/ui/upload', {
    method: 'POST',
    credentials: 'same-origin',
    body: fd,
  })
  if (res.status === 401) {
    window.location.href = `/app/login?next=${encodeURIComponent(window.location.pathname)}`
    throw new Error('Unauthenticated')
  }
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${body}`)
  }
  return res.json()
}

// ---------------------------------------------------------------------------
// Themes
// ---------------------------------------------------------------------------

export async function fetchThemes(): Promise<{ themes: string[]; current: string }> {
  return fetchJson('/api/ui/themes')
}
