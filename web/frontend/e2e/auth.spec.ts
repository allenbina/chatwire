/**
 * auth.spec.ts — verify that unauthenticated API responses redirect to /app/login.
 *
 * When /api/ui/conversations returns 401, api.ts sets
 * window.location.href = '/app/login?next=...'
 * which navigates within the SPA to the React LoginPage.
 */
import { test, expect } from '@playwright/test'
import { installUnauthMocks } from './mocks'

test.describe('Auth redirect', () => {
  test('redirects to /app/login when API returns 401', async ({ page }) => {
    await installUnauthMocks(page)

    // Navigate to the SPA shell; the app will load and immediately call
    // /api/ui/conversations which returns 401. api.ts then sets
    // window.location.href = '/app/login?next=...' navigating within the SPA.
    await page.goto('/app/')

    // Wait for the in-SPA redirect to /app/login
    await page.waitForURL(/\/app\/login/, { timeout: 8_000 })

    expect(page.url()).toMatch(/\/app\/login/)
  })

  test('login page renders a labelled password input', async ({ page }) => {
    await installUnauthMocks(page)
    await page.goto('/app/')
    await page.waitForURL(/\/app\/login/, { timeout: 8_000 })

    // The React LoginPage renders <label htmlFor="password"> + <input id="password">
    const input = page.getByLabel('Password')
    await expect(input).toBeVisible({ timeout: 3_000 })
    await expect(input).toHaveAttribute('type', 'password')
  })
})
