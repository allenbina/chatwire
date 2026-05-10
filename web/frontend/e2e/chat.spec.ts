/**
 * chat.spec.ts — core chat flow: load conversations, open one, see messages,
 * send a message (optimistic update).
 *
 * All API calls are intercepted via page.route — no live server required.
 *
 * Note: the message list uses @tanstack/react-virtual. Virtual items only
 * appear in the DOM when they fall within the scroll container's viewport.
 * Tests therefore check for the compose box and page URL (robust signals)
 * rather than for specific message text.
 */
import { test, expect } from '@playwright/test'
import { installMocks, MOCK_CONVERSATIONS } from './mocks'

test.describe('Chat flow', () => {
  test.beforeEach(async ({ page }) => {
    await installMocks(page)

    // Also stub the theme endpoint so useTheme doesn't fail.
    await page.route('/api/ui/themes', (r) =>
      r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ themes: ['dracula', 'catppuccin'], current: 'dracula' }),
      })
    )
    // Stub POST /api/settings/theme (theme persistence)
    await page.route('/api/settings/theme', (r) => r.fulfill({ status: 200, body: '' }))
    // Stub POST /api/ui/send
    await page.route('/api/ui/send', (r) =>
      r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) })
    )
  })

  test('conversation list loads', async ({ page }) => {
    await page.goto('/')

    // MOCK_CONVERSATIONS[0] is a handle conversation with name: 'Alice'
    const alice = page.getByText(MOCK_CONVERSATIONS[0].name)
    await expect(alice).toBeVisible({ timeout: 5_000 })

    // MOCK_CONVERSATIONS[1] is a group conversation with name: 'Team Chat'
    const team = page.getByText(MOCK_CONVERSATIONS[1].name)
    await expect(team).toBeVisible()
  })

  test('clicking a conversation navigates to the chat URL', async ({ page }) => {
    await page.goto('/')

    // Click the first conversation in the list by display name
    await page.getByText(MOCK_CONVERSATIONS[0].name).first().click()

    // URL should update to /chat/:handle
    await page.waitForURL(/\/chat\//, { timeout: 5_000 })

    // Compose box appears once a conversation is active (independent of virtualizer)
    const compose = page.getByRole('textbox', { name: /type a message/i })
    await expect(compose).toBeVisible({ timeout: 5_000 })
  })

  test('typing and submitting a message clears the compose box and calls the send API', async ({ page }) => {
    // Navigate directly to a conversation using the handle from MOCK_CONVERSATIONS[0]
    const handle = encodeURIComponent(
      MOCK_CONVERSATIONS[0].kind === 'handle'
        ? MOCK_CONVERSATIONS[0].handle
        : (MOCK_CONVERSATIONS[0] as { guid: string }).guid
    )
    await page.goto(`/chat/${handle}`)

    // Wait for the compose box — signals that the conversation loaded
    const compose = page.getByRole('textbox', { name: /type a message/i })
    await expect(compose).toBeVisible({ timeout: 5_000 })

    // Type a new message and press Enter — track the send API call in parallel
    const sendRequest = page.waitForRequest('/api/ui/send')
    await compose.fill('Test message from E2E')
    await compose.press('Enter')

    // The send API must be called (proves Enter triggered doSend)
    await sendRequest

    // The compose box should be cleared after a successful send (robust signal;
    // virtual list item visibility depends on scroll container height in CI)
    await expect(compose).toHaveValue('', { timeout: 5_000 })
  })
})
