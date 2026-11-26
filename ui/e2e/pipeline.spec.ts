import { expect, test } from './support/test';

test.describe('pipeline', () => {
  test('default route shows the pipeline overview with totals cards', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\/pipeline$/);
    await expect(page.getByRole('heading', { name: 'Pipeline' })).toBeVisible();

    const totals = page.getByTestId('totals');
    await expect(totals).toBeVisible();
    await expect(page.getByTestId('total-filings')).toBeVisible();
    await expect(page.getByTestId('total-companies')).toContainText(/\d/);
    expect(await totals.locator('.stat').count()).toBeGreaterThanOrEqual(3);

    await expect(page.getByTestId('runs')).toBeVisible();
    await expect(page.getByTestId('quarantine')).toBeVisible();
  });

  test('sidebar navigates between pages', async ({ page }) => {
    await page.goto('/pipeline');
    await page.getByTestId('nav-eval').click();
    await expect(page).toHaveURL(/\/eval$/);
    await expect(page.getByRole('heading', { name: 'Evaluation' })).toBeVisible();
    await expect(
      page.getByTestId('eval-table').or(page.getByTestId('state-empty')).first(),
    ).toBeVisible();
  });
});
