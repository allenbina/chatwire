/**
 * Vitest unit tests for api.ts
 *
 * Covers:
 *   convRouteKey
 *     - handle with display name → slugified name
 *     - handle without name (phone number) → raw handle
 *     - group with display name → slugified name
 *     - group without name → GUID
 *     - accented characters are stripped
 *     - special characters collapsed to hyphens
 *     - whitespace-only name treated as absent
 *     - slug falls back to "conversation" when result would be empty
 *
 *   resolveConvoHandle
 *     - empty param → null
 *     - raw phone handle (+...) returned as-is
 *     - raw email handle (@...) returned as-is
 *     - raw group GUID (;...) returned as-is
 *     - slug matched in conversations list → returns handle
 *     - slug matched for group → returns guid
 *     - slug not found → null
 *     - empty conversations list → null
 *
 *   fetchJson / API wrappers
 *     - 401 response → sets window.location.href to /login?next=...
 *     - non-ok response → throws Error with status + body
 *     - ok response → returns parsed JSON
 *     - fetchConversations → GET /api/ui/conversations, returns array
 *     - fetchMessages (handle) → correct query params
 *     - fetchMessages (group) → uses guid param
 *     - fetchOlderMessages → before_date + before_rowid params
 *     - sendMessage (1:1) → POST with handle + text
 *     - sendMessage (group) → POST with guid + text
 *     - markSeen → POST /api/ui/read-state with correct body
 *     - markAllSeen → POST /api/ui/read-state/all
 *     - sendTapback → POST /api/ui/tapback with rowid + type
 *     - editMessage → POST /api/ui/edit with rowid + text
 *     - unsendMessage → POST /api/ui/unsend with rowid
 *     - sendFile (handle) → POST /api/ui/upload with FormData
 *     - sendFile (group) → POST /api/ui/upload with guid in FormData
 *     - sendFile 401 → sets window.location.href to /login?next=...
 *     - sendFile non-ok → throws Error
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  convRouteKey,
  resolveConvoHandle,
  fetchConversations,
  fetchMessages,
  fetchOlderMessages,
  sendMessage,
  markSeen,
  markAllSeen,
  sendTapback,
  editMessage,
  unsendMessage,
  sendFile,
  type HandleConversation,
  type GroupConversation,
} from './api'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeHandle(overrides: Partial<HandleConversation> = {}): HandleConversation {
  return {
    kind: 'handle',
    handle: '+14695551234',
    name: '',
    preview: '',
    has_media: false,
    last_dt: 0,
    last_rowid: 0,
    last_seen_rowid: 0,
    n: 0,
    unseen: false,
    all_handles: [],
    is_favorite: false,
    last: '',
    ...overrides,
  }
}

function makeGroup(overrides: Partial<GroupConversation> = {}): GroupConversation {
  return {
    kind: 'group',
    guid: 'chat;+;abc123',
    name: '',
    preview: '',
    has_media: false,
    last_dt: 0,
    last_rowid: 0,
    last_seen_rowid: 0,
    n: 0,
    unseen: false,
    is_favorite: false,
    last: '',
    ...overrides,
  }
}

function mockFetch(response: object, ok = true, status = 200) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok,
    status,
    statusText: ok ? 'OK' : 'Error',
    json: async () => response,
    text: async () => JSON.stringify(response),
  }))
}

// ---------------------------------------------------------------------------
// window.location mock
// ---------------------------------------------------------------------------

let locationHref = ''

beforeEach(() => {
  locationHref = ''
  Object.defineProperty(window, 'location', {
    value: { href: '', pathname: '/app/chat' },
    writable: true,
    configurable: true,
  })
  Object.defineProperty(window.location, 'href', {
    get: () => locationHref,
    set: (v: string) => { locationHref = v },
    configurable: true,
  })
  Object.defineProperty(window.location, 'pathname', {
    value: '/app/chat',
    configurable: true,
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------------
// convRouteKey
// ---------------------------------------------------------------------------

describe('convRouteKey — handles', () => {
  it('returns slugified display name for a named handle', () => {
    const c = makeHandle({ name: 'Sarah Chen' })
    expect(convRouteKey(c)).toBe('sarah-chen')
  })

  it('returns raw handle when name is absent', () => {
    const c = makeHandle({ name: '' })
    expect(convRouteKey(c)).toBe('+14695551234')
  })

  it('strips accented characters', () => {
    const c = makeHandle({ name: 'André Müller' })
    expect(convRouteKey(c)).toBe('andre-muller')
  })

  it('collapses special characters to hyphens', () => {
    const c = makeHandle({ name: 'Hello, World! 2024' })
    expect(convRouteKey(c)).toBe('hello-world-2024')
  })

  it('trims leading and trailing hyphens', () => {
    const c = makeHandle({ name: '...test...' })
    expect(convRouteKey(c)).toBe('test')
  })

  it('falls back to "conversation" when slug would be empty', () => {
    // name consists only of characters that get stripped → empty slug
    const c = makeHandle({ name: '!!!' })
    expect(convRouteKey(c)).toBe('conversation')
  })
})

describe('convRouteKey — groups', () => {
  it('returns slugified name for a named group', () => {
    const c = makeGroup({ name: 'Team Lunch' })
    expect(convRouteKey(c)).toBe('team-lunch')
  })

  it('returns GUID when group has no name', () => {
    const c = makeGroup({ name: '', guid: 'chat;+;abc123' })
    expect(convRouteKey(c)).toBe('chat;+;abc123')
  })

  it('treats whitespace-only name as absent', () => {
    const c = makeGroup({ name: '   ', guid: 'chat;+;xyz' })
    // '   '.trim() === '' → name is absent → fall back to guid
    expect(convRouteKey(c)).toBe('chat;+;xyz')
  })
})

// ---------------------------------------------------------------------------
// resolveConvoHandle
// ---------------------------------------------------------------------------

describe('resolveConvoHandle', () => {
  it('returns null for empty param', () => {
    expect(resolveConvoHandle('', [])).toBeNull()
  })

  it('returns raw phone handle (+...) unchanged', () => {
    const handle = '+14695551234'
    expect(resolveConvoHandle(handle, [])).toBe(handle)
  })

  it('returns raw email handle (@...) unchanged', () => {
    const handle = 'alice@example.com'
    expect(resolveConvoHandle(handle, [])).toBe(handle)
  })

  it('returns raw group GUID (;...) unchanged', () => {
    const handle = 'chat;+;abc123'
    expect(resolveConvoHandle(handle, [])).toBe(handle)
  })

  it('resolves slug to handle for a matching handle conversation', () => {
    const conv = makeHandle({ handle: '+14695551234', name: 'Sarah Chen' })
    // convRouteKey(conv) === 'sarah-chen'
    expect(resolveConvoHandle('sarah-chen', [conv])).toBe('+14695551234')
  })

  it('resolves slug to guid for a matching group conversation', () => {
    const conv = makeGroup({ guid: 'chat;+;abc123', name: 'Team Lunch' })
    // convRouteKey(conv) === 'team-lunch'
    expect(resolveConvoHandle('team-lunch', [conv])).toBe('chat;+;abc123')
  })

  it('returns null when slug does not match any conversation', () => {
    const conv = makeHandle({ handle: '+14695551234', name: 'Sarah Chen' })
    expect(resolveConvoHandle('nobody', [conv])).toBeNull()
  })

  it('returns null when conversations list is empty', () => {
    expect(resolveConvoHandle('sarah-chen', [])).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// fetchJson — 401 redirect
// ---------------------------------------------------------------------------

describe('fetchJson — 401 redirect', () => {
  it('sets window.location.href to /login?next=... on 401', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      statusText: 'Unauthorized',
      json: async () => ({}),
      text: async () => '',
    }))

    await expect(fetchConversations()).rejects.toThrow('Unauthenticated')
    expect(locationHref).toContain('/login?next=')
  })
})

// ---------------------------------------------------------------------------
// fetchJson — error response
// ---------------------------------------------------------------------------

describe('fetchJson — non-ok response', () => {
  it('throws an Error with status text and body for a 500', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      text: async () => 'server blew up',
    }))

    await expect(fetchConversations()).rejects.toThrow('500')
  })
})

// ---------------------------------------------------------------------------
// fetchConversations
// ---------------------------------------------------------------------------

describe('fetchConversations', () => {
  it('returns the conversations array from the API', async () => {
    const conv = makeHandle({ name: 'Alice' })
    mockFetch({ conversations: [conv] })

    const result = await fetchConversations()
    expect(result).toHaveLength(1)
    expect(result[0].name).toBe('Alice')
  })

  it('calls GET /api/ui/conversations', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, status: 200,
      json: async () => ({ conversations: [] }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await fetchConversations()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/ui/conversations',
      expect.objectContaining({ credentials: 'same-origin' }),
    )
  })
})

// ---------------------------------------------------------------------------
// fetchMessages
// ---------------------------------------------------------------------------

describe('fetchMessages', () => {
  it('uses handle param for 1:1 chats', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, status: 200,
      json: async () => ({ messages: [], has_more: false }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await fetchMessages('+14695551234', false, 0, 100)
    const url: string = fetchMock.mock.calls[0][0]
    expect(url).toContain('handle=%2B14695551234')
    expect(url).not.toContain('guid=')
  })

  it('uses guid param for group chats', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, status: 200,
      json: async () => ({ messages: [], has_more: false }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await fetchMessages('chat;+;abc', true, 0, 100)
    const url: string = fetchMock.mock.calls[0][0]
    expect(url).toContain('guid=')
    expect(url).not.toContain('handle=')
  })

  it('passes since and limit params', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, status: 200,
      json: async () => ({ messages: [], has_more: false }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await fetchMessages('+1', false, 42, 50)
    const url: string = fetchMock.mock.calls[0][0]
    expect(url).toContain('since=42')
    expect(url).toContain('limit=50')
  })
})

// ---------------------------------------------------------------------------
// fetchOlderMessages
// ---------------------------------------------------------------------------

describe('fetchOlderMessages', () => {
  it('passes before_date and before_rowid params', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, status: 200,
      json: async () => ({ messages: [], has_more: false }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await fetchOlderMessages('+1', false, 1700000000, 99, 50)
    const url: string = fetchMock.mock.calls[0][0]
    expect(url).toContain('before_date=1700000000')
    expect(url).toContain('before_rowid=99')
    expect(url).toContain('limit=50')
  })
})

// ---------------------------------------------------------------------------
// sendMessage
// ---------------------------------------------------------------------------

describe('sendMessage', () => {
  it('posts handle + text for a 1:1 message', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, status: 200,
      json: async () => ({ status: 'sent', hint: '', service: 'iMessage' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await sendMessage('+1', 'hello', false)
    const body = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(body.handle).toBe('+1')
    expect(body.text).toBe('hello')
    expect(body.guid).toBeUndefined()
  })

  it('posts guid + text for a group message', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, status: 200,
      json: async () => ({ status: 'sent', hint: '', service: 'iMessage' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await sendMessage('chat;+;abc', 'hi', true)
    const body = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(body.guid).toBe('chat;+;abc')
    expect(body.handle).toBe('')
    expect(body.text).toBe('hi')
  })
})

// ---------------------------------------------------------------------------
// markSeen / markAllSeen
// ---------------------------------------------------------------------------

describe('markSeen', () => {
  it('posts conversation_id and last_rowid', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, status: 200,
      json: async () => ({}),
    })
    vi.stubGlobal('fetch', fetchMock)

    await markSeen('+14695551234', 77)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/ui/read-state')
    const body = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(body.conversation_id).toBe('+14695551234')
    expect(body.last_rowid).toBe(77)
  })
})

describe('markAllSeen', () => {
  it('posts to /api/ui/read-state/all', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, status: 200,
      json: async () => ({}),
    })
    vi.stubGlobal('fetch', fetchMock)

    await markAllSeen()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/ui/read-state/all')
    expect(fetchMock.mock.calls[0][1].method).toBe('POST')
  })
})

// ---------------------------------------------------------------------------
// sendTapback
// ---------------------------------------------------------------------------

describe('sendTapback', () => {
  it('posts rowid and type to /api/ui/tapback', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, status: 200,
      json: async () => ({}),
    })
    vi.stubGlobal('fetch', fetchMock)

    await sendTapback(42, 'heart')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/ui/tapback')
    const body = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(body.rowid).toBe(42)
    expect(body.type).toBe('heart')
  })
})

// ---------------------------------------------------------------------------
// editMessage / unsendMessage
// ---------------------------------------------------------------------------

describe('editMessage', () => {
  it('posts rowid and text to /api/ui/edit', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, status: 200,
      json: async () => ({}),
    })
    vi.stubGlobal('fetch', fetchMock)

    await editMessage(7, 'updated text')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/ui/edit')
    const body = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(body.rowid).toBe(7)
    expect(body.text).toBe('updated text')
  })
})

describe('unsendMessage', () => {
  it('posts rowid to /api/ui/unsend', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, status: 200,
      json: async () => ({}),
    })
    vi.stubGlobal('fetch', fetchMock)

    await unsendMessage(99)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/ui/unsend')
    const body = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(body.rowid).toBe(99)
  })
})

// ---------------------------------------------------------------------------
// sendFile
// ---------------------------------------------------------------------------

describe('sendFile', () => {
  it('sends handle in FormData for a 1:1 upload', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, status: 200,
      json: async () => ({ status: 'sent', hint: '', service: 'iMessage' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const file = new File(['data'], 'photo.jpg', { type: 'image/jpeg' })
    await sendFile('+1', false, file)

    expect(fetchMock.mock.calls[0][0]).toBe('/api/ui/upload')
    const fd: FormData = fetchMock.mock.calls[0][1].body
    expect(fd.get('handle')).toBe('+1')
    expect(fd.get('file')).toBe(file)
    expect(fd.get('guid')).toBeNull()
  })

  it('sends guid in FormData for a group upload', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, status: 200,
      json: async () => ({ status: 'sent', hint: '', service: 'iMessage' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const file = new File(['data'], 'doc.pdf', { type: 'application/pdf' })
    await sendFile('chat;+;abc', true, file)

    const fd: FormData = fetchMock.mock.calls[0][1].body
    expect(fd.get('guid')).toBe('chat;+;abc')
    expect(fd.get('file')).toBe(file)
    expect(fd.get('handle')).toBeNull()
  })

  it('redirects to /login on 401 upload response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      text: async () => '',
    }))

    const file = new File(['x'], 'x.txt', { type: 'text/plain' })
    await expect(sendFile('+1', false, file)).rejects.toThrow('Unauthenticated')
    expect(locationHref).toContain('/login?next=')
  })

  it('throws on non-ok upload response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 413,
      statusText: 'Too Large',
      text: async () => 'file too big',
    }))

    const file = new File(['x'], 'x.txt', { type: 'text/plain' })
    await expect(sendFile('+1', false, file)).rejects.toThrow('413')
  })
})
