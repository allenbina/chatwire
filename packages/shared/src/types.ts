/**
 * Shared TypeScript types for chatwire web + mobile.
 * These match the shapes returned by /api/ui/* endpoints.
 */

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
  /** Delivery status (from_me messages only). */
  status?: string
  service?: string
  /** Sender info (group chat incoming messages only). */
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

/** Returns the URL-safe routing key for a conversation. */
export function convRouteKey(c: Conversation): string {
  return c.kind === 'group' ? c.guid : c.handle
}

/** Server-side settings shape (subset relevant to mobile). */
export interface ServerSettings {
  theme: string
  themes: string[]
  time_format: string
}

/** Push notification subscription payload. */
export interface PushSubscribePayload {
  token: string
  platform: 'ios' | 'android' | 'web'
}
