import { DatePipe, DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { EvalRunOut } from '../../core/api.models';
import { ApiService } from '../../core/api.service';
import { PALETTE, formatMetric } from '../../core/format';
import { ChartComponent } from '../../shared/chart.component';
import { StateComponent } from '../../shared/state.component';

export interface MetricTables {
  /** Scalar numeric metric keys present in at least one run, in first-seen order. */
  scalars: string[];
  /** Nested numeric dicts (e.g. field_accuracy): name -> sorted sub-keys. */
  nested: { name: string; keys: string[] }[];
}

const isRecord = (v: unknown): v is Record<string, unknown> =>
  !!v && typeof v === 'object' && !Array.isArray(v);

export function collectMetrics(runs: readonly EvalRunOut[]): MetricTables {
  const scalars: string[] = [];
  const nested = new Map<string, Set<string>>();
  for (const r of runs) {
    for (const [k, v] of Object.entries(r.metrics)) {
      if (typeof v === 'number') {
        if (!scalars.includes(k)) scalars.push(k);
      } else if (isRecord(v)) {
        const set = nested.get(k) ?? new Set<string>();
        Object.entries(v).forEach(([sk, sv]) => typeof sv === 'number' && set.add(sk));
        nested.set(k, set);
      }
    }
  }
  return {
    scalars,
    nested: [...nested.entries()]
      .filter(([, keys]) => keys.size > 0)
      .map(([name, keys]) => ({ name, keys: [...keys].sort() })),
  };
}

@Component({
  selector: 'app-eval-page',
  imports: [StateComponent, ChartComponent, DatePipe, DecimalPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './eval.page.html',
})
export class EvalPage {
  private readonly api = inject(ApiService);

  protected readonly summary = rxResource({ stream: () => this.api.evalSummary() });

  protected readonly runs = computed(() =>
    this.summary.hasValue() ? this.summary.value().runs : [],
  );
  protected readonly tables = computed(() => collectMetrics(this.runs()));

  protected readonly accuracyFields = computed(
    () => this.tables().nested.find((n) => n.name === 'field_accuracy')?.keys ?? [],
  );

  protected readonly accuracyDatasets = computed(() =>
    this.runs().map((r, i) => {
      const fa = r.metrics['field_accuracy'];
      return {
        label: `${r.model} · ${r.prompt_version}`,
        data: this.accuracyFields().map((f) => {
          const v = isRecord(fa) ? fa[f] : undefined;
          return typeof v === 'number' ? v : null;
        }),
        backgroundColor: PALETTE[i % PALETTE.length],
      };
    }),
  );

  protected label(key: string): string {
    return key.replace(/_/g, ' ');
  }

  protected scalar(run: EvalRunOut, key: string): string {
    const v = run.metrics[key];
    return typeof v === 'number' ? formatMetric(key, v) : '—';
  }

  protected nestedValue(run: EvalRunOut, name: string, key: string): string {
    const d = run.metrics[name];
    const v = isRecord(d) ? d[key] : undefined;
    return typeof v === 'number' ? formatMetric(name, v) : '—';
  }
}
