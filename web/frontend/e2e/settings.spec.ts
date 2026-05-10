/**
 * settings.spec.ts — navigate to /settings, open Appearance accordion,
 * change theme, verify CSS custom properties update on :root.
 */
import { test, expect } from '@playwright/test'
import { installMocks } from './mocks'

const THEMES_RESPONSE = {
  themes: ['dracula', 'catppuccin', 'nord'],
  current: 'dracula',
}

test.describe('Settings page', () => {
  test.beforeEach(async ({ page }) => {
    await installMocks(page)

    await page.route('/api/ui/themes', (r) =>
      r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(THEMES_RESPONSE),
      })
    )
    // Accept theme persistence POSTs
    await page.route('/api/settings/theme', (r) => r.fulfill({ status: 200, body: '' }))
    // stub the settings API endpoints used by SettingsPage
    await page.route('/api/ui/settings', (r) =>
      r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
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
        }),
      })
    )
  })

  test('settings page renders the Appearance accordion', async ({ page }) => {
    await page.goto('/settings')

    const accordion = page.getByRole('button', { name: /Appearance/i })
    await expect(accordion).toBeVisible({ timeout: 5_000 })
  })

  test('opening Appearance accordion reveals theme swatches', async ({ page }) => {
    await page.goto('/settings')

    const accordion = page.getByRole('button', { name: /Appearance/i })
    await accordion.click()

    // Theme buttons should now be visible — look for at least the 'dracula' button
    const draculaBtn = page.getByRole('button', { name: /dracula/i })
    await expect(draculaBtn).toBeVisible({ timeout: 3_000 })
  })

  test('clicking a theme button updates :root CSS custom properties', async ({ page }) => {
    await page.goto('/settings')

    const accordion = page.getByRole('button', { name: /Appearance/i })
    await accordion.click()

    // Get initial accent color before switching
    const beforeAccent = await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue('--color-accent').trim()
    )

    // Click on a different theme (catppuccin) if dracula is current.
    // There are multiple Catppuccin variants — use the first one.
    const catBtn = page.getByRole('button', { name: /catppuccin/i }).first()
    await catBtn.click()

    // Wait a moment for the CSS variables to update
    await page.waitForTimeout(300)

    const afterAccent = await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue('--color-accent').trim()
    )

    // The accent color should have changed
    expect(afterAccent).not.toBe(beforeAccent)
    expect(afterAccent.length).toBeGreaterThan(0)
  })
})
