import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { FinancialPoint, RiskPoint } from '../../core/api.models';
import { ApiService } from '../../core/api.service';
import { PALETTE, compactNumber } from '../../core/format';
import { BadgeComponent } from '../../shared/badge.component';
import { ChartComponent } from '../../shared/chart.component';
import { StateComponent } from '../../shared/state.component';

/** One point per fiscal year; XBRL (reported) values win over LLM-extracted ones. */
export function dedupeFinancials(points: readonly FinancialPoint[]): FinancialPoint[] {
  const byYear = new Map<number, FinancialPoint>();
  for (const p of points) {
    const prev = byYear.get(p.fiscal_year);
    if (!prev || (prev.source !== 'xbrl' && p.source === 'xbrl')) byYear.set(p.fiscal_year, p);
  }
  return [...byYear.values()].sort((a, b) => a.fiscal_year - b.fiscal_year);
}

/** Pivots risk mentions into (years, one dataset per category). */
export function pivotRisks(points: readonly RiskPoint[]): {
  years: number[];
  series: { category: string; data: number[] }[];
} {
  const years = [...new Set(points.map((p) => p.year))].sort((a, b) => a - b);
  const categories = [...new Set(points.map((p) => p.category))].sort();
  const series = categories.map((category) => ({
    category,
    data: years.map((y) =>
      points
        .filter((p) => p.year === y && p.category === category)
        .reduce((s, p) => s + p.mentions, 0),
    ),
  }));
  return { years, series };
}

@Component({
  selector: 'app-company-detail-page',
  imports: [StateComponent, ChartComponent, BadgeComponent, RouterLink, DatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './company-detail.page.html',
})
export class CompanyDetailPage {
  private readonly api = inject(ApiService);

  readonly cik = input.required<string>();

  protected readonly detail = rxResource({
    params: () => this.cik(),
    stream: ({ params }) => this.api.company(params),
  });

  protected readonly compact = compactNumber;

  protected readonly financials = computed(() =>
    this.detail.hasValue() ? dedupeFinancials(this.detail.value().financials) : [],
  );

  protected readonly finLabels = computed(() => this.financials().map((f) => `FY${f.fiscal_year}`));

  protected readonly finDatasets = computed(() => {
    const f = this.financials();
    return [
      { label: 'Revenue', data: f.map((p) => p.revenue), backgroundColor: PALETTE[0] },
      { label: 'Net income', data: f.map((p) => p.net_income), backgroundColor: PALETTE[1] },
      {
        label: 'Operating cash flow',
        data: f.map((p) => p.operating_cash_flow),
        backgroundColor: PALETTE[2],
      },
    ];
  });

  protected readonly sources = computed(() => [...new Set(this.financials().map((f) => f.source))]);

  protected readonly risks = computed(() =>
    pivotRisks(this.detail.hasValue() ? this.detail.value().risks : []),
  );

  protected readonly riskDatasets = computed(() =>
    this.risks().series.map((s, i) => ({
      label: s.category,
      data: s.data,
      backgroundColor: PALETTE[i % PALETTE.length],
    })),
  );
}
