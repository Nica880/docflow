import { JsonPipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { Answer } from '../../core/api.models';
import { ApiService } from '../../core/api.service';
import { errorMessage } from '../../core/format';

export type ChatMessage =
  | { id: number; role: 'user'; text: string }
  | { id: number; role: 'assistant'; answer: Answer }
  | { id: number; role: 'error'; text: string };

export const EXAMPLE_QUESTIONS = [
  'Which companies had the highest revenue in the latest fiscal year?',
  'How did cybersecurity risk mentions change over time?',
  'What does Apple say about supply chain risk?',
];

@Component({
  selector: 'app-qa-page',
  imports: [RouterLink, JsonPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './qa.page.html',
  styleUrl: './qa.page.scss',
})
export class QaPage {
  private readonly api = inject(ApiService);
  private readonly list = viewChild<ElementRef<HTMLElement>>('list');
  private nextId = 1;

  protected readonly examples = EXAMPLE_QUESTIONS;
  protected readonly messages = signal<ChatMessage[]>([]);
  protected readonly draft = signal('');
  protected readonly pending = signal(false);

  protected ask(question?: string): void {
    const q = (question ?? this.draft()).trim();
    if (q.length < 3 || this.pending()) return;
    this.draft.set('');
    this.push({ id: this.nextId++, role: 'user', text: q });
    this.pending.set(true);
    this.api.ask(q).subscribe({
      next: (answer) => {
        this.pending.set(false);
        this.push({ id: this.nextId++, role: 'assistant', answer });
      },
      error: (err: unknown) => {
        this.pending.set(false);
        this.push({ id: this.nextId++, role: 'error', text: errorMessage(err) });
      },
    });
  }

  protected clear(): void {
    this.messages.set([]);
  }

  protected onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.ask();
    }
  }

  private push(msg: ChatMessage): void {
    this.messages.update((m) => [...m, msg]);
    queueMicrotask(() => {
      const el = this.list()?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }
}
