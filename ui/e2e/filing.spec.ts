import { expect, test } from './support/test';

test.describe('filing viewer', () => {
  test('shows section tabs and section text', async ({ page }) => {
    // Navigate first so in-page fetches go through the (optional) API mocks.
    await page.goto('/companies');
    const accession = await page.evaluate(async () => {
      const list = await (await fetch('/api/filings?limit=50')).json();
      for (const f of list.items as { accession_no: string }[]) {
        const res = await fetch(`/api/filings/${encodeURIComponent(f.accession_no)}`);
        if (!res.ok) continue;
        const detail = await res.json();
        if (detail.sections?.length) return f.accession_no;
      }
      return null;
    });
    test.skip(!accession, 'no parsed filing with sections available');

    await page.goto(`/filings/${accession}`);
    await expect(page.getByTestId('filing-title')).toBeVisible();
    const tabs = page.getByTestId('section-tab');
    await expect(tabs.first()).toBeVisible();

    const text = page.getByTestId('section-text');
    await expect(text).toBeVisible();
    await expect(text).not.toBeEmpty();

    if ((await tabs.count()) > 1) {
      await tabs.nth(1).click();
      await expect(tabs.nth(1)).toHaveAttribute('aria-selected', 'true');
      await expect(page.getByTestId('section-text')).not.toBeEmpty();
    }
    await expect(page.getByTestId('extractions')).toBeVisible();
  });
});
