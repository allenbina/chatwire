/**
 * auth.spec.ts — verify that unauthenticated API responses redirect to /login.
 *
 * When /api/ui/conversations returns 401, api.ts sets
 * window.location.href = '/login?next=...'
 * which navigates within the SPA to the React LoginPage.
 */
import { test, expect } from '@playwright/test'
import { installUnauthMocks } from './mocks'

test.describe('Auth redirect', () => {
  test('redirects to /login when API returns 401', async ({ page }) => {
    await installUnauthMocks(page)

    // Navigate to the SPA shell; the app will load and immediately call
    // /api/ui/conversations which returns 401. api.ts then sets
    // window.location.href = '/login?next=...' navigating within the SPA.
    await page.goto('/')

    // Wait for the in-SPA redirect to /login
    await page.waitForURL(/\/login/, { timeout: 8_000 })

    expect(page.url()).toMatch(/\/login/)
  })

  test('login page renders a labelled password input', async ({ page }) => {
    await installUnauthMocks(page)
    await page.goto('/')
    await page.waitForURL(/\/login/, { timeout: 8_000 })

    // The React LoginPage renders <label htmlFor="password"> + <input id="password">
    const input = page.getByLabel('Password')
    await expect(input).toBeVisible({ timeout: 3_000 })
    await expect(input).toHaveAttribute('type', 'password')
  })
})
