import { DatePipe, DecimalPipe, JsonPipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  linkedSignal,
} from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { ExtractionOut } from '../../core/api.models';
import { ApiService } from '../../core/api.service';
import { splitHighlights } from '../../core/highlight';
import { BadgeComponent } from '../../shared/badge.component';
import { StateComponent } from '../../shared/state.component';

export interface FieldConfidence {
  field: string;
  value: number;
}

/** Flattens a (possibly nested) confidence dict into `a.b` → number rows. */
export function flattenConfidence(conf: Record<string, unknown>, prefix = ''): FieldConfidence[] {
  const rows: FieldConfidence[] = [];
  for (const [k, v] of Object.entries(conf)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (typeof v === 'number') rows.push({ field: key, value: v });
    else if (v && typeof v === 'object' && !Array.isArray(v))
      rows.push(...flattenConfidence(v as Record<string, unknown>, key));
  }
  return rows;
}

@Component({
  selector: 'app-filing-page',
  imports: [StateComponent, BadgeComponent, RouterLink, DatePipe, DecimalPipe, JsonPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './filing.page.html',
  styleUrl: './filing.page.scss',
})
export class FilingPage {
  private readonly api = inject(ApiService);

  readonly accession = input.required<string>();
  /** Optional `?item=` query param, e.g. from a Q&A citation. */
  readonly item = input<string | undefined>(undefined);

  protected readonly detail = rxResource({
    params: () => this.accession(),
    stream: ({ params }) => this.api.filing(params),
  });

  protected readonly selected = linkedSignal<string | undefined>(() => {
    const wanted = this.item();
    if (!this.detail.hasValue()) return wanted;
    const sections = this.detail.value().sections;
    if (wanted && sections.some((s) => s.item === wanted)) return wanted;
    return sections[0]?.item;
  });

  protected readonly section = rxResource({
    params: () => {
      const item = this.selected();
      return item && this.detail.hasValue() ? { acc: this.accession(), item } : undefined;
    },
    stream: ({ params }) => this.api.section(params.acc, params.item),
  });

  protected readonly segments = computed(() =>
    this.section.hasValue()
      ? splitHighlights(this.section.value().text, this.section.value().highlights)
      : [],
  );

  protected confidenceRows(e: ExtractionOut): FieldConfidence[] {
    return flattenConfidence(e.confidence);
  }

  protected confColor(v: number): string {
    if (v >= 0.85) return 'var(--ok)';
    if (v >= 0.6) return 'var(--warn)';
    return 'var(--bad)';
  }
}
