import {
  Component,
  ElementRef,
  OnDestroy,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService, errorMessage } from './core/api.service';
import { formatDuration, formatValue, LANGUAGES } from './core/format';
import { AskOut, Shop, SpokenLanguage, TurnIn } from './core/models';
import { Recorder } from './core/recorder';
import { ResultCard } from './shared/result-card';

interface Message {
  id: number;
  role: 'user' | 'assistant';
  text: string;
  spoken?: boolean; // the user's question was a voice note
  reply?: AskOut;
}

// What the assistant is doing; each step shows on screen.
type Status = 'idle' | 'recording' | 'transcribing' | 'thinking';
const STATUS_LABELS: Record<Status, string> = {
  idle: '',
  recording: "J'écoute…",
  transcribing: 'Je transcris…',
  thinking: 'Je cherche dans la boutique…',
};

const SPOKEN: { code: SpokenLanguage; label: string }[] = [
  { code: 'wo', label: 'Wolof' },
  { code: 'fr', label: 'Français' },
  { code: 'en', label: 'English' },
];
const LANGUAGE_KEY = 'boutique-vocale.langue';

// Example questions, shown before the first question.
const SUGGESTIONS = [
  'Quel est le produit le plus acheté ce mois-ci ?',
  'Ñaata la Modou Diop am bor ci man ?',
  'Who owes me the most money?',
  'Liste mes factures à crédit de la semaine',
  "Qu'est-ce que je dois racheter ?",
];

function storedLanguage(): SpokenLanguage {
  try {
    const value = localStorage.getItem(LANGUAGE_KEY);
    return value === 'fr' || value === 'en' || value === 'wo' ? value : 'wo';
  } catch {
    return 'wo';
  }
}

@Component({
  selector: 'app-root',
  imports: [FormsModule, ResultCard],
  templateUrl: './app.html',
})
export class App implements OnDestroy {
  private readonly api = inject(ApiService);
  private readonly recorder = inject(Recorder);
  private readonly bottom = viewChild<ElementRef<HTMLElement>>('bottom');
  private readonly audioUrls = new Map<number, string>();
  private player: HTMLAudioElement | null = null;
  private tick: ReturnType<typeof setInterval> | null = null;
  private nextId = 1;

  readonly shop = signal<Shop | null>(null);
  readonly messages = signal<Message[]>([]);
  readonly status = signal<Status>('idle');
  readonly seconds = signal(0);
  readonly error = signal<string | null>(null);
  readonly draft = signal('');
  readonly language = signal<SpokenLanguage>(storedLanguage());
  readonly playing = signal<number | null>(null); // message id being read aloud
  readonly loadingVoice = signal<number | null>(null);
  readonly busy = computed(() => this.status() !== 'idle');
  readonly statusLabel = computed(() => STATUS_LABELS[this.status()]);
  readonly micSupported = Recorder.supported();
  readonly suggestions = SUGGESTIONS;
  readonly spoken = SPOKEN;
  readonly languages = LANGUAGES;

  constructor() {
    this.api.shop().subscribe({ next: (s) => this.shop.set(s) });
  }

  ngOnDestroy(): void {
    this.stopTick();
    this.player?.pause();
    this.audioUrls.forEach((url) => URL.revokeObjectURL(url));
  }

  setLanguage(code: SpokenLanguage): void {
    this.language.set(code);
    try {
      localStorage.setItem(LANGUAGE_KEY, code);
    } catch {
      // private browsing: the choice just isn't remembered
    }
  }

  send(text = this.draft()): void {
    const question = text.trim();
    if (!question || this.busy()) {
      return;
    }
    this.draft.set('');
    this.ask(question, false);
  }

  async toggleMic(): Promise<void> {
    if (this.status() === 'recording') {
      this.recorder.stop();
      return;
    }
    if (this.busy()) {
      return;
    }
    this.error.set(null);
    this.player?.pause();
    let recording: Promise<Blob>;
    try {
      recording = (await this.recorder.start()).done;
    } catch {
      this.error.set("Le micro n'est pas accessible. Autorisez-le dans le navigateur.");
      return;
    }
    this.status.set('recording');
    this.seconds.set(0);
    this.tick = setInterval(() => this.seconds.update((s) => s + 1), 1000);
    const audio = await recording;
    this.stopTick();
    if (audio.size < 1000) {
      this.status.set('idle');
      this.error.set('Vocal trop court : appuyez, parlez, puis appuyez de nouveau.');
      return;
    }
    this.status.set('transcribing');
    this.api.transcribe(audio, this.language()).subscribe({
      next: (heard) => this.ask(heard.text, true),
      error: (err: unknown) => this.fail(err),
    });
  }

  /** Reads an answer aloud, fetching its audio the first time. */
  listen(message: Message): void {
    const url = this.audioUrls.get(message.id);
    if (url) {
      this.play(message.id, url);
      return;
    }
    if (!message.reply || this.loadingVoice() !== null) {
      return;
    }
    this.loadingVoice.set(message.id);
    this.api.speak(message.reply.answer, message.reply.language).subscribe({
      next: (blob) => {
        this.loadingVoice.set(null);
        const fresh = URL.createObjectURL(blob);
        this.audioUrls.set(message.id, fresh);
        this.play(message.id, fresh);
      },
      error: () => {
        this.loadingVoice.set(null);
        this.error.set("La voix n'a pas pu être générée ; la réponse écrite reste valable.");
      },
    });
  }

  reset(): void {
    this.player?.pause();
    this.audioUrls.forEach((url) => URL.revokeObjectURL(url));
    this.audioUrls.clear();
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

  private ask(question: string, spoken: boolean): void {
    const history: TurnIn[] = this.messages().map((m) => ({ role: m.role, text: m.text }));
    this.push({ role: 'user', text: question, spoken });
    this.status.set('thinking');
    this.error.set(null);
    this.api.ask({ question, history }).subscribe({
      next: (reply) => {
        const message = this.push({ role: 'assistant', text: reply.answer, reply });
        this.status.set('idle');
        if (spoken) {
          this.listen(message); // a spoken question gets a spoken answer
        }
      },
      error: (err: unknown) => this.fail(err),
    });
  }

  private fail(err: unknown): void {
    this.error.set(errorMessage(err));
    this.status.set('idle');
  }

  private play(id: number, url: string): void {
    this.player?.pause();
    const player = new Audio(url);
    this.player = player;
    this.playing.set(id);
    player.onended = () => this.playing.set(null);
    // Some browsers block playback that does not follow a tap: the button stays.
    player.play().catch(() => this.playing.set(null));
  }

  private push(message: Omit<Message, 'id'>): Message {
    const full = { ...message, id: this.nextId++ };
    this.messages.update((list) => [...list, full]);
    setTimeout(() => this.bottom()?.nativeElement.scrollIntoView({ behavior: 'smooth' }));
    return full;
  }

  private stopTick(): void {
    if (this.tick) {
      clearInterval(this.tick);
      this.tick = null;
    }
  }
}
