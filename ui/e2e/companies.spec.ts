import { expect, test } from './support/test';

test.describe('companies', () => {
  test('lists companies and opens a company with a financials chart', async ({ page }) => {
    await page.goto('/companies');
    const rows = page.getByTestId('company-row');
    await expect(rows.first()).toBeVisible();
    expect(await rows.count()).toBeGreaterThanOrEqual(1);

    const firstLink = rows.first().getByTestId('company-link');
    const name = (await firstLink.textContent())?.trim() ?? '';
    await firstLink.click();

    await expect(page).toHaveURL(/\/companies\/\d+$/);
    await expect(page.getByTestId('company-name')).toHaveText(name);
    await expect(page.getByTestId('financials').locator('canvas, svg').first()).toBeVisible();
    await expect(page.getByTestId('company-filings')).toBeVisible();
  });

  test('search filters the table', async ({ page }) => {
    await page.goto('/companies');
    await expect(page.getByTestId('company-row').first()).toBeVisible();
    await page.getByTestId('company-search').fill('zzzz-no-such-company');
    await expect(page.getByTestId('state-empty')).toBeVisible();
  });
});
