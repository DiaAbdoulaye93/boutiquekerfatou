import { Component, ElementRef, inject, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService, errorMessage } from './core/api.service';
import { formatDuration, formatValue, LANGUAGES } from './core/format';
import { AskOut, Shop, TurnIn } from './core/models';
import { ResultCard } from './shared/result-card';

interface Message {
  role: 'user' | 'assistant';
  text: string;
  reply?: AskOut;
}

// Example questions, one per language, shown before the first question.
const SUGGESTIONS = [
  'Quel est le produit le plus acheté ce mois-ci ?',
  'Ñaata la Modou Diop am bor ci man ?',
  'Who owes me the most money?',
  'Liste mes factures à crédit de la semaine',
  "Qu'est-ce que je dois racheter ?",
];

@Component({
  selector: 'app-root',
  imports: [FormsModule, ResultCard],
  templateUrl: './app.html',
})
export class App {
  private readonly api = inject(ApiService);
  private readonly bottom = viewChild<ElementRef<HTMLElement>>('bottom');

  readonly shop = signal<Shop | null>(null);
  readonly messages = signal<Message[]>([]);
  readonly pending = signal(false);
  readonly error = signal<string | null>(null);
  readonly draft = signal('');
  readonly suggestions = SUGGESTIONS;
  readonly languages = LANGUAGES;

  constructor() {
    this.api.shop().subscribe({ next: (s) => this.shop.set(s) });
  }

  send(text = this.draft()): void {
    const question = text.trim();
    if (!question || this.pending()) {
      return;
    }
    const history: TurnIn[] = this.messages().map((m) => ({ role: m.role, text: m.text }));
    this.messages.update((list) => [...list, { role: 'user', text: question }]);
    this.draft.set('');
    this.error.set(null);
    this.pending.set(true);
    this.scrollDown();
    this.api.ask({ question, history }).subscribe({
      next: (reply) => {
        this.messages.update((list) => [...list, { role: 'assistant', text: reply.answer, reply }]);
        this.pending.set(false);
        this.scrollDown();
      },
      error: (err: unknown) => {
        this.error.set(errorMessage(err));
        this.pending.set(false);
      },
    });
  }

  reset(): void {
    this.messages.set([]);
    this.error.set(null);
  }

  meta(reply: AskOut): string {
    const cost = reply.cost_usd === null ? '' : ` · ${formatValue('', reply.cost_usd)} $`;
    return `${formatDuration(reply.duration_ms)} · ${reply.llm_calls} appels${cost}`;
  }

  period(shop: Shop): string {
    return `${formatValue('', shop.first_day)} → ${formatValue('', shop.last_day)}`;
  }

  private scrollDown(): void {
    setTimeout(() => this.bottom()?.nativeElement.scrollIntoView({ behavior: 'smooth' }));
  }
}
