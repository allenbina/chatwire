/**
 * auth.spec.ts — verify that unauthenticated requests redirect to /login.
 *
 * The backend API calls (/api/ui/conversations) return 401 via route intercept.
 * The React app's fetch wrapper detects 401 and does
 * window.location.href = '/login?next=...'.
 */
import { test, expect } from '@playwright/test'
import { installUnauthMocks } from './mocks'

test.describe('Auth redirect', () => {
  test('redirects to /login when API returns 401', async ({ page }) => {
    await installUnauthMocks(page)

    // Navigate to the SPA shell; the app will load and immediately call
    // /api/ui/conversations which returns 401.
    await page.goto('/app/')

    // Wait for the redirect to /login (window.location.href assignment).
    await page.waitForURL(/\/login/, { timeout: 5_000 })

    expect(page.url()).toMatch(/\/login/)
  })

  test('login page renders a password input', async ({ page }) => {
    await installUnauthMocks(page)
    await page.goto('/app/')
    await page.waitForURL(/\/login/, { timeout: 5_000 })

    // Our mocked /login returns an HTML form with a password field.
    const input = page.locator('input[name="password"]')
    await expect(input).toBeVisible({ timeout: 3_000 })
  })
})
