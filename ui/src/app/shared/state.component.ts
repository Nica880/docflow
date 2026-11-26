import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { errorMessage } from '../core/format';

/** Uniform loading / error / empty placeholder. Renders nothing when none apply. */
@Component({
  selector: 'app-state',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (loading()) {
      <div class="state state-loading" data-testid="state-loading" role="status">
        <span class="spinner" aria-hidden="true"></span> {{ loadingText() }}
      </div>
    } @else if (error()) {
      <div class="state state-error" data-testid="state-error" role="alert">
        <strong>Something went wrong.</strong> {{ message() }}
      </div>
    } @else if (empty()) {
      <div class="state state-empty" data-testid="state-empty">{{ emptyText() }}</div>
    }
  `,
})
export class StateComponent {
  readonly loading = input(false);
  readonly error = input<unknown>(undefined);
  readonly empty = input(false);
  readonly loadingText = input('Loading…');
  readonly emptyText = input('Nothing to show yet.');
  protected readonly message = computed(() => errorMessage(this.error()));
}
