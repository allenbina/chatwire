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
  last_rowid: number
  last_seen_rowid: number
  n: number
  unseen: boolean
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
  last_rowid: number
  last_seen_rowid: number
  n: number
  unseen: boolean
  is_favorite: boolean
  last: string
}

export type Conversation = HandleConversation | GroupConversation

/** Convert a display name to a URL-safe slug (lowercase, hyphens, no specials). */
function slugify(name: string): string {
  return name
    .toLowerCase()
    .normalize('NFD')                     // decompose accented chars
    .replace(/[\u0300-\u036f]/g, '')      // strip combining marks
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    || 'conversation'
}

/**
 * Returns the routing key (URL path segment) for a conversation.
 *
 * When the conversation has a display name, a slugified version is used so
 * URLs are human-readable (/chat/sarah-chen instead of /chat/%2B14695551234).
 * Group GUIDs are always used as-is (they're already URL-safe opaque tokens).
 */
export function convRouteKey(c: Conversation): string {
  const name = c.name?.trim()
  if (c.kind === 'handle') {
    return name ? slugify(name) : c.handle
  }
  // For groups: slugify the name if present, fall back to GUID.
  return name ? slugify(name) : c.guid
}

/**
 * Resolve a URL slug or raw handle/guid back to the conversation's real handle.
 *
 * If `param` already looks like a raw handle (+, @, or ; present), return it
 * unchanged. Otherwise search `conversations` for a matching route key.
 *
 * Returns null when `conversations` is empty (still loading) or no match.
 */
export function resolveConvoHandle(
  param: string,
  conversations: Conversation[],
): string | null {
  if (!param) return null
  // Already a raw handle — phone (+), email (@), or group GUID (;)
  if (/[+@;]/.test(param)) return param
  const convo = conversations.find((c) => convRouteKey(c) === param)
  if (!convo) return null
  return convo.kind === 'group' ? convo.guid : convo.handle
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { credentials: 'same-origin', ...init })
  if (res.status === 401) {
    // Session expired — redirect to the React login page preserving current location.
    window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`
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

export async function markSeen(conversationId: string, lastRowid: number): Promise<void> {
  await fetchJson('/api/ui/read-state', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ conversation_id: conversationId, last_rowid: lastRowid }),
  })
}

export async function markAllSeen(): Promise<void> {
  await fetchJson('/api/ui/read-state/all', { method: 'POST' })
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
    window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`
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

// ---------------------------------------------------------------------------
// Contact info sheet
// ---------------------------------------------------------------------------

export interface HandleRow {
  handle: string
  capability: string
  cap_class: string
}

export interface MemberRow {
  handle: string
  name: string
  capability: string
  cap_class: string
}

export interface MediaEntry {
  path: string
  name: string
  mime: string
  kind: 'image' | 'video'
}

export interface HandleContactInfo {
  kind: 'handle'
  handle: string
  name: string
  subtitle: string
  handles: HandleRow[]
  media: MediaEntry[]
}

export interface GroupContactInfo {
  kind: 'group'
  chat: string
  name: string
  subtitle: string
  members: MemberRow[]
  media: MediaEntry[]
}

export type ContactInfo = HandleContactInfo | GroupContactInfo

export async function fetchContactInfo(id: string, isGroup: boolean): Promise<ContactInfo> {
  const params = new URLSearchParams(isGroup ? { guid: id } : { handle: id })
  return fetchJson(`/api/ui/contact-info?${params}`)
}

export async function removeFromWhitelist(id: string, isGroup: boolean): Promise<void> {
  const params = new URLSearchParams(isGroup ? { guid: id } : { handle: id })
  await fetchJson(`/api/ui/whitelist?${params}`, { method: 'DELETE' })
}
