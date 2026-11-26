import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { ReviewAction, ReviewStatus, ReviewTaskOut } from '../../core/api.models';
import { ApiService } from '../../core/api.service';
import { errorMessage } from '../../core/format';
import { BadgeComponent } from '../../shared/badge.component';
import { StateComponent } from '../../shared/state.component';

@Component({
  selector: 'app-review-page',
  imports: [StateComponent, BadgeComponent, RouterLink, DecimalPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './review.page.html',
  styleUrl: './review.page.scss',
})
export class ReviewPage {
  private readonly api = inject(ApiService);

  protected readonly statuses: ReviewStatus[] = ['open', 'approved', 'corrected', 'rejected'];
  protected readonly status = signal<ReviewStatus>('open');
  protected readonly busyId = signal<number | null>(null);
  protected readonly correctingId = signal<number | null>(null);
  protected readonly correction = signal('');
  protected readonly actionError = signal<string | null>(null);

  protected readonly tasks = rxResource({
    params: () => ({ status: this.status(), limit: 100 }),
    stream: ({ params }) => this.api.reviewTasks(params),
  });

  protected startCorrect(task: ReviewTaskOut): void {
    this.correctingId.set(task.id);
    this.correction.set(task.value ?? '');
  }

  protected cancelCorrect(): void {
    this.correctingId.set(null);
  }

  protected act(task: ReviewTaskOut, action: ReviewAction['action']): void {
    const body: ReviewAction =
      action === 'correct' ? { action, value: this.correction() } : { action };
    this.busyId.set(task.id);
    this.actionError.set(null);
    this.api.review(task.id, body).subscribe({
      next: (updated) => {
        this.busyId.set(null);
        this.correctingId.set(null);
        this.tasks.update((page) => {
          if (!page) return page;
          const keep = updated.status === this.status();
          const items = keep
            ? page.items.map((t) => (t.id === updated.id ? updated : t))
            : page.items.filter((t) => t.id !== updated.id);
          return { items, total: keep ? page.total : Math.max(0, page.total - 1) };
        });
      },
      error: (err: unknown) => {
        this.busyId.set(null);
        this.actionError.set(`Could not ${action} task #${task.id}: ${errorMessage(err)}`);
      },
    });
  }

  protected confColor(v: number): string {
    if (v >= 0.85) return 'var(--ok)';
    if (v >= 0.6) return 'var(--warn)';
    return 'var(--bad)';
  }
}
