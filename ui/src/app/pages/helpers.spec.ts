import { EvalRunOut, FinancialPoint } from '../core/api.models';
import { dedupeFinancials, pivotRisks } from './companies/company-detail.page';
import { collectMetrics } from './eval/eval.page';

describe('page data helpers', () => {
  it('dedupeFinancials prefers XBRL over LLM values for the same fiscal year', () => {
    const p = (fiscal_year: number, source: string, revenue: number): FinancialPoint => ({
      fiscal_year,
      source,
      revenue,
      net_income: null,
      operating_cash_flow: null,
    });
    const out = dedupeFinancials([p(2024, 'llm', 1), p(2023, 'llm', 2), p(2024, 'xbrl', 3)]);
    expect(out.map((f) => [f.fiscal_year, f.source, f.revenue])).toEqual([
      [2023, 'llm', 2],
      [2024, 'xbrl', 3],
    ]);
  });

  it('pivotRisks fills missing category/year combinations with zero', () => {
    const { years, series } = pivotRisks([
      { year: 2023, category: 'cyber', mentions: 3 },
      { year: 2024, category: 'cyber', mentions: 5 },
      { year: 2024, category: 'supply', mentions: 2 },
    ]);
    expect(years).toEqual([2023, 2024]);
    expect(series).toEqual([
      { category: 'cyber', data: [3, 5] },
      { category: 'supply', data: [0, 2] },
    ]);
  });

  it('collectMetrics separates scalar metrics from nested numeric dicts', () => {
    const run = (metrics: Record<string, unknown>): EvalRunOut => ({
      id: 1,
      model: 'm',
      prompt_version: 'v1',
      n_docs: 1,
      metrics,
      created_at: '2026-01-01T00:00:00Z',
    });
    const t = collectMetrics([
      run({ schema_valid_rate: 0.9, field_accuracy: { revenue: 1, ceo: 0.5 }, note: 'x' }),
      run({ latency_p50_ms: 1200, field_accuracy: { net_income: 0.8 } }),
    ]);
    expect(t.scalars).toEqual(['schema_valid_rate', 'latency_p50_ms']);
    expect(t.nested).toEqual([{ name: 'field_accuracy', keys: ['ceo', 'net_income', 'revenue'] }]);
  });
});
