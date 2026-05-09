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
  { handle: '+15551234567', display_name: 'Alice', last_message: 'Hey!', unread: 0, is_group: false },
  { handle: 'group-abc123', display_name: 'Team Chat', last_message: 'Morning', unread: 2, is_group: true },
]

export const MOCK_MESSAGES = [
  {
    rowid: 1,
    text: 'Hello there',
    from_me: false,
    date: '2026-05-01T10:00:00',
    sender_name: 'Alice',
    attachments: [],
    reactions: [],
  },
  {
    rowid: 2,
    text: 'Hi! How are you?',
    from_me: true,
    date: '2026-05-01T10:01:00',
    sender_name: null,
    attachments: [],
    reactions: [],
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
  // /app/* routes return 200 (Vite dev server always serves the SPA shell),
  // but API calls get 401 so the React app redirects to /login.
  await page.route('/api/auth/check', (r) =>
    r.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ detail: 'Not authenticated' }) })
  )
  await page.route('/api/ui/conversations', (r) =>
    r.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ detail: 'Not authenticated' }) })
  )
  // The login page itself
  await page.route('/login', (r) =>
    r.fulfill({
      status: 200,
      contentType: 'text/html',
      body: '<html><body><form><input name="password"/><button type="submit">Login</button></form></body></html>',
    })
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
