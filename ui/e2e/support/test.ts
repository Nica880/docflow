import { test as base } from '@playwright/test';
import { installApiMocks } from './mock-api';

export const MOCK = process.env['E2E_MOCK'] === '1';

/** Playwright `test` that transparently mocks the API when `E2E_MOCK=1`. */
export const test = base.extend<{ apiMocks: void }>({
  apiMocks: [
    async ({ page }, use) => {
      if (MOCK) await installApiMocks(page);
      await use();
    },
    { auto: true },
  ],
});

export { expect } from '@playwright/test';
