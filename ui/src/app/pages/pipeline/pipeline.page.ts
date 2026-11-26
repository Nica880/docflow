import { DatePipe, DecimalPipe, KeyValuePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/api.service';
import { PALETTE, compactNumber, formatDuration } from '../../core/format';
import { BadgeComponent } from '../../shared/badge.component';
import { ChartComponent } from '../../shared/chart.component';
import { StateComponent } from '../../shared/state.component';

const TOTAL_LABELS: Record<string, string> = {
  companies: 'Companies',
  filings: 'Filings',
  sections: 'Sections',
  chunks: 'Chunks',
  extractions: 'Extractions',
  open_reviews: 'Open reviews',
  quarantined: 'Quarantined',
};

const STATUS_COLORS: Record<string, string> = {
  downloaded: '#7c8a9e',
  parsed: '#12a5c9',
  extracted: '#4f7cff',
  loaded: '#22b07d',
  quarantined: '#e5484d',
  failed: '#e5484d',
};

@Component({
  selector: 'app-pipeline-page',
  imports: [
    StateComponent,
    ChartComponent,
    BadgeComponent,
    DatePipe,
    DecimalPipe,
    KeyValuePipe,
    RouterLink,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './pipeline.page.html',
  styleUrl: './pipeline.page.scss',
})
export class PipelinePage {
  private readonly api = inject(ApiService);

  protected readonly overview = rxResource({ stream: () => this.api.pipelineOverview() });
  protected readonly formatDuration = formatDuration;
  protected readonly compact = compactNumber;

  protected readonly totals = computed(() => {
    if (!this.overview.hasValue()) return [];
    const t = this.overview.value().totals;
    const known = Object.keys(TOTAL_LABELS).filter((k) => k in t);
    const extra = Object.keys(t).filter((k) => !(k in TOTAL_LABELS));
    return [...known, ...extra].map((key) => ({
      key,
      label: TOTAL_LABELS[key] ?? key.replace(/_/g, ' '),
      value: t[key],
    }));
  });

  protected readonly statusBar = computed(() => {
    if (!this.overview.hasValue()) return [];
    const entries = Object.entries(this.overview.value().filings_by_status);
    const total = entries.reduce((s, [, n]) => s + n, 0) || 1;
    return entries.map(([status, count], i) => ({
      status,
      count,
      pct: (count / total) * 100,
      color: STATUS_COLORS[status] ?? PALETTE[i % PALETTE.length],
    }));
  });

  protected readonly throughputLabels = computed(() =>
    this.overview.hasValue() ? this.overview.value().throughput.map((p) => p.day) : [],
  );

  protected readonly throughputData = computed(() => [
    {
      label: 'Filings processed',
      data: this.overview.hasValue() ? this.overview.value().throughput.map((p) => p.filings) : [],
      backgroundColor: 'rgba(79,124,255,0.18)',
      borderColor: PALETTE[0],
      fill: true,
      tension: 0.3,
    },
  ]);
}
