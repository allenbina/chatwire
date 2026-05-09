import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright config for chatwire E2E tests.
 *
 * Tests use Playwright route intercepts (page.route) to mock the FastAPI
 * backend — no live server required. The webServer block is left out
 * intentionally so the suite runs headless in CI without starting uvicorn.
 *
 * Run: npm run e2e
 */
export default defineConfig({
  testDir: 'e2e',
  // Fail fast in CI; allow retries locally.
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:5173',
    // All API calls are intercepted — no real network needed.
    trace: 'on-first-retry',
    // Suppress browser console noise in output.
    // ignoreHTTPSErrors is irrelevant here (all HTTP), but safe to set.
    ignoreHTTPSErrors: true,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  // Start the Vite dev server for the SPA (does NOT require FastAPI — all
  // /api/* calls are intercepted by page.route in each test).
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173/app/',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
})
