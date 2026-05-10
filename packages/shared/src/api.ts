/**
 * ChaiwireClient — typed API client for the chatwire server.
 *
 * Works in both React Native (fetch polyfill from RN runtime) and
 * browser environments.
 */

import type {
  Conversation,
  Message,
  ServerSettings,
  PushSubscribePayload,
} from './types.js'

export interface ChaiwireClientOptions {
  /** Base URL of the chatwire server, e.g. "http://192.168.1.10:8723". */
  baseUrl: string
  /** Optional password for /login. When provided it is sent as Bearer token. */
  credentials?: string
}

export interface MessagesResult {
  messages: Message[]
  has_more: boolean
}

export interface SendResult {
  status: string
  hint: string
  service: string
}

export class ChaiwireClient {
  private baseUrl: string
  private credentials: string | undefined

  constructor(opts: ChaiwireClientOptions) {
    // Strip trailing slash
    this.baseUrl = opts.baseUrl.replace(/\/$/, '')
    this.credentials = opts.credentials
  }

  // ---------------------------------------------------------------------------
  // Internal helpers
  // ---------------------------------------------------------------------------

  private buildHeaders(): Record<string, string> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    }
    if (this.credentials) {
      headers['Authorization'] = `Bearer ${this.credentials}`
    }
    return headers
  }

  private async fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
    const url = `${this.baseUrl}${path}`
    const res = await fetch(url, {
      ...init,
      headers: {
        ...this.buildHeaders(),
        ...(init?.headers as Record<string, string> | undefined),
      },
    })
    if (!res.ok) {
      const body = await res.text()
      throw new Error(`${res.status} ${res.statusText}: ${body}`)
    }
    return res.json() as Promise<T>
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  /** Check server reachability. Returns true when server responds 200. */
  async healthz(): Promise<boolean> {
    try {
      const res = await fetch(`${this.baseUrl}/healthz`, {
        headers: this.buildHeaders(),
      })
      return res.ok
    } catch {
      return false
    }
  }

  /** Fetch all conversations (sorted by last message). */
  async getConversations(): Promise<Conversation[]> {
    const data = await this.fetchJson<{ conversations: Conversation[] }>(
      '/api/ui/conversations',
    )
    return data.conversations
  }

  /**
   * Fetch messages for a conversation.
   * @param handle - phone handle or group GUID
   * @param opts.isGroup - true when handle is a group GUID
   * @param opts.since - only return messages with date > since (0 = all)
   * @param opts.limit - max messages to return
   */
  async getMessages(
    handle: string,
    opts: { isGroup?: boolean; since?: number; limit?: number } = {},
  ): Promise<MessagesResult> {
    const { isGroup = false, since = 0, limit = 100 } = opts
    const params = new URLSearchParams({
      ...(isGroup ? { guid: handle } : { handle }),
      since: String(since),
      limit: String(limit),
    })
    return this.fetchJson<MessagesResult>(`/api/ui/messages?${params}`)
  }

  /**
   * Fetch older messages (pagination).
   * @param handle - phone handle or group GUID
   */
  async getOlderMessages(
    handle: string,
    opts: {
      isGroup?: boolean
      beforeDate: number
      beforeRowid: number
      limit?: number
    },
  ): Promise<MessagesResult> {
    const { isGroup = false, beforeDate, beforeRowid, limit = 50 } = opts
    const params = new URLSearchParams({
      ...(isGroup ? { guid: handle } : { handle }),
      before_date: String(beforeDate),
      before_rowid: String(beforeRowid),
      limit: String(limit),
    })
    return this.fetchJson<MessagesResult>(`/api/ui/messages?${params}`)
  }

  /** Send a text message. */
  async sendMessage(
    handle: string,
    text: string,
    isGroup = false,
  ): Promise<SendResult> {
    return this.fetchJson<SendResult>('/api/ui/send', {
      method: 'POST',
      body: JSON.stringify(
        isGroup ? { handle: '', guid: handle, text } : { handle, text },
      ),
    })
  }

  /** Fetch server settings. */
  async getSettings(): Promise<ServerSettings> {
    return this.fetchJson<ServerSettings>('/api/ui/settings')
  }

  /** Register an Expo push token with the server. */
  async subscribePush(payload: PushSubscribePayload): Promise<void> {
    await this.fetchJson<void>('/push/subscribe', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  }

  /**
   * Returns the full SSE URL for the /events endpoint.
   * The caller is responsible for creating the EventSource connection.
   */
  eventsUrl(): string {
    return `${this.baseUrl}/events`
  }

  /**
   * Returns the full URL for an attachment path.
   * attachment.path is a relative URL like /attachment/...
   */
  attachmentUrl(path: string): string {
    return path.startsWith('http') ? path : `${this.baseUrl}${path}`
  }
}
