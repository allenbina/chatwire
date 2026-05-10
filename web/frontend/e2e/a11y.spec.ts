/**
 * a11y.spec.ts — axe accessibility scan on key pages.
 *
 * Target: 0 critical violations on /* and /settings.
 * Uses @axe-core/playwright which wraps axe-core in Playwright.
 */
import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { installMocks } from './mocks'

test.describe('Accessibility (@axe-core)', () => {
  test.beforeEach(async ({ page }) => {
    await installMocks(page)

    await page.route('/api/ui/themes', (r) =>
      r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ themes: ['dracula', 'catppuccin'], current: 'dracula' }),
      })
    )
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

  test('main chat page (/) has 0 critical a11y violations', async ({ page }) => {
    await page.goto('/')

    // Wait for conversations to load
    await page.waitForSelector('[role="list"], [role="listitem"], nav, main', { timeout: 5_000 })

    const results = await new AxeBuilder({ page })
      // Only flag critical (serious + critical impact) issues
      .options({ runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] } })
      .analyze()

    const critical = results.violations.filter((v) =>
      v.impact === 'critical' || v.impact === 'serious'
    )

    if (critical.length > 0) {
      console.error(
        'A11y violations:\n' +
          critical.map((v) => `  [${v.impact}] ${v.id}: ${v.description}`).join('\n')
      )
    }

    expect(critical).toHaveLength(0)
  })

  test('settings page (/settings) has 0 critical a11y violations', async ({ page }) => {
    await page.goto('/settings')

    // Wait for settings content to render (accordion button is a reliable signal)
    await page.getByRole('button', { name: /Appearance/i }).waitFor({ timeout: 5_000 })

    const results = await new AxeBuilder({ page })
      .options({ runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] } })
      .analyze()

    const critical = results.violations.filter((v) =>
      v.impact === 'critical' || v.impact === 'serious'
    )

    if (critical.length > 0) {
      console.error(
        'A11y violations on settings:\n' +
          critical.map((v) => `  [${v.impact}] ${v.id}: ${v.description}`).join('\n')
      )
    }

    expect(critical).toHaveLength(0)
  })
})
