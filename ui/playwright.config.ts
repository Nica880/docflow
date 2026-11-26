import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env['E2E_BASE_URL'] ?? 'http://localhost:4200';
const startServer = process.env['E2E_START_SERVER'] === '1';
const mock = process.env['E2E_MOCK'] === '1';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: !!mock,
  // Against a real backend the review test mutates shared state, so run serially.
  workers: mock ? undefined : 1,
  forbidOnly: !!process.env['CI'],
  retries: process.env['CI'] ? 1 : 0,
  timeout: mock ? 30_000 : 90_000,
  expect: { timeout: mock ? 5_000 : 30_000 },
  reporter: process.env['CI'] ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: startServer
    ? {
        command: 'npm start -- --port 4200',
        url: baseURL,
        reuseExistingServer: true,
        timeout: 180_000,
      }
    : undefined,
});
