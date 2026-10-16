/**
 * Playwright Configuration for EdgeVoice Dashboard Tests
 *
 * Tests the static HTML dashboard served by backend at localhost:11000
 */
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/web_ui',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',

  use: {
    baseURL: 'http://localhost:11000',
    trace: 'on-first-retry',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  webServer: {
    command: 'echo "Backend server should be running at localhost:11000"',
    url: 'http://localhost:11000',
    reuseExistingServer: true,
    timeout: 5000,
  },
});
