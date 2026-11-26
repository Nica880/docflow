import { expect, test } from './support/test';

test.describe('review queue', () => {
  test('loads, and approving a task removes it from the open list', async ({ page }) => {
    await page.goto('/review');
    await expect(page.getByTestId('status-open')).toHaveAttribute('aria-pressed', 'true');

    const table = page.getByTestId('review-table');
    const empty = page.getByTestId('state-empty');
    await expect(table.or(empty).first()).toBeVisible();
    if (await empty.isVisible()) return;

    const row = page.getByTestId('review-row').first();
    const id = await row.getAttribute('data-task-id');
    expect(id).toBeTruthy();
    await expect(row.getByTestId('confidence-bar')).toBeVisible();

    await row.getByTestId('approve').click();
    await expect(page.locator(`[data-testid="review-row"][data-task-id="${id}"]`)).toHaveCount(0);

    await page.getByTestId('status-approved').click();
    await expect(page.locator(`[data-testid="review-row"][data-task-id="${id}"]`)).toBeVisible();
  });
});
