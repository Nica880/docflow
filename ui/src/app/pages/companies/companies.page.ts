import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { rxResource, toObservable, toSignal } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { debounceTime } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { StateComponent } from '../../shared/state.component';

const PAGE_SIZE = 25;

@Component({
  selector: 'app-companies-page',
  imports: [StateComponent, RouterLink, DecimalPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './companies.page.html',
})
export class CompaniesPage {
  private readonly api = inject(ApiService);

  protected readonly q = signal('');
  protected readonly sector = signal('');
  protected readonly offset = signal(0);
  protected readonly pageSize = PAGE_SIZE;

  private readonly debouncedQ = toSignal(toObservable(this.q).pipe(debounceTime(250)), {
    initialValue: '',
  });

  protected readonly companies = rxResource({
    params: () => ({
      q: this.debouncedQ().trim(),
      sector: this.sector(),
      limit: PAGE_SIZE,
      offset: this.offset(),
    }),
    stream: ({ params }) => this.api.companies(params),
  });

  private readonly allCompanies = rxResource({
    stream: () => this.api.companies({ limit: 500 }),
  });

  protected readonly sectors = computed(() => {
    if (!this.allCompanies.hasValue()) return [];
    const set = new Set(
      this.allCompanies
        .value()
        .items.map((c) => c.sector)
        .filter((s): s is string => !!s),
    );
    return [...set].sort();
  });

  protected readonly pageLabel = computed(() => {
    if (!this.companies.hasValue()) return '';
    const total = this.companies.value().total;
    if (!total) return '0 companies';
    const from = this.offset() + 1;
    const to = Math.min(this.offset() + PAGE_SIZE, total);
    return `${from}–${to} of ${total}`;
  });

  protected setQuery(value: string): void {
    this.q.set(value);
    this.offset.set(0);
  }

  protected setSector(value: string): void {
    this.sector.set(value);
    this.offset.set(0);
  }

  protected page(delta: number): void {
    this.offset.update((o) => Math.max(0, o + delta * PAGE_SIZE));
  }
}
