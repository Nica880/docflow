import { expect, test } from './support/test';

test.describe('Q&A', () => {
  test('example question yields an answer with citations or a refusal', async ({ page }) => {
    await page.goto('/qa');
    const chips = page.getByTestId('example-chip');
    await expect(chips).toHaveCount(3);
    await chips.filter({ hasText: 'What does Apple say about supply chain risk?' }).click();

    await expect(page.getByTestId('user-message')).toHaveCount(1);
    const answer = page.getByTestId('answer').first();
    await expect(answer).toBeVisible({ timeout: 90_000 });
    await expect(answer.locator('.answer-text')).not.toBeEmpty();

    const refused = (await answer.getAttribute('data-refused')) === 'true';
    if (!refused) {
      const citations = answer.getByTestId('citation');
      expect(await citations.count()).toBeGreaterThanOrEqual(1);
      await expect(citations.first()).toHaveAttribute('href', /\/filings\/[^/?]+/);
    }
  });

  test('off-topic question is refused', async ({ page }) => {
    await page.goto('/qa');
    await page.getByTestId('qa-input').fill('What is the weather in Paris?');
    await page.getByTestId('qa-send').click();

    const answer = page.getByTestId('answer').first();
    await expect(answer).toBeVisible({ timeout: 90_000 });
    await expect(answer).toHaveAttribute('data-refused', 'true');
    await expect(answer.getByTestId('refused')).toBeVisible();
  });
});
