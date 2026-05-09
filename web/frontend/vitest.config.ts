import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test-setup.ts',
    // Exclude Playwright E2E tests from Vitest runs
    exclude: ['**/node_modules/**', '**/e2e/**'],
  },
})
