import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

@Component({
  selector: 'app-badge',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span class="badge" [class]="'badge badge-' + tone()" data-testid="badge">{{
    value()
  }}</span>`,
})
export class BadgeComponent {
  readonly value = input.required<string>();

  protected readonly tone = computed(() => {
    const v = this.value().toLowerCase();
    if (/(success|ok|done|approved|extracted|loaded|complete)/.test(v)) return 'ok';
    if (/(fail|error|quarantin|rejected)/.test(v)) return 'bad';
    if (/(running|pending|queued|open|parsed|downloaded|new)/.test(v)) return 'warn';
    if (/corrected/.test(v)) return 'info';
    return 'neutral';
  });
}
