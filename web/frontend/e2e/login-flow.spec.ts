/**
 * login-flow.spec.ts — smoke test for the full login → settings → sign out flow.
 *
 * Covers:
 *   1. /login renders a password input associated to its label
 *   2. Submitting the correct password POSTs to /api/ui/auth/login and
 *      follows the `next` redirect to /
 *   3. From /* the user can navigate to /settings which renders the
 *      Appearance accordion button
 *   4. Clicking "Sign out" navigates the browser to /logout
 *
 * All API calls are intercepted via Playwright route mocks — no live server
 * required.  The Vite dev server is started automatically by playwright.config.ts.
 */
import { test, expect } from '@playwright/test'
import { installMocks } from './mocks'

test.describe('Login → Settings → Sign out flow', () => {
  test.beforeEach(async ({ page }) => {
    // Install standard authenticated mocks so pages beyond /login can load.
    await installMocks(page)

    // Login endpoint: accept any password, redirect to /
    await page.route('/api/ui/auth/login', (r) =>
      r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, next: '/' }),
      })
    )

    // Themes endpoint required by SettingsPage
    await page.route('/api/ui/themes', (r) =>
      r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ themes: ['dracula', 'catppuccin', 'nord'], current: 'dracula' }),
      })
    )

    // Intercept the logout navigation so the test stays within Playwright's
    // managed browser context (avoids net::ERR_CONNECTION_REFUSED).
    await page.route('/logout', (r) =>
      r.fulfill({
        status: 200,
        contentType: 'text/html',
        body: '<html><body>Signed out</body></html>',
      })
    )
  })

  test('step 1: /login renders a labelled password input', async ({ page }) => {
    await page.goto('/login')

    // The <label htmlFor="password"> + <input id="password"> pair must be present.
    const input = page.getByLabel('Password')
    await expect(input).toBeVisible({ timeout: 5_000 })
    await expect(input).toHaveAttribute('type', 'password')

    // Sign in button is present and enabled
    const btn = page.getByRole('button', { name: /sign in/i })
    await expect(btn).toBeVisible()
    await expect(btn).toBeEnabled()
  })

  test('step 2: submitting the form redirects to /', async ({ page }) => {
    await page.goto('/login')

    await page.getByLabel('Password').fill('hunter2')

    // Click submit and wait for the hard navigation triggered by
    // window.location.href = data.next ('/').
    await Promise.all([
      page.waitForURL(/\/$/, { timeout: 8_000 }),
      page.getByRole('button', { name: /sign in/i }).click(),
    ])

    expect(page.url()).toMatch(/\/$/)
  })

  test('step 3: /settings renders after login', async ({ page }) => {
    // Skip the login form and navigate directly to settings (mocks make
    // it appear as if the user is already authenticated).
    await page.goto('/settings')

    const accordion = page.getByRole('button', { name: /Appearance/i })
    await expect(accordion).toBeVisible({ timeout: 5_000 })
  })

  test('step 4: "Sign out" link navigates to /logout', async ({ page }) => {
    await page.goto('/settings')

    // Wait for settings to render before clicking sign out
    await page.getByRole('button', { name: /Appearance/i }).waitFor({ timeout: 5_000 })

    const signOutLink = page.getByRole('link', { name: /sign out/i })
    await expect(signOutLink).toBeVisible()

    // The link is <a href="/logout"> — clicking causes a full navigation.
    await Promise.all([
      page.waitForURL(/\/logout/, { timeout: 5_000 }),
      signOutLink.click(),
    ])

    expect(page.url()).toMatch(/\/logout/)
  })

  test('full smoke: login → /* → settings → sign out in one flow', async ({ page }) => {
    // --- 1. Start at login page ---
    await page.goto('/login')
    await expect(page.getByLabel('Password')).toBeVisible({ timeout: 5_000 })

    // --- 2. Log in ---
    await page.getByLabel('Password').fill('hunter2')
    await Promise.all([
      page.waitForURL(/\/$/, { timeout: 8_000 }),
      page.getByRole('button', { name: /sign in/i }).click(),
    ])

    // --- 3. Navigate to settings ---
    await page.goto('/settings')
    await expect(page.getByRole('button', { name: /Appearance/i })).toBeVisible({ timeout: 5_000 })

    // --- 4. Sign out ---
    const signOutLink = page.getByRole('link', { name: /sign out/i })
    await Promise.all([
      page.waitForURL(/\/logout/, { timeout: 5_000 }),
      signOutLink.click(),
    ])

    expect(page.url()).toMatch(/\/logout/)
  })
})
