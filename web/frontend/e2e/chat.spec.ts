/**
 * chat.spec.ts — core chat flow: load conversations, open one, see messages,
 * send a message (optimistic update).
 *
 * All API calls are intercepted via page.route — no live server required.
 */
import { test, expect } from '@playwright/test'
import { installMocks, MOCK_CONVERSATIONS, MOCK_MESSAGES } from './mocks'

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
    // Stub POST /send
    await page.route('/send', (r) =>
      r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) })
    )
  })

  test('conversation list loads', async ({ page }) => {
    await page.goto('/app/')

    const alice = page.getByText(MOCK_CONVERSATIONS[0].display_name)
    await expect(alice).toBeVisible({ timeout: 5_000 })

    const team = page.getByText(MOCK_CONVERSATIONS[1].display_name)
    await expect(team).toBeVisible()
  })

  test('clicking a conversation loads messages', async ({ page }) => {
    await page.goto('/app/')

    // Click the first conversation in the list
    await page.getByText(MOCK_CONVERSATIONS[0].display_name).click()

    // URL should update to /app/chat/:handle
    await page.waitForURL(/\/app\/chat\//, { timeout: 5_000 })

    // Messages should appear
    const firstMsg = page.getByText(MOCK_MESSAGES[0].text)
    await expect(firstMsg).toBeVisible({ timeout: 5_000 })

    const secondMsg = page.getByText(MOCK_MESSAGES[1].text)
    await expect(secondMsg).toBeVisible()
  })

  test('typing and submitting a message shows optimistic bubble', async ({ page }) => {
    // Navigate directly to a conversation
    const handle = encodeURIComponent(MOCK_CONVERSATIONS[0].handle)
    await page.goto(`/app/chat/${handle}`)

    // Wait for messages to load
    await expect(page.getByText(MOCK_MESSAGES[0].text)).toBeVisible({ timeout: 5_000 })

    // Type a new message
    const compose = page.locator('textarea, input[type="text"]').last()
    await compose.fill('Test message from E2E')

    // Submit (Enter key or send button)
    await compose.press('Enter')

    // Optimistic bubble should appear immediately
    await expect(page.getByText('Test message from E2E')).toBeVisible({ timeout: 3_000 })
  })
})
