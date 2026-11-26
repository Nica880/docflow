import { Page, Route } from '@playwright/test';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const FIXTURES = join(__dirname, '..', 'fixtures');

interface Company {
  cik: number;
  name: string;
  ticker: string | null;
  sector: string | null;
}
interface ReviewTask {
  id: number;
  status: string;
  value: string | null;
  reviewer_value: string | null;
  reviewed_at: string | null;
}
interface ApiPage<T> {
  items: T[];
  total: number;
}

function fixture<T = unknown>(name: string): T | undefined {
  const file = join(FIXTURES, `${name}.json`);
  return existsSync(file) ? (JSON.parse(readFileSync(file, 'utf-8')) as T) : undefined;
}

function json(route: Route, body: unknown, status = 200): Promise<void> {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

function paginate<T>(items: T[], url: URL): ApiPage<T> {
  const limit = Number(url.searchParams.get('limit') ?? 50);
  const offset = Number(url.searchParams.get('offset') ?? 0);
  return { items: items.slice(offset, offset + limit), total: items.length };
}

const STATUS_FOR: Record<string, string> = {
  approve: 'approved',
  correct: 'corrected',
  reject: 'rejected',
};

/**
 * Fulfils every `/api/**` request from `e2e/fixtures/*.json` so the UI can be tested without a
 * backend. Review actions are stateful per page so approve/correct/reject behave realistically.
 */
export async function installApiMocks(page: Page): Promise<void> {
  const tasks = (fixture<ApiPage<ReviewTask>>('review-open')?.items ?? []).map((t) => ({ ...t }));

  await page.route('**/api/**', async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const path = decodeURIComponent(url.pathname.replace(/^\/api/, ''));
    const method = req.method();
    const sp = url.searchParams;
    const fromFixture = (name: string) => {
      const body = fixture(name);
      return body ? json(route, body) : json(route, { detail: 'Not Found' }, 404);
    };

    if (method === 'GET') {
      if (path === '/health') return fromFixture('health');
      if (path === '/pipeline/overview') return fromFixture('pipeline-overview');
      if (path === '/eval') return fromFixture('eval');

      if (path === '/companies') {
        const q = (sp.get('q') ?? '').toLowerCase();
        const sector = sp.get('sector') ?? '';
        const all = (fixture<ApiPage<Company>>('companies')?.items ?? []).filter(
          (c) =>
            (!q ||
              c.name.toLowerCase().includes(q) ||
              (c.ticker ?? '').toLowerCase().includes(q) ||
              String(c.cik).includes(q)) &&
            (!sector || c.sector === sector),
        );
        return json(route, paginate(all, url));
      }
      const company = path.match(/^\/companies\/(\d+)$/);
      if (company) return fromFixture(`company-${Number(company[1])}`);

      if (path === '/filings') {
        const all = (
          fixture<ApiPage<{ cik: number; status: string }>>('filings')?.items ?? []
        ).filter(
          (f) =>
            (!sp.get('cik') || String(f.cik) === sp.get('cik')) &&
            (!sp.get('status') || f.status === sp.get('status')),
        );
        return json(route, paginate(all, url));
      }
      const section = path.match(/^\/filings\/([^/]+)\/sections\/([^/]+)$/);
      if (section) return fromFixture(`section-${section[1]}-${section[2]}`);
      const filing = path.match(/^\/filings\/([^/]+)$/);
      if (filing) return fromFixture(`filing-${filing[1]}`);

      if (path === '/review') {
        const status = sp.get('status');
        return json(
          route,
          paginate(
            tasks.filter((t) => !status || t.status === status),
            url,
          ),
        );
      }
    }

    if (method === 'POST') {
      const review = path.match(/^\/review\/(\d+)$/);
      if (review) {
        const task = tasks.find((t) => t.id === Number(review[1]));
        if (!task) return json(route, { detail: 'Not Found' }, 404);
        const body = req.postDataJSON() as { action: string; value?: string };
        task.status = STATUS_FOR[body.action] ?? task.status;
        task.reviewer_value = body.action === 'correct' ? (body.value ?? null) : task.value;
        task.reviewed_at = new Date().toISOString();
        return json(route, task);
      }
      if (path === '/qa') {
        const { question } = req.postDataJSON() as { question: string };
        const offTopic = /weather|recipe|football|joke/i.test(question);
        return fromFixture(offTopic ? 'qa-refused' : 'qa-answer');
      }
    }

    return json(route, { detail: 'Not Found' }, 404);
  });
}
