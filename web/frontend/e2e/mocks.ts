/**
 * Shared mock helpers for chatwire E2E tests.
 *
 * All backend responses are intercepted via Playwright page.route so tests
 * run fully headless without a live FastAPI server.
 */
import type { Page } from '@playwright/test'

// ---------------------------------------------------------------------------
// Fixture data
// ---------------------------------------------------------------------------

export const MOCK_CONVERSATIONS = [
  {
    kind: 'handle' as const,
    handle: '+15551234567',
    name: 'Alice',
    preview: 'Hey!',
    has_media: false,
    last_dt: 1746393600,
    n: 0,
    all_handles: ['+15551234567'],
    is_favorite: false,
    last: '+15551234567',
  },
  {
    kind: 'group' as const,
    guid: 'group-abc123',
    name: 'Team Chat',
    preview: 'Morning',
    has_media: false,
    last_dt: 1746393700,
    n: 2,
    is_favorite: false,
    last: 'group-abc123',
  },
]

export const MOCK_MESSAGES = [
  {
    rowid: 1,
    text: 'Hello there',
    from_me: false,
    date: 1746393600000,
    ts: '2026-05-01T10:00:00',
    sender_name: 'Alice',
    attachments: [],
    link_preview: null,
  },
  {
    rowid: 2,
    text: 'Hi! How are you?',
    from_me: true,
    date: 1746393660000,
    ts: '2026-05-01T10:01:00',
    sender_name: null,
    attachments: [],
    link_preview: null,
  },
]

export const MOCK_HEALTHZ = { version: '1.6.0', release: '1.6.0', status: 'ok' }

export const MOCK_SETTINGS = {
  theme: 'dracula',
  time_format: '12h',
  history_limit: 500,
  thumbnail_max_size: 800,
  custom_css: '',
  ntfy_topic: '',
  notification_detail: 'full',
  notify_mode: 'all',
  spam_whitelist: false,
  hiatus_active: false,
  reminder_active: false,
  api_key_set: false,
  plugins: [],
  port: 8723,
  bind: '0.0.0.0',
  proxy_headers: false,
}

// ---------------------------------------------------------------------------
// Route install helpers
// ---------------------------------------------------------------------------

/** Install all standard API mocks on the page. Call before navigation. */
export async function installMocks(page: Page) {
  // Auth — respond 200 (logged in)
  await page.route('/api/auth/check', (r) =>
    r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ authenticated: true }) })
  )

  // Health
  await page.route('/healthz', (r) =>
    r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_HEALTHZ) })
  )

  // Conversations
  await page.route('/api/ui/conversations', (r) =>
    r.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ conversations: MOCK_CONVERSATIONS }),
    })
  )

  // Messages
  await page.route('/api/ui/messages**', (r) =>
    r.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ messages: MOCK_MESSAGES, has_more: false }),
    })
  )

  // Settings
  await page.route('/api/ui/settings', (r) =>
    r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_SETTINGS) })
  )

  // Stats (disabled)
  await page.route('/api/ui/stats', (r) =>
    r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ enabled: false }) })
  )

  // GitHub releases — no update available
  await page.route('https://api.github.com/**', (r) =>
    r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ tag_name: 'v1.6.0' }) })
  )

  // SSE — return empty stream immediately so it doesn't hang
  await page.route('/events', (r) =>
    r.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: '',
    })
  )
}

/** Install mocks that simulate an unauthenticated session. */
export async function installUnauthMocks(page: Page) {
  // /app/* routes are served by the Vite dev server (SPA shell), but API
  // calls get 401 so api.ts sets window.location.href = '/app/login?next=...'
  // which navigates within the SPA to the React LoginPage.
  await page.route('/api/auth/check', (r) =>
    r.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ detail: 'Not authenticated' }) })
  )
  await page.route('/api/ui/conversations', (r) =>
    r.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ detail: 'Not authenticated' }) })
  )
  // SSE and health don't matter when unauthed
  await page.route('/healthz', (r) =>
    r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_HEALTHZ) })
  )
  await page.route('/events', (r) => r.fulfill({ status: 401, body: '' }))
  await page.route('https://api.github.com/**', (r) =>
    r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ tag_name: 'v1.6.0' }) })
  )
}
